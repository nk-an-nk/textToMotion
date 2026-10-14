import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const {browserArgs,requireHardware}=createRequire(import.meta.url)('../../scripts/webgl_backend.cjs');
test('GPU requests cannot force the existing SwiftShader path',()=>{
 assert(browserArgs('software').includes('--use-angle=swiftshader'));
 assert(!browserArgs('gpu').includes('--use-angle=swiftshader'));
 assert(browserArgs('gpu').includes('--use-angle=vulkan'));
});
test('software or unknown renderers cannot claim a successful GPU export',()=>{
 for(const name of ['ANGLE (Google, Vulkan (SwiftShader Device))','llvmpipe','Mesa lavapipe','Software Rasterizer'])assert.throws(()=>requireHardware({unmasked_renderer:name}));
 assert.throws(()=>requireHardware({renderer:'WebGL'}));
 assert.doesNotThrow(()=>requireHardware({unmasked_renderer:'ANGLE (NVIDIA, NVIDIA GeForce RTX 4090, Vulkan)'}));
});
