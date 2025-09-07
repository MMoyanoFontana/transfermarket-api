import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import col, delete, select

from app.models import League, Player, SessionDep, Team, TeamLeagueLink
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
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root() -> dict:
    return {"message": "Api funcionando"}


@app.post("/leagues/")
def update_leagues(background_tasks: BackgroundTasks) -> str:
    background_tasks.add_task(scrape_leagues)
    return "League update started in background"


@app.get("/leagues/")
def read_leagues(session: SessionDep) -> list[League]:
    leagues = session.exec(select(League)).all()
    print(leagues)
    return list(leagues)


@app.post("/leagues/teams/")
def update_teams(
    background_tasks: BackgroundTasks, avoid_leagues: list[int] = Query(default=None)
) -> str:
    background_tasks.add_task(scrape_teams, avoid_leagues=avoid_leagues)
    return "Team update started"


@app.delete("/leagues/{league_id}/")
def delete_leagues(session: SessionDep, league_id: str) -> None:
    stmt = delete(League).where(League.id == league_id)  # type: ignore
    session.exec(stmt)  # type: ignore
    session.commit()
    return


@app.get("/leagues/{league_id}/teams/")
def read_league_teams(session: SessionDep, league_id: str) -> list[Team]:
    stmt = (
        select(Team)
        .join(TeamLeagueLink, col(Team.id) == col(TeamLeagueLink.team_id))
        .where(TeamLeagueLink.league_id == league_id)
    )
    teams = session.exec(stmt).all()
    return list(teams)


@app.get("/teams/")
def read_all_teams(session: SessionDep) -> dict[str, list[Team]]:
    leagues = session.exec(select(League)).all()
    return {league.name: league.teams for league in leagues}


@app.post("/teams/players/")
def update_players(
    background_tasks: BackgroundTasks, include_leagues: list[int] = Query(default=None)
) -> str:
    background_tasks.add_task(
        scrape_players_for_existing_teams, include_leagues=include_leagues
    )
    return "Player update started"


@app.get("/teams/{team_id}/players/")
def read_players(session: SessionDep, team_id: str) -> list[Player]:
    players = session.exec(select(Player).where(Player.team_id == team_id)).all()
    print(players)
    return list(players)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}
