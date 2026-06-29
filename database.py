from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("sqlite://"):
        return database_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return database_url


def sync_database_url(database_url: str) -> str:
    """Return a sync SQLAlchemy URL for APScheduler's blocking job store."""
    normalized = normalize_database_url(database_url)
    if normalized.startswith("sqlite+aiosqlite://"):
        return normalized.replace("sqlite+aiosqlite://", "sqlite://", 1)
    if normalized.startswith("postgresql+asyncpg://"):
        return normalized.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    return database_url


def async_connect_args(database_url: str) -> dict:
    parsed = make_url(normalize_database_url(database_url))
    if parsed.drivername.startswith("postgresql"):
        # Supabase transaction pooler (6543) requires disabling prepared statements.
        args: dict = {"ssl": "require"}
        if parsed.port == 6543:
            args["statement_cache_size"] = 0
        return args
    return {}


def sync_connect_args(database_url: str) -> dict:
    parsed = make_url(normalize_database_url(database_url))
    if parsed.drivername.startswith("postgresql"):
        return {"sslmode": "require"}
    return {}


db_url = normalize_database_url(settings.DATABASE_URL)
parsed_db_url = make_url(db_url)
if parsed_db_url.drivername.startswith("sqlite") and parsed_db_url.database not in {None, ":memory:"}:
    Path(parsed_db_url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)

async_engine = create_async_engine(
    db_url,
    echo=settings.SQL_ECHO,
    connect_args=async_connect_args(settings.DATABASE_URL),
)

if parsed_db_url.drivername.startswith("sqlite"):
    @event.listens_for(async_engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

async def get_db_session():
    """Context provider/generator for SQLAlchemy database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
