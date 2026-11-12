from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Fail fast when development mode is paired with a shared/production database:
# SQL echo would write bound parameters (emails, tokens) to the log, and
# `create_all` would create tables straight from the models, hiding a missing
# Alembic migration. Checked here — at import — so every entry point (uvicorn,
# the crawler, the CLI tools) is covered.
if settings.unsafe_dev_mode:
    raise RuntimeError(
        f"APP_ENV=development but DATABASE_URL points at "
        f"{settings.database_host!r}. Development mode enables SQL echo (which "
        f"logs bound parameters — emails, tokens) and create_all (which hides "
        f"missing Alembic migrations). Set APP_ENV=production for this database."
    )

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.is_dev,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
