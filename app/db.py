import os
import urllib.parse
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine
load_dotenv()
DATABASE_SERVER = os.getenv("DATABASE_SERVER")
DATABASE_DB=os.getenv("DATABASE_DB")
DATABASE_USER=os.getenv("DATABASE_USER")
DATABASE_PASSWORD=os.getenv("DATABASE_PASSWORD")

if not DATABASE_SERVER or not DATABASE_DB or not DATABASE_USER or not DATABASE_PASSWORD:
    raise ValueError("DB vars are not set in the environment variables")



def make_engine():
    odbc = urllib.parse.quote_plus(
        "Driver=ODBC Driver 18 for SQL Server;"
        f"Server=tcp:{os.getenv('DATABASE_SERVER')},1433;"
        f"Database={os.getenv('DATABASE_DB')};"
        f"Uid={os.getenv('DATABASE_USER')};"
        f"Pwd={os.getenv('DATABASE_PASSWORD')};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "LoginTimeout=30;"
        "ConnectRetryCount=3;"         # reintentos de conexión
        "ConnectRetryInterval=10;"     # segundos entre reintentos
    )
    # mssql+pyodbc con pool sano
    engine = create_engine(
        f"mssql+pyodbc:///?odbc_connect={odbc}",
        pool_pre_ping=True,            # evita conexiones muertas (40613/idle)
        pool_recycle=1800,             # recicla cada 30 min
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        future=True,
    )
    return engine


engine = make_engine()
SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
