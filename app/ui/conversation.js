import {MotionViewer} from './viewer.js';
import {ConversationManager,transcriptMatches} from './conversation-manager.js';
import {GestureScheduler} from './gesture-scheduler.js';
import {RealtimeSpeechEngine} from './realtime-engine.js';
import {OfflineSpeechEngine} from './offline-speech.js';
import {ResearchLog} from './research-log.js';

const $=id=>document.getElementById(id),manager=new ConversationManager(),log=new ResearchLog();
let config={},offlineMotion=null,offlineVoice=null,micOn=false,requestTokens=new Set(),previous=performance.now();
const viewer=new MotionViewer($('viewport')),sink=viewer.vrmSink;sink.manual=true;
function message(text){$('dialogue-message').textContent=text;$('dialogue-message').hidden=!text;}
function record(name,details={}) {
  log.record(name,{turn_id:manager.turn?.id,response_id:manager.turn?.responseId,...details});$('event-log').textContent=log.events.slice(-25).map(e=>`${e.time_ms===null?'null':e.time_ms.toFixed(1)} ${e.clock_domain} ${e.name} ${e.detail}`).join('\n');
}
const scheduler=new GestureScheduler(sink,{onEvent:(name,details)=>{
  record(name,details);$('gesture-state').textContent=scheduler.state;
  if(['gesture_expired','gesture_invalidated','motion_failed'].includes(name))cancelRequests(details.detail||name);
}});
const live=new RealtimeSpeechEngine($('reply-audio'),{onEvent:handleEvent,
  onState:text=>{$('connection-status').textContent=text;},onError:text=>{message(text);record('network_error',{detail:text});interrupt(false);}});
