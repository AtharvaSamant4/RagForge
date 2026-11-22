import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import APIKey, LoginSession, Project, RateBucket, User


def digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f"pbkdf2:600000:{salt}:{value}"


def password_valid(password: str, encoded: str) -> bool:
    _, iterations, salt, expected = encoded.split(":")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    return hmac.compare_digest(actual, expected)


def rate_limit(db: Session, identity: str, limit: int | None = None):
    # Atomic upsert; a delayed old-window request cannot reopen a newer bucket.
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    window = int(time.time() // 60)
    key = digest(identity)
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    stmt = insert(RateBucket).values(key=key, window=window, count=1)
    from sqlalchemy import case
    stmt = stmt.on_conflict_do_update(index_elements=[RateBucket.key], set_={"window": case((RateBucket.window > window, RateBucket.window), else_=window), "count": case((RateBucket.window >= window, RateBucket.count + 1), else_=1)}).returning(RateBucket.count)
    count = db.scalar(stmt)
    db.execute(delete(RateBucket).where(RateBucket.window < window - 120))
    db.commit()
    if count > (limit if limit is not None else settings().rate_limit_per_minute):
        raise HTTPException(429, "Request limit reached. Try again in a minute.", headers={"Retry-After": "60"})


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    raw = request.cookies.get("ragforge_session", "")
    session = db.get(LoginSession, digest(raw)) if raw else None
    if not session or session.expires_at < time.time():
        raise HTTPException(401, "Sign in to continue")
    user = db.get(User, session.user_id)
    if not user or user.disabled:
        raise HTTPException(401, "Sign in to continue")
    request.state.pilot_user_id = user.id
    return user


@dataclass
class Access:
    project: Project
    principal: str
    is_owner: bool


def access(project_id: str, request: Request, db: Session, scope: str = "read", owner_only: bool = False) -> Access:
    authorization = request.headers.get("authorization", "")
    if authorization:
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Use a Bearer API key")
        key = db.scalar(select(APIKey).where(APIKey.token_hash == digest(authorization[7:])))
        if not key or (key.expires_at is not None and key.expires_at<=time.time()):
            raise HTTPException(401, "Invalid or revoked API key")
        if key.project_id != project_id:
            raise HTTPException(404, "Project not found")
        if owner_only or scope not in key.scopes:
            raise HTTPException(403, "This credential does not grant the required scope")
        rate_limit(db, "key:" + key.id)
        key.last_used_at = time.time()
        db.commit()
        project = db.get(Project, project_id)
        owner=db.get(User,project.owner_id) if project else None
        if not owner or owner.disabled:
            raise HTTPException(401,"Invalid or revoked API key")
        request.state.pilot_user_id = owner.id
        return Access(project, "key:" + key.id, False)
    user = current_user(request, db)
    project = db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    if not project:
        raise HTTPException(404, "Project not found")
    rate_limit(db, "user:" + user.id)
    return Access(project, "user:" + user.id, True)
