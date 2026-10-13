#!/usr/bin/env python3
"""Client for the already-running NVIDIA official Kimodo demo, using its Viser UI protocol.

No GPU is provisioned, no account/payment is used, TLS is verified, no remote JavaScript is
executed, and the server's normal session limits are honored. Output is the official Download
button's NPZ payload. This protocol is version-dependent; failures never become sample output.
"""
import argparse
import asyncio
import base64
import json
import os
import re
import ssl
import time
import urllib.request
from pathlib import Path
import msgspec
import websockets

ENDPOINT='wss://nvidia-kimodo.hf.space/'
PROTOCOL='viser-v1.0.16'


async def generate(prompt,duration,seed,output):
    with urllib.request.urlopen('https://huggingface.co/api/spaces/nvidia/Kimodo',timeout=20) as response:
        space_info=json.load(response)
    if space_info.get('runtime',{}).get('stage')!='RUNNING':
        raise RuntimeError('公式Kimodoデモは現在稼働していません。GPU起動・再開処理は行いません。')
    context=ssl.create_default_context(cafile=os.environ.get('SSL_CERT_FILE'))
    components={};timeline={};notifications=[];server_notices=[];download_parts={};download_header=None;download_bytes=None
    changed=asyncio.Event();download_requested=False
    connected=time.monotonic()
    async with asyncio.timeout(240):
        async with websockets.connect(ENDPOINT,ssl=context,subprotocols=[PROTOCOL],
                                      open_timeout=20,max_size=64*1024*1024) as socket:
            async def send(kind,**fields):
                await socket.send(msgspec.msgpack.encode({'type':kind,**fields}))

            async def read():
                nonlocal timeline,download_header,download_bytes
                async for packet in socket:
                    data=msgspec.msgpack.decode(packet)
                    for message in data.get('messages',[data]):
                        kind=message.get('type','')
                        if kind=='GuiUpdateMessage':
                            uuid=message['uuid'];updates=message['updates'];component=components.setdefault(uuid,{'props':{}})
                            component['props'].update(updates)
                            if 'value' in updates:component['value']=updates['value']
                        elif kind.startswith('Gui') and 'uuid' in message:
                            components[message['uuid']]=message
                        elif kind=='TimelineMessage':timeline=message
                        elif 'Notification' in kind:notifications.append(message)
                        if kind=='GuiMarkdownMessage' or kind=='GuiUpdateMessage':
                            content=message.get('props',{}).get('_markdown',message.get('updates',{}).get('_markdown',''))
                            if content and any(word in content.lower() for word in ('queue','session','busy','limit')):
                                server_notices.append(content[:700])
                                del server_notices[:-6]
                        if kind=='RunJavascriptMessage' and download_requested:
                            # Extract only the documented download literal; never execute the JS.
                            source=message.get('source','')
                            match=re.search(r'const b64\s*=\s*("[A-Za-z0-9+/=]+")\s*;',source)
                            if match:download_bytes=base64.b64decode(json.loads(match[1]),validate=True)
                        elif kind=='FileTransferStartDownload' and download_requested:
                            download_header=message
                        elif kind=='FileTransferPart' and download_requested:
                            download_parts[message['part_index']]=message['content']
                        changed.set()

            async def wait(predicate,timeout=60):
                try:
                    async with asyncio.timeout(timeout):
                        while not predicate():
                            if reader.done():
                                reader.result()
                                raise RuntimeError('Official demo closed its connection before the requested operation completed.')
                            changed.clear()
                            if predicate():break
                            await changed.wait()
                except TimeoutError as error:
                    if reader.done():reader.result()
                    notices=json.dumps({'notifications':notifications,'session_notices':server_notices},ensure_ascii=False)[-1600:]
                    raise RuntimeError('Official demo did not acknowledge the requested operation within its limit. Server notifications: '+notices) from error

            def find(label,kind=None):
                matches=[x for x in components.values() if x.get('props',{}).get('label')==label and (kind is None or x.get('type')==kind)]
                if len(matches)!=1:raise RuntimeError(f'Official demo UI changed: {label!r} is not unique.')
                return matches[0]

            async def update(label,value,kind=None):
                component=find(label,kind)
                await send('GuiUpdateMessage',uuid=component['uuid'],updates={'value':value})

            reader=asyncio.create_task(read())
            reader.add_done_callback(lambda task:changed.set())
            try:
                await send('ViewerCameraMessage',wxyz=[1.,0.,0.,0.],position=[3.,2.,4.],fov=.8,near=.01,far=100.,
                           image_height=900,image_width=1400,look_at=[0.,1.,0.],up_direction=[0.,1.,0.])
                # Respect the official queue instead of assuming RUNNING implies a free user slot.
                await wait(lambda: bool(timeline) and any(x.get('props',{}).get('label')=='Generate' for x in components.values()),150)
                starters=[x for x in components.values() if x.get('props',{}).get('label')=='Start Demo']
                if starters:await send('GuiUpdateMessage',uuid=starters[0]['uuid'],updates={'value':True})
                # Initialize the official single-character example before generation: the
                # current demo requires exactly one existing session motion even without constraints.
                await update('Example','01_single_text_prompt','GuiDropdownMessage')
                folder=find('Examples','GuiFolderMessage')
                load_buttons=[x for x in components.values() if x.get('props',{}).get('label')=='Load Example' and x.get('container_uuid')==folder['uuid']]
                if len(load_buttons)!=1:raise RuntimeError('Official example load control changed.')
                notifications.clear()
                await send('GuiUpdateMessage',uuid=load_buttons[0]['uuid'],updates={'value':True})
                await wait(lambda:any('example loaded!' in json.dumps(n).lower() or 'failed to load' in json.dumps(n).lower() for n in notifications))
                if not any('example loaded!' in json.dumps(n).lower() for n in notifications):
                    raise RuntimeError('Official example initialization failed: '+json.dumps(notifications)[-2000:])
                await update('Num Samples',1,'GuiSliderMessage')
                await wait(lambda:find('Num Samples','GuiSliderMessage').get('value')==1)
                await update('Clear All Constraints',True,'GuiButtonMessage')
                await update('Seed',seed,'GuiNumberMessage')
                fps=float(find('Model FPS','GuiNumberMessage')['value'])
                original_prompts=list(timeline.get('prompts',[]))
                frames=int(duration*fps)
                # splittext mode maintains at least one prompt; deleting its last prompt causes
                # it to be recreated. Edit and resize the existing one rather than waiting for zero.
                if original_prompts:
                    primary=original_prompts[0]
                    for entry in original_prompts[1:]:await send('TimelinePromptDeleteMessage',prompt_id=entry['uuid'])
                    await send('TimelinePromptUpdateMessage',prompt_id=primary['uuid'],new_text=prompt)
                    await send('TimelinePromptResizeMessage',prompt_id=primary['uuid'],new_start_frame=0,new_end_frame=frames-1)
                else:
                    await send('TimelinePromptAddMessage',start_frame=0,end_frame=frames-1,text=prompt,color=None)
                await wait(lambda:any(p.get('text')==prompt and p.get('end_frame')==frames-1 for p in timeline.get('prompts',[])))
                # The acknowledgement must describe exactly our single prompt, not a preloaded example.
                if len(timeline['prompts'])!=1:raise RuntimeError('Official session still contains unrelated prompts.')
                notifications.clear()
                started=time.monotonic()
                await update('Generate',True,'GuiButtonMessage')
                def terminal():
                    for notification in notifications:
                        content=json.dumps(notification).lower()
                        if 'have been generated successfully' in content or 'error during generation' in content or 'failed to generate' in content or 'generation failed' in content:return True
                    return False
                await wait(terminal,150)
                evidence=next((n for n in notifications if 'have been generated successfully' in json.dumps(n).lower()),None)
                if evidence is None:raise RuntimeError('Official generation failed: '+json.dumps(notifications)[-1500:])
                generation_elapsed=time.monotonic()-started
                await update('Format','NPZ','GuiDropdownMessage')
                await update('Name','motion-lab-output','GuiTextMessage')
                download_requested=True
                await update('Download',True,'GuiButtonMessage')
                await wait(lambda:download_bytes is not None or (download_header is not None and len(download_parts)==download_header['part_count']),30)
                if download_bytes is None:download_bytes=b''.join(download_parts[i] for i in range(download_header['part_count']))
                if not download_bytes.startswith(b'PK') or len(download_bytes)>32*1024*1024:
                    raise RuntimeError('Official download did not contain a bounded NPZ ZIP payload.')
                path=Path(output);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(download_bytes)
                version=find('Version','GuiDropdownMessage')['value']
                metadata={'model_id':'kimodo','task_type':'instruction','backend':'nvidia_official_online_demo',
                          'endpoint':'https://nvidia-kimodo.hf.space/','space_repository':'nvidia/Kimodo',
                          'space_commit':space_info['sha'],'model_code_git_commit':None,'protocol':PROTOCOL,
                          'text_conditioned':True,'audio_conditioned':False,'trained_model_output':True,
                          'prompt':prompt,'seed':seed,'fps':fps,'duration_requested':duration,'frames_requested':frames,
                          'checkpoint':version,'checkpoint_sha256':None,
                          'device':'remote: '+str(space_info.get('runtime',{}).get('hardware',{}).get('current','unknown'))+' (provider-reported)',
                          'inference_time':generation_elapsed,'time_to_first_result':time.monotonic()-connected,
                          'timing_note':'Generation wall time includes remote text encoding and network notification latency, not isolated GPU kernel time.',
                          'server_success_notification':evidence,'download_bytes':len(download_bytes)}
                path.with_suffix('.metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
                return metadata
            finally:
                reader.cancel()
                await asyncio.gather(reader,return_exceptions=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('prompt')
    parser.add_argument('--duration',type=float,default=3)
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if not .5<=args.duration<=10 or len(args.prompt)>4000 or not args.prompt.strip():parser.error('Use a nonempty prompt and duration between 0.5 and 10 seconds.')
    print(json.dumps(asyncio.run(generate(args.prompt,args.duration,args.seed,args.output)),ensure_ascii=False))
