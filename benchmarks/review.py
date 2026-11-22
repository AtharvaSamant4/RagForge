"""Human-operated review queue. Corrections are audited and require separate approval."""
import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path
from filelock import FileLock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from benchmarks.metrics import canonical_bytes


def validate_evidence(case, root=ROOT):
    if not isinstance(case.get('question'),str) or not 1<=len(case['question'])<=4000:
        raise ValueError('Question must contain 1-4000 characters')
    if type(case.get('expect_refusal')) is not bool:raise ValueError('expect_refusal must be boolean')
    refs=case.get('source_refs',[])
    if not isinstance(refs,list) or len(refs)>20:raise ValueError('Invalid evidence list')
    for ref in refs:
        name=ref.get('document','');quote=ref.get('quote','')
        if Path(name).name!=name or not name.endswith('.md') or not (root/'corpus'/name).is_file():raise ValueError('Choose an existing corpus Markdown filename')
        if not isinstance(quote,str) or not quote or quote not in canonical_bytes(root/'corpus'/name).decode('utf-8'):raise ValueError('Expected evidence must be an exact source quotation')
    if not case['expect_refusal'] and not refs:raise ValueError('Answerable cases require evidence')
    if any(q not in [r['quote'] for r in refs] for q in case.get('expected_quotes',[])):raise ValueError('Expected quotes must appear in evidence')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['list','show','approve','reject','correct','reopen'])
    parser.add_argument('--id');parser.add_argument('--reviewer');parser.add_argument('--notes')
    parser.add_argument('--correction',help='JSON file with question, source_refs, expected_quotes and/or expect_refusal')
    args=parser.parse_args()
    candidates=json.loads((ROOT/'candidates.json').read_text(encoding='utf-8'))
    history=ROOT/'review-history.jsonl'
    with FileLock(str(ROOT/'.review.lock')):
        records=[json.loads(line) for line in history.read_text(encoding='utf-8').splitlines() if line.strip()] if history.exists() else []
        latest={r['id']:r for r in records}
        if args.action=='list':
            for case in candidates:
                current=latest.get(case['id'],case)
                print(case['id'],'|',current.get('decision','pending'),'|',current['question'])
            return
        candidate=next((c for c in candidates if c['id']==args.id),None)
        if not candidate:parser.error('Choose an existing candidate with --id')
        current={**candidate,**latest.get(args.id,{})}
        print(json.dumps(current,indent=2))
        print('PROPOSED ANSWER:', 'Refuse: insufficient supported evidence.' if current['expect_refusal'] else '\n'.join(current.get('expected_quotes',[])))
        for ref in current['source_refs']:
            print('\nSOURCE: '+ref['document']+'\n'+canonical_bytes(ROOT/'corpus'/ref['document']).decode('utf-8'))
        if args.action=='show':return
        if not args.reviewer or not args.notes:parser.error('Human review requires --reviewer and --notes after inspecting the complete sources')
        if current.get('decision') in ('approve','reject') and args.action!='reopen':parser.error('Candidate already reviewed; reopen it to preserve the audit trail before correcting/reviewing')
        if args.action=='correct':
            if not args.correction:parser.error('--correction JSON file required')
            correction=json.loads(Path(args.correction).read_text(encoding='utf-8'))
            if not correction or set(correction)-{'question','source_refs','expected_quotes','expect_refusal'}:parser.error('Unsupported correction fields')
            current.update(correction)
        try:validate_evidence(current)
        except ValueError as exc:parser.error(str(exc))
        record={**current,'reviewer':args.reviewer,'review_notes':args.notes,'reviewed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'decision':args.action,'status':'human_approved' if args.action=='approve' else 'candidate_unverified','split':'human_approved' if args.action=='approve' else 'candidate','source_sha256':{ref['document']:hashlib.sha256(canonical_bytes(ROOT/'corpus'/ref['document'])).hexdigest() for ref in current['source_refs']}}
        record['corpus_sha256']=hashlib.sha256(b''.join(p.name.encode()+canonical_bytes(p) for p in sorted((ROOT/'corpus').glob('*.md')))).hexdigest()
        with history.open('a',encoding='utf-8') as out:out.write(json.dumps(record)+'\n')
        latest[record['id']]=record
        # Derived approved split is rebuilt; history is append-only, including reopen/corrections.
        target=ROOT/'approved.jsonl';temporary=ROOT/'approved.jsonl.tmp'
        temporary.write_text(''.join(json.dumps(r)+'\n' for r in latest.values() if r['decision']=='approve'),encoding='utf-8');temporary.replace(target)
        print('Recorded '+args.action+' by '+args.reviewer)


if __name__=='__main__':main()
