const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const hash=buffer=>crypto.createHash('sha256').update(buffer).digest('hex');

function validateTimeline(manifest){
 if(manifest.schema!=='motion-lab/segmented-dialogue-v1'||manifest.status!=='generated'||manifest.fps!==30||!manifest.new_motion_inference)throw new Error('A completed, newly generated 30fps manifest is required.');
 if(!Array.isArray(manifest.segments)||!manifest.segments.length||manifest.segments.length>20)throw new Error('Invalid segment count.');
 let cursor=0;const ids=new Set();
 for(const unit of manifest.segments){
  if(!/^[A-Za-z0-9_-]{1,40}$/.test(unit.id)||ids.has(unit.id))throw new Error('Invalid or duplicate segment ID.');ids.add(unit.id);
  if(!Number.isInteger(unit.frame_count)||unit.frame_count<1||unit.start_frame!==cursor||unit.speech_start_frame!==cursor||unit.gesture_start_frame!==cursor||unit.end_frame!==cursor+unit.frame_count)throw new Error('Speech and gesture must begin on the same contiguous frame.');
  if(!(unit.audio_seconds>0)||unit.audio_seconds>unit.frame_count/manifest.fps||unit.frame_count/manifest.fps-unit.audio_seconds>1/manifest.fps+1e-6||!(unit.motion_seconds>0)||!unit.new_gesture_generated)throw new Error('Invalid speech/gesture duration or generation evidence.');
  cursor=unit.end_frame;
 }
 if(cursor!==manifest.frame_count||Math.abs(cursor/manifest.fps-manifest.duration_seconds)>1e-8)throw new Error('Timeline duration differs from its frame count.');
 if(!Number.isFinite(manifest.blend_ms)||manifest.blend_ms<0||manifest.blend_ms>1000)throw new Error('Invalid blend duration.');
 return cursor;
}

function loadAssets(filename){
 const root=path.dirname(path.resolve(filename)),manifest=JSON.parse(fs.readFileSync(filename,'utf8'));validateTimeline(manifest);
 const local=(name)=>{if(typeof name!=='string')throw new Error('Missing artifact path.');const resolved=path.resolve(root,name),relative=path.relative(root,resolved);if(path.isAbsolute(name)||relative==='..'||relative.startsWith('..'+path.sep))throw new Error('Artifact must remain inside the manifest directory.');return resolved;};
 const verified=(name,expected)=>{const bytes=fs.readFileSync(local(name));if(hash(bytes)!==expected)throw new Error('Artifact SHA-256 mismatch: '+name);return bytes;};
 const units=manifest.segments.map(unit=>{
  const motion=JSON.parse(verified(unit.motion,unit.motion_sha256)),audio=verified(unit.audio,unit.audio_sha256);
  const speech=JSON.parse(fs.readFileSync(local(unit.speech_metadata),'utf8')),receipt=JSON.parse(fs.readFileSync(local(unit.motion_receipt),'utf8'));
  if(speech.requested_text!==unit.text||speech.audio_sha256!==unit.audio_sha256||receipt.motion_prompt!==unit.motion_prompt||receipt.original_text!==unit.text||receipt.motion_sha256!==unit.motion_sha256||receipt.model!==manifest.model||motion.metadata?.trained_model_output!==true)throw new Error('Speech or motion provenance differs from its unit.');
  if(Math.abs(motion.positions.length/motion.fps-unit.motion_seconds)>1e-8)throw new Error('Native gesture duration mismatch.');
  return {unit,motion,audio,speech,receipt,audioPath:local(unit.audio),videoPath:path.join(root,'segments',unit.id,'video.mp4')};
 });
 verified(manifest.timeline_audio,manifest.timeline_audio_sha256);
 return {root,manifest,units,timelinePath:local(manifest.timeline_audio)};
}
module.exports={hash,validateTimeline,loadAssets};
