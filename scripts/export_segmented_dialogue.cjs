#!/usr/bin/env node
// Separate exporter: five independent clips, continuous VRM pose, sample-aligned speech.
const {chromium}=require('@playwright/test');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {spawn,spawnSync}=require('node:child_process');
const {once}=require('node:events');
const {hash,loadAssets}=require('./segmented_video_plan.cjs');
const {browserArgs,isSoftwareRenderer,requireHardware}=require('./webgl_backend.cjs');
const help='node scripts/export_segmented_dialogue.cjs --manifest manifest.json --avatar avatar.vrm --output combined.mp4 [--base-url http://127.0.0.1:8765] [--chromium PATH] [--renderer software|gpu|auto] [--gpu-backend vulkan|gl] [--reuse-assets]';
const args={};
for(let i=2;i<process.argv.length;i++){
 if(process.argv[i]==='--help'){console.log(help);process.exit(0);}
 if(process.argv[i]==='--reuse-assets'){args['reuse-assets']=true;continue;}
 if(!['--manifest','--avatar','--output','--base-url','--chromium','--renderer','--gpu-backend'].includes(process.argv[i])||!process.argv[i+1])throw new Error(help);
 args[process.argv[i].slice(2)]=process.argv[++i];
}
function command(binary,argv){const result=spawnSync(binary,argv,{encoding:'utf8',maxBuffer:4*1024*1024});if(result.error||result.status!==0)throw new Error(binary+': '+(result.error?.message||result.stderr));return result.stdout;}
function inspectVideo(filename,frames){
 const media=JSON.parse(command('ffprobe',['-v','error','-count_frames','-show_entries','stream=codec_name,codec_type,width,height,r_frame_rate,nb_read_frames,sample_rate,channels:format=duration,size','-of','json',filename]));
 const video=media.streams.find(stream=>stream.codec_type==='video'),audio=media.streams.find(stream=>stream.codec_type==='audio');
 if(video?.width!==1920||video?.height!==1080||video.r_frame_rate!=='30/1'||Number(video.nb_read_frames)!==frames||video.codec_name!=='h264'||audio?.codec_name!=='aac')throw new Error('Output media validation failed: '+filename);
 return media;
}
async function main(){
 for(const key of ['manifest','avatar','output'])if(!args[key])throw new Error(help);
 const assets=loadAssets(args.manifest),{manifest,units,root}=assets,fps=manifest.fps,width=1920,height=1080;
 const output=path.resolve(args.output),metadataPath=output.replace(/\.mp4$/i,'.json');
 if(!/\.mp4$/i.test(output))throw new Error('Output must be an MP4.');
 for(const file of [output,metadataPath,...units.map(unit=>unit.videoPath)])if(fs.existsSync(file))throw new Error('Existing output is preserved. Choose a new directory or move your previous render: '+file);
 const avatar=fs.readFileSync(args.avatar),baseURL=args['base-url']||'http://127.0.0.1:8765';
 if(!(await fetch(baseURL+'/api/health')).ok)throw new Error('Start Motion Lab before exporting.');
 const executablePath=args.chromium||process.env.CHROMIUM_PATH||(fs.existsSync('/usr/bin/chromium')?'/usr/bin/chromium':undefined);
 const rendererMode=args.renderer||'software',gpuBackend=args['gpu-backend']||'vulkan';
 const browser=await chromium.launch({...(executablePath?{executablePath}:{}),args:browserArgs(rendererMode,gpuBackend)});
 const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'motion-segmented-')),errors=[],began=performance.now(),renderResults=[];
 let encoder=null,encoderExit=null,encoderError='';
 try{
  const page=await browser.newPage({viewport:{width,height}});page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/__export_segmented',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><html lang="ja"><head><meta charset="utf-8"><script type="importmap">{"imports":{"three":"/vendor/three/build/three.module.js","three/addons/":"/vendor/three/examples/jsm/","@pixiv/three-vrm":"/vendor/three-vrm/three-vrm.module.js","@pixiv/three-vrm-animation":"/vendor/three-vrm-animation/three-vrm-animation.module.js"}}</script></head><body style="margin:0"><div id="scene"></div></body></html>`}));
  await page.goto(baseURL+'/__export_segmented');
  const setup=await page.evaluate(async data=>{
   const THREE=await import('three'),{MotionViewer}=await import('/static/viewer.js'),{faceFrontMotion}=await import('/static/presentation-motion.js'),decode=value=>Uint8Array.from(atob(value),char=>char.charCodeAt(0));
   const {width,height,fps,manifest}=data,header=100,footer=160,container=document.querySelector('#scene');
   container.style.width=width+'px';container.style.height=(height-header-footer)+'px';
   const viewer=new MotionViewer(container);viewer.renderer.setPixelRatio(1);viewer.resize();viewer.vrmSink.manual=true;
   const gl=viewer.renderer.getContext(),debug=gl.getExtension('WEBGL_debug_renderer_info');
   const webgl={renderer:gl.getParameter(gl.RENDERER),vendor:gl.getParameter(gl.VENDOR),unmasked_renderer:debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):null,unmasked_vendor:debug?gl.getParameter(debug.UNMASKED_VENDOR_WEBGL):null};
   if(data.rendererMode==='gpu'&&(!webgl.unmasked_renderer||/swiftshader|llvmpipe|softpipe|software|basic render|lavapipe/i.test(webgl.unmasked_renderer)))throw new Error('Hardware WebGL is required; software fallback refused.');
   const sink=viewer.vrmSink,avatar=await sink.loadAvatar(decode(data.avatarEncoded).buffer);viewer.resetCamera();viewer.controls.enabled=false;
   sink.vrm.scene.updateMatrixWorld(true);const bounds=new THREE.Box3().setFromObject(sink.vrm.scene),center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3());
   const distance=Math.max(size.y/2/Math.tan(THREE.MathUtils.degToRad(viewer.camera.fov/2)),size.x/2/viewer.camera.aspect/Math.tan(THREE.MathUtils.degToRad(viewer.camera.fov/2)))*1.5;
   viewer.controls.target.copy(center);viewer.camera.position.set(center.x,center.y,center.z+distance);viewer.camera.lookAt(center);viewer.controls.update();
   const anisotropy=Math.min(8,viewer.renderer.capabilities.getMaxAnisotropy());
   sink.vrm.scene.traverse(object=>{for(const material of (Array.isArray(object.material)?object.material:[object.material]))if(material)for(const value of Object.values(material))if(value?.isTexture)value.anisotropy=anisotropy;});
   const context=new AudioContext({sampleRate:24000}),clips=data.units.map(unit=>sink.prepareMotion(faceFrontMotion(unit.motion))),audios=[];
   for(const unit of data.units){const audio=await context.decodeAudioData(decode(unit.audioEncoded).buffer);if(Math.abs(audio.duration-unit.audio_seconds)>1/24000)throw new Error('Decoded speech length differs from manifest: '+unit.id+' '+audio.duration+' / '+unit.audio_seconds);audios.push(audio);}
   await context.close();
   const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;const ctx=canvas.getContext('2d'),source=viewer.renderer.domElement;
   const stats=manifest.segments.map(unit=>({id:unit.id,maxRMS:0,maxLip:0,rendered_frames:0})),boundaries=[],samples=[];
   let active=-1,last=-1;
   function textLines(text,x,y,maxWidth){let line='';for(const char of text){if(line&&ctx.measureText(line+char).width>maxWidth){ctx.fillText(line,x,y);line='';y+=36;}line+=char;}ctx.fillText(line,x,y);}
   window.__segmentedFrame=frame=>{
    if(frame!==last+1)throw new Error('Every frame must render exactly once, in order.');last=frame;
    const index=manifest.segments.findIndex(unit=>frame>=unit.start_frame&&frame<unit.end_frame);if(index<0)throw new Error('Frame is outside the timeline.');
    const unit=manifest.segments[index],localFrame=frame-unit.start_frame,clock=localFrame/fps,clip=clips[index],audio=audios[index],channel=audio.getChannelData(0);
    let before=null;
    if(index!==active){before=sink.rest.get('hips').node.position.clone();sink.play(clip,{offline:true});active=index;}
    const speaking=clock<audio.duration,begin=Math.floor(clock*audio.sampleRate),end=Math.min(channel.length,begin+Math.round(.025*audio.sampleRate));
    let rms=0;if(speaking){for(let i=begin;i<end;i++)rms+=channel[i]*channel[i];rms=Math.sqrt(rms/Math.max(1,end-begin));}
    // Retime each complete native gesture to its utterance, including its final pose.
    const motionTime=unit.frame_count===1?0:localFrame/(unit.frame_count-1)*Math.max(0,clip.duration-1/data.units[index].motion.fps);
    sink.elapsed=Math.max(0,frame/fps-1/fps);sink.tick(1/fps,{speaking:manifest.avatar_role!=='listener'&&speaking,lip:rms,offlineTime:motionTime});
    const blendSeconds=Math.min(manifest.blend_ms/1000,unit.frame_count/fps/3);
    if(blendSeconds>0&&clock<blendSeconds){sink.blendFrom(clock/blendSeconds);sink.vrm.update(0);}
    if(before){const after=sink.rest.get('hips').node.position.clone();boundaries.push({id:unit.id,frame,speech_start_frame:frame,gesture_start_frame:frame,root_before:before.toArray(),root_after:after.toArray(),root_jump_metres:after.distanceTo(before),blend_seconds:blendSeconds});}
    for(const bone of sink.rest.values())if(![...bone.node.position.toArray(),...bone.node.quaternion.toArray()].every(Number.isFinite))throw new Error('Nonfinite avatar pose.');
    const hips=sink.rest.get('hips');if(hips){hips.node.position.copy(hips.p);sink.vrm.update(0);}
    viewer.draw(0);const lip=sink.vrm.expressionManager?.getValue('aa')||0;stats[index].maxRMS=Math.max(stats[index].maxRMS,rms);stats[index].maxLip=Math.max(stats[index].maxLip,lip);stats[index].rendered_frames++;
    ctx.fillStyle='#edf1ed';ctx.fillRect(0,0,width,height);ctx.drawImage(source,0,header);
    ctx.fillStyle='#162b35';ctx.fillRect(0,0,width,header);ctx.fillStyle='#ffffff';ctx.font='bold 32px "Noto Sans CJK JP",sans-serif';ctx.fillText(manifest.title,32,42);
    ctx.fillStyle='#d3f2de';ctx.font='22px "Noto Sans CJK JP",sans-serif';ctx.fillText(`${manifest.model} / ${index+1} / ${manifest.segments.length} · 区間ごとの音声＋ジェスチャー · 正面1080p / 30fps`,32,77);
    ctx.fillStyle='#ffffff';ctx.fillRect(0,height-footer,width,footer);ctx.fillStyle='#162b35';ctx.font='28px "Noto Sans CJK JP",sans-serif';textLines(unit.text,32,height-footer+42,width-64);
    ctx.fillStyle='#687a80';ctx.font='16px "Noto Sans CJK JP",sans-serif';ctx.fillText('Avatar: '+avatar.name+' / '+(avatar.authors||[]).join(', '),32,height-22);ctx.fillText((frame/fps).toFixed(2)+' s',width-140,height-22);
    if(localFrame===0||localFrame%fps===0)samples.push({id:unit.id,frame,unit_seconds:clock,motion_seconds:motionTime,speaking,rms,lip});
    return canvas.toDataURL('image/png').split(',')[1];
   };
   window.__segmentedStats=()=>({segments:stats,boundaries,samples});
   return {avatar,webgl,camera:{position:viewer.camera.position.toArray(),target:viewer.controls.target.toArray(),front_alignment:viewer.camera.position.clone().sub(viewer.controls.target).normalize().dot(new THREE.Vector3(0,0,1))},source_canvas:{width:source.width,height:source.height},output_canvas:{width,height},anisotropy};
  },{avatarEncoded:avatar.toString('base64'),manifest,width,height,fps,rendererMode,units:units.map(({unit,motion,audio})=>({...unit,motion,audioEncoded:audio.toString('base64')}))});
  if(rendererMode==='gpu')requireHardware(setup.webgl);
  if(setup.source_canvas.width!==1920||setup.source_canvas.height!==820||setup.camera.front_alignment<.99999)throw new Error('Native canvas or front camera validation failed.');
  fs.mkdirSync(path.dirname(output),{recursive:true});let lastReport=performance.now();
  for(const {unit,audioPath,videoPath} of units){
   const beganUnit=performance.now(),silent=path.join(temporary,unit.id+'.mp4');encoderError='';
   console.log(JSON.stringify({stage:'render',segment:unit.id,frames:unit.frame_count,start_frame:unit.start_frame}));
   encoder=spawn('ffmpeg',['-hide_banner','-loglevel','error','-n','-f','image2pipe','-framerate',String(fps),'-vcodec','png','-i','pipe:0','-c:v','libx264','-preset','medium','-crf','16','-pix_fmt','yuv420p','-an',silent],{stdio:['pipe','ignore','pipe']});
   encoder.stderr.on('data',chunk=>{encoderError+=chunk.toString();});encoder.stdin.on('error',()=>{});
   encoderExit=new Promise((resolve,reject)=>{encoder.once('error',reject);encoder.once('close',resolve);});
   for(let frame=unit.start_frame;frame<unit.end_frame;frame++){
    const png=Buffer.from(await page.evaluate(index=>window.__segmentedFrame(index),frame),'base64');
    if(!encoder.stdin.write(png))await once(encoder.stdin,'drain');
    if(performance.now()-lastReport>15000){console.log(JSON.stringify({rendered_frames:frame+1,total_frames:manifest.frame_count,elapsed_seconds:Math.round((performance.now()-began)/1000)}));lastReport=performance.now();}
   }
   encoder.stdin.end();const code=await encoderExit;encoder=null;if(code!==0)throw new Error('FFmpeg: '+encoderError);
   command('ffmpeg',['-hide_banner','-loglevel','error','-n','-i',silent,'-i',audioPath,'-map','0:v:0','-map','1:a:0','-c:v','copy','-af','apad','-c:a','aac','-b:a','192k','-t',String(unit.frame_count/fps),'-movflags','+faststart',videoPath]);
   const completedAt=new Date().toISOString(),submittedAt=Date.parse(unit.input_submitted_at_utc||'');
   const renderSeconds=(performance.now()-beganUnit)/1000;
   renderResults.push({id:unit.id,video:path.relative(root,videoPath).replaceAll('\\','/'),video_sha256:hash(fs.readFileSync(videoPath)),render_wall_seconds:renderSeconds,
    input_to_skeleton_seconds:unit.input_to_skeleton_seconds??unit.skeleton_seconds,
    input_to_mp4_seconds:Number.isFinite(submittedAt)?Math.max(0,(Date.parse(completedAt)-submittedAt)/1000):null,
    skeleton_and_mp4_processing_seconds:unit.skeleton_seconds+renderSeconds,mp4_completed_at_utc:completedAt,
    media:inspectVideo(videoPath,unit.frame_count),silent});
   console.log(JSON.stringify({segment:unit.id,mp4:videoPath,render_wall_seconds:renderSeconds,input_to_skeleton_seconds:renderResults.at(-1).input_to_skeleton_seconds,input_to_mp4_seconds:renderResults.at(-1).input_to_mp4_seconds}));
  }
  // Concatenate the encoded video segments, then encode the original PCM timeline once.
  // This avoids accumulating separate AAC priming offsets at the five boundaries.
  const list=path.join(temporary,'concat.txt');
  fs.writeFileSync(list,renderResults.map((result,index)=>`file '${result.silent.replaceAll('\\','/').replaceAll("'","'\\''")}'\nduration ${units[index].unit.frame_count/fps}\n`).join(''));
  command('ffmpeg',['-hide_banner','-loglevel','error','-n','-f','concat','-safe','0','-i',list,'-i',assets.timelinePath,'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t',String(manifest.duration_seconds),'-movflags','+faststart',output]);
  const media=inspectVideo(output,manifest.frame_count),stats=await page.evaluate(()=>window.__segmentedStats());
  if(errors.length||stats.segments.some((unit,index)=>unit.maxRMS<.001||(manifest.avatar_role!=='listener'&&unit.maxLip<.01)||unit.rendered_frames!==units[index].unit.frame_count)||stats.boundaries.some(boundary=>manifest.blend_ms>0&&boundary.root_jump_metres>1e-6))throw new Error('Speech, lip movement, frame coverage or boundary continuity check failed: '+errors.join(';'));
  for(const result of renderResults)delete result.silent;
  const renderSeconds=(performance.now()-began)/1000;
  const receipt={schema:'motion-lab/segmented-vrm-video-v1',recorded_at_utc:new Date().toISOString(),manifest_sha256:hash(fs.readFileSync(args.manifest)),
   renderer:'app/ui/viewer.js + app/ui/motion-sink.js',render_mode:'offline_fixed_timestep',fps,rendered_frames:manifest.frame_count,skipped_render_frames:0,
   requested_renderer:rendererMode,hardware_webgl:!isSoftwareRenderer(setup.webgl)&&!!setup.webgl.unmasked_renderer,gpu_backend:gpuBackend,
   new_motion_inference:!args['reuse-assets'],generated_assets_reused:!!args['reuse-assets'],live_realtime_session:false,audio_conditioned_model:false,speech_and_gesture_start_policy:'same_frame_per_segment',
   audio_offset_seconds:0,presentation_root_policy:'all source joints rotated to remove torso yaw before retargeting; avatar root anchored; original joints preserved',timeline_audio_sha256:manifest.timeline_audio_sha256,encoding:{codec:'H.264',crf:16,audio:'AAC 192k'},lossy_intermediate:false,
   model:manifest.model,segments:manifest.segments,segment_videos:renderResults,capture:{...setup,...stats},render_wall_seconds:renderSeconds,
   speech_generation_seconds:units.reduce((sum,{unit})=>sum+unit.speech_generation_seconds,0),skeleton_seconds:units.reduce((sum,{unit})=>sum+unit.skeleton_seconds,0),
   media,video_sha256:hash(fs.readFileSync(output)),browser_errors:errors};
  receipt.total_processing_seconds=receipt.speech_generation_seconds+receipt.skeleton_seconds+renderSeconds;
  const starts=manifest.segments.map(unit=>Date.parse(unit.input_submitted_at_utc||'')).filter(Number.isFinite);
  receipt.combined_mp4_completed_at_utc=new Date().toISOString();
  receipt.input_to_combined_mp4_seconds=starts.length?Math.max(0,(Date.parse(receipt.combined_mp4_completed_at_utc)-Math.min(...starts))/1000):null;
  fs.writeFileSync(metadataPath,JSON.stringify(receipt,null,2)+'\n');
  fs.writeFileSync(path.join(root,'render-timings.csv'),'\ufeffid,speech_seconds,skeleton_seconds,mp4_render_seconds,total_seconds,input_to_skeleton_seconds,input_to_mp4_seconds,skeleton_and_mp4_processing_seconds,mp4_completed_at_utc,video\n'+renderResults.map((result,index)=>{const unit=units[index].unit;return [unit.id,unit.speech_generation_seconds,unit.skeleton_seconds,result.render_wall_seconds,unit.speech_generation_seconds+unit.skeleton_seconds+result.render_wall_seconds,result.input_to_skeleton_seconds,result.input_to_mp4_seconds??'',result.skeleton_and_mp4_processing_seconds,result.mp4_completed_at_utc,result.video].join(',');}).join('\n')+'\n');
  console.log(JSON.stringify({mp4:output,segment_videos:renderResults.map(result=>result.video),render_wall_seconds:renderSeconds,total_processing_seconds:receipt.total_processing_seconds,input_to_combined_mp4_seconds:receipt.input_to_combined_mp4_seconds,frames:manifest.frame_count,duration_seconds:manifest.duration_seconds}));
 }finally{if(encoder){encoder.stdin.destroy();encoder.kill();await encoderExit.catch(()=>{});}await browser.close();fs.rmSync(temporary,{recursive:true,force:true});}
}
main().catch(error=>{console.error(error.stack||error.message);process.exitCode=1;});
