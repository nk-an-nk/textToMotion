import {MotionViewer} from './viewer.js';
const $=id=>document.getElementById(id);
const state={mode:'instruction',models:[],records:[],selected:new Set(),motions:[],audioId:null,time:0,duration:0,playing:false,speed:1,pending:new Set()};
let viewer;
try{viewer=new MotionViewer($('viewport'));}catch(error){$('empty-scene').textContent='WebGL を初期化できません。モーションの保存・取得は利用できます。';console.error(error);}

async function api(url,options={}){
  const response=await fetch(url,options);const data=await response.json();
  if(!response.ok){const detail=Array.isArray(data.detail)?data.detail.map(x=>x.msg).join('\n'):data.detail;throw new Error(detail||`HTTP ${response.status}`);}return data;
}
const post=(url,data)=>api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
function message(text){$('message').hidden=!text;$('message').textContent=text;}
function labelFor(record){if(record.task_type==='unconditional_diagnostic')return 'ARDY（無条件CPU診断）';return record.model_id==='synthetic_viewer_fixture'?'人工サンプル（推論なし）':record.model_id==='user_import'?'取り込みデータ':state.models.find(m=>m.id===record.model_id)?.name||record.model_id;}
function displayModel(){
  const model=state.models.find(m=>m.id===$('model').value);if(!model)return;
  $('model-status').textContent=model.execution_status+ (model.implemented?' · 実行アダプターあり':' · 実行アダプター未実装');
  $('blockers').replaceChildren(...model.blockers.map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));
  $('official').href=model.official_url;
  $('diagnose-ardy').hidden=!model.can_diagnose;
  if(model.backend==='official_demo'){
    const li=document.createElement('li');li.textContent='NVIDIA公式オンラインデモを使用します。入力文を外部へ送信します。1回10秒以内、サービスのセッション制限に従います。';$('blockers').append(li);
  }
}
function populateModels(){
  const prior=$('model').value;
  const list=state.models.filter(m=>m.tasks.includes(state.mode));
  $('model').replaceChildren(...list.map(m=>{const option=document.createElement('option');option.value=m.id;option.textContent=`${m.name} · ${m.execution_status}`;return option;}));
  if(list.some(m=>m.id===prior))$('model').value=prior;
  if(!prior){const ready=list.find(m=>m.can_generate);if(ready)$('model').value=ready.id;else if(state.mode==='instruction'&&list.some(m=>m.id==='ardy'))$('model').value='ardy';}
  $('compare-models').replaceChildren(...list.map(m=>{const label=document.createElement('label');const input=document.createElement('input');input.type='checkbox';input.value=m.id;label.append(input,document.createTextNode(`${m.name} (${m.execution_status})`));return label;}));
  displayModel();
}
$('model').addEventListener('change',displayModel);
document.querySelectorAll('[data-mode]').forEach(button=>button.addEventListener('click',()=>{
  state.mode=button.dataset.mode;document.querySelectorAll('[data-mode]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-selected',String(b===button));});
  $('audio-input').hidden=state.mode!=='audio';$('duration').disabled=state.mode==='audio';
  $('text-label').textContent={instruction:'動作の指示',conversation_text:'会話の内容',audio:'文字起こし / メモ（任意）'}[state.mode];populateModels();
}));
const examples={wave:['Raise your right hand and wave for three seconds.',''],sequence:['Walk forward, stop, and bow.',''],conversation:['今日はとても嬉しいことがあったんです','Something wonderful happened to me today.']};
document.querySelectorAll('[data-example]').forEach(button=>button.addEventListener('click',()=>{[$('text').value,$('translation').value]=examples[button.dataset.example];}));
const utterances={};
document.querySelectorAll('[data-utterance]').forEach(button=>button.addEventListener('click',()=>{
  const example=utterances[button.dataset.utterance];if(!example)return;
  document.querySelector('[data-mode="instruction"]').click();$('model').value='ardy';displayModel();
  [$('text').value,$('translation').value]=[example.input_text,example.model_text];
  $('duration').value=example.duration;
  $('seed').value=example.seed;
}));
async function uploadAudio(file){
  if(!file)return;message('音声を確認しています…');const form=new FormData();form.append('file',file);
  const result=await api('/api/audio',{method:'POST',body:form});state.audioId=result.audio_id;
  $('audio').src=result.url;$('audio-info').textContent=`${result.duration.toFixed(2)}秒 · ${result.sample_rate} Hz · ${result.channels} ch`;
  $('sync-note').textContent='音声の時刻に動作を同期';message('WAV を読み込みました。生成時の条件付けと、ビューアーでの同期再生は別に記録します。');
}
for(const id of ['wav','sync-wav'])$(id).addEventListener('change',event=>uploadAudio(event.target.files[0]).catch(error=>message(error.message)));
$('generate').addEventListener('click',async()=>{
  $('generate').disabled=true;message('入力とモデルの準備状況を確認しています…');
  try{
    const data={task_type:state.mode,text:$('text').value,translated_text:$('translation').value,audio_id:state.audioId,duration:Number($('duration').value),seed:Number($('seed').value)};
    const extra=[...$('compare-models').querySelectorAll('input:checked')].map(x=>x.value);
    const names=[...new Set([$('model').value,...extra])];
    const result=names.length>1?await post('/api/compare',{...data,model_names:names}):{results:[await post('/api/generate',{...data,model_name:names[0]})]};
    const rejected=result.results.filter(x=>x.status==='rejected');
    for(const record of result.results)if(record.id)state.pending.add(record.id);
    message(rejected.length?rejected.map(x=>`${x.model_id}: ${x.error}`).join('\n'): '推論を開始しました。結果が得られると下に表示します。');
    await refresh();
  }catch(error){message(error.message);}finally{$('generate').disabled=false;}
});
$('diagnose-ardy').addEventListener('click',async()=>{
  $('diagnose-ardy').disabled=true;
  try{const record=await post('/api/diagnose/ardy',{duration:Number($('duration').value),seed:Number($('seed').value)});state.pending.add(record.id);message('学習済み ARDY の無条件CPU推論を開始しました。入力テキストは使用しません。');await refresh();}catch(error){message(error.message);}finally{$('diagnose-ardy').disabled=false;}
});
$('fixture').addEventListener('click',async()=>{
  try{const record=await post('/api/viewer-fixture'+(state.audioId?`?audio_id=${state.audioId}`:''),{});state.selected=new Set([record.id]);await refresh();message('ビューアー検証用の人工サンプルです。学習済みモデルの推論は実行していません。');}catch(error){message(error.message);}
});
$('motion-file').addEventListener('change',async event=>{
  const file=event.target.files[0];if(!file)return;
  const data=new FormData();data.append('file',file);data.append('source_up',$('source-up').value);data.append('source_unit',$('source-unit').value);if(state.audioId)data.append('audio_id',state.audioId);
  try{const record=await api('/api/import',{method:'POST',body:data});state.selected=new Set([record.id]);await refresh();message('元データと変換結果を保存しました。取り込みはモデル推論として数えません。');}catch(error){message(error.message);}
});

