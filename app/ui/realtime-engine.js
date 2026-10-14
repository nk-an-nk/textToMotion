import {AudioObserver} from './audio-clock.js';

export class RealtimeSpeechEngine {
  constructor(audio,{onEvent=()=>{},onState=()=>{},onError=()=>{}}={}) {
    this.audio=audio;this.onEvent=onEvent;this.onState=onState;this.onError=onError;this.observer=new AudioObserver(audio);this.activeResponse=null;this.generationActive=false;this.generation=0;
  }
  async connect(config) {
    await this.disconnect();const generation=++this.generation;this.onState('接続中');
    try {
      await this.observer.activate();
      const pc=this.pc=new RTCPeerConnection();this.sender=pc.addTransceiver('audio',{direction:'sendrecv'}).sender;
      const channel=this.channel=pc.createDataChannel('oai-events');
      channel.onmessage=message=>{try{this.event(JSON.parse(message.data));}catch(error){this.onError(error.message);}};
      channel.onerror=()=>this.onError('Realtime DataChannelで通信エラーが発生しました。');
      channel.onopen=()=>this.onState('接続済み');channel.onclose=()=>this.onState('切断');
      pc.ontrack=async event=>{
        if(generation!==this.generation)return;
        const stream=event.streams[0]||new MediaStream([event.track]);this.audio.srcObject=stream;
        try {await this.observer.attach(stream);if(generation===this.generation)await this.audio.play();}catch(error){if(generation===this.generation)this.onError('音声再生: '+error.message);}
      };
      pc.onconnectionstatechange=()=>{if(['failed','disconnected','closed'].includes(pc.connectionState))this.onError('WebRTC接続が切れました。再接続してください。');};
      await pc.setLocalDescription(await pc.createOffer());
      const response=await fetch('/api/realtime/calls',{method:'POST',headers:{'Content-Type':'application/sdp'},body:pc.localDescription.sdp});
      if(!response.ok){const error=await response.json();throw new Error(error.detail||'Realtime接続に失敗しました。');}
      if(generation!==this.generation)return;
      await pc.setRemoteDescription({type:'answer',sdp:await response.text()});
      this.timer=setTimeout(()=>{this.onError('設定したセッション時間に達したため切断します。');this.disconnect();},config.session_seconds*1000);
    } catch(error) {await this.disconnect();this.onError(error.message);throw error;}
  }
  event(event) {
    if(event.type==='response.created'){this.activeResponse=event.response.id;this.generationActive=true;}
    if(event.type==='response.done'&&event.response.id===this.activeResponse)this.generationActive=false;
    if(event.type==='output_audio_buffer.started'&&event.response_id===this.activeResponse){this.audio.muted=false;this.observer.clock.arm();}
    if(event.type==='output_audio_buffer.stopped'&&event.response_id===this.activeResponse)this.observer.clock.drained();
    if(event.type==='input_audio_buffer.speech_started')this.interrupt();
    if(event.type==='error')this.onError(event.error?.message||'Realtime APIエラー');
    this.onEvent(event);
  }
  send(event) {if(this.channel?.readyState!=='open')throw new Error('Realtime APIに接続してください。');this.channel.send(JSON.stringify(event));}
  addText(text) {this.send({type:'conversation.item.create',item:{type:'message',role:'user',content:[{type:'input_text',text}]}});}
  respond({plannedText=null,turnId}={}) {
    const response={output_modalities:['audio'],metadata:{turn_id:turnId}};
    if(plannedText)response.instructions='次の日本語の回答候補を音声で伝えてください。内容と表現を保ってください: '+plannedText;
    this.send({type:'response.create',response});
  }
  async microphone(enabled) {
    if(!this.pc)throw new Error('先にRealtime APIへ接続してください。');
    if(enabled) {
      const generation=this.generation,sender=this.sender;
      const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});
      if(!this.pc||generation!==this.generation){stream.getTracks().forEach(track=>track.stop());return false;}
      try {await sender.replaceTrack(stream.getAudioTracks()[0]);this.mic=stream;return true;}
      catch(error){stream.getTracks().forEach(track=>track.stop());throw error;}
    } else {await this.sender.replaceTrack(null);this.mic?.getTracks().forEach(track=>track.stop());this.mic=null;return false;}
  }
  interrupt() {
    this.audio.muted=true;this.observer.clock.reset();
    if(this.channel?.readyState==='open') {
      if(this.generationActive)this.send({type:'response.cancel',response_id:this.activeResponse});
      this.send({type:'output_audio_buffer.clear'}); // WebRTC server owns truncation of unplayed audio.
    }
    this.generationActive=false;
  }
  async disconnect() {
    this.generation++;clearTimeout(this.timer);this.mic?.getTracks().forEach(track=>track.stop());this.mic=null;
    if(this.pc){this.interrupt();this.pc.onconnectionstatechange=null;this.channel?.close();this.pc.close();}
    this.pc=null;this.channel=null;this.audio.pause();this.audio.srcObject=null;await this.observer.close();this.onState('未接続');
  }
}
