import logging
import random
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from sqlmodel import Session, col, select

from app.db import engine
from app.models import League, Player, Team

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
    "Midfield": "Mediocampista",
    "Attack": "Delantero",
}


PRETTIER_NAME = {
    "CA Boca Juniors": "Boca Juniors",
    "CA River Plate": "River Plate",
    "CA Independiente": "Independiente",
    "CA Vélez Sarsfield": "Vélez Sarsfield",
    "Club Estudiantes de La Plata": "Estudiantes de La Plata",
    "CA Rosario Central": "Rosario Central",
    "CA Talleres": "Talleres (C)",
    "AA Argentinos Juniors": "Argentinos Juniors",
    "Club Atlético Belgrano": "Belgrano (C)",
    "CA San Lorenzo de Almagro": "San Lorenzo",
    "CA Lanús": "Lanús",
    "Club Atlético Tigre": "Tigre",
    "CA Huracán": "Huracán",
    "Club Atlético Platense": "Platense",
    "Defensa y Justicia": "Defensa y Justicia",
    "CD Godoy Cruz Antonio Tomba": "Godoy Cruz",
    "Instituto ACC": "Instituto (C)",
    "CS Independiente Rivadavia": "Independiente Rivadavia",
    "CA Barracas Central": "Barracas Central",
    "CA Unión (Santa Fe)": "Unión de Santa Fe",
    "CA Newell's Old Boys": "Newell´s Old Boys",
    "Club Atlético Tucumán": "Atlético Tucumán",
    "CA Central Córdoba (SdE)": "Central Córdoba (SdE)",
    "CA Banfield": "Banfield",
    "Club de Gimnasia y Esgrima La Plata": "Gimnasia de La Plata",
    "CA Sarmiento (Junin)": "Sarmiento de Junín",
    "CA Aldosivi": "Aldosivi",
    "CA San Martín (San Juan)": "San Martín (SJ)",
    "Club Deportivo Riestra": "Deportivo Riestra",
    "Sociedade Esportiva Palmeiras": "Palmeiras",
    "CR Flamengo": "Flamengo",
    "Botafogo de Futebol e Regatas": "Botafogo",
    "Cruzeiro Esporte Clube": "Cruzeiro",
    "Sport Club Corinthians Paulista": "Corinthians",
    "Clube de Regatas Vasco da Gama": "Vasco da Gama",
    "Esporte Clube Bahia": "Bahia",
    "Clube Atlético Mineiro": "Atlético Mineiro",
    "Fluminense Football Club": "Fluminense",
    "São Paulo Futebol Clube": "São Paulo",
    "Red Bull Bragantino": "RB Bragantino",
    "Sport Club Internacional": "Internacional",
    "Grêmio Foot-Ball Porto Alegrense": "Grêmio",
    "Santos FC": "Santos",
    "Fortaleza Esporte Clube": "Fortaleza",
    "Sport Club do Recife": "Sport Recife",
    "Esporte Clube Vitória": "Vitória",
    "Ceará Sporting Club": "Ceará",
    "Esporte Clube Juventude": "Juventude",
    "Mirassol Futebol Clube (SP)": "Mirassol",
    "Club Universidad de Chile": "Universidad de Chile",
    "Club Alianza Lima": "Alianza Lima",
    "Bolivar La Paz": "Bolívar",
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
        raise ValueError("No teams found in the table.")
    tbody = table.find("tbody")
    if not tbody:
        raise ValueError("No teams found in the table.")
    rows = tbody.find_all("tr", recursive=False)
    if not rows:
        raise ValueError("No teams found in the table.")
    for row in rows:
        team_cell = row.find("td", class_=["hauptlink", "no-border-links"])
        if not team_cell:
            raise ValueError("No teams found in the table.")
        link_tag = team_cell.find("a")
        if not link_tag or "href" not in link_tag.attrs:
            raise ValueError("No valid team link found.")
        team_name = link_tag.get_text(strip=True)
        team_link = urljoin("https://www.transfermarkt.com", link_tag["href"])
        team_id_match = re.search(r"/verein/(\w+)", link_tag["href"])
        fubol_xd_name = PRETTIER_NAME.get(team_name, team_name)
        if not team_id_match:
            raise ValueError(f"Could not extract team ID from link: {link_tag['href']}")
        team_id = team_id_match.group(1)
        teams.append(
            Team(
                tm_id=team_id or None,
                name=team_name,
                link=team_link,
                fubolxd_name=fubol_xd_name,
            )
        )
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
        raise ValueError("No player rows found in the table.")
    tbody = table.find("tbody")
    if not tbody:
        logging.warning("No tbody found in the players table.")
        raise ValueError("No player rows found in the table.")
    rows = tbody.find_all("tr", recursive=False)
    if not rows:
        logging.warning("No rows found in the players table body.")
        raise ValueError("No player rows found in the table.")
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


def scrape_players_for_existing_teams(
    offset: int | None = 0, limit: int | None = 1000
) -> None:
    with Session(engine) as session:
        stmt = select(Team).order_by(col(Team.id)).offset(offset).limit(limit)
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
            del players
    return


def scrape_leagues() -> None:
    DEFAULT_LEAGUES = {
        # Top 5 Europe
        "Premier League": "https://www.transfermarkt.com/premier-league/startseite/wettbewerb/GB1",
        "LaLiga": "https://www.transfermarkt.com/laliga/startseite/wettbewerb/ES1",
        "Serie A": "https://www.transfermarkt.com/serie-a/startseite/wettbewerb/IT1",
        "Bundesliga": "https://www.transfermarkt.com/bundesliga/startseite/wettbewerb/L1",
        "Ligue 1": "https://www.transfermarkt.com/ligue-1/startseite/wettbewerb/FR1",
        # Otras Europa
        "Eredivise": "https://www.transfermarkt.com/eredivisie/startseite/wettbewerb/NL1",
        "Primeira Liga": "https://www.transfermarkt.com/liga-nos/startseite/wettbewerb/PO1",
        # Sudamérica
        "Liga Profesional Argentina": "https://www.transfermarkt.com/superliga/startseite/wettbewerb/ARGC",
        "Brasileirão Série A": "https://www.transfermarkt.com/campeonato-brasileiro-serie-a/startseite/wettbewerb/BRA1",
        "Copa Argentina 2025": "https://www.transfermarkt.com/copa-argentina/teilnehmer/pokalwettbewerb/ARCA/saison_id/2024",
        # Continentales
        "UEFA Champions League": "https://www.transfermarkt.com/uefa-champions-league/teilnehmer/pokalwettbewerb/CL/saison_id/2025",
        "UEFA Europa League": "https://www.transfermarkt.com/europa-league/teilnehmer/pokalwettbewerb/EL/saison_id/2025",
        "Copa Libertadores 2025": "https://www.transfermarkt.com/copa-libertadores/teilnehmer/pokalwettbewerb/CLI/saison_id/2024",
        "Copa Sudamericana 2025": "https://www.transfermarkt.com/copa-sudamericana/teilnehmer/pokalwettbewerb/CS/saison_id/2024",
    }
    with Session(engine) as session:
        for name, link in DEFAULT_LEAGUES.items():
            if session.exec(select(League).where(League.name == name)).first():
                logging.info(f"League {name} already exists. Skipping.")
                continue
            league_id_match = re.search(r"/(?:pokal)?wettbewerb/(\w+)", link)
            league_id = league_id_match.group(1) if league_id_match else name
            league_db = League(tm_id=league_id, name=name, link=link)
            session.add(league_db)
        session.commit()
    return
