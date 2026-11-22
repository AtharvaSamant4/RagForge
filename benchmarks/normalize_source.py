"""Prepare permitted PDF/DOCX/CSV/TXT/Markdown for exact-quote label review."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.ingestion import validate_file
from app.parse_isolation import execute_parser
from app.config import settings


def normalize(source,output,permitted=False):
    source,output=Path(source),Path(output)
    if not permitted:raise ValueError('Explicit permission to use this source for evaluation is required')
    if source.is_symlink() or not source.is_file():raise ValueError('Choose a regular permitted source')
    if output.suffix!='.md' or output.exists() or output.is_symlink() or output.with_suffix('.source.json').exists():raise ValueError('Choose a new Markdown output and provenance file')
    with source.open('rb') as handle:data=handle.read(settings().max_upload_mb*1024**2+1)
    name,kind=validate_file(source.name,data)
    # Extraction uses the same bounded isolated parser as hosted ingestion.
    parsed=execute_parser(data,kind)
    sections,metadata=parsed['sections'],parsed['metadata']
    normalized='\n\n'.join(text for text,_ in sections).replace('\r\n','\n').removeprefix('\ufeff').encode('utf-8')
    provenance={'normalizer_version':1,'original_name':name,'original_sha256':hashlib.sha256(data).hexdigest(),'normalized_sha256':hashlib.sha256(normalized).hexdigest(),'kind':kind,'parser':metadata.get('parser','bounded text parser')}
    output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with output.open('xb') as handle:handle.write(normalized)
    output.chmod(0o600)
    try:
        with output.with_suffix('.source.json').open('x',encoding='utf-8') as handle:json.dump(provenance,handle,indent=2);handle.write('\n')
        output.with_suffix('.source.json').chmod(0o600)
    except Exception:
        output.unlink();raise
    return provenance


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file',required=True);parser.add_argument('--output',required=True);parser.add_argument('--permitted-data',action='store_true')
    args=parser.parse_args();normalize(args.file,args.output,args.permitted_data)
    print('Prepared bounded source text and original/normalized checksums. Inspect the original and proposed labels before human review; no approval created.')


if __name__=='__main__':main()
