import os

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Postgres in production, e.g. postgresql+psycopg://pitchlab:pitchlab@localhost:5432/pitchlab
# Falls back to a local SQLite file so the app runs with zero setup.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pitchlab.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


@event.listens_for(Engine, "connect")
def _sqlite_foreign_keys(dbapi_conn, _record):
    # SQLite ignores ON DELETE CASCADE unless this is switched on per connection
    if type(dbapi_conn).__module__.startswith("sqlite3"):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(bind=None) -> None:
    """Create tables, then add any nullable columns that were added to models since.

    A stopgap until the schema is managed with Alembic: it only ever adds nullable columns.
    """
    bind = bind or engine
    Base.metadata.create_all(bind)
    insp = inspect(bind)
    with bind.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing and col.nullable:
                    col_type = col.type.compile(dialect=bind.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {col_type}'))
        _migrate_pitcher_name_uniqueness(conn, insp)


def _migrate_pitcher_name_uniqueness(conn, insp) -> None:
    """Pitcher names used to be globally unique; with accounts they are unique per owner."""
    for ix in insp.get_indexes("pitchers"):
        if ix["column_names"] == ["name"] and ix.get("unique"):
            conn.execute(text(f"DROP INDEX {ix['name']}"))
            conn.execute(text("CREATE INDEX ix_pitchers_name ON pitchers (name)"))
    names = {ix["name"] for ix in insp.get_indexes("pitchers")}
    names |= {uc["name"] for uc in insp.get_unique_constraints("pitchers")}
    if "uq_pitchers_owner_name" not in names:
        conn.execute(text(
            "CREATE UNIQUE INDEX uq_pitchers_owner_name ON pitchers (owner_id, name)"))
