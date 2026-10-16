#!/usr/bin/env python3
"""Control the owned trial over HTTPS/WSS when SSH egress is unavailable."""
import argparse
import asyncio
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.runpod_trial import owned_pod


class TrialJupyter:
    def __init__(self, state_path, auth_path):
        state = json.loads(state_path.read_text())
        if state.get('terminated_at_utc') or not owned_pod(state):
            raise RuntimeError('The owned trial Pod is not running.')
        self.base = 'https://' + state['pod_id'] + '-8888.proxy.runpod.net'
        self.token = json.loads(auth_path.read_text())['token']

    def request(self, method, route, body=None, raw=False):
        request = urllib.request.Request(self.base + route,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': 'token ' + self.token, 'Content-Type': 'application/json',
                     'User-Agent': 'motion-lab-trial/1.0'}, method=method)
        with urllib.request.urlopen(request, timeout=90) as response:
            content = response.read()
            return content if raw else json.loads(content) if content else None

    def upload(self, source, destination):
        content = base64.b64encode(source.read_bytes()).decode()
        self.request('PUT', '/api/contents/' + urllib.parse.quote(destination, safe='/'),
                     {'type': 'file', 'format': 'base64', 'content': content})
        return {'uploaded': destination, 'bytes': source.stat().st_size}

    def download(self, source, destination):
        if destination.exists():
            raise RuntimeError('Existing local artifact is preserved.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary=destination.with_name(destination.name+'.partial')
        request=urllib.request.Request(self.base+'/files/'+urllib.parse.quote(source,safe='/'),
            headers={'Authorization':'token '+self.token,'User-Agent':'motion-lab-trial/1.0'})
        with urllib.request.urlopen(request,timeout=90) as response, temporary.open('xb') as target:
            while chunk:=response.read(1024*1024):target.write(chunk)
        temporary.replace(destination)
        return {'downloaded': str(destination), 'bytes': destination.stat().st_size}

    async def execute(self, code):
        import websockets
        kernel = self.request('POST', '/api/kernels', {'name': 'python3'})['id']
        session = uuid.uuid4().hex
        msgid = uuid.uuid4().hex
        url = self.base.replace('https:', 'wss:') + '/api/kernels/' + kernel + '/channels?session_id=' + session
        try:
            async with websockets.connect(url, additional_headers={'Authorization': 'token ' + self.token},
                    origin=self.base, open_timeout=20, max_size=4 * 1024 * 1024) as socket:
                await socket.send(json.dumps({'header': {'msg_id': msgid, 'username': 'motion-lab',
                    'session': session, 'date': datetime.now(timezone.utc).isoformat(),
                    'msg_type': 'execute_request', 'version': '5.3'}, 'parent_header': {},
                    'metadata': {}, 'channel': 'shell', 'content': {'code': code, 'silent': False,
                    'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True}}))
                while True:
                    message = json.loads(await asyncio.wait_for(socket.recv(), timeout=60))
                    if message.get('parent_header', {}).get('msg_id') != msgid:
                        continue
                    kind = message.get('msg_type', message.get('header', {}).get('msg_type'))
                    if kind == 'stream':
                        print(message['content']['text'].replace(self.token, '[REDACTED]'), end='', flush=True)
                    if kind == 'execute_reply':
                        if message['content']['status'] != 'ok':
                            raise RuntimeError(message['content'].get('ename', 'Remote execution failed') + ': ' +
                                               message['content'].get('evalue', '').replace(self.token, '[REDACTED]'))
                        return {'remote_execution': 'ok'}
        finally:
            try:
                self.request('DELETE', '/api/kernels/' + kernel)
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=Path('.motion-lab/runpod-trial.json'))
    parser.add_argument('--auth', type=Path, default=Path('.motion-lab/runpod/jupyter_auth.json'))
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--execute', type=Path)
    action.add_argument('--upload', type=Path)
    action.add_argument('--download')
    parser.add_argument('--remote')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        client = TrialJupyter(args.state, args.auth)
        if args.execute:
            result = asyncio.run(client.execute(args.execute.read_text()))
        elif args.upload:
            result = client.upload(args.upload, args.remote or args.upload.name)
        else:
            if not args.output:
                raise ValueError('--output is required for download.')
            result = client.download(args.download, args.output)
        print(json.dumps(result))
    except Exception as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        sys.exit(1)
