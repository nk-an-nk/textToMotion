#!/usr/bin/env node
// Record the application's real VRM renderer with a locally supplied WAV.
// This replays saved motion/audio; it does not assert a live conversation or new motion inference.
const {chromium}=require('@playwright/test');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const help=`Usage: node scripts/record_vrm_demo.cjs --avatar FILE.vrm --motion motion.json
  --output demo.mp4 [--wav speech.wav] [--speech-metadata speech.json]
  [--title TITLE] [--base-url http://127.0.0.1:8765] [--chromium PATH]
Requires a running Motion Lab server, Playwright Chromium and FFmpeg.
The VRM stays local. Output includes MP4 and source/recording metadata JSON.`;
const args={};
for(let i=2;i<process.argv.length;i++) {
 const name=process.argv[i];
 if(name==='--help'){console.log(help);process.exit(0);}
 if(!['--avatar','--motion','--output','--wav','--speech-metadata','--title','--base-url','--chromium'].includes(name)||!process.argv[i+1])throw new Error(help);
 args[name.slice(2)]=process.argv[++i];
}
const hash=buffer=>crypto.createHash('sha256').update(buffer).digest('hex');
async function main() {
 for(const name of ['avatar','motion','output'])if(!args[name])throw new Error('Missing --'+name+'\n'+help);
 const output=path.resolve(args.output),metadataPath=output.replace(/\.mp4$/i,'.json');
 if(!/\.mp4$/i.test(output))throw new Error('--output must end in .mp4.');
 if(fs.existsSync(output)||fs.existsSync(metadataPath))throw new Error('Output exists; choose a new filename to preserve recordings.');
 const avatarBuffer=fs.readFileSync(args.avatar),motionBuffer=fs.readFileSync(args.motion),motion=JSON.parse(motionBuffer);
 const wavBuffer=args.wav?fs.readFileSync(args.wav):null;
 const speechMetadata=args['speech-metadata']?JSON.parse(fs.readFileSync(args['speech-metadata'],'utf8')):null;
 if(speechMetadata&&(!wavBuffer||speechMetadata.audio_sha256!==hash(wavBuffer)))throw new Error('Speech metadata does not match the WAV.');
 const providerSpeech=speechMetadata?.schema==='motion-lab/realtime-speech-v1';
 const baseURL=args['base-url']||'http://127.0.0.1:8765';
 const health=await fetch(baseURL+'/api/health');if(!health.ok)throw new Error('Motion Lab is not running at --base-url.');
 const executablePath=args.chromium||process.env.CHROMIUM_PATH||(fs.existsSync('/usr/bin/chromium')?'/usr/bin/chromium':undefined);
 const browser=await chromium.launch({...(executablePath?{executablePath}:{}),args:['--no-sandbox','--use-angle=swiftshader','--autoplay-policy=no-user-gesture-required']});
 const errors=[];
 let rawPath;
 try {
  const page=await browser.newPage({viewport:{width:960,height:640}});page.on('pageerror',e=>errors.push(e.message));
  // Local harness, same origin/modules as the app; no original app animation loop competes for the CPU.
  await page.route('**/__capture_vrm',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><html lang="ja"><head><meta charset="utf-8">
   <script type="importmap">{"imports":{"three":"/vendor/three/build/three.module.js","three/addons/":"/vendor/three/examples/jsm/","@pixiv/three-vrm":"/vendor/three-vrm/three-vrm.module.js","@pixiv/three-vrm-animation":"/vendor/three-vrm-animation/three-vrm-animation.module.js"}}</script>
   </head><body style="margin:0"><div id="scene" style="width:800px;height:450px"></div></body></html>`}));
  await page.goto(baseURL+'/__capture_vrm');
  const recording=await page.evaluate(async({avatarEncoded,motion,audioEncoded,title,voiceLabel})=>{
   const {MotionViewer}=await import('/static/viewer.js');
   const decode=value=>Uint8Array.from(atob(value),c=>c.charCodeAt(0));
   const viewer=new MotionViewer(document.querySelector('#scene'));viewer.vrmSink.manual=true;
   const avatar=await viewer.vrmSink.loadAvatar(decode(avatarEncoded).buffer);
   const sink=viewer.vrmSink,clip=sink.prepareMotion(motion);viewer.resetCamera();
   // Leave space above the neutral avatar for raised hands; preserve the model itself.
   viewer.camera.position.sub(viewer.controls.target).multiplyScalar(1.18).add(viewer.controls.target);
   viewer.controls.target.y+=.12;viewer.camera.position.y+=.12;viewer.controls.update();
   viewer.draw(0); // Finish the first WebGL shader compilation before starting the recording clock.
   await new Promise(resolve=>setTimeout(resolve,250));
   let audio=null,audioContext=null,analyser=null,levels=null,destination=null;
   if(audioEncoded) {
    audio=new Audio();audio.src='data:audio/wav;base64,'+audioEncoded;audio.preload='auto';
    await new Promise((resolve,reject)=>{audio.onloadedmetadata=resolve;audio.onerror=()=>reject(new Error('WAV cannot be decoded.'));audio.load();});
    if(!Number.isFinite(audio.duration)||audio.duration>30)throw new Error('WAV must be at most 30 seconds.');
    audioContext=new AudioContext();await audioContext.resume();
    const source=audioContext.createMediaElementSource(audio);analyser=audioContext.createAnalyser();analyser.fftSize=512;
    levels=new Float32Array(analyser.fftSize);destination=audioContext.createMediaStreamDestination();
    source.connect(analyser);analyser.connect(destination);analyser.connect(audioContext.destination);
   }
   const movie=document.createElement('canvas');movie.width=960;movie.height=640;
   const ctx=movie.getContext('2d'),stream=movie.captureStream(30);
   for(const track of destination?.stream.getAudioTracks()||[])stream.addTrack(track);
   const mime=audio?'video/webm;codecs=vp8,opus':'video/webm;codecs=vp8';
   if(!MediaRecorder.isTypeSupported(mime))throw new Error('Chromium cannot record '+mime);
   const recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:2000000,audioBitsPerSecond:128000}),chunks=[],samples=[];
   recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
   const finish=new Promise(resolve=>{recorder.onstop=resolve;});
   let start=performance.now(),previous=start,motionStarted=false,returned=false,frames=0,maxRMS=0,maxLip=0,playError=null;
   const lead=.6,runSeconds=Math.max(clip.duration,audio?.duration||0),finishAt=lead+runSeconds+1;
   function frame(now) {
    const wall=(now-start)/1000,delta=Math.min(.1,(now-previous)/1000);previous=now;
    if(wall>=lead&&!motionStarted){motionStarted=true;sink.play(clip,{offline:true});audio?.play().catch(e=>{playError=e.message;});}
    const clock=motionStarted?(audio?audio.currentTime:Math.max(0,wall-lead)):0;
    // A finished WAV holds its currentTime; the motion can finish after a shorter utterance.
    const motionTime=audio?.ended?Math.max(clock,wall-lead):clock;
    const speaking=!!audio&&!audio.paused&&!audio.ended;
    let rms=0;if(analyser){analyser.getFloatTimeDomainData(levels);rms=Math.sqrt(levels.reduce((sum,value)=>sum+value*value,0)/levels.length);}
    maxRMS=Math.max(maxRMS,rms);
    if(motionStarted&&!returned&&motionTime>=clip.duration){sink.returnToIdle();returned=true;}
    sink.tick(delta,{speaking,lip:rms,offlineTime:Math.min(motionTime,clip.duration)});viewer.draw(0);
    maxLip=Math.max(maxLip,sink.vrm.expressionManager?.getValue('aa')||0);
    ctx.fillStyle='#edf1ed';ctx.fillRect(0,0,960,640);ctx.drawImage(viewer.renderer.domElement,0,80,960,540);
    ctx.fillStyle='#162b35';ctx.fillRect(0,0,960,80);ctx.fillStyle='#ffffff';ctx.font='bold 22px "Noto Sans CJK JP",sans-serif';ctx.fillText(title,20,30);
    ctx.font='16px "Noto Sans CJK JP",sans-serif';ctx.fillStyle='#d3f2de';ctx.fillText(voiceLabel,20,59);
    ctx.fillStyle='#ffffff';ctx.fillRect(0,580,960,60);ctx.fillStyle='#162b35';ctx.font='15px "Noto Sans CJK JP",sans-serif';
    ctx.fillText('保存済みモーション / 新規Text-to-Motion推論なし / 音声時計で再生',20,603);
    ctx.font='12px sans-serif';ctx.fillStyle='#687a80';ctx.fillText('Avatar: '+avatar.name+' / '+(avatar.authors||[]).join(', '),20,625);
    ctx.fillText(clock.toFixed(2)+' s / '+sink.mode,790,625);
    frames++;if(frames%10===0)samples.push({wall_seconds:wall,audio_seconds:clock,motion_seconds:motionTime,rms,mode:sink.mode});
    if(wall<finishAt&&!playError)requestAnimationFrame(frame);else setTimeout(()=>recorder.stop(),250);
   }
   recorder.start(100);requestAnimationFrame(frame);await finish;
   audio?.pause();stream.getTracks().forEach(track=>track.stop());await audioContext?.close();
   if(playError)throw new Error('Audio playback failed: '+playError);
   if(audio&&maxRMS<.001)throw new Error('The WAV did not produce a detected audio signal.');
   const blob=new Blob(chunks,{type:mime});
   const base64=await new Promise(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.slice(reader.result.indexOf(';base64,')+8));reader.readAsDataURL(blob);});
   return {base64,blob_bytes:blob.size,chunk_count:chunks.length,avatar,frames,wall_seconds:(performance.now()-start)/1000,audio_seconds:audio?.duration||null,
    motion_seconds:clip.duration,maxRMS,maxLip,samples,audio_tracks:audio?1:0,canvas:{width:960,height:640}};
  },{avatarEncoded:avatarBuffer.toString('base64'),motion,audioEncoded:wavBuffer?.toString('base64')||null,
     title:args.title||'VRMアバター / 保存済みモーションの再生',voiceLabel:providerSpeech?'音声: Realtime APIで生成した日本語音声の再生（合成音声）':wavBuffer?'音声: 指定されたWAVの再生':'音声なし'});
  if(errors.length)throw new Error('Browser errors: '+errors.join('; '));
  console.log(JSON.stringify({rendered_frames:recording.frames,capture_seconds:recording.wall_seconds,webm_bytes:recording.blob_bytes,chunks:recording.chunk_count,audio_seconds:recording.audio_seconds,max_audio_signal:recording.maxRMS}));
  fs.mkdirSync(path.dirname(output),{recursive:true});rawPath=output.replace(/\.mp4$/i,'.webm');
  if(fs.existsSync(rawPath))throw new Error('Temporary WebM exists; choose a new output filename.');
  fs.writeFileSync(rawPath,Buffer.from(recording.base64,'base64'));
  // Software WebGL can delay recorder packet timestamps. Keep speech samples
  // continuous rather than inserting silence from those timestamp gaps.
  const encoded=spawnSync('ffmpeg',['-hide_banner','-loglevel','error','-n','-i',rawPath,'-vf','fps=30','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',
    ...(wavBuffer?['-af','asetpts=N/SR/TB','-c:a','aac','-b:a','128k']:['-an']),'-movflags','+faststart',output],{encoding:'utf8'});
  if(encoded.status!==0)throw new Error('FFmpeg failed: '+(encoded.stderr||encoded.error?.message));
  const probe=spawnSync('ffprobe',['-v','error','-show_entries','stream=codec_name,codec_type,width,height,r_frame_rate,sample_rate,channels:format=duration,size','-of','json',output],{encoding:'utf8'});
  if(probe.status!==0)throw new Error('ffprobe could not validate the MP4.');
  const media=JSON.parse(probe.stdout);
  if(wavBuffer&&!media.streams.some(stream=>stream.codec_type==='audio'))throw new Error('MP4 is missing its audio track.');
  const {base64,...capture}=recording;
  const metadata={schema:'motion-lab/vrm-video-v1',recorded_at_utc:new Date().toISOString(),renderer:'app/ui/viewer.js + app/ui/motion-sink.js',
    playback_only:true,new_motion_inference:false,live_realtime_session:false,voice_generated_with_realtime:providerSpeech,
    motion:{filename:path.basename(args.motion),sha256:hash(motionBuffer),skeleton_type:motion.skeleton_type,trained_model_output:motion.metadata?.trained_model_output??null,metadata:motion.metadata},
    audio:wavBuffer?{filename:path.basename(args.wav),sha256:hash(wavBuffer),generation:speechMetadata}:null,
    capture,media,video_sha256:hash(fs.readFileSync(output)),browser_errors:errors};
  fs.writeFileSync(metadataPath,JSON.stringify(metadata,null,2)+'\n');fs.unlinkSync(rawPath);rawPath=null;
  console.log(JSON.stringify({mp4:output,metadata:metadataPath,seconds:media.format.duration,audio_tracks:capture.audio_tracks,rendered_frames:capture.frames,max_lip_expression:capture.maxLip}));
 } finally {await browser.close();}
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
