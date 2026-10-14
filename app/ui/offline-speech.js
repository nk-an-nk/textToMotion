import {AudioObserver} from './audio-clock.js';

export function validationWav(seconds=4) {
  const rate=16000,frames=Math.round(rate*seconds),buffer=new ArrayBuffer(44+frames*2),view=new DataView(buffer);
  const str=(at,text)=>[...text].forEach((c,i)=>view.setUint8(at+i,c.charCodeAt(0)));
  str(0,'RIFF');view.setUint32(4,buffer.byteLength-8,true);str(8,'WAVEfmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);
  view.setUint16(22,1,true);view.setUint32(24,rate,true);view.setUint32(28,rate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);
  str(36,'data');view.setUint32(40,frames*2,true);
  for(let i=0;i<frames;i++){const t=i/rate,level=t<.08||t>seconds-.3?0:.12*(.7+.3*Math.sin(t*6));view.setInt16(44+i*2,Math.sin(t*2*Math.PI*220)*32767*level,true);}
  return buffer;
}

export class OfflineSpeechEngine {
  constructor(audio,onEvent){this.audio=audio;this.onEvent=onEvent;this.observer=new AudioObserver(audio);this.url=null;this.generation=0;}
  async play(reply,responseId,wav=null,turnId=null) {
    await this.stop();const generation=++this.generation;
    this.url=URL.createObjectURL(new Blob([wav||validationWav()],{type:'audio/wav'}));this.audio.srcObject=null;this.audio.src=this.url;this.audio.muted=false;
    this.onEvent({type:'response.created',response:{id:responseId,metadata:{turn_id:turnId}},offline:true});
    this.onEvent({type:'response.output_audio_transcript.done',response_id:responseId,item_id:'offline-'+responseId,transcript:reply,offline:true});
    this.onEvent({type:'response.done',response:{id:responseId,status:'completed'},offline:true});
    await this.audio.play();if(generation!==this.generation)return;
    const stream=this.audio.captureStream?.();if(stream)await this.observer.attach(stream);
    this.observer.clock.arm();
    this.audio.onended=()=>{this.observer.clock.ended=true;this.onEvent({type:'offline.audio.ended',response_id:responseId,offline:true});};
  }
  async stop() {this.generation++;this.audio.pause();this.audio.onended=null;this.audio.removeAttribute('src');this.audio.load();if(this.url)URL.revokeObjectURL(this.url);this.url=null;await this.observer.close();}
}
