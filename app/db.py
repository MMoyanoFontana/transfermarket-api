import os
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

load_dotenv()
db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise ValueError("DATABASE_URL is not set in the environment variables")

engine = create_engine(db_url, connect_args={"timeout": 60})
SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