async function selectMotions(){
  const records=state.records.filter(x=>state.selected.has(x.id)&&x.artifacts?.normalized_motion_path);
  if(records.map(x=>x.id).join(',')===state.motions.map(x=>x.record.id).join(','))return;
  pause();
  state.motions=await Promise.all(records.map(async record=>({record,data:await api(`/api/experiments/${record.id}/files/${record.artifacts.normalized_motion_path}`)})));
  state.duration=Math.max(0,...state.motions.map(x=>x.data.positions.length/x.data.fps));
  $('timeline').max=state.duration;seek(0);viewer?.load(state.motions);
  $('empty-scene').hidden=state.motions.length>0;
  $('legend').replaceChildren(...state.motions.map((motion,index)=>{const tag=document.createElement('div');tag.className='legend-item';const dot=document.createElement('span');dot.className='legend-dot';dot.style.background='#'+viewer?.actors[index]?.color.toString(16).padStart(6,'0');tag.append(dot,document.createTextNode(labelFor(motion.record)));return tag;}));
  const synthetic=state.motions.some(x=>x.data.metadata?.trained_model_output===false);
  const unconditional=records.some(x=>x.task_type==='unconditional_diagnostic');
  $('motion-notice').hidden=!synthetic&&!unconditional;$('motion-notice').textContent=synthetic?'表示中にビューアー検証用の人工アニメーションが含まれます。学習済みモデルの生成結果ではありません。':'実学習済み ARDY の無条件CPU診断です。テキスト・音声条件付き生成の成功ではありません。';
  if(records[0]){
    $('metadata').textContent=JSON.stringify(records[0],null,2);
    if(records[0].input_audio){$('audio').src=`/api/experiments/${records[0].id}/files/input.wav`;$('sync-note').textContent='音声の時刻に動作を同期';}
  }
}
async function refresh(){
  state.records=await api('/api/experiments');
  for(const id of [...state.pending]){const record=state.records.find(x=>x.id===id);if(record&&['succeeded','failed'].includes(record.status)){state.pending.delete(id);if(record.status==='succeeded')state.selected.add(id);else message(record.error);}}
  drawResults();await selectMotions();
}
function drawResults(){
  if(!state.records.length)return;
  $('results').replaceChildren(...state.records.map(record=>{
    const row=document.createElement('tr'),cell=()=>{const td=document.createElement('td');row.append(td);return td;};
    const toggle=document.createElement('input');toggle.type='checkbox';toggle.checked=state.selected.has(record.id);toggle.disabled=!record.artifacts?.normalized_motion_path;toggle.setAttribute('aria-label',`${labelFor(record)}を表示`);toggle.addEventListener('change',()=>{toggle.checked?state.selected.add(record.id):state.selected.delete(record.id);selectMotions().catch(error=>message(error.message));});cell().append(toggle);
    const model=cell();model.textContent=labelFor(record);const id=document.createElement('code');id.textContent=record.id.slice(0,8);model.append(id);
    const status=cell(),tag=document.createElement('span');tag.className='result-status '+record.status;tag.textContent={succeeded:record.task_type==='import'?'保存済み':'推論成功',failed:'失敗',running:'推論中',queued:'待機',native_only:'未変換'}[record.status]||record.status;status.append(tag);
    if(record.error){const error=document.createElement('p');error.className='result-error';error.textContent=record.error;status.append(error);}
    cell().textContent=record.duration?`${record.duration.toFixed(2)} s / ${record.fps} fps`:'—';
    const skeleton=record.timings?.skeleton_seconds??(record.task_type==='import'?null:record.time_to_first_result);
    cell().textContent=skeleton!=null?`${skeleton.toFixed(2)} s`:'未測定';
    const total=record.timings?.total_seconds;cell().textContent=total!=null?`${total.toFixed(2)} s`:'未測定';
    const files=cell();const labels={original_motion_path:record.model_id==='text_to_vrma'?'元 VRMA':'元データ',normalized_motion_path:'モーション JSON',rendered_video_path:'動画 MP4',motion_spec_path:'元 spec JSON'};
    for(const [key,filename] of Object.entries(record.artifacts||{})){const link=document.createElement('a');link.textContent=labels[key]||filename;link.href=`/api/experiments/${record.id}/files/${filename}`;link.download='';files.append(link);}
    const meta=document.createElement('a');meta.textContent='実験記録';meta.href=`/api/experiments/${record.id}/files/experiment.json`;meta.download='';files.append(meta);
    if(record.artifacts?.normalized_motion_path&&!record.artifacts.rendered_video_path){const render=document.createElement('button');render.textContent='動画を作成';render.addEventListener('click',async()=>{render.disabled=true;render.textContent='書き出し中…';try{await post(`/api/experiments/${record.id}/render`,{});await refresh();}catch(error){message(error.message);render.disabled=false;render.textContent='動画を作成';}});files.append(render);}
    return row;
  }));
}
function seek(value){state.time=Math.min(Math.max(0,value),state.duration);$('timeline').value=state.time;if($('audio').src&&Number.isFinite($('audio').duration))$('audio').currentTime=Math.min(state.time,$('audio').duration);updateTime();viewer?.draw(state.time);}
function updateTime(){$('time').textContent=`${state.time.toFixed(2)} / ${state.duration.toFixed(2)} s`;}
function pause(){state.playing=false;$('audio').pause();}
$('play').addEventListener('click',async()=>{if(!state.duration)return;if(state.time>=state.duration)seek(0);state.playing=true;if($('audio').src){try{await $('audio').play();}catch(error){state.playing=false;message('音声の再生を開始できません: '+error.message);}}});
$('pause').addEventListener('click',pause);$('stop').addEventListener('click',()=>{pause();seek(0);});
$('timeline').addEventListener('input',event=>seek(Number(event.target.value)));
$('speed').addEventListener('change',event=>{state.speed=Number(event.target.value);$('audio').playbackRate=state.speed;});
$('avatar').addEventListener('change',event=>viewer?.setAvatar(event.target.checked));$('reset-camera').addEventListener('click',()=>viewer?.resetCamera());$('refresh').addEventListener('click',()=>refresh().catch(error=>message(error.message)));
$('audio').addEventListener('play',()=>{state.playing=true;});$('audio').addEventListener('pause',()=>{state.playing=false;});$('audio').addEventListener('seeked',()=>{state.time=Math.min($('audio').currentTime,state.duration);});$('audio').addEventListener('ended',pause);
let previous=performance.now();
function tick(now){const delta=(now-previous)/1000;previous=now;
  if(state.playing){state.time=$('audio').src?Math.min($('audio').currentTime,state.duration):Math.min(state.time+delta*state.speed,state.duration);if(state.time>=state.duration)pause();$('timeline').value=state.time;updateTime();}viewer?.draw(state.time);requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
setInterval(async()=>{if(state.pending.size){try{await refresh();}catch(error){message(error.message);}}},1200);
try{const [health,models,items]=await Promise.all([api('/api/health'),api('/api/models'),api('/api/examples/ardy-utterances')]);for(const item of items)utterances[item.id]=item;state.models=models;populateModels();$('readiness').textContent=`アプリ起動済み · 構成済み ${health.ready_models} モデル`;await refresh();}catch(error){$('readiness').textContent='接続エラー';message(error.message);}
