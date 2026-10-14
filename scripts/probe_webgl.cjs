#!/usr/bin/env node
// Cheap hardware check before allocating time to a full VRM export.
const {chromium}=require('@playwright/test');
const fs=require('node:fs');
const {browserArgs,isSoftwareRenderer,requireHardware}=require('./webgl_backend.cjs');
const args={};
for(let i=2;i<process.argv.length;i++){
 if(!['--renderer','--gpu-backend','--output','--chromium'].includes(process.argv[i])||!process.argv[i+1])throw new Error('node scripts/probe_webgl.cjs [--renderer gpu|software|auto] [--gpu-backend vulkan|gl] [--output report.json]');
 args[process.argv[i].slice(2)]=process.argv[++i];
}
async function main(){
 const mode=args.renderer||'gpu';
 if(args.output&&fs.existsSync(args.output))throw new Error('Existing probe output is preserved.');
 const executablePath=args.chromium||process.env.CHROMIUM_PATH||(fs.existsSync('/usr/bin/chromium')?'/usr/bin/chromium':undefined);
 const browser=await chromium.launch({...(executablePath?{executablePath}:{}),args:browserArgs(mode,args['gpu-backend']||'vulkan')});
 try{
  const page=await browser.newPage();
  const info=await page.evaluate(()=>{
   const canvas=document.createElement('canvas');canvas.width=64;canvas.height=64;
   const gl=canvas.getContext('webgl2');if(!gl)throw new Error('WebGL2 is unavailable.');
   const extension=gl.getExtension('WEBGL_debug_renderer_info');
   gl.clearColor(.2,.6,.4,1);gl.clear(gl.COLOR_BUFFER_BIT);const pixel=new Uint8Array(4);gl.readPixels(0,0,1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel);
   if(Math.abs(pixel[1]-153)>2)throw new Error('WebGL readback failed.');
   return {renderer:gl.getParameter(gl.RENDERER),vendor:gl.getParameter(gl.VENDOR),
    unmasked_renderer:extension?gl.getParameter(extension.UNMASKED_RENDERER_WEBGL):null,
    unmasked_vendor:extension?gl.getParameter(extension.UNMASKED_VENDOR_WEBGL):null,version:gl.getParameter(gl.VERSION),pixel:Array.from(pixel)};
  });
  const report={checked_at_utc:new Date().toISOString(),requested_renderer:mode,gpu_backend:args['gpu-backend']||'vulkan',hardware_webgl:!isSoftwareRenderer(info)&&!!info.unmasked_renderer,...info};
  if(args.output)fs.writeFileSync(args.output,JSON.stringify(report,null,2)+'\n');
  if(mode==='gpu')requireHardware(info);
  console.log(JSON.stringify(report));
 }finally{await browser.close();}
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
