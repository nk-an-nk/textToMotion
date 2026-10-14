export class ResearchLog {
  constructor({provenance='live',mode='D'}={}){this.provenance=provenance;this.mode=mode;this.events=[];}
  record(name,{timeMs=performance.now(),clock='client_performance',estimated=false,...details}={}) {
    this.events.push({name,clock_domain:clock,time_ms:timeMs,estimated,experiment_mode:this.mode,provenance:this.provenance,
      turn_id:details.turn_id||'',response_id:details.response_id||'',gesture_id:details.gesture_id||'',detail:String(details.detail||'').slice(0,2000)});
    if(this.events.length>2000)this.events.shift();
  }
  csv() {
    const columns=['name','clock_domain','time_ms','estimated','experiment_mode','provenance','turn_id','response_id','gesture_id','detail'];
    const escape=value=>{let text=value===null||value===undefined?'':String(value);if(/^[=+\-@\t\r\n]/.test(text))text="'"+text;return '"'+text.replaceAll('"','""')+'"';};
    return '\ufeff'+[columns,...this.events.map(row=>columns.map(key=>row[key]))].map(row=>row.map(escape).join(',')).join('\r\n');
  }
  download() {const url=URL.createObjectURL(new Blob([this.csv()],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='dialogue-events.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  async save() {
    const response=await fetch('/api/research/sessions',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({save_locally:true,experiment_mode:this.mode,provenance:this.provenance,events:this.events})});
    if(!response.ok)throw new Error('研究記録のローカル保存に失敗しました。');return response.json();
  }
}
