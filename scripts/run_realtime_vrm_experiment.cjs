const {chromium}=require('@playwright/test');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const dir=process.env.MOTION_LAB_EXPERIMENT_DIR||path.join(root,'.motion-lab','realtime-run-'+Date.now());fs.mkdirSync(dir,{recursive:true});
(async()=>{
 const browser=await chromium.launch({args:['--use-angle=d3d11','--autoplay-policy=no-user-gesture-required']});
 const context=await browser.newContext({viewport:{width:1440,height:1100}});
 const page=await context.newPage();const errors=[];let motion=null;
 page.on('pageerror',e=>errors.push(e.message));
 page.on('response',async response=>{
  if(/\/api\/motion\/requests\/[0-9a-f]{32}$/.test(new URL(response.url()).pathname)&&response.ok()){
   try{const value=await response.json();if(value.status==='succeeded')motion=value;}catch{}
  }
 });
 // A longer, explicitly requested spoken explanation gives the batch model time
 // to complete. This is comparison mode C, not the default three-second deadline.
 await page.addInitScript(()=>{
  const original=RTCDataChannel.prototype.send;
  RTCDataChannel.prototype.send=function(value){
   try{const e=JSON.parse(value);if(e.type==='response.create'){e.response.max_output_tokens=4096;value=JSON.stringify(e);}}catch{}
   return original.call(this,value);
  };
 });
 let result={status:'running',avatar:'VRM1_Constraint_Twist_Sample',model:'kimodo',mode:'C',max_output_tokens:4096};
 try{
  await page.goto('http://127.0.0.1:8765/conversation');
  await page.locator('#avatar-file').setInputFiles(process.env.MOTION_LAB_TEST_VRM||path.join(root,'.motion-lab/avatars/VRM1_Constraint_Twist_Sample.vrm'));
  await page.locator('#empty-scene').waitFor({state:'hidden'});
  result.webgl_renderer=await page.evaluate(()=>{
   const gl=document.querySelector('#viewport canvas').getContext('webgl2'),ext=gl.getExtension('WEBGL_debug_renderer_info');
   return ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);
  });
  await page.getByText('実験・同期設定',{exact:true}).click();
  await page.locator('#experiment-mode').selectOption('C');
  await page.locator('#motion-model').selectOption('kimodo');
  await page.locator('#motion-override').fill('Raise your right hand above your shoulder and wave repeatedly for 8 seconds.');
  await page.locator('#connect').click();
  await page.waitForFunction(()=>document.getElementById('connection-status').textContent==='接続済み',null,{timeout:35000});
  await page.waitForFunction(()=>document.getElementById('reply-audio').srcObject?.getAudioTracks().length>0,null,{timeout:10000});
  await page.evaluate(()=>{
   const canvas=document.querySelector('#viewport canvas'),audio=document.getElementById('reply-audio');
   const stream=new MediaStream([...canvas.captureStream(20).getVideoTracks(),...audio.srcObject.getAudioTracks()]);
   const recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8,opus',videoBitsPerSecond:1500000});
   const chunks=[];recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
   window.demoRecording={recorder,chunks};recorder.start(1000);
  });
  const prompt='日本語で、研究用の音声対話アバターがどのように文章から声と動きを作るか、初心者向けに詳しく説明してください。音声認識、応答生成、動作生成、3Dモデルへの適用、遅延の課題について順番に、二十文以上、千二百文字程度で話してください。急がず、ゆっくり落ち着いて説明してください。';
  result.input=prompt;result.motion_prompt='Raise your right hand above your shoulder and wave repeatedly for 8 seconds.';
  const started=Date.now();await page.locator('#utterance').fill(prompt);await page.locator('#send').click();
  let applied=false,firstText=null;
  while(Date.now()-started<145000){
   const state=await page.locator('#gesture-state').textContent();
   if(firstText===null&&(await page.locator('#reply-transcript').inputValue()))firstText=(Date.now()-started)/1000;
   if(/BLENDING|PLAYING_GENERATED/.test(state)){applied=true;result.gesture_visible_seconds=(Date.now()-started)/1000;await page.screenshot({path:path.join(dir,'generated-gesture.png'),fullPage:true});break;}
   const msg=await page.locator('#dialogue-message').textContent();if(/接続|API|通信エラー/.test(msg)&&!(await page.locator('#reply-transcript').inputValue()))throw new Error(msg);
   if((await page.locator('#event-log').textContent()).includes('audio_playback_ended'))break;
   await page.waitForTimeout(500);
  }
  if(applied)await page.waitForTimeout(11000);
  result.first_text_seconds=firstText;result.new_motion=motion;result.generated_gesture_applied=applied;
  result.transcript=await page.locator('#reply-transcript').inputValue();
  result.status=applied?'succeeded':'live_speech_without_generated_gesture';
  result.messages=await page.locator('#dialogue-message').textContent();
  await page.locator('#save-events').click();
  const download=page.waitForEvent('download');await page.locator('#export-events').click();
  fs.copyFileSync(await (await download).path(),path.join(dir,'events.csv'));
 }catch(e){result.status='failed';result.error=e.message;await page.screenshot({path:path.join(dir,'failure.png'),fullPage:true}).catch(()=>{});}
 finally{
  try{
   const base64=await page.evaluate(async()=>{
    const r=window.demoRecording;if(!r)return null;
    await new Promise(resolve=>{r.recorder.onstop=resolve;r.recorder.stop()});
    const bytes=new Uint8Array(await new Blob(r.chunks,{type:'video/webm'}).arrayBuffer());
    let s='';for(let i=0;i<bytes.length;i+=32768)s+=String.fromCharCode(...bytes.subarray(i,i+32768));return btoa(s);
   });
   if(base64)fs.writeFileSync(path.join(dir,'avatar-and-realtime.webm'),Buffer.from(base64,'base64'));
  }catch(e){result.recording_error=e.message;}
  await page.locator('#disconnect').click().catch(()=>{});result.browser_errors=errors;
  fs.writeFileSync(path.join(dir,'result.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify({status:result.status,error:result.error,first_text_seconds:result.first_text_seconds,gesture_visible_seconds:result.gesture_visible_seconds,new_motion_id:motion?.request_id,generated_gesture_applied:result.generated_gesture_applied,browser_errors:errors}));
  await browser.close();
 }
})();
