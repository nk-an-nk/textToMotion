"""Read-only integrity, relative-link and privacy checks for the MTG package."""
import argparse
import hashlib
import json
from pathlib import Path
import re

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    folder=args.root/'reports/mtg'
    entries=json.loads((folder/'logs/artifact_manifest.json').read_text(encoding='utf-8'))
    errors=[]
    for item in entries:
        file=folder/item['file']
        if not file.resolve().is_relative_to(folder.resolve()) or not file.is_file():
            errors.append('Missing/invalid artifact: '+item['file']);continue
        content=file.read_bytes()
        if hashlib.sha256(content).hexdigest()!=item['sha256'] or len(content)!=item['bytes']:
            errors.append('SHA-256/size mismatch: '+item['file'])
        if len(content)>=100*1024**2:errors.append('Oversized artifact: '+item['file'])
        if file.suffix.lower()=='.vrm':errors.append('Avatar data must stay local: '+item['file'])
        if file.suffix.lower() in ('.md','.json','.csv','.xml','.txt','.log'):
            text=content.decode('utf-8-sig')
            if re.search(r'(?:hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{32,})',text):errors.append('Credential-like content: '+item['file'])
            if re.search(r'C:[\\/]+Users[\\/]+(?!\$)[A-Za-z0-9_.-]+',text,re.I):errors.append('Local user path: '+item['file'])
        if file.suffix.lower()=='.md':
            for link in re.findall(r'\]\(([^)]+)\)',content.decode('utf-8')):
                if link.startswith(('https://','http://','#')):continue
                path=(file.parent/link.split('#')[0]).resolve()
                if not path.exists():errors.append('Broken relative link: '+item['file']+' -> '+link)
    if errors:raise SystemExit('\n'.join(errors))
    print(f'{len(entries)} artifacts: SHA-256, sizes, relative links and privacy checks passed.')

if __name__=='__main__':main()
