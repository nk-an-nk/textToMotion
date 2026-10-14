const {defineConfig}=require('@playwright/test');
module.exports=defineConfig({testDir:'tests/browser',testMatch:'live.spec.cjs',workers:1,timeout:180000,
  reporter:[['list'],['junit',{outputFile:'reports/live-dialogue-tests.xml'}]],
  use:{baseURL:process.env.MOTION_LAB_LIVE_URL||'http://127.0.0.1:8765',viewport:{width:1440,height:1100},
    launchOptions:{...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--use-angle=swiftshader']}}});
