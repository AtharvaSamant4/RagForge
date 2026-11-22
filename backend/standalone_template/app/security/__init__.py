"""A new deployment credential; hosted cookies/keys are never accepted."""
import hashlib
import hmac
import os
import re
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import case
from ..engine.db import get_db
from ..engine.models import RateBucket
from ..engine.config import settings

bearer = HTTPBearer(auto_error=False)


def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db=Depends(get_db)):
    expected = os.environ.get("STANDALONE_API_KEY_HASH", "")
    try:expired=float(os.environ.get('STANDALONE_API_KEY_EXPIRES_AT','0'))
    except ValueError:raise HTTPException(503,'Invalid standalone credential expiry configuration') from None
    if expired and expired<=time.time():raise HTTPException(401,'Standalone API key expired; rotate credentials')
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise HTTPException(503, "Initialize deployment credentials with python scripts/init.py, then restart")
    actual = hashlib.sha256((credentials.credentials if credentials else "").encode()).hexdigest()
    if not credentials or credentials.scheme.lower() != "bearer" or not hmac.compare_digest(actual, expected):
        raise HTTPException(401, "Invalid standalone API key", headers={"WWW-Authenticate": "Bearer"})
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    window = int(time.time() // 60)
    stmt = insert(RateBucket).values(key="standalone", window=window, count=1)
    count = db.scalar(stmt.on_conflict_do_update(index_elements=[RateBucket.key], set_={"window": case((RateBucket.window > window, RateBucket.window), else_=window), "count": case((RateBucket.window >= window, RateBucket.count + 1), else_=1)}).returning(RateBucket.count))
    db.commit()
    if count > settings().rate_limit_per_minute:
        raise HTTPException(429, "Request limit reached", headers={"Retry-After": "60"})
