const {test,expect}=require('@playwright/test');
const fs=require('node:fs');

function wavBuffer(seconds=4){
  const sampleRate=16000,frames=sampleRate*seconds,buffer=Buffer.alloc(44+frames*2);
  buffer.write('RIFF',0);buffer.writeUInt32LE(buffer.length-8,4);buffer.write('WAVEfmt ',8);buffer.writeUInt32LE(16,16);
  buffer.writeUInt16LE(1,20);buffer.writeUInt16LE(1,22);buffer.writeUInt32LE(sampleRate,24);buffer.writeUInt32LE(sampleRate*2,28);
  buffer.writeUInt16LE(2,32);buffer.writeUInt16LE(16,34);buffer.write('data',36);buffer.writeUInt32LE(frames*2,40);
  for(let i=0;i<frames;i++)buffer.writeInt16LE(Math.round(Math.sin(i/sampleRate*Math.PI*880)*1000),44+i*2);
  return buffer;
}

test('synthetic provenance, actual 3D camera, playback, seek, speed and downloads',async({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/');await expect(page.locator('#readiness')).toContainText('アプリ起動済み');
  await page.locator('#fixture').click();await expect(page.locator('#results')).toContainText('人工サンプル（推論なし）');
  await expect(page.locator('#motion-notice')).toContainText('学習済みモデルの生成結果ではありません');
  await expect(page.locator('#empty-scene')).toBeHidden();
  const canvas=page.locator('#viewport canvas');await expect(canvas).toBeVisible();
  const initial=await canvas.screenshot();const box=await canvas.boundingBox();
  await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();
  await page.mouse.move(box.x+box.width*.7,box.y+box.height*.6,{steps:10});await page.mouse.up();await page.waitForTimeout(250);
  expect(Buffer.compare(initial,await canvas.screenshot())).not.toBe(0);
  await page.locator('#play').click();await page.waitForTimeout(350);await page.locator('#pause').click();
  const time=()=>page.locator('#time').textContent();expect(parseFloat(await time())).toBeGreaterThan(.15);
  const paused=parseFloat(await time());await page.waitForTimeout(180);expect(parseFloat(await time())).toBeCloseTo(paused,1);
  await page.locator('#timeline').evaluate(el=>{el.value='1.5';el.dispatchEvent(new Event('input',{bubbles:true}));});
  await expect(page.locator('#time')).toHaveText('1.50 / 4.00 s');
  await page.locator('#speed').selectOption('2');await page.locator('#play').click();await page.waitForTimeout(200);await page.locator('#pause').click();
  expect(parseFloat(await time())).toBeGreaterThan(1.75);
  await page.locator('#stop').click();await expect(page.locator('#time')).toHaveText('0.00 / 4.00 s');
  await page.locator('#avatar').check();await expect(page.locator('#avatar')).toBeChecked();
  const downloadPromise=page.waitForEvent('download');await page.getByRole('link',{name:'モーション JSON',exact:true}).first().click();
  const download=await downloadPromise;const data=JSON.parse(fs.readFileSync(await download.path(),'utf8'));
  expect(data.metadata.trained_model_output).toBe(false);expect(data.positions.length).toBe(120);
  await page.screenshot({path:'reports/viewer-screenshot.png',fullPage:true});expect(errors).toEqual([]);
});

test('uploaded WAV is the playback clock and respects seek/rate',async({page})=>{
  await page.goto('/');await page.locator('#fixture').click();await expect(page.locator('#empty-scene')).toBeHidden();
  await page.locator('#sync-wav').setInputFiles({name:'synchronization-test.wav',mimeType:'audio/wav',buffer:wavBuffer()});
  await expect(page.locator('#sync-note')).toContainText('音声の時刻');
  await expect.poll(()=>page.locator('#audio').evaluate(a=>a.readyState)).toBeGreaterThanOrEqual(1);
  await page.locator('#timeline').evaluate(el=>{el.value='1.2';el.dispatchEvent(new Event('input',{bubbles:true}));});
  await expect.poll(()=>page.locator('#audio').evaluate(a=>a.currentTime)).toBeCloseTo(1.2,1);
  await page.locator('#speed').selectOption('1.5');expect(await page.locator('#audio').evaluate(a=>a.playbackRate)).toBe(1.5);
  await page.locator('#play').click();await page.waitForTimeout(400);
  // Read both clocks in one browser turn after a frame; separate protocol calls
  // sample different times while the audio continues at 1.5x speed.
  const delta=await page.evaluate(async()=>{
    await new Promise(resolve=>requestAnimationFrame(resolve));
    return Math.abs(document.getElementById('audio').currentTime-parseFloat(document.getElementById('time').textContent));
  });
  expect(delta).toBeLessThan(.12);
  await page.locator('#pause').click();expect(await page.locator('#audio').evaluate(a=>a.paused)).toBe(true);
});

test('unavailable models report an error instead of generating sample animation',async({page})=>{
  await page.goto('/');await expect(page.locator('#readiness')).toContainText('アプリ起動済み');
  const before=await page.locator('#results tr').count();
  await page.locator('#model').selectOption('ardy');await page.locator('#generate').click();
  await expect(page.locator('#message')).toContainText('未');await expect(page.locator('#empty-scene')).toBeVisible();
  await expect(page.locator('#results tr')).toHaveCount(before);
  await page.locator('#wav').setInputFiles({name:'invalid.wav',mimeType:'audio/wav',buffer:Buffer.from('not wav')});
  await expect(page.locator('#message')).toContainText('有効な PCM WAV');
});

test('motion import retains source label and comparison draws multiple selected results',async({page,request})=>{
  const sample=await (await request.post('/api/viewer-fixture')).json();
  const motion=await (await request.get(`/api/experiments/${sample.id}/files/motion.json`)).json();
  await page.goto('/');await page.locator('#motion-file').setInputFiles({name:'imported.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(motion))});
  await expect(page.locator('#results')).toContainText('取り込みデータ');
  // Select this test's known source instead of assuming the last row is playable.
  const sourceRow=page.locator('#results tr').filter({has:page.locator('code').filter({hasText:sample.id.slice(0,8)})});
  await sourceRow.locator('input[type=checkbox]').check();
  await expect(page.locator('#legend .legend-item')).toHaveCount(2);
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('short and medium ARDY presets retain literal utterances and timings CSV downloads',async({page})=>{
  await page.goto('/');await expect(page.locator('#readiness')).toContainText('アプリ起動済み');
  await page.getByText('ARDY：発話文の試行',{exact:true}).click();
  await page.locator('[data-utterance="hello"]').click();
  await expect(page.locator('#model')).toHaveValue('ardy');
  await expect(page.locator('#text')).toHaveValue('こんにちは');
  await expect(page.locator('#translation')).toHaveValue('Hello.');
  await expect(page.locator('#duration')).toHaveValue('3');
  await page.locator('[data-utterance="idea"]').click();
  await expect(page.locator('#text')).toHaveValue('今日は新しい研究のアイデアを思いつきました。みなさんの意見を聞かせてください。');
  await expect(page.locator('#translation')).toHaveValue("I came up with a new research idea today. I'd like to hear what you think.");
  await expect(page.locator('#duration')).toHaveValue('6');
  await page.locator('#fixture').click();await expect(page.locator('#results')).toContainText('人工サンプル（推論なし）');
  const downloadPromise=page.waitForEvent('download');await page.locator('#timing-csv').click();
  const download=await downloadPromise;const content=fs.readFileSync(await download.path(),'utf8');
  expect(content).toContain('skeleton_seconds');expect(content).toContain('total_seconds');
  expect(content).toContain('synthetic_viewer_fixture');
  await expect(page.getByRole('columnheader',{name:'骨格まで',exact:true})).toBeVisible();
  await expect(page.getByRole('columnheader',{name:'MP4まで（合計）',exact:true})).toBeVisible();
});
