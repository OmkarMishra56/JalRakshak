
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import get_settings

settings = get_settings()

async_engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


sync_engine = create_engine(settings.sync_database_url, echo=False, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
