"""Minimal SQLAlchemy engine, used only to check whether the pgvector
collection has already been populated (see knowledge_base/build_index.py).

The vector store itself is managed entirely by langchain-postgres' PGVector;
this project has no ORM models of its own.
"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
