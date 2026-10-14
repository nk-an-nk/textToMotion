// Use the official exported ARDY pipeline and VRMA builder without upstream edits.
import {readFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';

const input=JSON.parse(readFileSync(process.argv[2],'utf8'));
const {generateMotionWithArdy}=await import(pathToFileURL(join(input.source,'src/apiServer.js')));
const {buildVRMA}=await import(pathToFileURL(join(input.source,'src/vrmaBuilder.js')));
const spec=await generateMotionWithArdy(input.prompt,{
  ardyUrl:input.engine_url,apiKey:'',duration:input.duration,
  fetchImpl:async(url,options)=>{
    const body=JSON.parse(options.body);
    // The public Node API omits seed; its exported fetch hook lets us pass the
    // requested seed to the official Python engine's supported seed field.
    body.seed=input.seed;
    return fetch(url,{...options,body:JSON.stringify(body),signal:AbortSignal.timeout(900000)});
  }
});
if(spec.planning?.used)throw new Error('Unexpected LLM planning; this comparison selects ARDY only.');
writeFileSync(input.spec_path,JSON.stringify(spec,null,2));
writeFileSync(input.vrma_path,Buffer.from(buildVRMA(spec)));
console.log(`Official text-to-vrma ARDY pipeline exported VRMA: duration=${spec.duration}`);