const offline=new OfflineSpeechEngine($('reply-audio'),handleEvent);
const isOffline=()=>$('engine-mode').value==='offline';
async function api(url,data=null,method='POST') {
  const response=await fetch(url,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});
  if(!response.ok){let error={};try{error=await response.json();}catch{}throw new Error(error.detail||`HTTP ${response.status}`);}return response.json();
}
function renderChat() {
  $('chat-history').replaceChildren(...manager.history.map(turn=>{
    const node=document.createElement('div');node.className='chat-entry';const user=document.createElement('strong');user.textContent='あなた';
    const reply=document.createElement('strong');reply.textContent=isOffline()?'定型応答（検証用）':'アバター';
    node.append(user,document.createTextNode(turn.userText),reply,document.createTextNode(turn.reply||(turn.cancelled?'中断しました。':'応答を準備しています…')));return node;
  }));
}
async function cancelRequests(reason) {
  const tokens=[...requestTokens];requestTokens.clear();
  for(const token of tokens) {
    token.cancelled=true;token.wake?.();
    if(token.requestId) {
      try {await api('/api/motion/requests/'+token.requestId,null,'DELETE');}
      catch(error){record('motion_cancel_failed',{detail:error.message,turn_id:token.turn.id});}
    }
  }
}
function wait(ms,token) {return new Promise(resolve=>{const timer=setTimeout(resolve,ms);token.wake=()=>{clearTimeout(timer);resolve();};});}
async function obtainMotion(plan,turn,token) {
  const started=performance.now();record('motion_requested',{turn_id:turn.id,response_id:plan.response_id,gesture_id:plan.gesture_id,timeMs:isOffline()?null:started});
  if(isOffline()&&!offlineMotion)throw new Error('オフライン検証のモーションJSONが未指定です。新規推論は実行しません。');
  let clip;
  if(isOffline()&&offlineMotion) {
    record('recorded_motion_loaded',{turn_id:turn.id,detail:'保存済み結果の再生。新たな推論ではありません。'});
    const begin=performance.now();clip=sink.prepareMotion(offlineMotion);record('vrm_conversion_completed',{detail:`${(performance.now()-begin).toFixed(1)} ms`});
    $('motion-status').textContent=`保存済みモーションを検証再生（新規生成なし）\n骨格: ${offlineMotion.skeleton_type}`;
    record('model_generation_started',{timeMs:null,clock:'server_monotonic'});record('model_generation_finished',{timeMs:null,clock:'server_monotonic'});
  } else {
    const created=await api('/api/motion/requests',{turn_id:turn.id,response_id:plan.response_id,gesture_id:plan.gesture_id,
      model_name:$('motion-model').value,original_text:plan.original_text,motion_prompt:plan.motion_prompt,
      duration:plan.expected_duration_ms/1000,seed:0,deadline_ms:plan.deadline_ms,allow_external_demo:$('allow-external').checked});
    token.requestId=created.request_id;
    if(token.cancelled){await api('/api/motion/requests/'+token.requestId,null,'DELETE');return null;}
    let result=created;
    while(['queued','running'].includes(result.status)) {
      if(token.cancelled)return null;
      if(performance.now()-started>120000)throw new Error('モーションサービスの待機時間を超えました。');
      $('motion-status').textContent=`${result.status}\nrequest_id: ${created.request_id}\n入力: ${plan.motion_prompt}`;
      await wait(250,token);if(token.cancelled)return null;
      result=await api('/api/motion/requests/'+created.request_id,null,'GET');
    }
    if(result.status!=='succeeded')throw new Error(result.error||'モーション生成失敗: '+result.status);
    record('model_generation_started',{timeMs:result.server_started_monotonic_ms??null,clock:'server_monotonic'});
    record('model_generation_finished',{timeMs:result.server_finished_monotonic_ms??null,clock:'server_monotonic'});
    record('first_motion_available',{turn_id:turn.id});record('first_partial_chunk',{timeMs:null});
    const conversionStart=performance.now();
    if(result.has_vrma) {
      const response=await fetch('/api/motion/requests/'+created.request_id+'/vrma');if(!response.ok)throw new Error('VRMA取得に失敗しました。');
      clip=await sink.prepareVRMA(await response.arrayBuffer());
    } else clip=sink.prepareMotion(await api('/api/motion/requests/'+created.request_id+'/motion',null,'GET'));
    record('vrm_conversion_completed',{turn_id:turn.id,detail:`${(performance.now()-conversionStart).toFixed(1)} ms`});
    $('motion-status').textContent=`${result.trained_model_output===true?'学習済みモデルの結果を取得':'推論の出所は未検証'}\n骨格まで: ${result.timings?.skeleton_seconds?.toFixed(2)??'未測定'} s\n入力: ${plan.motion_prompt}`;
  }
  await wait(Number($('delivery-delay').value),token);return token.cancelled?null:clip;
}
async function launchMotion(plan,turn,{beforeResponse=false}={}) {
  if(turn.cancelled||manager.turn!==turn)return null;
  if(!plan.motion_prompt||$('experiment-mode').value==='A')return null;
  if(!sink.vrm){record('motion_unavailable',{detail:'VRMを先に読み込んでください。'});return null;}
  if(!beforeResponse&&!scheduler.request(plan))return null;
  const token={turn,cancelled:false};requestTokens.add(token);
  try {
    const clip=await obtainMotion(plan,turn,token);
    if(!clip||token.cancelled||manager.turn!==turn||turn.cancelled)return null;
    if(beforeResponse&&!turn.responseId) {turn.preparedClip=clip;return clip;}
    if(!manager.active(turn.responseId))return null;
    plan.response_id=turn.responseId;
    if(turn.transcriptMismatch)return null;
    if(beforeResponse&&scheduler.pending?.plan.gesture_id!==plan.gesture_id){plan.requires_transcript_match=!!turn.plannedReply&&!turn.transcriptVerified;scheduler.request(plan);}
    // Conversion can take longer than a frame. Re-read the playback clock before
    // deciding whether a clip can start, instead of using the last RAF sample.
    const playback=(isOffline()?offline:live).observer.sample();
    if(playback.started&&scheduler.speech==='SPEAKING')scheduler.tick(playback.elapsedMs);
    if(playback.ended||$('reply-audio').paused&&scheduler.speech==='SPEAKING')scheduler.endSpeech();
    scheduler.result(plan,clip);return clip;
  } catch(error) {
    if(!token.cancelled&&manager.turn===turn){scheduler.failure(error.message);message('動作生成: '+error.message+'\n音声会話とデフォルト動作は継続します。');record('motion_failed',{detail:error.message,turn_id:turn.id});}
    return null;
  } finally {requestTokens.delete(token);}
}
async function planTurn(turn) {
  if(turn.planStarted||!manager.active(turn.responseId))return;turn.planStarted=true;
  try {
    const plan=await api('/api/conversation/plan',{turn_id:turn.id,response_id:turn.responseId,user_text:turn.userText,
      response_text:turn.reply,motion_prompt_override:$('motion-override').value,deadline_ms:Number($('gesture-deadline').value)});
    if(manager.turn!==turn||!manager.active(turn.responseId))return;
    $('planner-output').textContent=JSON.stringify(plan,null,2);record('gesture_planned',{turn_id:turn.id,detail:plan.motion_prompt||plan.reason,estimated:true});
    launchMotion(plan,turn);
  }catch(error){message(error.message);}
}
function handleEvent(event) {
  record('realtime_event',{detail:event.type,estimated:!!event.offline});
  const turn=manager.turn;
  if(event.type==='input_audio_buffer.speech_started') {interrupt(false);manager.begin('',event.item_id);renderChat();}
  if(event.type==='input_audio_buffer.speech_stopped')record('user_speech_end_observed',{estimated:true});
  if(event.type==='conversation.item.input_audio_transcription.completed') {
    if(manager.turn?.userItemId===event.item_id){manager.turn.userText=event.transcript;renderChat();startReply(manager.turn).catch(error=>message(error.message));}
  }
  if(event.type==='response.created') {
    const active=manager.attachResponse(event.response.id,event.response.metadata?.turn_id);
    if(!active){record('stale_response_discarded',{response_id:event.response.id});return;}
    scheduler.mode=$('experiment-mode').value;scheduler.blendMs=Number($('blend-duration').value);
    scheduler.begin(active.id,event.response.id);record('response_created_received',{turn_id:active.id,response_id:event.response.id});
    record('llm_generation_started',{timeMs:null,clock:'server_monotonic'});
    if(active.preparedPlan) {
      active.preparedPlan.response_id=event.response.id;active.planStarted=true;scheduler.request(active.preparedPlan);
      if(active.preparedClip)scheduler.result(active.preparedPlan,active.preparedClip);
      record('provisional_response_bound',{turn_id:active.id,response_id:event.response.id});
    }
  }
  const transcriptTypes=['response.output_audio_transcript.delta','response.output_audio_transcript.done','response.output_text.delta','response.output_text.done'];
  if(transcriptTypes.includes(event.type)) {
    const active=manager.transcript(event,event.type.endsWith('.done'));if(!active)return;
    $('reply-transcript').value=active.reply;renderChat();
    if(!active.firstText){active.firstText=true;record('first_response_text',{turn_id:active.id,response_id:event.response_id});}
    if(active.plannedReply&&event.type.endsWith('.done')&&!transcriptMatches(active.plannedReply,active.reply)) {
      scheduler.verifyTranscript(false);active.planStarted=true;active.transcriptMismatch=true;
      record('text_first_mismatch',{detail:'指定文と音声書き起こしが一致しないため計画動作を無効化しました。'});
    } else if(active.plannedReply&&event.type.endsWith('.done')) {
      active.transcriptVerified=true;scheduler.verifyTranscript(true);
    } else if(!active.plannedReply&&(event.type.endsWith('.done')||/[。！？!?]/.test(active.reply)))planTurn(active);
  }
  if(event.type==='response.done') {record('response_generation_done_received',{response_id:event.response.id});record('llm_generation_finished',{timeMs:null,clock:'server_monotonic'});}
  if(event.type==='offline.audio.ended'&&manager.active(event.response_id)){scheduler.endSpeech();cancelRequests('speech_ended');}
  if(event.type==='output_audio_buffer.cleared'&&manager.active(event.response_id))interrupt(false);
}
async function startReply(turn) {
  const mode=$('experiment-mode').value,textFirst=$('speech-mode').value==='text'&&!isOffline();
  if(textFirst) {
    record('text_first_requested',{turn_id:turn.id});
    const prepared=await api('/api/conversation/prepare',{text:turn.userText});if(manager.turn!==turn||turn.cancelled)return;
    turn.plannedReply=prepared.reply;turn.preparedPlan=await api('/api/conversation/plan',{turn_id:turn.id,response_id:'pre-response:'+turn.id,
      user_text:turn.userText,response_text:prepared.reply,motion_prompt_override:prepared.motion_prompt,deadline_ms:Number($('gesture-deadline').value)});
    turn.preparedPlan.anchor_text=prepared.anchor_text;turn.preparedPlan.gesture_type=prepared.gesture_type;turn.preparedPlan.translation_method='llm_structured_checked';
    turn.preparedPlan.requires_transcript_match=true;
  } else if(mode==='B') turn.preparedPlan=await api('/api/conversation/plan',{turn_id:turn.id,response_id:'pre-response:'+turn.id,
    user_text:turn.userText,response_text:'',motion_prompt_override:$('motion-override').value,deadline_ms:Number($('gesture-deadline').value)});
  if(turn.preparedPlan) {
    $('planner-output').textContent=JSON.stringify(turn.preparedPlan,null,2);
    const promise=launchMotion(turn.preparedPlan,turn,{beforeResponse:true});
    if(mode==='B') {
      let timer;await Promise.race([promise,new Promise(resolve=>{timer=setTimeout(resolve,30000);})]);clearTimeout(timer);
      if(manager.turn!==turn||turn.cancelled)return;
      if(!turn.preparedClip){await cancelRequests('wait_limit');record('speech_wait_limit',{turn_id:turn.id});}
    }
  }
  if(manager.turn!==turn||turn.cancelled)return;
  if(isOffline()) {
    const reply=turn.userText.includes('嬉しい')?'それはよかったですね！どんなことがあったんですか？':turn.userText.includes('自己紹介')?'こんにちは。研究用のアバターです。よろしくお願いします。':turn.userText.includes('手')?'はい。手を振る動作を準備します。':'こんにちは。今日はどうされましたか？';
    await offline.play(reply,'offline-'+crypto.randomUUID(),offlineVoice,turn.id);
  } else live.respond({plannedText:turn.plannedReply,turnId:turn.id});
}
async function interrupt(clearAudio=true) {
  record('interrupt_started');manager.interrupt();scheduler.interrupt();cancelRequests('interrupted');
  renderChat();
  if(isOffline())await offline.stop();else if(clearAudio)live.interrupt();
}
$('send').onclick=async()=>{
  const text=$('utterance').value.trim();if(!text)return;message('');$('send').disabled=true;
  try {await interrupt();const turn=manager.begin(text);renderChat();
    if(!isOffline())live.addText(text);
    record('user_text_submitted',{turn_id:turn.id});await startReply(turn);
  }catch(error){message(error.message);}finally{$('send').disabled=false;}
};
$('utterance').onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('send').click();}};
document.querySelectorAll('[data-chat-example]').forEach(button=>button.onclick=()=>{$('utterance').value=button.dataset.chatExample;});
$('connect').onclick=async()=>{message('');try{await interrupt();await live.connect(config);}catch(error){message(error.message);}};
$('disconnect').onclick=async()=>{await interrupt();await live.disconnect();micOn=false;$('microphone').textContent='マイク開始';};
$('microphone').onclick=async()=>{try{$('microphone').disabled=true;micOn=await live.microphone(!micOn);$('microphone').textContent=micOn?'マイク停止':'マイク開始';}catch(error){message(error.message);}finally{$('microphone').disabled=isOffline();}};
$('interrupt').onclick=()=>interrupt();
$('engine-mode').onchange=async()=>{await interrupt();await live.disconnect();await offline.stop();configure();};
$('experiment-mode').onchange=async()=>{await interrupt();scheduler.mode=$('experiment-mode').value;log.mode=scheduler.mode;};
$('default-gestures').onchange=()=>{sink.defaultEnabled=$('default-gestures').checked;};
$('avatar-file').onchange=async event=>{
  try {await interrupt();const file=event.target.files[0];if(!file)return;const meta=await sink.loadAvatar(await file.arrayBuffer());
    $('avatar-meta').textContent=`${meta.name} / ${meta.authors?.join(', ')} / ${meta.licenseUrl} / 再配布: ${meta.allowRedistribution?'可':'不可'}`;
    $('empty-scene').hidden=true;record('avatar_loaded',{detail:meta.name});viewer.resetCamera();
  }catch(error){message(error.message);}
};
$('avatar-display').onchange=()=>{if(sink.vrm){sink.vrm.scene.visible=$('avatar-display').value==='vrm';sink.skeleton.visible=$('avatar-display').value==='skeleton';}};
$('camera-reset').onclick=()=>viewer.resetCamera();
$('offline-motion').onchange=async event=>{try {const file=event.target.files[0];if(file.size>32*1024*1024)throw new Error('モーションの上限は32MiBです。');offlineMotion=JSON.parse(await file.text());record('offline_motion_selected',{detail:'保存済み結果の検証再生。新規推論ではありません。'});}catch(error){message(error.message);}};
$('offline-voice').onchange=async event=>{const file=event.target.files[0];if(file.size>32*1024*1024){message('WAVの上限は32MiBです。');return;}offlineVoice=await file.arrayBuffer();};
$('export-events').onclick=()=>log.download();$('save-events').onclick=async()=>{try{const result=await log.save();message('音声を含まない研究記録を保存しました。ID: '+result.id);}catch(error){message(error.message);}};
function configure() {
  const offlineMode=isOffline();$('connect').disabled=offlineMode||!config.enabled;$('microphone').disabled=offlineMode;
  $('motion-model').disabled=offlineMode;$('allow-external').disabled=offlineMode;
  $('offline-settings').hidden=!offlineMode;$('speech-mode').querySelector('[value="text"]').disabled=!config.text_first_enabled||offlineMode;
  if(!config.text_first_enabled||offlineMode)$('speech-mode').value='voice';
  $('connection-status').textContent=offlineMode?'オフライン検証':'未接続';$('config-note').textContent=offlineMode?'定型文・検証音で制御を確認します。AIの実生成ではありません。':config.reason||`${config.model} / ${config.session_seconds}秒で切断`;
  $('provenance').classList.toggle('offline',offlineMode);$('provenance').textContent=offlineMode?'オフライン検証：定型文・検証音または保存済みWAV／モーション。新規AI推論・新規Text-to-Motion生成ではありません。':'音声時計とローカル信号検出を使用。スピーカー出力の遅延・正確な単語時刻は未測定です。';
  log.provenance=offlineMode?'offline_validation':'live';
  record('experiment_config',{detail:JSON.stringify({mode:$('experiment-mode').value,speech_mode:$('speech-mode').value,default_gestures:sink.defaultEnabled,model:$('motion-model').value,deadline_ms:Number($('gesture-deadline').value),blend_ms:Number($('blend-duration').value)})});
}
function frame(now) {
  const delta=Math.min(.1,(now-previous)/1000);previous=now;
  const clock=(isOffline()?offline:live).observer.sample();
  if(clock.started&&scheduler.speech==='PREPARING'){scheduler.startSpeech();record('audio_clock_onset',{clock:'client_audio',timeMs:(isOffline()?offline:live).observer.clock.startTime*1000});}
  if(clock.started&&scheduler.speech==='SPEAKING')scheduler.tick(clock.elapsedMs);
  if(clock.ended&&scheduler.speech==='SPEAKING'){scheduler.endSpeech();cancelRequests('speech_ended');}
  sink.tick(delta,{speaking:scheduler.speech==='SPEAKING',lip:clock.lip});
  if(['BLENDING','PLAYING_GENERATED'].includes(scheduler.state)&&sink.mode==='returning'){record('gesture_completed');scheduler.pending=null;scheduler.transition('RETURNING_TO_IDLE');}
  if(scheduler.state==='RETURNING_TO_IDLE'&&sink.mode==='default')scheduler.transition(scheduler.speech==='SPEAKING'?'SPEAKING_DEFAULT':'IDLE');
  $('speech-time').textContent=clock.elapsedMs===null?'音声待機':`${(clock.elapsedMs/1000).toFixed(2)} s / ${scheduler.state}`;
  $('dialogue-timeline').value=(clock.elapsedMs||0)/1000;viewer.draw(0);requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
try {config=await api('/api/realtime/config',null,'GET');if(!config.enabled)$('engine-mode').value='offline';configure();}catch(error){message(error.message);}
window.addEventListener('pagehide',()=>{live.disconnect();offline.stop();cancelRequests('page_closed');});
$('reply-audio').addEventListener('pause',()=>{if(scheduler.speech==='SPEAKING'){scheduler.endSpeech();cancelRequests('audio_paused');}});
