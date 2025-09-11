from typing import Literal

from sqlmodel import Field, Relationship, SQLModel, String


class TeamLeagueLink(SQLModel, table=True):
    __tablename__: str = "team_league_link"

    team_id: int | None = Field(default=None, foreign_key="team.id", primary_key=True)
    league_id: int | None = Field(
        default=None, foreign_key="league.id", primary_key=True
    )


# https://sqlmodel.tiangolo.com/tutorial/fastapi/multiple-models/#multiple-models-with-inheritance
class TeamBase(SQLModel):
    fubolxd_name: str


class Team(TeamBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    fubolxd_id: str | None = None
    name: str = Field(index=True)
    link: str
    tm_id: str | None = None
    team_type: Literal["Club", "Seleccion"] = Field(default="Club", sa_type=String)
    leagues: list["League"] = Relationship(
        back_populates="teams", link_model=TeamLeagueLink
    )
    # Disambiguated relationships
    players: list["Player"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "or_(Team.id==Player.team_id, Team.id==Player.national_team_id)",
            "foreign_keys": "[Player.team_id, Player.national_team_id]"
        },
    )

    def __repr__(self) -> str:
        return f"Team(id={self.id!r}, name={self.name!r})"


class TeamPublic(TeamBase):
    id: int


class LeagueBase(SQLModel):
    name: str = Field(index=True)


class League(LeagueBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    league_type: Literal["Clubes", "Selecciones"] = Field(
        default="Clubes", sa_type=String
    )
    tm_id: str | None = None
    fubolxd_id: str | None = None
    link: str
    teams: list[Team] = Relationship(
        back_populates="leagues", link_model=TeamLeagueLink
    )

    def __repr__(self) -> str:
        return f"League(name={self.name!r})"


class LeaguePublic(LeagueBase):
    id: int


class PlayerBase(SQLModel):
    name: str = Field(index=True)
    position: Literal["Arquero", "Defensor", "Mediocampista", "Delantero"] | None = (
        Field(default=None, sa_type=String)
    )


class Player(PlayerBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    team: Team | None = Relationship(
        back_populates="players",
        sa_relationship_kwargs={"foreign_keys": "Player.team_id"},
    )
    team_id: int | None = Field(default=None, foreign_key="team.id")
    national_team: Team | None = Relationship(
        back_populates="players",
        sa_relationship_kwargs={"foreign_keys": "Player.national_team_id"},
    )
    national_team_id: int | None = Field(default=None, foreign_key="team.id")
    tm_id: str | None = None
    fubolxd_id: str | None = None
    link: str

    def __repr__(self) -> str:
        return f"Player(name={self.name!r}, position={self.position!r}, team={self.team!r})"


class PlayerPublic(PlayerBase):
    id: int


# Response models, to include relationships
class TeamPublicWithPlayers(TeamPublic):
    players: list[PlayerPublic] = []
