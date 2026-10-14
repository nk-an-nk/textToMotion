import os
from pathlib import Path
import re
import subprocess
ROOT=Path(__file__).resolve().parents[1]
key=os.environ.get('OPENAI_API_KEY')
if not key:
 keyfile=next(p for p in [ROOT/'config/reaitimeapi.txt',ROOT/'config/realtimeapi.txt',ROOT/'configs/realtimeapi.txt'] if p.is_file())
 match=re.search(r'sk-[A-Za-z0-9_\-]+',keyfile.read_text(encoding='utf-8-sig'))
 if not match:raise RuntimeError('API key was not found.')
 key=match.group()
env=os.environ.copy()
env.update(OPENAI_API_KEY=key,OPENAI_REALTIME_ENABLED='1',OPENAI_API_BUDGET_USD='3',
           OPENAI_MAX_CALLS='3',OPENAI_SESSION_SECONDS='180',PYTHONUTF8='1',PYTHONIOENCODING='utf-8',
           MOTION_LAB_DATA=str(ROOT/'.motion-lab'),MOTION_LAB_OUTPUTS=str(ROOT/'.motion-lab/outputs'),
           HF_HOME=str(ROOT/'.motion-lab/hf-cache'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
p=subprocess.Popen([str(ROOT/'.venv/Scripts/python.exe'),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8765'],cwd=ROOT,env=env)
(ROOT/'.motion-lab/realtime-server.pid').write_text(str(p.pid))
try:p.wait()
finally:
 if p.poll() is None:subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
