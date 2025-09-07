import os
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import Depends
from sqlmodel import Field, Relationship, Session, SQLModel, String, create_engine


class TeamLeagueLink(SQLModel, table=True):
    team_id: int | None = Field(default=None, foreign_key="team.id", primary_key=True)
    league_id: int | None = Field(
        default=None, foreign_key="league.id", primary_key=True
    )


class Team(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tm_id: str | None = Field(default=None, index=True)
    fubolxd_id: str | None = Field(default=None, index=True)
    name: str
    link: str
    leagues: list["League"] = Relationship(
        back_populates="teams", link_model=TeamLeagueLink
    )
    players: list["Player"] = Relationship(back_populates="team")

    def __repr__(self) -> str:
        return f"Team(id={self.id!r}, name={self.name!r})"


class League(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tm_id: str | None = None
    fubolxd_id: str | None = None
    name: str
    link: str
    teams: list[Team] = Relationship(
        back_populates="leagues", link_model=TeamLeagueLink
    )

    def __repr__(self) -> str:
        return f"League(name={self.name!r})"


class Player(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tm_id: str | None = None
    fubolxd_id: str | None = None
    name: str
    position: Literal["Arquero", "Defensor", "Mediocampista", "Delantero"] | None = (
        Field(default=None, sa_type=String)
    )
    link: str
    team_id: int | None = Field(default=None, foreign_key="team.id")
    team: Team | None = Relationship(back_populates="players")

    def __repr__(self) -> str:
        return f"Player(name={self.name!r}, position={self.position!r}, team={self.team!r})"


load_dotenv()
db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise ValueError("DATABASE_URL is not set in the environment variables")

engine = create_engine(db_url)
SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
