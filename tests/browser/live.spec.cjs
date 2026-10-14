const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
test('live Realtime audio plus newly generated local motion reaches the VRM during the same response',async({page,request})=>{
  test.skip(process.env.MOTION_LAB_LIVE_E2E!=='1','Not run: explicit paid-API opt-in, API key, licensed VRM and local GPU models required.');
  test.setTimeout(180000);
  const avatar=process.env.MOTION_LAB_TEST_VRM;expect(avatar&&fs.existsSync(avatar),'Provide a licensed VRM 1.0 path').toBeTruthy();
  const config=await (await request.get('/api/realtime/config')).json();expect(config.enabled).toBe(true);
  const models=await (await request.get('/api/models')).json();const model=models.find(m=>m.id===(process.env.MOTION_LAB_LIVE_MODEL||'kimodo'));
  expect(model?.can_generate&&model.backend!=='official_demo','Verified local GPU model required').toBe(true);
  let generated=false;
  page.on('response',async response=>{if(/\/api\/motion\/requests\/[0-9a-f]{32}$/.test(new URL(response.url()).pathname)&&response.ok()){
    try{const value=await response.json();if(value.status==='succeeded'&&value.trained_model_output===true)generated=true;}catch{}}
  });
  await page.goto('/conversation');await page.locator('#avatar-file').setInputFiles(avatar);await expect(page.locator('#empty-scene')).toBeHidden();
  await page.getByText('実験・同期設定',{exact:true}).click();await page.locator('#gesture-deadline').fill('30000');
  await page.locator('#motion-model').selectOption(model.id);await page.locator('#motion-override').fill('Raise your right hand and wave for three seconds.');
  await page.locator('#connect').click();await expect(page.locator('#connection-status')).toHaveText('接続済み',{timeout:30000});
  await page.locator('#utterance').fill('研究用の音声対話と動作生成について、日本語で八つの文で説明してください。');await page.locator('#send').click();
  await expect(page.locator('#reply-transcript')).not.toHaveValue('',{timeout:30000});
  await expect(page.locator('#event-log')).toContainText('first_audio_playback',{timeout:30000});
  await expect.poll(()=>generated,{timeout:90000}).toBe(true);
  await expect.poll(()=>page.locator('#gesture-state').textContent(),{timeout:30000}).toMatch(/BLENDING|PLAYING_GENERATED/);
  expect(await page.locator('#reply-audio').evaluate(a=>!a.paused)).toBe(true);
  const downloadPromise=page.waitForEvent('download');await page.locator('#export-events').click();const download=await downloadPromise;
  fs.copyFileSync(await download.path(),'reports/live-dialogue-events.csv');await page.locator('#disconnect').click();
});
