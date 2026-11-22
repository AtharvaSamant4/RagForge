"""Importer/reviewer contracts with explicitly synthetic temporary labels only."""
import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from benchmarks.datasets import create,validate_dataset
from benchmarks.evaluate import load_cases


def imported(tmp_path,kind='independent_holdout'):
    source=tmp_path/'sources';source.mkdir()
    quote='The synthetic orbital widget is maintained every seventeen days.'
    (source/'unfamiliar.md').write_text(quote,encoding='utf-8')
    case={'id':'synthetic-temporary-1','question':'How often is the synthetic orbital widget maintained?','expect_refusal':False,'source_refs':[{'document':'unfamiliar.md','quote':quote}],'expected_quotes':[quote]}
    if kind=='pilot_queries':case.update(participant_approved_for_evaluation=True,participant_approval_reference='Synthetic permission test, no real participant')
    labels=tmp_path/'labels.json';labels.write_text(json.dumps([case]),encoding='utf-8')
    output=tmp_path/'dataset'
    create(source,labels,output,kind,'Synthetic temporary QA corpus, not a real independent result',True,True)
    return output


def review(directory,action):
    result=subprocess.run([sys.executable,'benchmarks/review.py',action,'--dataset-dir',str(directory),'--id','synthetic-temporary-1','--reviewer','AUTOMATED SYNTHETIC TEST FIXTURE','--notes','Temporary contract test only; no human approval claimed'],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_import_never_approves_labels_or_changes_default_queue(tmp_path):
    directory=imported(tmp_path)
    metadata=validate_dataset(directory)
    assert metadata['kind']=='independent_holdout'
    assert not (directory/'approved.jsonl').exists()
    assert load_cases('holdout',dataset_dir=directory)[2]==[]
    case=json.loads((directory/'candidates.json').read_text())[0]
    assert case['status']=='candidate_unverified'
    review(directory,'approve')
    cases=load_cases('holdout',dataset_dir=directory)[2]
    assert len(cases)==1 and cases[0]['reviewer']=='AUTOMATED SYNTHETIC TEST FIXTURE'
    review(directory,'reopen')
    assert load_cases('holdout',dataset_dir=directory)[2]==[]


def test_source_changes_and_forged_derived_approval_fail(tmp_path):
    directory=imported(tmp_path)
    review(directory,'approve')
    p=directory/'approved.jsonl';case=json.loads(p.read_text());case['question']='Forged derived label?';p.write_text(json.dumps(case)+'\n')
    with pytest.raises(ValueError,match='audited'):load_cases('holdout',dataset_dir=directory)
    p=directory/'corpus/unfamiliar.md';p.write_text('Changed source')
    with pytest.raises(ValueError,match='checksums'):validate_dataset(directory)


def test_pilot_query_permission_and_split_are_explicit(tmp_path):
    directory=imported(tmp_path,'pilot_queries')
    assert load_cases('pilot-approved',dataset_dir=directory)[2]==[]
    with pytest.raises(ValueError,match='kind'):load_cases('holdout',dataset_dir=directory)
    review(directory,'approve')
    cases=load_cases('pilot-approved',dataset_dir=directory)[2]
    assert len(cases)==1 and cases[0]['participant_approved_for_evaluation']


def test_unsafe_paths_and_missing_permission_rejected(tmp_path):
    source=tmp_path/'sources';source.mkdir();(source/'safe.md').write_text('Synthetic source')
    labels=tmp_path/'labels.json';labels.write_text(json.dumps([{'id':'x','question':'Synthetic question?','expect_refusal':False,'source_refs':[{'document':'../safe.md','quote':'Synthetic source'}]}]))
    with pytest.raises(ValueError):create(source,labels,tmp_path/'invalid','independent_holdout','Synthetic QA',True,True)
    assert not (tmp_path/'invalid').exists()
    with pytest.raises(ValueError,match='permission'):create(source,labels,tmp_path/'invalid2','pilot_queries','Synthetic QA',True)


def test_pdf_source_preparation_is_bounded_and_not_human_approval(tmp_path):
    from benchmarks.normalize_source import normalize
    original=ROOT/'samples/acme-handbook.pdf'
    target=tmp_path/'prepared/acme-handbook.md'
    with pytest.raises(ValueError,match='permission'):normalize(original,target)
    provenance=normalize(original,target,True)
    assert provenance['kind']=='pdf' and '30 day refund period' in target.read_text(encoding='utf-8')
    assert len(provenance['original_sha256'])==64
    with pytest.raises(ValueError,match='new Markdown'):normalize(original,target,True)
