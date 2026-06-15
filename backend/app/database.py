from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings


connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_sqlite_schema_compatibility():
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "disease_reports" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("disease_reports")}
    with engine.begin() as connection:
        if "status" not in columns:
            connection.execute(text("ALTER TABLE disease_reports ADD COLUMN status VARCHAR(60) DEFAULT 'completed'"))
        if "analysis_json" not in columns:
            connection.execute(text("ALTER TABLE disease_reports ADD COLUMN analysis_json JSON"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
