"""Optional offline proof only. No callbacks, collection agent or hosted dependency."""
import json
import time
import uuid
from fastapi import HTTPException
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from .bootstrap import ROOT, MANIFEST

_boot_id = None
_started_at = None
_cited_at = None


def start_runtime():
    global _boot_id, _started_at, _cited_at
    _boot_id, _started_at, _cited_at = str(uuid.uuid4()), time.time(), None


def observe(result):
    global _cited_at
    if result.get('citations') and not result.get('refused') and _cited_at is None:
        _cited_at = time.time()


def evidence():
    path = ROOT / 'config/pilot-evidence.json'
    if not path.is_file():
        raise HTTPException(403, 'This export has no opted-in pilot evidence ticket; ordinary queries work independently')
    config = json.loads(path.read_text(encoding='utf-8'))
    if config['expires_at'] <= time.time():
        raise HTTPException(410, 'Pilot evidence ticket expired; ordinary application use is unaffected')
    if config['template_sha256'] != MANIFEST['template_sha256'] or _started_at is None:
        raise HTTPException(409, 'Runtime evidence configuration mismatch')
    payload = {k: config[k] for k in ('deployment_id', 'export_id', 'template_sha256', 'challenge')}
    payload.update(version=1, boot_id=_boot_id, started_at=_started_at, cited_query_at=_cited_at, database_ready=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    signature = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(config['private_key_hex'])).sign(encoded).hex()
    return {'payload': payload, 'signature': signature}
