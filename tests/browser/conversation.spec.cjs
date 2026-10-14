const {test,expect}=require('@playwright/test');
const fs=require('node:fs');const path=require('node:path');
const {vrmFixture,vrmaFixture}=require('./vrm-fixture.cjs');
const realAvatar=process.env.MOTION_LAB_TEST_VRM||'/workspace/shared/motion-lab/upstreams/text_to_vrma/public/models/AvatarSample_VRM1.0.vrm';
async function loadFixture(page){await page.locator('#avatar-file').setInputFiles({name:'test-humanoid.vrm',mimeType:'model/gltf-binary',buffer:vrmFixture()});await expect(page.locator('#empty-scene')).toBeHidden();}
async function recordedFixture(request){const result=await (await request.post('/api/viewer-fixture')).json();return (await request.get(`/api/experiments/${result.id}/files/motion.json`)).json();}

test('offline conversation has actual audio playback, Japanese fixture reply, default motion and unknown model timings',async({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));await page.goto('/conversation');
  await expect(page.locator('#connection-status')).toContainText('オフライン検証');await expect(page.locator('#connect')).toBeDisabled();
  await loadFixture(page);await page.getByText('実験・同期設定',{exact:true}).click();await page.locator('#experiment-mode').selectOption('A');
  await page.locator('#send').click();await expect(page.locator('#reply-transcript')).toHaveValue('こんにちは。今日はどうされましたか？');
  await expect(page.locator('#event-log')).toContainText('first_audio_playback');
  await expect.poll(()=>page.locator('#reply-audio').evaluate(audio=>audio.currentTime)).toBeGreaterThan(.1);
  await expect(page.locator('#provenance')).toContainText('新規AI推論・新規Text-to-Motion生成ではありません');
  await page.locator('#interrupt').click();await expect(page.locator('#gesture-state')).toHaveText('INTERRUPTED');
  expect(await page.locator('#reply-audio').evaluate(audio=>audio.paused)).toBe(true);
  const downloadPromise=page.waitForEvent('download');await page.locator('#export-events').click();
  const download=await downloadPromise;const csv=fs.readFileSync(await download.path(),'utf8');
  expect(csv).toContain('offline_validation');expect(csv).toContain('server_monotonic');expect(csv).toContain('first_audio_playback');
  expect(errors).toEqual([]);
});

test('offline missing motion preserves speech and never sends a new inference request',async({page})=>{
  const inferenceRequests=[];page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/api/motion/requests'))inferenceRequests.push(r.url());});
  await page.goto('/conversation');await loadFixture(page);await page.locator('#utterance').fill('右手を挙げて、手を振ってください');
  await page.locator('#send').click();await expect(page.locator('#dialogue-message')).toContainText('音声会話とデフォルト動作は継続');
  await expect(page.locator('#event-log')).toContainText('motion_failed');
  await expect.poll(()=>page.locator('#reply-audio').evaluate(audio=>audio.currentTime)).toBeGreaterThan(.2);
  expect(await page.locator('#reply-audio').evaluate(audio=>audio.paused)).toBe(false);
  expect(await page.locator('#event-log').textContent()).not.toContain('generated_gesture_started');
  expect(inferenceRequests).toEqual([]);
});

