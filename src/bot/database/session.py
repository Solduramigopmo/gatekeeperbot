from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .base import Base

SessionFactory = async_sessionmaker[AsyncSession]


def _ensure_sqlite_dir(url: str) -> None:
    if not url.startswith("sqlite"):
        return
    if ":///" not in url:
        return
    path_part = url.split(":///", 1)[1]
    if path_part in {"", ":memory:"}:
        return
    Path(path_part).parent.mkdir(parents=True, exist_ok=True)


async def create_engine_and_session(
    url: str,
    *,
    echo: bool = False,
    create_tables: bool = False,
) -> tuple[AsyncEngine, SessionFactory]:
    _ensure_sqlite_dir(url)
    engine = create_async_engine(url, echo=echo, pool_pre_ping=True, future=True)
    if create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    factory: SessionFactory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


async def dispose_engine(engine: AsyncEngine) -> None:
    await engine.dispose()


@asynccontextmanager
async def open_session(factory: SessionFactory) -> AsyncIterator[AsyncSession]:
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
