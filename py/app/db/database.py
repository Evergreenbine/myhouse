from pathlib import Path

from app.core.config import DATA_DIR

DATABASE_PATH = DATA_DIR / "local.db"
DATABASE_URL = "sqlite:///" + str(DATABASE_PATH).replace("\\", "/")

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import DeclarativeBase, sessionmaker

    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    class Base(DeclarativeBase):
        pass

except ImportError:
    engine = None
    SessionLocal = None

    class Base:  # type: ignore[no-redef]
        pass


def get_db():
    if SessionLocal is None:
        raise RuntimeError("SQLAlchemy is not installed. Run `pip install -r requirements.txt`.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

