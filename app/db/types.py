from __future__ import annotations

from sqlalchemy import BigInteger, Integer, JSON, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB


JsonType = JSON().with_variant(JSONB(astext_type=String()), "postgresql")
UuidType = Uuid(as_uuid=True)
PrimaryKeyBigInt = BigInteger().with_variant(Integer, "sqlite")
