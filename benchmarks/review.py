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
    parser.add_argument('action',choices=['list','show','next','approve','reject','correct','reopen'])
    parser.add_argument('--id');parser.add_argument('--reviewer');parser.add_argument('--notes')
    parser.add_argument('--correction',help='JSON file with question, source_refs, expected_quotes and/or expect_refusal')
    parser.add_argument('--dataset-dir', help='Separate imported unfamiliar/pilot dataset; defaults to the 120-candidate queue')
    parser.add_argument('--pending', action='store_true', help='List only unreviewed/reopened/corrected labels')
    parser.add_argument('--limit', type=int, default=1000)
    args=parser.parse_args()
    root=Path(args.dataset_dir).resolve() if args.dataset_dir else ROOT
    dataset_metadata={}
    if args.dataset_dir:
        from benchmarks.datasets import validate_dataset
        dataset_metadata=validate_dataset(root)
    if not 1 <= args.limit <= 1000: parser.error('--limit must be 1-1000')
    candidates=json.loads((root/'candidates.json').read_text(encoding='utf-8'))
    history=root/'review-history.jsonl'
    with FileLock(str(root/'.review.lock')):
        records=[json.loads(line) for line in history.read_text(encoding='utf-8').splitlines() if line.strip()] if history.exists() else []
        latest={r['id']:r for r in records}
        if args.action=='list':
            shown=0
            for case in candidates:
                current=latest.get(case['id'],case)
                if args.pending and current.get('decision') in ('approve','reject'): continue
                if shown >= args.limit: break
                shown+=1
                print(case['id'],'|',current.get('decision','pending'),'|',current['question'])
            return
        candidate=next((c for c in candidates if latest.get(c['id'],{}).get('decision') not in ('approve','reject')),None) if args.action=='next' else next((c for c in candidates if c['id']==args.id),None)
        if not candidate and args.action=='next':
            print('No pending candidates remain.');return
        if not candidate:parser.error('Choose an existing candidate with --id')
        current={**candidate,**latest.get(candidate['id'],{})}
        print(json.dumps(current,indent=2))
        print('PROPOSED ANSWER:', 'Refuse: insufficient supported evidence.' if current['expect_refusal'] else '\n'.join(current.get('expected_quotes',[])))
        for ref in current['source_refs']:
            if args.dataset_dir:
                original=dataset_metadata.get('normalization_provenance',{}).get(ref['document'])
                if original:print('ORIGINAL SOURCE REFERENCE:',json.dumps(original),'Inspect the retained permitted original file as well as normalized text.')
            print('\nSOURCE: '+ref['document']+'\n'+canonical_bytes(root/'corpus'/ref['document']).decode('utf-8'))
        if args.action in ('show','next'):return
        if not args.reviewer or not args.notes:parser.error('Human review requires --reviewer and --notes after inspecting the complete sources')
        if current.get('decision') in ('approve','reject') and args.action!='reopen':parser.error('Candidate already reviewed; reopen it to preserve the audit trail before correcting/reviewing')
        if args.action=='correct':
            if not args.correction:parser.error('--correction JSON file required')
            correction=json.loads(Path(args.correction).read_text(encoding='utf-8'))
            if not correction or set(correction)-{'question','source_refs','expected_quotes','expect_refusal'}:parser.error('Unsupported correction fields')
            current.update(correction)
        try:validate_evidence(current,root)
        except ValueError as exc:parser.error(str(exc))
        record={**current,'reviewer':args.reviewer,'review_notes':args.notes,'reviewed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'decision':args.action,'status':'human_approved' if args.action=='approve' else 'candidate_unverified','split':'human_approved' if args.action=='approve' else 'candidate','source_sha256':{ref['document']:hashlib.sha256(canonical_bytes(root/'corpus'/ref['document'])).hexdigest() for ref in current['source_refs']}}
        record['corpus_sha256']=hashlib.sha256(b''.join(p.name.encode()+canonical_bytes(p) for p in sorted((root/'corpus').glob('*.md')))).hexdigest()
        with history.open('a',encoding='utf-8') as out:out.write(json.dumps(record)+'\n')
        latest[record['id']]=record
        # Derived approved split is rebuilt; history is append-only, including reopen/corrections.
        target=root/'approved.jsonl';temporary=root/'approved.jsonl.tmp'
        temporary.write_text(''.join(json.dumps(r)+'\n' for r in latest.values() if r['decision']=='approve'),encoding='utf-8');temporary.replace(target)
        print('Recorded '+args.action+' by '+args.reviewer)


if __name__=='__main__':main()