test('recorded-motion switch, delayed result expiry and interruption preserve turn ownership',async({page,request})=>{
  await page.goto('/conversation');await loadFixture(page);
  await page.getByText('実験・同期設定',{exact:true}).click();
  const motion=await recordedFixture(request);await page.locator('#offline-motion').setInputFiles({name:'authored-viewer-fixture.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(motion))});
  await page.locator('#utterance').fill('右手を挙げて、手を振ってください');await page.locator('#delivery-delay').selectOption('1000');
  await page.locator('#send').click();await expect(page.locator('#event-log')).toContainText('generated_gesture_started');
  await expect(page.locator('#motion-status')).toContainText('新規生成なし');
  await page.locator('#interrupt').click();await expect(page.locator('#gesture-state')).toHaveText('INTERRUPTED');
  await page.locator('#gesture-deadline').fill('300');await page.locator('#send').click();
  await expect(page.locator('#event-log')).toContainText('gesture_expired');
  await page.locator('#interrupt').click();await page.locator('#utterance').fill('こんにちは');await page.locator('#send').click();
  await expect(page.locator('#reply-transcript')).toHaveValue('こんにちは。今日はどうされましたか？');
  await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('retargeting two authored humanoid sizes preserves side, finite rotations, root continuity and minimum-swing limits',async({page,request})=>{
  await page.goto('/conversation');const motion=await recordedFixture(request);
  const result=await page.evaluate(async({buffers,motion})=>{
    const THREE=await import('three');const {VRMAvatarMotionSink}=await import('/static/motion-sink.js');
    const output=[];
    for(const encoded of buffers) {
      const binary=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0)),sink=new VRMAvatarMotionSink(new THREE.Scene());
      await sink.loadAvatar(binary.buffer);const clip=sink.prepareMotion(motion);sink.play(clip,{offline:true});
      const samples=[];
      for(const t of [0,.5,1,2]) {
        sink.tick(0,{offlineTime:t});sink.vrm.scene.updateMatrixWorld(true);
        samples.push(['leftHand','rightHand','hips'].map(name=>sink.vrm.humanoid.getNormalizedBoneNode(name).getWorldPosition(new THREE.Vector3()).toArray()));
      }
      output.push({samples,finite:clip.tracks.every(track=>[...track.values].every(Number.isFinite)),scale:clip.userData.scale,method:clip.userData.method});sink.dispose();
    }
    return output;
  },{buffers:[vrmFixture(1).toString('base64'),vrmFixture(1.4).toString('base64')],motion});
  expect(result.every(value=>value.finite)).toBe(true);expect(result[1].scale/result[0].scale).toBeCloseTo(1.4,2);
  const left=motion.joint_names.indexOf('left_hand'),right=motion.joint_names.indexOf('right_hand');
  const sourceSide=Math.sign(motion.positions[0][left][0]-motion.positions[0][right][0]);
  for(const value of result){expect(Math.sign(value.samples[0][0][0]-value.samples[0][1][0])).toBe(sourceSide);expect(value.method).toContain('no inferred axial twist');}
});

test('stopping during experiment B preparation never restarts speech when the delayed motion arrives',async({page,request})=>{
  await page.goto('/conversation');await loadFixture(page);await page.getByText('実験・同期設定',{exact:true}).click();
  const motion=await recordedFixture(request);await page.locator('#offline-motion').setInputFiles({name:'test-motion.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(motion))});
  await page.locator('#experiment-mode').selectOption('B');await page.locator('#delivery-delay').selectOption('1000');await page.locator('#utterance').fill('右手を振ってください');
  await page.locator('#send').click();await expect(page.locator('#motion-status')).toContainText('新規生成なし');await page.locator('#interrupt').click();
  await page.waitForTimeout(1200);expect(await page.locator('#reply-audio').evaluate(audio=>audio.paused)).toBe(true);
  await expect(page.locator('#chat-history')).toContainText('中断しました');expect(await page.locator('#event-log').textContent()).not.toContain('first_audio_playback');
});

test('actual free VRM and existing trained Kimodo/ARDY results load and animate without redistributing the avatar',async({page})=>{
  test.skip(!fs.existsSync(realAvatar),'Set MOTION_LAB_TEST_VRM to a licensed local VRM 1.0 file.');
  const motionPaths=['outputs/9c59514de11744aeb0a97038e73c7e5d/motion.json','outputs/cfc9aaf72a0944cf8449a978df8d5e29/motion.json'];
  test.skip(!motionPaths.every(file=>fs.existsSync(file)),'Previously generated Kimodo and ARDY recordings absent; not an inference test.');
  test.setTimeout(60000);const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/conversation');await page.locator('#avatar-file').setInputFiles(realAvatar);
  await expect(page.locator('#avatar-meta')).toContainText('pixiv VRoid Project');await expect(page.locator('#empty-scene')).toBeHidden();
  await expect(page.locator('#avatar-meta')).toContainText('再配布: 不可');
  for(const file of motionPaths) {
    await page.locator('#offline-motion').setInputFiles(path.resolve(file));
    await page.locator('#utterance').fill('右手を挙げて、手を振ってください');await page.locator('#send').click();
    await expect.poll(()=>page.locator('#gesture-state').textContent()).toMatch(/BLENDING|PLAYING_GENERATED/);
    await page.locator('#interrupt').click();
  }
  await page.locator('#utterance').fill('こんにちは');await page.locator('#send').click();
  await expect(page.locator('#event-log')).toContainText('first_audio_playback');
  await page.screenshot({path:'reports/conversation-vrm-screenshot.png',fullPage:true});
  expect(errors).toEqual([]);
});

test('official VRMA loader and animation clips support sequential playback and keep the root continuous',async({page})=>{
  await page.goto('/');await page.locator('#vrm-file').setInputFiles({name:'fixture.vrm',mimeType:'model/gltf-binary',buffer:vrmFixture()});
  await expect(page.locator('#vrm-info')).toContainText('Authored format fixture');
  await page.locator('#vrma-file').setInputFiles([{name:'one.vrma',mimeType:'model/gltf-binary',buffer:vrmaFixture()},{name:'two.vrma',mimeType:'model/gltf-binary',buffer:vrmaFixture()}]);
  await expect(page.locator('#timeline')).toHaveAttribute('max','2');await page.locator('#play').click();
  await expect.poll(()=>page.locator('#time').textContent()).toMatch(/^1\./);await page.locator('#stop').click();await expect(page.locator('#time')).toHaveText('0.00 / 2.00 s');
  const info=await page.evaluate(async({avatar,animation})=>{
    const THREE=await import('three');const {VRMAvatarMotionSink}=await import('/static/motion-sink.js');const sink=new VRMAvatarMotionSink(new THREE.Scene());
    const buffer=data=>Uint8Array.from(atob(data),c=>c.charCodeAt(0)).buffer;await sink.loadAvatar(buffer(avatar));
    const clip=await sink.prepareVRMA(buffer(animation));sink.playSequence([clip,clip]);sink.tick(0,{offlineTime:.999});
    const a=sink.vrm.humanoid.getNormalizedBoneNode('hips').position.x;sink.tick(0,{offlineTime:1.001});
    const b=sink.vrm.humanoid.getNormalizedBoneNode('hips').position.x;return {delta:Math.abs(b-a),finite:clip.tracks.every(t=>[...t.values].every(Number.isFinite))};
  },{avatar:vrmFixture().toString('base64'),animation:vrmaFixture().toString('base64')});
  expect(info.finite).toBe(true);expect(info.delta).toBeLessThan(.01);
});
