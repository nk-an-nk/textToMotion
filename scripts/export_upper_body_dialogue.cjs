#!/usr/bin/env node
// Upper-body presentation of a measured resident-GPU dialogue. Legacy exporters stay separate.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn,spawnSync}=require('node:child_process');const {once}=require('node:events');
const {chromium}=require('@playwright/test');const {browserArgs}=require('./webgl_backend.cjs');const {hash}=require('./segmented_video_plan.cjs');
const args={};for(let i=2;i<process.argv.length;i++){if(!['--plan','--avatar','--output','--base-url'].includes(process.argv[i])||!process.argv[i+1])throw Error('Use --plan PLAN --avatar VRM --output MP4');args[process.argv[i].slice(2)]=process.argv[++i];}
function command(bin,list){const r=spawnSync(bin,list,{encoding:'utf8',maxBuffer:4*1024*1024});if(r.status!==0||r.error)throw Error(r.stderr||r.error.message);return r.stdout;}
async function main(){
 const root=path.dirname(path.resolve(args.plan)),plan=JSON.parse(fs.readFileSync(args.plan)),output=path.resolve(args.output);
 const lesson=plan.schema==='motion-lab/listener-lesson-video-plan-v1';
 if(!lesson&&(plan.schema!=='motion-lab/audio-dialogue-video-plan-v1'||!plan.measurement.measured_end_to_end||plan.measurement.typed_student_input!==false))throw Error('Actual audio-input measurement is required.');
 if(fs.existsSync(output)||fs.existsSync(output.replace(/\.mp4$/,'.json')))throw Error('Existing output is preserved.');
 const motionBytes=fs.readFileSync(path.join(root,plan.motion_file));if(hash(motionBytes)!==plan.motion_sha256)throw Error('Motion checksum differs.');
 const motion=JSON.parse(motionBytes),avatar=fs.readFileSync(args.avatar),audio=fs.readFileSync(path.join(root,'teacher.wav'));
 const base=args['base-url']||'http://127.0.0.1:8765',browser=await chromium.launch({args:browserArgs('software','vulkan')});
 const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'motion-audio-dialogue-')),began=performance.now();let encoder;
 try{
  const errors=[],page=await browser.newPage({viewport:{width:1920,height:1080}});page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/__audio_dialogue',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><html><head><meta charset="utf-8"><script type="importmap">{"imports":{"three":"/vendor/three/build/three.module.js","three/addons/":"/vendor/three/examples/jsm/","@pixiv/three-vrm":"/vendor/three-vrm/three-vrm.module.js","@pixiv/three-vrm-animation":"/vendor/three-vrm-animation/three-vrm-animation.module.js"}}</script></head><body style="margin:0"><div id="scene"></div></body></html>'}));
  await page.goto(base+'/__audio_dialogue');
  const setup=await page.evaluate(async d=>{
   const THREE=await import('three'),{MotionViewer}=await import('/static/viewer.js'),{faceFrontMotion}=await import('/static/presentation-motion.js'),decode=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
   const {plan,motion}=d,m=plan.measurement,lesson=plan.schema==='motion-lab/listener-lesson-video-plan-v1',scene=document.querySelector('#scene');scene.style.width='1920px';scene.style.height='770px';
   const viewer=new MotionViewer(scene),sink=viewer.vrmSink;sink.manual=true;viewer.renderer.setPixelRatio(1);viewer.resize();
   const avatar=await sink.loadAvatar(decode(d.avatar).buffer);viewer.resetCamera();viewer.controls.enabled=false;
   // Frame the upper body, including space above the head for raised hands.
   sink.vrm.scene.updateMatrixWorld(true);const bounds=new THREE.Box3().setFromObject(sink.vrm.scene);
   const center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3());
   const hipsY=sink.rest.get('hips').node.getWorldPosition(new THREE.Vector3()).y;
   const headY=sink.rest.get('head').node.getWorldPosition(new THREE.Vector3()).y;
   const lower=hipsY-.12,upper=Math.max(bounds.max.y,headY+.25);
   center.y=(lower+upper)/2;size.y=upper-lower;
   const distance=Math.max(size.y/2/Math.tan(THREE.MathUtils.degToRad(viewer.camera.fov/2)),size.x/2/viewer.camera.aspect/Math.tan(THREE.MathUtils.degToRad(viewer.camera.fov/2)))*1.5;
   viewer.controls.target.copy(center);viewer.camera.position.set(center.x,center.y,center.z+distance);viewer.camera.lookAt(center);viewer.controls.update();
   const gl=viewer.renderer.getContext(),debug=gl.getExtension('WEBGL_debug_renderer_info'),webgl=debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);
   const canvas=document.createElement('canvas');canvas.width=1920;canvas.height=1080;const ctx=canvas.getContext('2d');
   const ac=new AudioContext({sampleRate:24000}),voice=await ac.decodeAudioData(decode(d.audio).buffer);await ac.close();const channel=voice.getChannelData(0);
   const clip=plan.motion_scope==='full_body'?sink.prepareMotion(faceFrontMotion(motion)):null;
   let playing=false,last=-1;const stats={maxLip:0,maxHeadPitch:0,frames:0,maxLowerBodyRotationError:0,maxLowerBodyPositionError:0,maxRawLowerBodyRotationError:0};
   const lockedNames=['hips','leftUpperLeg','leftLowerLeg','leftFoot','leftToes','rightUpperLeg','rightLowerLeg','rightFoot','rightToes'];
   sink.vrm.update(0);sink.vrm.scene.updateMatrixWorld(true);
   const rawRest=new Map(lockedNames.map(name=>[name,sink.vrm.humanoid.getRawBoneNode(name)?.getWorldQuaternion(new THREE.Quaternion())]));
   function lockLowerBody(){
    const spine=sink.rest.get('spine').node;
    sink.vrm.scene.updateMatrixWorld(true);
    const spineWorld=spine.getWorldQuaternion(new THREE.Quaternion());
    for(const name of lockedNames){const b=sink.rest.get(name);if(b){b.node.quaternion.copy(b.q);b.node.position.copy(b.p);}}
    sink.vrm.scene.updateMatrixWorld(true);
    spine.quaternion.copy(spine.parent.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(spineWorld));
    sink.vrm.update(0);sink.vrm.scene.updateMatrixWorld(true);
    for(const name of lockedNames){const b=sink.rest.get(name);if(b){
     stats.maxLowerBodyRotationError=Math.max(stats.maxLowerBodyRotationError,b.node.quaternion.angleTo(b.q));
     stats.maxLowerBodyPositionError=Math.max(stats.maxLowerBodyPositionError,b.node.position.distanceTo(b.p));}}
    for(const name of lockedNames){const node=sink.vrm.humanoid.getRawBoneNode(name),q=rawRest.get(name);if(node&&q)stats.maxRawLowerBodyRotationError=Math.max(stats.maxRawLowerBodyRotationError,node.getWorldQuaternion(new THREE.Quaternion()).angleTo(q));}
   }
   function lines(text,x,y){let s='';for(const c of text){if(ctx.measureText(s+c).width>1850){ctx.fillText(s,x,y);s='';y+=34;}s+=c;}ctx.fillText(s,x,y);}
   function scalar(v){while(Array.isArray(v))v=v[0];return Number(v);}
   // Official MaAI predicts nod parameters. The interpolation is an explicit renderer,
   // and the avatar's body remains its default pose.
   const nods=[];if(plan.motion_scope==='head_only'&&!motion.nod_events){
    let available=0;for(const p of motion.predictions){if(p.input_audio_seconds<available||scalar(p.p_nod)<.5)continue;
     const amplitude=Math.abs(scalar(p.nod_range)),speed=Math.max(.001,scalar(p.nod_speed)),count=Math.max(1,Math.round(scalar(p.nod_repetitions_pred))+1);
     const duration=Math.min(4,Math.max(.2,4*amplitude*count/speed));nods.push({start:p.input_audio_seconds,amplitude,count,duration});available=p.input_audio_seconds+duration;}
   }
   window.__dialogueFrame=frame=>{
    if(frame<=last)throw Error('Rendered frames must advance.');last=frame;const t=frame/30,relative=t-plan.student_audio_seconds,local=t-plan.teacher_start_seconds;
    if(local>=0&&!playing){if(clip)sink.play(clip,{offline:true});playing=true;}
    const begin=Math.max(0,Math.floor(local*voice.sampleRate)),end=Math.min(channel.length,begin+600);let rms=0;
    if(local>=0&&local<voice.duration){for(let i=begin;i<end;i++)rms+=channel[i]**2;rms=Math.sqrt(rms/Math.max(1,end-begin));}
    const speaking=!lesson&&local>=0&&local<voice.duration;
    sink.elapsed=Math.max(0,t-1/30);sink.tick(1/30,{speaking,lip:rms,
     offlineTime:clip&&playing?Math.min(Math.max(0,local/plan.teacher_audio_seconds)*(clip.duration-1/motion.fps),clip.duration-1/motion.fps):null});
    if(plan.motion_scope==='head_only'&&playing){let pitch=0;
     if(motion.nod_events){for(const n of motion.nod_events){const index=Math.floor((local-n.start_seconds)*n.fps);if(index>=0&&index<n.pitch_frames_radians.length)pitch=-n.pitch_frames_radians[index];}}
     else for(const n of nods){const u=local-n.start;if(u>=0&&u<n.duration)pitch=n.amplitude*(1-Math.cos(2*Math.PI*n.count*u/n.duration))/2;}
     const head=sink.rest.get('head');if(head)head.node.quaternion.copy(head.q).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1,0,0),pitch));sink.vrm.update(0);stats.maxHeadPitch=Math.max(stats.maxHeadPitch,Math.abs(pitch));}
    // Presentation keeps the teacher at its lectern and facing the student.
    // Original learned trajectories remain in motion.json for evaluation.
    const hips=sink.rest.get('hips');if(hips){hips.node.position.copy(hips.p);sink.vrm.update(0);}
    lockLowerBody();viewer.draw(0);stats.maxLip=Math.max(stats.maxLip,sink.vrm.expressionManager?.getValue('aa')||0);stats.frames++;
    ctx.fillStyle='#edf1ed';ctx.fillRect(0,0,1920,1080);ctx.drawImage(viewer.renderer.domElement,0,100);
    ctx.fillStyle='#162b35';ctx.fillRect(0,0,1920,100);ctx.fillStyle='white';ctx.font='bold 29px "Noto Sans CJK JP",sans-serif';ctx.fillText(lesson?`${plan.model} / 同一発話の聞き手反応 / ${t.toFixed(2)} 秒`:`${plan.model} / 音声入力→教師の返答 / 生徒の発話終了から ${relative.toFixed(2)} 秒`,24,38);
    ctx.font='21px "Noto Sans CJK JP",sans-serif';ctx.fillText(plan.caption+' · '+(m.gpu_name||'GPU未記録')+' / '+m.resident_mode+' · 上半身・下半身固定 · 正面1080p',24,76);
    ctx.fillStyle='white';ctx.fillRect(0,870,1920,210);ctx.fillStyle='#162b35';ctx.font='27px "Noto Sans CJK JP",sans-serif';
    lines(lesson?'話者：'+(plan.lesson_segments.find(u=>t>=u.start_seconds&&t<u.end_seconds)?.text||''):(t<plan.student_audio_seconds?'生徒：'+plan.student_text:local<0?'教師の音声と動作を準備中…':'先生：'+plan.teacher_text),24,908);
    const f=m.first_teacher_audio_seconds_after_student_end,b=m.bone_ready_observed_seconds_after_student_end,a=m.asr_seconds_after_student_end;
    ctx.font='22px "Noto Sans CJK JP",sans-serif';
    if(!lesson){ctx.fillText(`音声認識 ${a.toFixed(2)}s ${relative>=a?'✓':''}  |  Realtime最初の音声 ${f.toFixed(2)}s ${relative>=f?'✓':''}  |  動作完了 ${b.toFixed(2)}s ${relative>=b?'✓':''}`,24,990);
    ctx.fillText(`発話・動作開始 ${(plan.teacher_start_seconds-plan.student_audio_seconds).toFixed(2)}s / ${m.input_translation?`LLM英訳 ${m.translation_seconds.toFixed(2)}s + `:''}骨格 ${m.motion_generation_seconds.toFixed(2)}s / 初音声との差 ${m.bone_minus_first_realtime_audio_seconds.toFixed(2)}s`,24,1023);}
    else ctx.fillText('学習済みの頭部パラメーターを補間して表示 / 翻訳なし / 聞き手の口は動かしません',24,990);
    ctx.font='16px "Noto Sans CJK JP",sans-serif';ctx.fillText('Avatar: '+avatar.name+' / '+(avatar.authors||[]).join(', ')+' · 生徒音声は録音済み合成音声',24,1062);
    return canvas.toDataURL('image/png').split(',')[1];
   };window.__dialogueStats=()=>stats;return {avatar,webgl,front_alignment:viewer.camera.position.clone().sub(viewer.controls.target).normalize().dot(new THREE.Vector3(0,0,1))};
  },{plan,motion,avatar:avatar.toString('base64'),audio:audio.toString('base64')});
  const silent=path.join(temporary,'silent.mp4');encoder=spawn('ffmpeg',['-hide_banner','-loglevel','error','-n','-f','image2pipe','-vcodec','png','-framerate','30','-i','pipe:0','-an','-c:v','libx264','-crf','16','-preset','fast','-pix_fmt','yuv420p',silent]);
  let stderr='';encoder.stderr.on('data',c=>stderr+=c);const exited=new Promise((resolve,reject)=>{encoder.once('error',reject);encoder.once('close',resolve);});
  let cachedFrame=null;
  for(let frame=0;frame<plan.frame_count;frame++){
   // The waiting avatar is a static presentation. Update its clock once a second;
   // repeat that image at 30fps, preserving the full measured waiting duration.
   if(frame/30>=plan.teacher_start_seconds||frame%30===0||cachedFrame===null)
    cachedFrame=Buffer.from(await page.evaluate(f=>window.__dialogueFrame(f),frame),'base64');
   if(!encoder.stdin.write(cachedFrame))await once(encoder.stdin,'drain');
   if(frame%150===0)console.log(JSON.stringify({model:plan.model,frames:frame,total:plan.frame_count}));
  }
  encoder.stdin.end();if(await exited!==0)throw Error(stderr);encoder=null;
  command('ffmpeg',['-hide_banner','-loglevel','error','-n','-i',silent,'-i',path.join(root,'timeline.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t',String(plan.duration_seconds),'-movflags','+faststart',output]);
  const media=JSON.parse(command('ffprobe',['-v','error','-count_frames','-show_entries','stream=codec_type,width,height,r_frame_rate,nb_read_frames:format=duration','-of','json',output]));
  const video=media.streams.find(s=>s.codec_type==='video'),stats=await page.evaluate(()=>window.__dialogueStats());
  if(video.width!==1920||video.height!==1080||video.r_frame_rate!=='30/1'||Number(video.nb_read_frames)!==plan.frame_count||(!lesson&&stats.maxLip<.01)||errors.length||setup.front_alignment<.99||stats.maxLowerBodyRotationError>1e-5||stats.maxLowerBodyPositionError>1e-8||stats.maxRawLowerBodyRotationError>1e-5)throw Error('Rendered video validation failed.');
  const result={schema:'motion-lab/audio-dialogue-video-v1',model:plan.model,plan,render_wall_seconds:(performance.now()-began)/1000,
   live_recording:false,render_mode:'offline_replay_of_real_measurement',hardware_webgl:false,setup,stats,media,
   idle_image_update_seconds:1,waiting_duration_compressed:false,
   audio_gesture_start_offset_seconds:0,upper_body_only:true,presentation_root_policy:'source torso yaw removed; hips and lower body fixed; spine world orientation retained; original learned joints preserved',video_sha256:hash(fs.readFileSync(output)),browser_errors:errors};
  fs.writeFileSync(output.replace(/\.mp4$/,'.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({mp4:output,render_wall_seconds:result.render_wall_seconds}));
 }finally{if(encoder)encoder.kill();await browser.close();fs.rmSync(temporary,{recursive:true,force:true});}
}
main().catch(e=>{console.error(e.stack);process.exitCode=1;});
