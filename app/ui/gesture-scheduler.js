export const STATES=['IDLE','RESPONSE_PREPARING','SPEAKING_DEFAULT','MOTION_PENDING','MOTION_READY','BLENDING','PLAYING_GENERATED','RETURNING_TO_IDLE','INTERRUPTED','ERROR'];

export class GestureScheduler {
  constructor(sink,{mode='D',blendMs=300,onEvent=()=>{}}={}) {
    this.sink=sink;this.mode=mode;this.blendMs=blendMs;this.onEvent=onEvent;this.epoch=0;this.state='IDLE';this.speech='IDLE';this.pending=null;this.elapsedMs=null;
  }
  event(name,detail=''){this.onEvent(name,{turn_id:this.turnId,response_id:this.responseId,gesture_id:this.pending?.plan.gesture_id,detail});}
  transition(state) {if(this.state!==state){this.state=state;this.event('motion_state',state);}}
  begin(turnId,responseId) {
    this.invalidate('new_turn');this.turnId=turnId;this.responseId=responseId;this.epoch++;
    this.speech='PREPARING';this.elapsedMs=null;this.transition('RESPONSE_PREPARING');return this.epoch;
  }
  request(plan) {
    if(plan.turn_id!==this.turnId||plan.response_id!==this.responseId||this.mode==='A')return false;
    if(!plan.motion_prompt||plan.gesture_type==='none'){this.event('default_only',plan.reason);return false;}
    this.pending={plan,epoch:this.epoch,status:'pending',clip:null,needsVerification:!!plan.requires_transcript_match};this.transition('MOTION_PENDING');return true;
  }
  result(plan,clip,epoch=this.epoch) {
    if(epoch!==this.epoch||!this.pending||plan.gesture_id!==this.pending.plan.gesture_id||plan.turn_id!==this.turnId||plan.response_id!==this.responseId) {
      this.event('stale_result_discarded');return false;
    }
    if(this.speech==='ENDED'||this.speech==='INTERRUPTED'){this.invalidate('speech_ended');return false;}
    this.pending.clip=clip;this.pending.status=this.pending.needsVerification?'awaiting_transcript':'ready';this.transition('MOTION_READY');return this.maybePlay();
  }
  verifyTranscript(valid) {
    if(!this.pending)return;
    if(!valid){this.invalidate('text_first_transcript_mismatch');this.sink.returnToIdle();return;}
    this.pending.needsVerification=false;if(this.pending.status==='awaiting_transcript')this.pending.status='ready';this.maybePlay();
  }
  startSpeech() {if(this.speech==='ENDED'||this.speech==='INTERRUPTED')return;this.speech='SPEAKING';this.elapsedMs=0;this.event('first_audio_playback');if(!this.pending)this.transition('SPEAKING_DEFAULT');this.maybePlay();}
  tick(elapsedMs) {
    if(this.speech!=='SPEAKING')return;this.elapsedMs=elapsedMs;
    if(this.state==='BLENDING'&&elapsedMs-this.playStartMs>=this.blendMs){this.transition('PLAYING_GENERATED');this.event('blend_completed');}
    if(['pending','awaiting_transcript'].includes(this.pending?.status)&&this.mode==='D'&&elapsedMs>this.pending.plan.deadline_ms)this.invalidate('deadline_expired');
    if(this.pending?.status==='ready')this.maybePlay();
  }
  maybePlay() {
    const p=this.pending;if(!p||p.status!=='ready'||this.speech!=='SPEAKING'||this.elapsedMs===null)return false;
    if(this.mode==='D') {
      if(this.elapsedMs>p.plan.deadline_ms){this.invalidate('deadline_expired');return false;}
      if(this.elapsedMs<p.plan.earliest_start_ms)return false;
    }
    this.sink.blendSeconds=this.blendMs/1000;
    this.sink.play(p.clip);p.status='playing';this.playStartMs=this.elapsedMs;this.transition('BLENDING');this.event('generated_gesture_started');return true;
  }
  failure(reason) {if(!this.pending)return;this.pending.status='failed';this.event('motion_failed',reason);this.pending=null;this.transition(this.speech==='SPEAKING'?'SPEAKING_DEFAULT':'ERROR');}
  invalidate(reason) {
    if(this.pending){this.event(reason==='deadline_expired'?'gesture_expired':'gesture_invalidated',reason);this.pending=null;}
    if(this.speech==='SPEAKING'&&!['BLENDING','PLAYING_GENERATED'].includes(this.state))this.transition('SPEAKING_DEFAULT');
  }
  endSpeech() {this.speech='ENDED';this.invalidate('speech_ended');this.epoch++;this.sink.returnToIdle();this.transition('RETURNING_TO_IDLE');this.event('audio_playback_ended');}
  interrupt() {this.speech='INTERRUPTED';this.epoch++;this.invalidate('interrupted');this.sink.returnToIdle({immediate:true});this.transition('INTERRUPTED');this.event('interrupt_completed');}
}
