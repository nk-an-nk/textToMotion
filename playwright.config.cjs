const {defineConfig}=require('@playwright/test');
const os=require('node:os');
const path=require('node:path');
const temporary=path.join(os.tmpdir(),`motion-lab-browser-${process.pid}-${Date.now()}`);
module.exports=defineConfig({
  testDir:'tests/browser',timeout:30000,workers:1,
  reporter:[['list'],['junit',{outputFile:'reports/browser-tests.xml'}]],
  use:{baseURL:'http://127.0.0.1:8877',viewport:{width:1440,height:1100},
    launchOptions:{executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox','--use-angle=swiftshader']},
    screenshot:'only-on-failure'},
  webServer:{command:'.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8877',
    url:'http://127.0.0.1:8877/api/health',reuseExistingServer:false,timeout:30000,
    env:{MOTION_LAB_DATA:path.join(temporary,'data'),MOTION_LAB_OUTPUTS:path.join(temporary,'outputs')}},
});
