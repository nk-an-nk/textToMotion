const {defineConfig}=require('@playwright/test');
const os=require('node:os');
const path=require('node:path');
const fs=require('node:fs');
const temporary=path.join(os.tmpdir(),`motion-lab-browser-${process.pid}-${Date.now()}`);
const appPython=process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python';
const chromium=process.env.CHROMIUM_PATH||(fs.existsSync('/usr/bin/chromium')?'/usr/bin/chromium':null);
module.exports=defineConfig({
  testDir:'tests/browser',timeout:30000,workers:1,
  reporter:[['list'],['junit',{outputFile:'reports/browser-tests.xml'}]],
  use:{baseURL:'http://127.0.0.1:8877',viewport:{width:1440,height:1100},
    launchOptions:{...(chromium?{executablePath:chromium}:{}),args:['--no-sandbox','--use-angle=swiftshader']},
    screenshot:'only-on-failure'},
  webServer:{command:`"${appPython}" -m uvicorn app.main:app --host 127.0.0.1 --port 8877`,
    url:'http://127.0.0.1:8877/api/health',reuseExistingServer:false,timeout:30000,
    env:{MOTION_LAB_DATA:path.join(temporary,'data'),MOTION_LAB_OUTPUTS:path.join(temporary,'outputs'),OPENAI_REALTIME_ENABLED:'0',OPENAI_API_BUDGET_USD:'0'}},
});
