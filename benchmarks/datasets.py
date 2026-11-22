"""Import permitted unfamiliar Markdown/TXT labels without marking them reviewed."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.metrics import canonical_bytes
from benchmarks.review import validate_evidence


def frozen_hash():
    return hashlib.sha256(canonical_bytes(ROOT / 'benchmarks/frozen-config.json')).hexdigest()


def validate_dataset(directory):
    directory = Path(directory).resolve()
    metadata = json.loads((directory / 'dataset.json').read_text(encoding='utf-8'))
    if metadata.get('schema_version') != 1 or metadata.get('kind') not in ('independent_holdout', 'pilot_queries') or metadata.get('frozen_config_sha256') != frozen_hash() or not metadata.get('provenance') or metadata.get('permitted_data') is not True:
        raise ValueError('Dataset requires permitted provenance and the unchanged frozen configuration')
    if metadata['kind'] == 'independent_holdout' and metadata.get('not_used_for_tuning') is not True:
        raise ValueError('Holdout must be attested unused for tuning')
    corpus = directory / 'corpus'
    if corpus.is_symlink() or not corpus.is_dir():
        raise ValueError('Unsafe dataset corpus')
    actual = {}
    for path in corpus.iterdir():
        if path.is_symlink() or not path.is_file() or not re.fullmatch(r'[A-Za-z0-9_.-]+\.md', path.name) or path.stat().st_size > 20 * 1024 ** 2:
            raise ValueError('Corpus must contain only bounded regular Markdown files')
        actual[path.name] = hashlib.sha256(canonical_bytes(path)).hexdigest()
    if actual != metadata.get('source_sha256'):
        raise ValueError('Dataset source checksums changed; create/review a new version')
    return metadata


def create(source_dir, labels, output, kind, provenance, permitted, unused=False):
    if not permitted or kind == 'independent_holdout' and not unused:
        raise ValueError('Explicit permitted-data and unused-for-tuning attestations are required')
    source_dir, output = Path(source_dir).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(source_dir):
        raise ValueError('Choose a new dataset directory outside the source directory')
    if Path(source_dir).is_symlink():
        raise ValueError('Unsafe source directory')
    cases = json.loads(Path(labels).read_text(encoding='utf-8-sig'))
    if not isinstance(cases, list) or not 1 <= len(cases) <= 1000 or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Choose 1-1000 uniquely identified proposed cases')
    sources = {}; normalization = {}
    for path in source_dir.iterdir():
        if path.suffix.lower() not in ('.md', '.txt'):
            continue
        name = path.stem + '.md'
        if path.is_symlink() or not path.is_file() or not re.fullmatch(r'[A-Za-z0-9_.-]+\.md', name) or name in sources or path.stat().st_size > 20 * 1024 ** 2:
            raise ValueError('Use unique safe bounded regular Markdown/TXT sources')
        data = canonical_bytes(path); data.decode('utf-8')
        sources[name] = data
        sidecar=path.with_suffix('.source.json')
        if sidecar.exists():
            if sidecar.is_symlink() or sidecar.stat().st_size>65536:raise ValueError('Unsafe source provenance')
            record=json.loads(sidecar.read_text(encoding='utf-8'))
            if record.get('normalizer_version')!=1 or record.get('normalized_sha256')!=hashlib.sha256(data).hexdigest():raise ValueError('Normalized source provenance mismatch')
            normalization[name]={key:record[key] for key in ('original_name','original_sha256','normalized_sha256','kind','parser')}
    if not 1 <= len(sources) <= 50 or sum(map(len, sources.values())) > 50 * 1024 ** 2:
        raise ValueError('Choose 1-50 sources totaling at most 50 MiB')
    if kind == 'independent_holdout':
        known_sources = {hashlib.sha256(canonical_bytes(p)).hexdigest() for p in (ROOT / 'benchmarks/corpus').glob('*.md')}
        known_questions = {c['question'].strip().casefold() for filename in ('fixtures.json', 'candidates.json') for c in json.loads((ROOT / 'benchmarks' / filename).read_text(encoding='utf-8-sig'))}
        if any(hashlib.sha256(data).hexdigest() in known_sources for data in sources.values()) or any(c['question'].strip().casefold() in known_questions for c in cases):
            raise ValueError('Independent data must not reuse development documents/questions')
    if kind == 'pilot_queries' and any(c.get('participant_approved_for_evaluation') is not True or not c.get('participant_approval_reference') for c in cases):
        raise ValueError('Every actual pilot query needs explicit participant evaluation permission provenance')
    output.mkdir(parents=True, mode=0o700)
    try:
        (output / 'corpus').mkdir(mode=0o700)
        for name, data in sources.items():
            path = output / 'corpus' / name; path.write_bytes(data); path.chmod(0o600)
        for case in cases:
            validate_evidence(case, output)
        metadata = {'schema_version': 1, 'kind': kind, 'provenance': provenance, 'permitted_data': True, 'not_used_for_tuning': bool(unused), 'frozen_config_sha256': frozen_hash(), 'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()},'normalization_provenance':normalization}
        candidates = [{**case, 'status': 'candidate_unverified', 'split': kind} for case in cases]
        for name, value in [('dataset.json', metadata), ('candidates.json', candidates)]:
            path = output / name; path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8'); path.chmod(0o600)
    except Exception:
        # This is the newly created directory only; never touch the input corpus.
        if not output.is_symlink() and output.resolve() == output:
            shutil.rmtree(output)
        raise
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', required=True); parser.add_argument('--labels', required=True)
    parser.add_argument('--output', required=True); parser.add_argument('--kind', choices=['independent_holdout', 'pilot_queries'], required=True)
    parser.add_argument('--provenance', required=True); parser.add_argument('--permitted-data', action='store_true')
    parser.add_argument('--not-used-for-tuning', action='store_true')
    args = parser.parse_args()
    create(args.source_dir, args.labels, args.output, args.kind, args.provenance, args.permitted_data, args.not_used_for_tuning)
    print('Imported proposed labels only. Human review is still required; no score or approval was created.')


if __name__ == '__main__':
    main()
