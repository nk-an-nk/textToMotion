import test from 'node:test';
import assert from 'node:assert/strict';
import {GestureScheduler} from '../../app/ui/gesture-scheduler.js';
import {PlaybackClock} from '../../app/ui/audio-clock.js';
import {ConversationManager,transcriptMatches} from '../../app/ui/conversation-manager.js';
import {RealtimeSpeechEngine} from '../../app/ui/realtime-engine.js';
import {ResearchLog} from '../../app/ui/research-log.js';
const plan={turn_id:'t',response_id:'r',gesture_id:'g',motion_prompt:'Wave your right hand.',gesture_type:'explicit_action',earliest_start_ms:0,deadline_ms:2500};
function setup(mode='D'){const calls=[],events=[],sink={play:clip=>calls.push(clip),returnToIdle:()=>calls.push('idle')};const s=new GestureScheduler(sink,{mode,onEvent:(name,data)=>events.push({name,data})});s.begin('t','r');return {s,calls,events};}
for(const delay of [0,1000,3000,10000])test(`D delivery delay ${delay} ms preserves speech and discards late results`,()=>{
  const {s,calls,events}=setup();s.request(plan);s.startSpeech();s.tick(delay);s.result(plan,{name:'recorded-test-clip'});
  assert.equal(s.speech,'SPEAKING');assert.equal(calls.filter(c=>c.name).length,delay<=2500?1:0);
  if(delay>2500)assert.ok(events.some(e=>e.name==='gesture_expired'));
});
test('no generated motion before observed audio, earliest window honored and blend completes',()=>{
  const {s,calls,events}=setup();const p={...plan,earliest_start_ms:800};s.request(p);s.result(p,{name:'clip'});assert.equal(calls.filter(c=>c.name).length,0);
  s.startSpeech();s.tick(799);assert.equal(calls.filter(c=>c.name).length,0);s.tick(800);assert.equal(s.state,'BLENDING');s.tick(1100);assert.equal(s.state,'PLAYING_GENERATED');assert.ok(events.some(e=>e.name==='blend_completed'));
});
test('interrupt and next turn invalidate old completed requests',()=>{
  const {s,calls}=setup();s.request(plan);s.startSpeech();const epoch=s.epoch;s.interrupt();s.begin('t2','r2');s.startSpeech();
  assert.equal(s.result(plan,{name:'old'},epoch),false);assert.equal(calls.filter(c=>c.name).length,0);
});
test('speech end cancels staged gestures and returns to idle',()=>{
  const {s,calls}=setup();s.request(plan);s.startSpeech();s.endSpeech();assert.equal(s.result(plan,{name:'late'}),false);assert.ok(calls.includes('idle'));
});
test('model failure leaves speech running and uses default',()=>{
  const {s}=setup();s.request(plan);s.startSpeech();s.failure('GPU unavailable');assert.equal(s.speech,'SPEAKING');assert.equal(s.state,'SPEAKING_DEFAULT');
});
test('experiment A skips generation, B stages until audio, C ignores deadline while speech continues',()=>{
  assert.equal(setup('A').s.request(plan),false);
  const b=setup('B');b.s.request(plan);b.s.result(plan,{name:'clip'});assert.equal(b.calls.filter(c=>c.name).length,0);b.s.startSpeech();assert.equal(b.calls.filter(c=>c.name).length,1);
  const c=setup('C');c.s.request(plan);c.s.startSpeech();c.s.tick(10000);c.s.result(plan,{name:'late-but-experiment-C'});assert.equal(c.calls.filter(c=>c.name).length,1);
});
test('audio buffer event and transcript arrival do not establish playback; silence drains on audio clock',()=>{
  const audio={currentTime:100,paused:false,readyState:2},clock=new PlaybackClock(audio);clock.arm();assert.equal(clock.sample(0).started,false);
  audio.currentTime=100.3;assert.equal(clock.sample(.1).started,true);audio.currentTime=100.8;assert.equal(clock.sample(.1).elapsedMs,500);
  clock.drained();assert.equal(clock.sample(.1).ended,false);audio.currentTime=101.1;assert.equal(clock.sample(0).ended,true);
});
test('response.done ends generation while playback remains armed; WebRTC interrupt clears unplayed audio',()=>{
  const sent=[],engine=new RealtimeSpeechEngine({muted:false,pause(){}},{onEvent:()=>{}});engine.channel={readyState:'open',send:message=>sent.push(JSON.parse(message))};
  engine.event({type:'response.created',response:{id:'r'}});engine.event({type:'output_audio_buffer.started',response_id:'r'});
  engine.event({type:'response.done',response:{id:'r'}});assert.equal(engine.observer.clock.armed,true);assert.equal(engine.observer.clock.serverDrained,false);
  engine.interrupt();assert.deepEqual(sent.map(e=>e.type),['output_audio_buffer.clear']);
  engine.event({type:'response.created',response:{id:'r2'}});engine.interrupt();assert.deepEqual(sent.slice(-2).map(e=>e.type),['response.cancel','output_audio_buffer.clear']);
});
test('conversation correlates transcript item/content and rejects old response or wrong turn',()=>{
  const manager=new ConversationManager(),t=manager.begin('こんにちは');manager.attachResponse('r',t.id);
  manager.transcript({response_id:'r',item_id:'i',delta:'こん'});manager.transcript({response_id:'r',item_id:'i',transcript:'こんにちは。'},true);assert.equal(t.reply,'こんにちは。');
  manager.interrupt();assert.equal(manager.transcript({response_id:'r',item_id:'i',delta:'late'}),null);
  const next=manager.begin('new');assert.equal(manager.attachResponse('old',t.id),null);assert.equal(next.responseId,null);
  manager.interrupt();assert.equal(next.cancelled,true);assert.equal(manager.attachResponse('delayed-pre-response',next.id),null);
  assert.equal(transcriptMatches('こんにちは。','こんにちは！'),true);assert.equal(transcriptMatches('右手','左手'),false);
});
test('research keeps unknown times null and does not combine clock domains',()=>{
  const log=new ResearchLog({provenance:'offline_validation'});log.record('llm_generation_started',{timeMs:null,clock:'server_monotonic'});log.record('first_audio_playback',{timeMs:2,clock:'client_audio'});
  assert.equal(log.events[0].time_ms,null);assert.ok(log.csv().includes('server_monotonic'));assert.ok(log.csv().includes('client_audio'));assert.equal(log.events[0].provenance,'offline_validation');
});
test('text-first generated gestures wait for transcript verification and discard mismatches',()=>{
  const good=setup();good.s.request({...plan,requires_transcript_match:true});good.s.startSpeech();good.s.result(plan,{name:'clip'});assert.equal(good.calls.filter(c=>c.name).length,0);
  good.s.verifyTranscript(true);assert.equal(good.calls.filter(c=>c.name).length,1);
  const bad=setup();bad.s.request({...plan,requires_transcript_match:true});bad.s.startSpeech();bad.s.result(plan,{name:'clip'});bad.s.verifyTranscript(false);assert.equal(bad.calls.filter(c=>c.name).length,0);assert.equal(bad.s.pending,null);
});
test('disconnect while microphone permission is pending stops late tracks and does not attach them',async()=>{
  const descriptor=Object.getOwnPropertyDescriptor(globalThis,'navigator');let resolve,stopped=false,attached=false;
  const stream={getTracks:()=>[{stop:()=>{stopped=true;}}],getAudioTracks:()=>[{}]};
  Object.defineProperty(globalThis,'navigator',{value:{mediaDevices:{getUserMedia:()=>new Promise(done=>{resolve=done;})}},configurable:true});
  try {
    const engine=new RealtimeSpeechEngine({});engine.pc={};engine.sender={replaceTrack:async()=>{attached=true;}};
    const permission=engine.microphone(true);engine.generation++;engine.pc=null;resolve(stream);
    assert.equal(await permission,false);assert.equal(stopped,true);assert.equal(attached,false);
  }finally {if(descriptor)Object.defineProperty(globalThis,'navigator',descriptor);else delete globalThis.navigator;}
});
