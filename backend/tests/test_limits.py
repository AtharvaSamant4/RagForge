from fastapi import HTTPException
import pytest

from app.db import SessionLocal
from app.security import rate_limit


def test_database_backed_rate_limit():
    with SessionLocal() as db:
        rate_limit(db, "test-principal", 2)
    with SessionLocal() as db:
        rate_limit(db, "test-principal", 2)
        with pytest.raises(HTTPException) as error:
            rate_limit(db, "test-principal", 2)
        assert error.value.status_code == 429
        rate_limit(db, "other-principal", 2)
