import logging
import random
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from sqlmodel import Session, col, select

from app.models import League, Player, Team, TeamLeagueLink, engine

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


DEFAULT_DELAY_RANGE = (5, 60)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

HEADERS_BASE = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

POSITION_TRANSLATE = {
    "Goalkeeper": "Arquero",
    "Defender": "Defensor",
    "Midfielder": "Mediocampista",
    "Forward": "Delantero",
}


def polite_get_soup(url, timeout=30) -> BeautifulSoup:
    sleep_time = random.uniform(*DEFAULT_DELAY_RANGE)
    logging.info(f"Fetching URL: {url} Delay before request: {sleep_time}")
    time.sleep(sleep_time)
    headers = HEADERS_BASE.copy()
    headers["User-Agent"] = random.choice(USER_AGENTS)
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_teams_from_soup(soup: BeautifulSoup) -> list[Team]:
    teams = []
    table = soup.find("table", class_="items")
    if not table:
        logging.warning("No table with class 'items' found in the soup.")
        return teams
    tbody = table.find("tbody")
    if not tbody:
        logging.warning("No tbody found in the teams table.")
        return teams
    rows = tbody.find_all("tr", recursive=False)
    for row in rows:
        team_cell = row.find("td", class_="hauptlink no-border-links")
        link_tag = team_cell.find("a")
        team_name = link_tag.get_text(strip=True)
        team_link = urljoin("https://www.transfermarkt.com", link_tag["href"])
        team_id_match = re.search(r"/verein/(\w+)", link_tag["href"])
        if team_id_match:
            team_id = team_id_match.group(1)
        teams.append(Team(tm_id=team_id or None, name=team_name, link=team_link))
    return teams


def scrape_teams(avoid_leagues: list[int] | None = None) -> None:
    with Session(engine) as session:
        if avoid_leagues is None:
            stmt = select(League)
        else:
            stmt = select(League).where(League.id.notin_(avoid_leagues))
        logging.info("Starting team load...")
        logging.info(
            f"Avoiding leagues: {avoid_leagues}",
        )
        leagues = session.exec(stmt).all()
        for league in leagues:
            logging.info(f"Loading {league.name} teams:")
            soup = polite_get_soup(league.link)
            teams = extract_teams_from_soup(soup)
            logging.info(f" Found {len(teams)} teams.")
            for team in teams:
                logging.info(f"Processing team: {team.name}")
                # Por si el equipo ya existe, ej equipos de premier league en champions
                existing_team = session.exec(
                    select(Team).where(Team.tm_id == team.tm_id)
                ).first()
                if existing_team:
                    logging.info(f"Team {team.name} already exists. Linking to league.")
                    team = existing_team
                session.add(team)
                if league not in team.leagues:
                    team.leagues.append(league)
        session.commit()
    return


def extract_players_from_soup(soup) -> list[Player]:
    players = []
    table = soup.find("table", class_="items")
    if not table:
        logging.warning("No table with class 'items' found in the soup.")
        return players
    tbody = table.find("tbody")
    if not tbody:
        logging.warning("No tbody found in the players table.")
        return players
    rows = tbody.find_all("tr", recursive=False)
    for row in rows:
        position_cell = row.find("td", class_=["zentriert", "rueckennummer"])
        if not position_cell or "title" not in position_cell.attrs:
            logging.warning("Position cell missing or lacks title attribute.")
            continue
        player_cell = row.find("td", class_="hauptlink")
        link_tag = player_cell.find("a")
        player_position = POSITION_TRANSLATE.get(position_cell["title"], None)
        player_name = link_tag.get_text(strip=True)
        player_link = urljoin("https://www.transfermarkt.com", link_tag["href"])

        player_id_match = re.search(r"/spieler/(\d+)", link_tag["href"])
        player_id = player_id_match.group(1) if player_id_match else None

        players.append(
            Player(
                tm_id=player_id,
                name=player_name,
                position=player_position,  # type: ignore
                link=player_link,
            )
        )
    return players


def scrape_players_for_existing_teams(include_leagues: list[int] | None = None) -> None:
    with Session(engine) as session:
        if include_leagues is None:
            teams = session.exec(select(Team)).all()
        else:
            stmt = (
                select(Team)
                .join(TeamLeagueLink, col(Team.id) == col(TeamLeagueLink.team_id))
                .where(TeamLeagueLink.league_id.in_(include_leagues))
            )
            teams = session.exec(stmt).all()
        for team in teams:
            logging.info(f"Loading players for team: {team.name}")
            soup = polite_get_soup(team.link)
            players = extract_players_from_soup(soup)
            for player in players:
                logging.info(f" Adding/Updating player: {player.name}")
                existing_player = session.exec(
                    select(Player).where(Player.tm_id == player.tm_id)
                ).first()
                if existing_player and existing_player.team_id == team.id:
                    logging.info(f"Player {player.name} already exists. Skipping.")
                    continue
                elif existing_player and existing_player.team_id != team.id:
                    logging.info(
                        f"Player {player.name} already exists and is linked to another team. Updating team link."
                    )
                    player = existing_player
                player.team_id = team.id
                player.team = team
                session.add(player)
        session.commit()
    return


def scrape_leagues() -> None:
    DEFAULT_LEAGUES = {
        # Top 5 Europe
        "Premier League": "https://www.transfermarkt.com/premier-league/startseite/wettbewerb/GB1",
        "LaLiga": "https://www.transfermarkt.com/laliga/startseite/wettbewerb/ES1",
        "Serie A": "https://www.transfermarkt.com/serie-a/startseite/wettbewerb/IT1",
        "Bundesliga": "https://www.transfermarkt.com/bundesliga/startseite/wettbewerb/L1",
        "Ligue 1": "https://www.transfermarkt.com/ligue-1/startseite/wettbewerb/FR1",
        # Sudamérica
        "Primera División Argentina": "https://www.transfermarkt.com/superliga/startseite/wettbewerb/AR1N",
        "Brasileirão Série A": "https://www.transfermarkt.com/campeonato-brasileiro-serie-a/startseite/wettbewerb/BRA1",
    }
    with Session(engine) as session:
        for name, link in DEFAULT_LEAGUES.items():
            if session.exec(select(League).where(League.name == name)).first():
                continue
            league_id_match = re.search(r"/(?:pokal)?wettbewerb/(\w+)", link)
            league_id = league_id_match.group(1) if league_id_match else name
            league_db = League(tm_id=league_id, name=name, link=link)
            session.merge(league_db)
        session.commit()
    return
