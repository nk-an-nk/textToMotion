const MODES=['software','gpu','auto'];
function browserArgs(mode='software', backend='vulkan'){
 if(!MODES.includes(mode)||!['vulkan','gl'].includes(backend))throw new Error('Invalid renderer mode or GPU backend.');
 const common=['--no-sandbox','--autoplay-policy=no-user-gesture-required'];
 if(mode==='software')return [...common,'--use-angle=swiftshader'];
 if(mode==='gpu')return [...common,'--ignore-gpu-blocklist','--use-gl=angle','--use-angle='+backend,
  ...(backend==='vulkan'?['--enable-features=Vulkan','--disable-vulkan-surface']:[])];
 return common;
}
function isSoftwareRenderer(info){return /swiftshader|llvmpipe|softpipe|software|basic render|lavapipe/i.test(info.unmasked_renderer||info.renderer||'');}
function requireHardware(info){if(!info.unmasked_renderer||isSoftwareRenderer(info))throw new Error('Hardware WebGL is required; software fallback is refused. Detected: '+(info.unmasked_renderer||info.renderer||'unknown'));}
module.exports={browserArgs,isSoftwareRenderer,requireHardware};
