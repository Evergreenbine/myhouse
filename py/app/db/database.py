from os import getenv

try:
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL
    from sqlalchemy.orm import DeclarativeBase, sessionmaker

    mysql_url = URL.create(
        "mysql+pymysql",
        username=getenv("MYSQL_USER", "myhouse"),
        password=getenv("MYSQL_PASSWORD", ""),
        host=getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(getenv("MYSQL_PORT", "3306")),
        database=getenv("MYSQL_DATABASE", "myhouse"),
    )
    engine = create_engine(mysql_url, pool_pre_ping=True, future=True)
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
