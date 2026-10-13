import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('MOTION_LAB_DATA', ROOT / '.motion-lab')).resolve()
OUTPUTS = Path(os.environ.get('MOTION_LAB_OUTPUTS', ROOT / 'outputs')).resolve()
UI = ROOT / 'app' / 'ui'
