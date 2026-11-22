"""Evaluate one pre-frozen configuration. Never select/tune settings from these cases."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from benchmarks.metrics import canonical_bytes
from benchmarks.review import validate_evidence


def load_cases(split, holdout=None, dataset_dir=None):
    root=ROOT/'benchmarks'
    config_path=root/'frozen-config.json'
    config=json.loads(config_path.read_text(encoding='utf-8-sig'))
    config_hash=hashlib.sha256(canonical_bytes(config_path)).hexdigest()
    fixtures=json.loads((root/'fixtures.json').read_text(encoding='utf-8-sig'))
    candidates=json.loads((root/'candidates.json').read_text(encoding='utf-8-sig'))
    approved_path=root/'approved.jsonl'
    approved=[json.loads(line) for line in approved_path.read_text(encoding='utf-8-sig').splitlines() if line.strip()] if approved_path.exists() else []
    if dataset_dir:
        from benchmarks.datasets import validate_dataset
        metadata=validate_dataset(dataset_dir)
        if (split,metadata['kind']) not in [('holdout','independent_holdout'),('pilot-approved','pilot_queries')]:raise ValueError('Imported dataset kind does not match the requested evaluation split')
        root=Path(dataset_dir).resolve()
        approved_path=root/'approved.jsonl'
        cases=[json.loads(line) for line in approved_path.read_text(encoding='utf-8').splitlines() if line.strip()] if approved_path.exists() else []
        corpus_hash=hashlib.sha256(b''.join(p.name.encode()+canonical_bytes(p) for p in sorted((root/'corpus').glob('*.md')))).hexdigest()
        history=root/'review-history.jsonl'
        latest={r['id']:r for line in history.read_text(encoding='utf-8').splitlines() if line.strip() for r in [json.loads(line)]} if history.exists() else {}
        known={c['question'].strip().casefold() for c in fixtures+candidates+approved}
        for case in cases:
            record=latest.get(case['id'],{})
            if record!=case or case.get('decision')!='approve' or case.get('status')!='human_approved' or not case.get('reviewer') or not case.get('reviewed_at') or case.get('corpus_sha256')!=corpus_hash:raise ValueError('Labels require the latest audited human approval of unchanged sources')
            if split=='holdout' and case['question'].strip().casefold() in known:raise ValueError('Holdout duplicates a development/candidate question')
            if split=='pilot-approved' and (case.get('participant_approved_for_evaluation') is not True or not case.get('participant_approval_reference')):raise ValueError('Pilot query evaluation permission is missing')
    elif split=='development':cases=fixtures
    elif split=='human-approved':
        cases=approved
        if any(c.get('status')!='human_approved' or not c.get('reviewer') or not c.get('reviewed_at') for c in cases):raise ValueError('Missing review provenance')
    elif not holdout:cases=[]
    else:
        data=json.loads(Path(holdout).read_text(encoding='utf-8-sig'))
        if data.get('kind')!='independent_holdout' or data.get('frozen_config_sha256')!=config_hash or data.get('not_used_for_tuning') is not True or not data.get('reviewer') or not data.get('reviewed_at') or not data.get('provenance'):raise ValueError('Independent holdout requires pre-frozen configuration hash and reviewer/provenance/unused-for-tuning attestation')
        cases=data['cases']
        known={c['question'].strip().casefold() for c in fixtures+candidates+approved}
        if any(c['question'].strip().casefold() in known for c in cases):raise ValueError('Holdout duplicates a development/candidate question')
    if len({c['id'] for c in cases})!=len(cases):raise ValueError('Duplicate case identity')
    for case in cases:validate_evidence(case,root)
    return config,config_hash,[{**c,'source_split':c.get('split'),'split':split,'status':c.get('status','independent_holdout'),'category':c.get('category','holdout')} for c in cases]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split',choices=['development','human-approved','holdout','pilot-approved'],required=True)
    parser.add_argument('--dataset-dir',help='Imported unfamiliar/approved pilot dataset with an audited review queue')
    parser.add_argument('--holdout-file');parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.dataset_dir and args.holdout_file:parser.error('Choose either an imported dataset or a legacy holdout file')
    config,config_hash,cases=load_cases(args.split,args.holdout_file,args.dataset_dir)
    from benchmarks.run import run
    run(args.output,False,[config['pipeline']['semantic_min_score']],frozen_config={**config,'sha256':config_hash},cases_override=cases,dataset_kind=args.split,corpus_dir=Path(args.dataset_dir)/'corpus' if args.dataset_dir else None)


if __name__=='__main__':main()
