"""Fail-closed request/text reservations; these are not dollar-price estimates."""
from datetime import datetime, timezone
from .config import settings
from .db import SessionLocal
from .embeddings import EmbeddingError
from .models import ProviderUsage


def reserve_hosted(characters):
    s=settings()
    if not 0<=characters<=s.hosted_call_input_chars:raise EmbeddingError('Hosted request exceeds its configured input budget')
    if s.hosted_daily_requests<=0 or s.hosted_daily_input_chars<=0:raise EmbeddingError('Hosted requests are disabled by the operator budget')
    day=datetime.now(timezone.utc).date().isoformat()
    with SessionLocal() as db:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        insert=pg_insert if db.bind.dialect.name=='postgresql' else sqlite_insert
        db.execute(insert(ProviderUsage).values(day=day,requests=0,input_chars=0).on_conflict_do_nothing(index_elements=[ProviderUsage.day]))
        from sqlalchemy import update
        reserved=db.scalar(update(ProviderUsage).where(ProviderUsage.day==day,ProviderUsage.requests<s.hosted_daily_requests,ProviderUsage.input_chars+characters<=s.hosted_daily_input_chars).values(requests=ProviderUsage.requests+1,input_chars=ProviderUsage.input_chars+characters).returning(ProviderUsage.requests))
        db.commit()
        if reserved is None:raise EmbeddingError('Hosted daily request/text budget exhausted; retry after UTC reset or ask the operator')
