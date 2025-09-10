import os
from contextlib import asynccontextmanager
from typing import Annotated

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import col, select

from app.db import SessionDep
from app.models import League, LeaguePublic, Team, TeamLeagueLink, TeamPublicWithPlayers
from app.scraper import scrape_leagues, scrape_players_for_existing_teams, scrape_teams

load_dotenv()
FUBOLXD_URL = os.getenv("FUBOLXD_URL")
MOYA_IP = os.getenv("MOYA_IP")
if not FUBOLXD_URL:
    raise ValueError("FUBOLXD_URL is not set in the environment variables")
if not MOYA_IP:
    raise ValueError("MOYA_IP is not set in the environment variables")

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FUBOLXD_URL, f"http://{MOYA_IP}"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get(
    "/leagues/",
    response_model=list[LeaguePublic],
    description="Obtiene la lista de todas las ligas.",
    responses={
        "200": {
            "description": "Lista de ligas",
            "content": {
                "application/json": {
                    "example": [
                        {"name": "Premier League", "id": 1},
                        {"name": "LaLiga", "id": 2},
                    ]
                }
            },
        }
    },
)
def read_leagues(session: SessionDep) -> list[League]:
    leagues = session.exec(select(League)).all()
    print(leagues)
    return list(leagues)


@app.get(
    "/leagues/{league_id}/teams/",
    response_model=list[TeamPublicWithPlayers],
    description="Obtiene los equipos de una liga específica con sus jugadores.",
    responses={
        "200": {
            "description": "Equipos de liga league_id con sus jugadores",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "fubolxd_name": "Boca Juniors",
                            "id": 97,
                            "players": [
                                {
                                    "name": "Miguel Merentiel",
                                    "position": "Delantero",
                                    "id": 2671,
                                },
                                {
                                    "name": "Leandro Paredes",
                                    "position": "Mediocampista",
                                    "id": 2656,
                                },
                            ],
                        },
                        {
                            "fubolxd_name": "Talleres (C)",
                            "id": 104,
                            "players": [
                                {
                                    "name": "Guido Herrera",
                                    "position": "Arquero",
                                    "id": 2850,
                                },
                                {
                                    "name": "Emanuel Reynoso",
                                    "position": "Mediocampista",
                                    "id": 2866,
                                },
                            ],
                        },
                    ]
                }
            },
        },
        "404": {"description": "Liga no encontrada"},
    },
)
def read_league_teams(
    session: SessionDep,
    league_id: str,
) -> list[Team]:
    stmt = (
        select(Team)
        .join(TeamLeagueLink, col(Team.id) == col(TeamLeagueLink.team_id))
        .where(TeamLeagueLink.league_id == league_id)
    )
    teams = session.exec(stmt).all()
    if not teams:
        raise HTTPException(status_code=404)
    return list(teams)


@app.get("/health/", description="Verifica el estado de salud de la API.")
def read_health() -> dict:
    return {"status": "ok"}


subapp = FastAPI()

subapp.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://{MOYA_IP}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Internal use only
@subapp.post("/leagues/")
def update_leagues(background_tasks: BackgroundTasks) -> str:
    background_tasks.add_task(scrape_leagues)
    return "League update started in background"


@subapp.post("/teams/")
def update_teams(
    background_tasks: BackgroundTasks,
    avoid_leagues: list[int] = Query(default=None),
) -> str:
    background_tasks.add_task(scrape_teams, avoid_leagues=avoid_leagues)
    return "Team update started"


@subapp.post("/players/")
def update_players(
    background_tasks: BackgroundTasks,
    offset: int = 0,  # team offset ie. will start from team = offset + 1
    limit: Annotated[int, Query(le=100)] = 100,  # how many teams to process in this run
) -> str:
    background_tasks.add_task(
        scrape_players_for_existing_teams, offset=offset, limit=limit
    )
    return "Player update started"


app.mount("/subapp", subapp)
