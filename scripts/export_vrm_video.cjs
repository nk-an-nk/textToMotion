#!/usr/bin/env node
// Native-resolution offline rendering: one lossless PNG per output frame, original WAV audio.
const {chromium}=require('@playwright/test');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {spawn,spawnSync}=require('node:child_process');
const {once}=require('node:events');
const help=`Usage: node scripts/export_vrm_video.cjs --avatar FILE.vrm --motion motion.json --output demo.mp4
  [--wav speech.wav] [--speech-metadata speech.json] [--title TITLE]
  [--width 1920] [--height 1080] [--fps 30] [--preview-only yes]
  [--base-url http://127.0.0.1:8765] [--chromium PATH]
Uses the application's actual VRM renderer; offline rendering speed is not runtime FPS.`;
const args={};
for(let i=2;i<process.argv.length;i++){
 const name=process.argv[i];if(name==='--help'){console.log(help);process.exit(0);}
 if(!['--avatar','--motion','--output','--wav','--speech-metadata','--title','--width','--height','--fps','--preview-only','--base-url','--chromium'].includes(name)||!process.argv[i+1])throw new Error(help);
 args[name.slice(2)]=process.argv[++i];
}
const hash=buffer=>crypto.createHash('sha256').update(buffer).digest('hex');
async function main(){
 for(const name of ['avatar','motion','output'])if(!args[name])throw new Error('Missing --'+name+'\n'+help);
 const output=path.resolve(args.output),metadataPath=output.replace(/\.mp4$/i,'.json');
 const width=Number(args.width||1920),height=Number(args.height||1080),fps=Number(args.fps||30);
 if(!/\.mp4$/i.test(output)||fs.existsSync(output)||fs.existsSync(metadataPath))throw new Error('Use a new .mp4 filename; existing results are preserved.');
 if(!Number.isInteger(width)||!Number.isInteger(height)||width<960||height<640||width>3840||height>2160||width%2||height%2||![24,30,60].includes(fps))throw new Error('Use even 960–3840 / 640–2160 dimensions and 24, 30 or 60 FPS.');
 const avatarBuffer=fs.readFileSync(args.avatar),motionBuffer=fs.readFileSync(args.motion),motion=JSON.parse(motionBuffer);
 const wavBuffer=args.wav?fs.readFileSync(args.wav):null;
 const speech=args['speech-metadata']?JSON.parse(fs.readFileSync(args['speech-metadata'],'utf8')):null;
 if(speech&&(!wavBuffer||speech.audio_sha256!==hash(wavBuffer)))throw new Error('WAV and speech metadata hashes do not match.');
 const providerSpeech=speech?.schema==='motion-lab/realtime-speech-v1';
 const baseURL=args['base-url']||'http://127.0.0.1:8765';
 const health=await fetch(baseURL+'/api/health');if(!health.ok)throw new Error('Start Motion Lab at --base-url before exporting.');
 const executablePath=args.chromium||process.env.CHROMIUM_PATH||(fs.existsSync('/usr/bin/chromium')?'/usr/bin/chromium':undefined);
 const browser=await chromium.launch({...(executablePath?{executablePath}:{}),args:['--no-sandbox','--use-angle=swiftshader','--autoplay-policy=no-user-gesture-required']});
 let encoder=null,encoderError='',encoderExit=null;
 const began=performance.now(),errors=[];
 try{
  const page=await browser.newPage({viewport:{width,height}});page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/__export_vrm',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><html lang="ja"><head><meta charset="utf-8">
   <script type="importmap">{"imports":{"three":"/vendor/three/build/three.module.js","three/addons/":"/vendor/three/examples/jsm/","@pixiv/three-vrm":"/vendor/three-vrm/three-vrm.module.js","@pixiv/three-vrm-animation":"/vendor/three-vrm-animation/three-vrm-animation.module.js"}}</script>
   </head><body style="margin:0"><div id="scene"></div></body></html>`}));
  await page.goto(baseURL+'/__export_vrm');
  const setup=await page.evaluate(async data=>{
   const THREE=await import('three'),{MotionViewer}=await import('/static/viewer.js');
   const decode=value=>Uint8Array.from(atob(value),c=>c.charCodeAt(0));
   const {width,height,fps}=data,header=Math.round(height*.0926),footer=Math.round(height*.1482),sceneHeight=height-header-footer;
   const container=document.querySelector('#scene');container.style.width=width+'px';container.style.height=sceneHeight+'px';
   const viewer=new MotionViewer(container);viewer.renderer.setPixelRatio(1);viewer.resize();viewer.vrmSink.manual=true;
   const sink=viewer.vrmSink,avatar=await sink.loadAvatar(decode(data.avatarEncoded).buffer),clip=sink.prepareMotion(data.motion);
   viewer.resetCamera();viewer.controls.enabled=false;
   const anisotropy=Math.min(8,viewer.renderer.capabilities.getMaxAnisotropy());
   sink.vrm.scene.traverse(object=>{for(const material of (Array.isArray(object.material)?object.material:[object.material]))if(material){
    for(const value of Object.values(material))if(value?.isTexture)value.anisotropy=anisotropy;
   }});
   let audio=null,channel=null;
   if(data.audioEncoded){const context=new AudioContext();audio=await context.decodeAudioData(decode(data.audioEncoded).buffer);channel=audio.getChannelData(0);await context.close();if(audio.duration>60)throw new Error('Audio must be at most 60 seconds.');}
   const lead=.5,seconds=Math.ceil((lead+Math.max(clip.duration,audio?.duration||0)+.5)*fps)/fps,frameCount=Math.round(seconds*fps);
   const movie=document.createElement('canvas');movie.width=width;movie.height=height;const ctx=movie.getContext('2d');
   const source=viewer.renderer.domElement,samples=[];let started=false,returned=false,maxRMS=0,maxLip=0;
   function wrappedText(text,x,y,maxWidth,lineHeight){let line='';for(const char of text){if(line&&ctx.measureText(line+char).width>maxWidth){ctx.fillText(line,x,y);line='';y+=lineHeight;}line+=char;}if(line)ctx.fillText(line,x,y);return y;}
   window.__exportFrame=index=>{
    const time=index/fps,clock=time-lead,motionTime=Math.max(0,clock),speaking=!!audio&&clock>=0&&clock<audio.duration;
    if(clock>=0&&!started){sink.play(clip,{offline:true});started=true;}
    if(started&&!returned&&motionTime>=clip.duration){sink.returnToIdle();returned=true;}
    let rms=0;if(speaking){const end=Math.min(channel.length,Math.floor(clock*audio.sampleRate)),begin=Math.max(0,end-Math.round(.025*audio.sampleRate));for(let i=begin;i<end;i++)rms+=channel[i]*channel[i];rms=Math.sqrt(rms/Math.max(1,end-begin));}
    sink.elapsed=Math.max(0,time-1/fps);sink.tick(1/fps,{speaking,lip:rms,offlineTime:Math.min(motionTime,clip.duration)});viewer.draw(0);
    maxRMS=Math.max(maxRMS,rms);maxLip=Math.max(maxLip,sink.vrm.expressionManager?.getValue('aa')||0);
    // Exact native-size copy: no scaled low-resolution source or lossy intermediate.
    ctx.fillStyle='#edf1ed';ctx.fillRect(0,0,width,height);ctx.drawImage(source,0,header);
    ctx.fillStyle='#162b35';ctx.fillRect(0,0,width,header);ctx.fillStyle='#ffffff';ctx.font=`bold ${Math.round(height*.03)}px "Noto Sans CJK JP",sans-serif`;ctx.fillText(data.title,32,Math.round(header*.42));
    ctx.fillStyle='#d3f2de';ctx.font=`${Math.round(height*.02)}px "Noto Sans CJK JP",sans-serif`;ctx.fillText(data.voiceLabel+` / 正面・${width}×${height}・${fps}fps書き出し`,32,Math.round(header*.76));
    ctx.fillStyle='#ffffff';ctx.fillRect(0,height-footer,width,footer);ctx.fillStyle='#162b35';ctx.font=`${Math.round(height*.023)}px "Noto Sans CJK JP",sans-serif`;
    wrappedText(data.transcript||'保存済みモーションのオフライン書き出し',32,height-footer+35,width-64,Math.round(height*.032));
    ctx.fillStyle='#687a80';ctx.font=`${Math.round(height*.015)}px "Noto Sans CJK JP",sans-serif`;ctx.fillText('Avatar: '+avatar.name+' / '+(avatar.authors||[]).join(', ')+' · 保存済みモーション',32,height-22);
    ctx.fillText(Math.max(0,clock).toFixed(2)+' s',width-130,height-22);
    if(index%fps===0)samples.push({frame:index,time_seconds:time,audio_seconds:Math.max(0,clock),rms,lip:sink.vrm.expressionManager?.getValue('aa')||0,mode:sink.mode});
    return movie.toDataURL('image/png').split(',')[1];
   };
   viewer.draw(0);
   const camera={position:viewer.camera.position.toArray(),target:viewer.controls.target.toArray(),front_alignment:viewer.camera.position.clone().sub(viewer.controls.target).normalize().dot(new THREE.Vector3(0,0,1)),fov:viewer.camera.fov};
   window.__exportStats=()=>({maxRMS,maxLip,samples});
   return {avatar,camera,seconds,frameCount,audio_seconds:audio?.duration||null,audio_offset_seconds:lead,motion_seconds:clip.duration,source_canvas:{width:source.width,height:source.height},output_canvas:{width,height},anisotropy};
  },{avatarEncoded:avatarBuffer.toString('base64'),audioEncoded:wavBuffer?.toString('base64')||null,motion,width,height,fps,
     title:args.title||'VRMアバター / 正面・高画質',voiceLabel:providerSpeech?'Realtime APIの合成音声':wavBuffer?'指定WAVの音声':'音声なし',transcript:speech?.requested_text||''});
  if(setup.source_canvas.width!==width||setup.camera.front_alignment<.99999)throw new Error('Native resolution or front camera check failed.');
  fs.mkdirSync(path.dirname(output),{recursive:true});
  if(args['preview-only']==='yes'){
   for(const seconds of [0,1.6]){const png=await page.evaluate(frame=>window.__exportFrame(frame),Math.round(seconds*fps));const file=output.replace(/\.mp4$/i,`-preview-${seconds}.png`);if(fs.existsSync(file))throw new Error('Preview exists.');fs.writeFileSync(file,Buffer.from(png,'base64'));}
   console.log(JSON.stringify({preview:true,...setup}));return;
  }
  encoder=spawn('ffmpeg',['-hide_banner','-loglevel','error','-n','-f','image2pipe','-framerate',String(fps),'-vcodec','png','-i','pipe:0',
    ...(wavBuffer?['-i',path.resolve(args.wav)]:[]),'-c:v','libx264','-preset','medium','-crf','16','-pix_fmt','yuv420p',
    ...(wavBuffer?['-af',`adelay=${Math.round(setup.audio_offset_seconds*1000)}:all=1,apad`,'-c:a','aac','-b:a','192k']:['-an']),'-t',String(setup.seconds),'-movflags','+faststart',output],{stdio:['pipe','ignore','pipe']});
  encoder.stderr.on('data',chunk=>{encoderError+=chunk.toString();});
  encoderExit=new Promise((resolve,reject)=>{encoder.once('error',reject);encoder.once('close',resolve);});
  let lastReport=performance.now();const distinct=new Set();
  for(let frame=0;frame<setup.frameCount;frame++){
   const png=Buffer.from(await page.evaluate(index=>window.__exportFrame(index),frame),'base64');
   if(frame%fps===0)distinct.add(hash(png));
   if(!encoder.stdin.write(png))await once(encoder.stdin,'drain');
   if(performance.now()-lastReport>15000||frame===setup.frameCount-1){console.log(JSON.stringify({rendered_frames:frame+1,total_frames:setup.frameCount,percent:Math.round((frame+1)*100/setup.frameCount),elapsed_seconds:Math.round((performance.now()-began)/1000)}));lastReport=performance.now();}
  }
  encoder.stdin.end();const code=await encoderExit;encoder=null;if(code!==0||encoderError)throw new Error('FFmpeg encoding failed: '+encoderError);
  const stats=await page.evaluate(()=>window.__exportStats());if(wavBuffer&&(stats.maxRMS<.001||stats.maxLip<.01))throw new Error('Audio signal or lip movement missing.');
  if(errors.length)throw new Error('Browser errors: '+errors.join('; '));
  const probe=spawnSync('ffprobe',['-v','error','-count_frames','-show_entries','stream=codec_name,codec_type,width,height,r_frame_rate,nb_read_frames,sample_rate,channels:format=duration,size','-of','json',output],{encoding:'utf8'});
  if(probe.status!==0)throw new Error('ffprobe failed.');const media=JSON.parse(probe.stdout),video=media.streams.find(s=>s.codec_type==='video');
  if(Number(video.nb_read_frames)!==setup.frameCount||video.width!==width||video.height!==height)throw new Error('Unexpected output frame count or resolution.');
  const metadata={schema:'motion-lab/vrm-video-v2',recorded_at_utc:new Date().toISOString(),renderer:'app/ui/viewer.js + app/ui/motion-sink.js',
    render_mode:'offline_fixed_timestep',fps,rendered_frames:setup.frameCount,skipped_render_frames:0,lossy_intermediate:false,encoding:{codec:'H.264',crf:16},
    playback_only:true,new_motion_inference:false,live_realtime_session:false,voice_generated_with_realtime:providerSpeech,
    motion:{filename:path.basename(args.motion),sha256:hash(motionBuffer),skeleton_type:motion.skeleton_type,trained_model_output:motion.metadata?.trained_model_output??null,metadata:motion.metadata},
    audio:wavBuffer?{filename:path.basename(args.wav),sha256:hash(wavBuffer),generation:speech}:null,capture:{...setup,...stats,distinct_sampled_frames:distinct.size},
    render_wall_seconds:(performance.now()-began)/1000,media,video_sha256:hash(fs.readFileSync(output)),browser_errors:errors};
  fs.writeFileSync(metadataPath,JSON.stringify(metadata,null,2)+'\n');
  console.log(JSON.stringify({mp4:output,frames:setup.frameCount,resolution:[width,height],duration_seconds:setup.seconds,render_wall_seconds:metadata.render_wall_seconds}));
 }finally{if(encoder){encoder.stdin.destroy();encoder.kill();}await browser.close();}
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
