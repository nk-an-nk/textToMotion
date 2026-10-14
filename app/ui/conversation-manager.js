export class ConversationManager {
  constructor(){this.turn=null;this.history=[];this.responses=new Map();this.items=new Map();this.cancelled=new Set();}
  begin(text='',itemId=null) {
    if(this.turn?.responseId)this.cancelled.add(this.turn.responseId);
    const turn={id:crypto.randomUUID(),userText:text,userItemId:itemId,responseId:null,reply:'',plannedReply:null,cancelled:false,transcripts:new Map()};
    this.turn=turn;this.history.push(turn);if(this.history.length>100)this.history.shift();return turn;
  }
  attachResponse(id,turnId=null) {
    if(turnId&&this.turn?.id!==turnId)return null;
    if(this.turn?.cancelled)return null;
    if(this.cancelled.has(id))return null;
    if(!this.turn)this.begin();this.turn.responseId=id;this.responses.set(id,this.turn);
    if(this.responses.size>200)this.responses.delete(this.responses.keys().next().value);return this.turn;
  }
  active(id) {return !this.turn?.cancelled&&!this.cancelled.has(id)&&this.turn?.responseId===id;}
  transcript(event,done=false) {
    if(!this.active(event.response_id))return null;
    const turn=this.responses.get(event.response_id),key=[event.item_id,event.content_index??0].join(':');
    const previous=turn.transcripts.get(key)||'';
    turn.transcripts.set(key,done?(event.transcript??event.text??previous):previous+(event.delta||''));
    this.items.set(event.item_id,event.response_id);turn.reply=[...turn.transcripts.values()].join('');return turn;
  }
  interrupt(){if(this.turn){this.turn.cancelled=true;if(this.turn.responseId)this.cancelled.add(this.turn.responseId);}}
}

export function transcriptMatches(planned,actual) {
  const normalize=value=>value.normalize('NFKC').replace(/[\s\p{P}\p{S}]/gu,'');
  return normalize(planned)===normalize(actual);
}
