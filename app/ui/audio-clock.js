/** Audio-element clock plus a local analyser. This does not measure sound at the DAC. */
export class PlaybackClock {
  constructor(audio,{threshold=.008,drainSilenceMs=250}={}) {this.audio=audio;this.threshold=threshold;this.drainSilenceMs=drainSilenceMs;this.reset();}
  reset() {this.startTime=null;this.lastSignalTime=null;this.serverDrained=false;this.armed=false;this.level=0;this.ended=false;}
  arm(){this.reset();this.armed=true;}
  drained(){this.serverDrained=true;}
  sample(level) {
    this.level=level;const time=this.audio.currentTime;
    const playable=!this.audio.paused&&this.audio.readyState>=2&&Number.isFinite(time);
    if(this.armed&&playable&&level>this.threshold) {
      if(this.startTime===null)this.startTime=time;
      this.lastSignalTime=time;
    }
    if(this.serverDrained&&this.startTime!==null&&playable&&level<=this.threshold&&
        (time-(this.lastSignalTime??time))*1000>=this.drainSilenceMs)this.ended=true;
    return {started:this.startTime!==null,elapsedMs:this.startTime===null?null:Math.max(0,(time-this.startTime)*1000),
      ended:this.ended,lip:level,precision:'local_audio_timeline_with_signal_onset; output-device latency unknown'};
  }
}

export class AudioObserver {
  constructor(audio){this.audio=audio;this.clock=new PlaybackClock(audio);}
  async activate(){if(!this.context||this.context.state==='closed')this.context=new AudioContext();await this.context.resume();}
  async attach(stream) {
    this.source?.disconnect();this.mute?.disconnect();this.clock.reset();await this.activate();
    this.source=this.context.createMediaStreamSource(stream);this.analyser=this.context.createAnalyser();this.analyser.fftSize=512;
    this.source.connect(this.analyser);this.mute=this.context.createGain();this.mute.gain.value=0;
    this.analyser.connect(this.mute);this.mute.connect(this.context.destination); // Silent tap; the audio element owns speaker output.
    this.values=new Float32Array(this.analyser.fftSize);
  }
  sample() {
    let rms=0;if(this.analyser){this.analyser.getFloatTimeDomainData(this.values);rms=Math.sqrt(this.values.reduce((sum,v)=>sum+v*v,0)/this.values.length);}
    return this.clock.sample(rms);
  }
  async close(){this.source?.disconnect();if(this.context&&this.context.state!=='closed')await this.context.close();this.analyser=null;this.clock.reset();}
}
