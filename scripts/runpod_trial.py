#!/usr/bin/env python3
"""One bounded RunPod trial. API credentials stay in the local environment."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.runpod_plan import estimate, inspect


def api(method, path, body=None):
    token = os.environ.get('RUNPOD_API_KEY')
    if not token:
        raise RuntimeError('RUNPOD_API_KEY is unavailable.')
    request = urllib.request.Request(
        'https://rest.runpod.io/v1' + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                 'User-Agent': 'motion-lab-trial/1.0'}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = response.read()
            return json.loads(data) if data else None
    except urllib.error.HTTPError as error:
        if error.code == 404 and method == 'GET':
            return None
        raise RuntimeError(f'RunPod {method} returned HTTP {error.code}.') from None


def save(path, state):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    os.replace(temporary, path)


def owned_pod(state):
    pod = api('GET', '/pods/' + state['pod_id'])
    if pod and (pod.get('id') != state['pod_id'] or pod.get('name') != state['pod_name']):
        raise RuntimeError('Pod ownership check failed. No mutation performed.')
    return pod


def terminate(path, reason):
    state = json.loads(path.read_text())
    if state.get('terminated_at_utc'):
        return state
    pod = owned_pod(state)
    if pod:
        api('DELETE', '/pods/' + state['pod_id'])
    remaining = api('GET', '/pods')
    if any(p.get('id') == state['pod_id'] for p in remaining):
        raise RuntimeError('Pod deletion is not confirmed yet; retry termination.')
    state.update(termination_reason=reason,
                 terminated_at_utc=datetime.now(timezone.utc).isoformat(),
                 deletion_confirmed=True)
    save(path, state)
    return state


def watch(path):
    # A separate local process enforces the deadline even while a remote command hangs.
    # This is not a provider-enforced cap and does not survive replacement of this machine.
    failures = 0
    while True:
        state = json.loads(path.read_text())
        if state.get('terminated_at_utc'):
            return
        if state.get('creation_failed') and not state.get('pod_id'):
            return
        if time.time() >= state['deadline_epoch']:
            if not state.get('pod_id'):
                return
            try:
                terminate(path, 'trial deadline reached')
                print('Trial Pod terminated at deadline.', flush=True)
                return
            except Exception:
                failures += 1
                print(f'Termination retry {failures}; cleanup still required.', flush=True)
        time.sleep(20)


def create(path, plan, public_key, max_minutes):
    if path.exists():
        raise RuntimeError('An existing trial state is preserved. Inspect it before creating another Pod.')
    if not 0 < max_minutes <= plan['max_hours'] * 60:
        raise ValueError('Trial duration exceeds the configured maximum.')
    account = inspect(plan, account=True)
    rows = {r['id']: r for r in account['gpu_candidates']}
    candidates = [gpu for gpu in plan['gpu_type_ids'] if gpu in rows]
    if not candidates:
        raise RuntimeError('No GPU quote fits the authorized budget.')
    reserve = max(rows[gpu]['usd_with_reserve'] for gpu in candidates)
    if account['balance_usd'] is None or account['balance_usd'] < reserve:
        raise RuntimeError('RunPod balance is insufficient; no deposit or Pod creation performed.')
    public_key_text = public_key.read_text().strip()
    if not public_key_text.startswith('ssh-ed25519 ') or '\n' in public_key_text:
        raise ValueError('Use a dedicated single-line Ed25519 public key.')
    name = 'motion-lab-trial-' + uuid.uuid4().hex[:12]
    began = time.time()
    state = {'schema': 'motion-lab/runpod-trial-state-v1', 'pod_name': name,
             'started_at_utc': datetime.now(timezone.utc).isoformat(),
             'started_epoch': began, 'deadline_epoch': began + max_minutes * 60,
             'max_minutes': max_minutes, 'budget_yen': plan['budget_yen'],
             'usd_to_jpy_budget_rate': plan['usd_to_jpy_budget_rate'], 'pod_id': None}
    path.parent.mkdir(parents=True, exist_ok=True)
    save(path, state)
    log = path.with_suffix('.watch.log').open('ab')
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--state', str(path), '--watch'],
                     stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    log.close()
    body = {'name': name, 'cloudType': 'SECURE', 'computeType': 'GPU',
            'gpuTypeIds': candidates, 'gpuTypePriority': 'custom', 'gpuCount': 1,
            'imageName': 'runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404',
            'containerDiskInGb': 40, 'volumeInGb': 40, 'volumeMountPath': '/workspace',
            'ports': ['22/tcp'], 'supportPublicIp': True, 'interruptible': False,
            'minVCPUPerGPU': 4, 'minRAMPerGPU': 16,
            'env': {'PUBLIC_KEY': public_key_text, 'NVIDIA_DRIVER_CAPABILITIES': 'all'}}
    try:
        pod = api('POST', '/pods', body)
    except Exception:
        # Never blindly repeat a POST: reconcile the unique trial name after an ambiguous response.
        matches = [p for p in api('GET', '/pods') if p.get('name') == name]
        if len(matches) != 1:
            state['creation_failed'] = True
            save(path, state)
            raise
        pod = matches[0]
    state.update(pod_id=pod['id'], image=body['imageName'],
                 cost_per_hour_usd=pod.get('costPerHr'), gpu=pod.get('gpu', {}).get('id'),
                 container_disk_gb=40, volume_gb=40)
    save(path, state)
    try:
        state['budget_estimate'] = estimate(plan, float(pod['costPerHr']))
        save(path, state)
    except Exception:
        terminate(path, 'actual quote failed budget validation')
        raise
    return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=Path('.motion-lab/runpod-trial.json'))
    parser.add_argument('--config', type=Path, default=Path('configs/runpod_trial.json'))
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--create', action='store_true')
    action.add_argument('--status', action='store_true')
    action.add_argument('--terminate', action='store_true')
    action.add_argument('--watch', action='store_true')
    parser.add_argument('--public-key', type=Path)
    parser.add_argument('--max-minutes', type=float, default=45)
    args = parser.parse_args()
    try:
        if args.create:
            if args.public_key is None:
                raise ValueError('--public-key is required for creation.')
            result = create(args.state.resolve(), json.loads(args.config.read_text()),
                            args.public_key, args.max_minutes)
        elif args.watch:
            watch(args.state.resolve())
            sys.exit(0)
        elif args.terminate:
            result = terminate(args.state.resolve(), 'trial finished')
        else:
            state = json.loads(args.state.read_text())
            pod = owned_pod(state)
            result = {'trial': state, 'pod_present': bool(pod),
                      'pod': {key: pod.get(key) for key in
                              ['id', 'name', 'desiredStatus', 'costPerHr', 'publicIp', 'portMappings', 'gpu']}
                      if pod else None}
        print(json.dumps(result))
    except Exception as error:
        # HTTP bodies and response environments never enter logs.
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
