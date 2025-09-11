import logging
import os
import urllib.parse
import time
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends
from sqlalchemy import NullPool
from sqlmodel import Session, SQLModel, create_engine

load_dotenv()
DATABASE_SERVER = os.getenv("DATABASE_SERVER")
DATABASE_DB = os.getenv("DATABASE_DB")
DATABASE_USER = os.getenv("DATABASE_USER")
DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD")

if not DATABASE_SERVER or not DATABASE_DB or not DATABASE_USER or not DATABASE_PASSWORD:
    raise ValueError("DB vars are not set in the environment variables")


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def make_engine():
    odbc = urllib.parse.quote_plus(
        "Driver=ODBC Driver 18 for SQL Server;"
        f"Server=tcp:{os.getenv('DATABASE_SERVER')},1433;"
        f"Database={os.getenv('DATABASE_DB')};"
        f"Uid={os.getenv('DATABASE_USER')};"
        f"Pwd={os.getenv('DATABASE_PASSWORD')};"
        "Encrypt=yes;TrustServerCertificate=no;"
        "Login Timeout=60;"
        "Connection Timeout=60;"
        "ConnectRetryCount=3;"
        "ConnectRetryInterval=20;"
    )

    # mssql+pyodbc con pool sano
    engine = create_engine(
        f"mssql+pyodbc:///?odbc_connect={odbc}",
        poolclass=NullPool,
        future=True,
    )
    return engine


engine = make_engine()


def _check_db_once() -> None:
    logger.info("Comprobando conexión a la DB...")
    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT 1")


def wait_for_db(max_attempts: int = 8, base_delay: float = 1.5) -> bool:
    """
    Reintenta con backoff exponencial (1.5s, 3s, 6s, ... máx 30s)
    hasta que la DB responda. No bloquea el event loop.
    """
    for i in range(max_attempts):
        try:
            _check_db_once()
            logger.info("DB disponible")
            return True
        except Exception as e:
            msg = str(e).lower()
            logger.warning(
                f"DB no disponible, reintentando... ({i + 1}/{max_attempts}) {msg}"
            )
            delay = min(30.0, base_delay * (2**i))
            time.sleep(delay)
    return False


def _create_all_safe():
    """Ejecuta create_all en thread, para no bloquear el loop."""
    logger.info("Creando metada")
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
