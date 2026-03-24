# /data_agent.py

import requests
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
import json
import os
from dotenv import load_dotenv
import logging # Import logging module
# Import the OddsAgent to fetch real-time odds
from odds_agent import OddsAgent

load_dotenv()

# --- FIX: REMOVED THE CIRCULAR IMPORT FROM STREAMLIT_APP ---
# The lines below caused the circular import.
# from streamlit_app import fetch_matches_from_db, init_data_agent
# --- END FIX ---

class DataAgent:
    """
    Data Agent for fetching and managing sports data.
    Provides tools for API fetching, storage, SQL-Augmented Context retrieval,
    and fetching live bookmaker odds.
    """

    # --- CRITICAL CHANGE: Accept odds_api_key in __init__ ---
    def __init__(self, sport_type: str = "football", db_path: str = "betting_edge.db", odds_api_key: Optional[str] = None):
        # Configure logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

        # Load API keys
        api_keys = {
            "football": os.getenv("API_KEY_FOOTBALL"),
            "college_football": os.getenv("API_KEY_CFB"),
            "basketball": os.getenv("API_KEY_BASKETBALL")
        }

        self.sport_type = sport_type
        self.api_key = api_keys.get(sport_type)

        if not self.api_key:
            self.api_key = os.getenv("API_KEY_FOOTBALL_DATA") # Fallback check

        if not self.api_key:
            raise ValueError(f"API key for {sport_type} not found. Check your .env file or environment variables.")

        # --- CONFIGURATION ---
        if sport_type == "football":
            self.base_url = "https://api.football-data.org/v4"
            self.headers = {'X-Auth-Token': self.api_key}

        elif sport_type == "college_football":
            self.base_url = "https://api.collegefootballdata.com"
            self.headers = {'Authorization': f'Bearer {self.api_key}', 'Accept': 'application/json'}

        elif sport_type == "basketball":
            self.base_url = "https://api.collegebasketballdata.com"
            self.headers = {'Authorization': f'Bearer {self.api_key}', 'Accept': 'application/json'}
        else:
            raise ValueError(f"Unsupported sport_type: {sport_type}")

        self.db_path = db_path
        self._init_database()
        
        # --- CRITICAL CHANGE: Initialize the OddsAgent with the provided API key ---
        if odds_api_key:
            try:
                self.odds_agent = OddsAgent(api_key=odds_api_key)
                self.logger.info("OddsAgent initialized successfully within DataAgent.")
            except ValueError as e:
                self.logger.error(f"Failed to initialize OddsAgent: {e}")
                self.odds_agent = None # Set to None if initialization fails
        else:
            self.logger.warning("No ODDS_API_KEY provided to DataAgent. Odds fetching functionality will be limited.")
            self.odds_agent = None # Explicitly set to None if no key is provided

    def _init_database(self):
        """Initialize SQLite database with required schemas."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                match_id INTEGER PRIMARY KEY, sport_type TEXT, league_id INTEGER,
                league_name TEXT, season INTEGER, match_date TEXT, home_team_id INTEGER,
                home_team_name TEXT, away_team_id INTEGER, away_team_name TEXT,
                home_score INTEGER, away_score INTEGER, status TEXT, venue TEXT, last_updated TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS match_stats (
                stat_id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, team_id INTEGER,
                team_name TEXT, shots_on_goal INTEGER, total_shots INTEGER, ball_possession INTEGER,
                last_updated TEXT, FOREIGN KEY (match_id) REFERENCES matches(match_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS odds (
                odds_id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER, bookmaker TEXT,
                bet_type TEXT, home_team_odds REAL, draw_odds REAL, away_team_odds REAL, last_updated TEXT,
                FOREIGN KEY (match_id) REFERENCES matches(match_id)
            )
        ''')

        cursor.execute('CREATE TABLE IF NOT EXISTS user_profiles (user_id INTEGER PRIMARY KEY, username TEXT UNIQUE)')

        conn.commit()
        conn.close()
        self.logger.info(f"Database initialized at {self.db_path}")

    # --- CORE FETCHING LOGIC (Unchanged from what you provided) ---
    def fetch_matches(self, league_id: int = None, season: int = None,
                      from_date: Optional[str] = None, to_date: Optional[str] = None,
                      year: Optional[int] = None, week: Optional[int] = None) -> List[Dict]:
        if self.sport_type == "college_football":
            return self._fetch_college_data(path="/games", year=year or season, week=week)
        elif self.sport_type == "basketball":
            return self._fetch_college_data(path="/games", year=year or season, week=week)
        else: # football
            id_map = {39: 'PL', 140: 'PD', 135: 'SA', 78: 'BL1', 61: 'FL1', 2001: 'CL'}
            competition_code = id_map.get(league_id, 'PL')
            return self._fetch_football_data_org(competition_code, season)

    def _fetch_football_data_org(self, competition_code: str, season: int) -> List[Dict]:
        url = f"{self.base_url}/competitions/{competition_code}/matches"
        params = {'season': season}

        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            raw_matches = data.get('matches', [])
            converted_games = []
            for m in raw_matches:
                converted = {
                    'fixture': {'id': m['id'], 'date': m['utcDate'], 'status': {'long': m['status']}, 'venue': {'name': 'Unknown'}},
                    'league': {'id': data['competition']['id'], 'name': data['competition']['name'], 'season': season},
                    'teams': {'home': {'id': m['homeTeam']['id'], 'name': m['homeTeam']['name']}, 'away': {'id': m['awayTeam']['id'], 'name': m['awayTeam']['name']}},
                    'goals': {'home': m['score']['fullTime']['home'], 'away': m['score']['fullTime']['away']}
                }
                converted_games.append(converted)
            return converted_games
        except Exception as e:
            self.logger.error(f"Error fetching from football-data.org: {e}")
            return []

    def _fetch_college_data(self, path: str, year: int, week: Optional[int] = None) -> List[Dict]:
        endpoint = f"{self.base_url}{path}"
        params = {'year': year}
        try:
            response = requests.get(endpoint, headers=self.headers, params=params)
            response.raise_for_status()
            if 'application/json' not in response.headers.get('Content-Type', ''): return []
            data = response.json()
            converted_games = []
            for game in data:
                if game.get('season') == year:
                    converted_game = {
                        'fixture': {'id': game.get('id', 0), 'date': game.get('startDate', ''), 'status': {'long': 'completed' if game.get('completed') else 'scheduled'}, 'venue': {'name': game.get('venue') or 'TBD'}},
                        'league': {'id': 0, 'name': 'College Football' if self.sport_type == 'college_football' else 'College Basketball', 'season': game.get('season', year)},
                        'teams': {'home': {'id': game.get('homeId', 0), 'name': game.get('homeTeam', 'TBD')}, 'away': {'id': game.get('awayId', 0), 'name': game.get('awayTeam', 'TBD')}},
                        'goals': {'home': game.get('homePoints'), 'away': game.get('awayPoints')}
                    }
                    converted_games.append(converted_game)
            return converted_games
        except Exception as e:
            self.logger.error(f"Error fetching college games: {e}")
            return []

    def store_match(self, match_data: Dict):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        cursor = conn.cursor()
        try:
            f, l, t, g = match_data['fixture'], match_data['league'], match_data['teams'], match_data['goals']
            cursor.execute('''INSERT OR REPLACE INTO matches (match_id, sport_type, league_id, league_name, season, match_date, home_team_id, home_team_name, away_team_id, away_team_name, home_score, away_score, status, venue, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (f['id'], self.sport_type, l['id'], l['name'], l['season'], f['date'], t['home']['id'], t['home']['name'], t['away']['id'], t['away']['name'], g['home'], g['away'], f['status']['long'], f['venue']['name'], datetime.now().isoformat()))
            conn.commit()
        except Exception as e:
            self.logger.error(f"Error storing match: {e}")
        finally:
            conn.close()

    # --- CORE SQL-RAG IMPLEMENTATION ---

    def _safe_fetch_one(self, query: str, params: tuple) -> Dict:
        """Safely executes a query and returns a dictionary or an empty dict {}."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute(query, params)
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row is not None else {}
        except Exception as e:
            # Catches errors if table is completely missing or SQL is malformed
            self.logger.error(f"SQL Error in safe_fetch: {e}")
            conn.close()
            return {}

    def get_full_match_context(self, match_id: int) -> Dict:
        """
        Retrieves all necessary structured data for the Recommendation Agent.
        """

        # 1. Get Match and Score Details
        match_details = self._safe_fetch_one(
            'SELECT * FROM matches WHERE match_id = ?',
            (match_id,)
        )

        # Default to -1 if match details couldn't be found
        home_team_id = match_details.get('home_team_id', -1)

        # 2. Get Statistics (Focus on Home Team)
        home_stats = self._safe_fetch_one(
            'SELECT ball_possession, total_shots, shots_on_goal FROM match_stats WHERE match_id = ? AND team_id = ?',
            (match_id, home_team_id)
        )

        # 3. Get Latest Odds (from local DB)
        latest_odds = self._safe_fetch_one(
            'SELECT bookmaker, home_team_odds, away_team_odds, draw_odds FROM odds WHERE match_id = ? ORDER BY last_updated DESC LIMIT 1',
            (match_id,)
        )

        # Combine into a single, clean dictionary for the LLM
        return {
            "match_details": match_details,
            "home_team_stats": home_stats,
            "latest_odds": latest_odds,
        }

    # --- REAL-TIME ODDS FETCHING ---

    def fetch_odds(self, match_id: int) -> Optional[Dict[str, float]]:
        """
        Fetches the latest bookmaker odds for a given match_id.
        Tries to get from DB first, if not found or stale, fetches from Odds API.
        Returns None for finished matches (no live odds available).
        """
        if self.odds_agent is None:
            self.logger.error("OddsAgent not initialized. Cannot fetch live odds.")
            return None

        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        cursor = conn.cursor()

        # 1. Try to get recent odds from the database
        # Consider adding a timestamp check here for "staleness"
        cursor.execute(
            "SELECT home_team_odds, away_team_odds, draw_odds FROM odds WHERE match_id = ? ORDER BY last_updated DESC LIMIT 1",
            (match_id,),
        )
        db_odds = cursor.fetchone()

        # If fresh odds are in DB, return them
        if db_odds:
            # You might want to add a check here for `last_updated` to see if they are recent enough
            # For now, we'll just return if found.
            self.logger.info(f"Using database odds for match ID {match_id}.")
            return {
                "home_team_odds": db_odds[0],
                "away_team_odds": db_odds[1],
                "draw_odds": db_odds[2],
            }

        # 2. If not in DB or stale, get match details to query Odds API
        cursor.execute(
            "SELECT home_team_name, away_team_name, sport_type, league_name, status FROM matches WHERE match_id = ?",
            (match_id,),
        )
        match_details = cursor.fetchone()
        conn.close() # Close connection after fetching match details

        if not match_details:
            self.logger.warning(f"Match ID {match_id} not found in database to fetch live odds.")
            return None

        home_team, away_team, sport_type_from_db, league_name, match_status = match_details

        # Skip odds fetching for finished matches - Odds API only has upcoming odds
        if match_status and match_status.upper() in ['FINISHED', 'COMPLETED', 'MATCH FINISHED']:
            self.logger.info(f"Match ID {match_id} ({home_team} vs {away_team}) is already finished. Skipping odds fetch.")
            return None

        # --- DYNAMIC MAPPING LOGIC (as you provided) ---
        odds_api_sport_map = {
            "football": {
                "Premier League": "soccer_epl",
                "La Liga": "soccer_spain_la_liga",
                "Primera Division": "soccer_spain_la_liga",  # Same as La Liga
                "Serie A": "soccer_italy_serie_a",
                "Bundesliga": "soccer_germany_bundesliga1",
                "Ligue 1": "soccer_france_ligue_1",
                "UEFA Champions League": "soccer_uefa_champs_league",
                "DEFAULT": "soccer",
            },
            "college_football": {
                "NCAAF": "americanfootball_ncaaf",
                "DEFAULT": "americanfootball_ncaaf",
            },
            "basketball": {
                "NBA": "basketball_nba",
                "NCAAB": "basketball_ncaab",
                "DEFAULT": "basketball_nba",
            },
        }

        odds_api_sport = None
        if sport_type_from_db in odds_api_sport_map:
            if league_name in odds_api_sport_map[sport_type_from_db]:
                odds_api_sport = odds_api_sport_map[sport_type_from_db][league_name]
            else:
                odds_api_sport = odds_api_sport_map[sport_type_from_db].get("DEFAULT")
        
        if not odds_api_sport:
            self.logger.warning(f"No Odds API sport mapping for internal sport_type: '{sport_type_from_db}' "
                                f"or league_name: '{league_name}'. Attempting generic fallback.")
            if "football" in sport_type_from_db:
                odds_api_sport = "soccer"
            elif "basketball" in sport_type_from_db:
                odds_api_sport = "basketball_nba"
            elif "americanfootball" in sport_type_from_db:
                odds_api_sport = "americanfootball_ncaaf"
            else:
                self.logger.error(f"Unable to determine Odds API sport key for {sport_type_from_db}.")
                return None
        # --- END DYNAMIC MAPPING LOGIC ---

        # 3. Fetch odds from the external API
        self.logger.info(f"🔍 DataAgent: Calling OddsAgent for '{home_team} vs {away_team}' "
                          f"(League: '{league_name}') with Odds API sport key: '{odds_api_sport}'...")

        odds_data_from_api = self.odds_agent.get_upcoming_odds(
            sport=odds_api_sport,
            regions="us,eu,au,uk",
            markets="h2h"
        )

        # Fallback: If UEFA Champions League returns no data, try generic "soccer"
        if not odds_data_from_api and odds_api_sport == "soccer_uefa_champs_league":
            self.logger.info(f"   ⚠️ No results for '{odds_api_sport}', trying generic 'soccer' fallback...")
            odds_data_from_api = self.odds_agent.get_upcoming_odds(
                sport="soccer",
                regions="us,eu,au,uk",
                markets="h2h"
            )
            odds_api_sport = "soccer"  # Update for logging

        if not odds_data_from_api:
            self.logger.warning(f"No raw odds data returned from Odds API for {home_team} vs {away_team} using sport key '{odds_api_sport}'.")
            return None

        # 4. Find the matching event in the API response (ROBUST MATCHING)
        # Strip common prefixes/suffixes like "FC", "AFC", "United" to improve matching
        # Manual alias map: DB name fragment → Odds API name fragment (both lowercased, accent-stripped)
        _TEAM_ALIASES = {
            # UCL / international
            "sporting clube de portugal": "sporting lisbon",
            "sporting cp": "sporting lisbon",
            "club atletico de madrid": "atletico madrid",
            "atletico de madrid": "atletico madrid",
            "fc internazionale milano": "inter milan",
            "inter milano": "inter milan",
            "internazionale": "inter milan",
            "borussia dortmund": "dortmund",
            "rb leipzig": "leipzig",
            "rasenballsport leipzig": "leipzig",
            "arsenal fc": "arsenal",
            "chelsea fc": "chelsea",
            "manchester city fc": "manchester city",
            "manchester united fc": "manchester united",
            "liverpool fc": "liverpool",
            "tottenham hotspur fc": "tottenham hotspur",
            "aston villa fc": "aston villa",
            "newcastle united fc": "newcastle united",
            "west ham united fc": "west ham",
            "wolverhampton wanderers fc": "wolves",
            "wolverhampton wanderers": "wolves",
            "nottingham forest fc": "nottingham forest",
            "brighton & hove albion fc": "brighton",
            "brighton and hove albion": "brighton",
            "brentford fc": "brentford",
            "fulham fc": "fulham",
            "crystal palace fc": "crystal palace",
            "everton fc": "everton",
            "ipswich town fc": "ipswich",
            "leicester city fc": "leicester",
            "southampton fc": "southampton",
            "paris saint-germain fc": "paris saint-germain",
            "paris saint germain": "paris saint-germain",
            "olympique de marseille": "marseille",
            "olympique lyonnais": "lyon",
            "stade rennais fc": "rennes",
            "rc lens": "lens",
            "ogc nice": "nice",
            "as monaco fc": "monaco",
            "fc girondins de bordeaux": "bordeaux",
            "fc nantes": "nantes",
            "fc lorient": "lorient",
            "fc metz": "metz",
            "stade brestois 29": "brest",
            "bayer 04 leverkusen": "bayer leverkusen",
            "bayer leverkusen": "leverkusen",
            "fc bayern munchen": "bayern munich",
            "fc bayern münchen": "bayern munich",
            "vfb stuttgart": "stuttgart",
            "eintracht frankfurt": "frankfurt",
            "sc freiburg": "freiburg",
            "1. fc union berlin": "union berlin",
            "1. fsv mainz 05": "mainz",
            "tsg 1899 hoffenheim": "hoffenheim",
            "sv werder bremen": "werder bremen",
            "vfl wolfsburg": "wolfsburg",
            "vfl bochum 1848": "bochum",
            "fc augsburg": "augsburg",
            "1. fc heidenheim 1846": "heidenheim",
            "fc st. pauli 1910": "st. pauli",
            "ac milan": "milan",
            "as roma": "roma",
            "ssc napoli": "napoli",
            "juventus fc": "juventus",
            "acf fiorentina": "fiorentina",
            "s.s. lazio": "lazio",
            "ss lazio": "lazio",
            "atalanta bc": "atalanta",
            "torino fc": "torino",
            "udinese calcio": "udinese",
            "us sassuolo calcio": "sassuolo",
            "fc empoli": "empoli",
            "hellas verona fc": "verona",
            "cagliari calcio": "cagliari",
            "bologna fc 1909": "bologna",
            "real madrid cf": "real madrid",
            "fc barcelona": "barcelona",
            "sevilla fc": "sevilla",
            "villarreal cf": "villarreal",
            "real betis balompie": "real betis",
            "real betis balompié": "real betis",
            "athletic club": "athletic bilbao",
            "real sociedad de futbol": "real sociedad",
            "deportivo alaves": "alaves",
            "getafe cf": "getafe",
            "rayo vallecano de madrid": "rayo vallecano",
            "ud las palmas": "las palmas",
            "cd leganes": "leganes",
            "real valladolid cf": "valladolid",
            "girona fc": "girona",
            "osasuna": "osasuna",
            "cd espanyol de barcelona": "espanyol",
        }

        def normalize_team_name(name):
            """Remove common prefixes/suffixes and extra words for better matching."""
            import unicodedata

            if not name:
                return ""
            name = str(name).lower().strip()
            # Remove accents (é -> e, á -> a, etc.)
            name = ''.join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn')
            # Normalize ampersands and "and"
            name = name.replace(' & ', ' and ')

            # Apply manual alias map before further stripping
            if name in _TEAM_ALIASES:
                return _TEAM_ALIASES[name]

            # Remove common club prefixes (but keep meaningful parts like "real", "athletic")
            prefixes = ['afc ', 'fc ', 'club ', 'ca ']
            for prefix in prefixes:
                if name.startswith(prefix):
                    name = name[len(prefix):].strip()
            # Remove "de futbol" and similar Spanish phrases
            name = name.replace(' de futbol', '').replace(' de futbol', '')
            # Remove common club suffixes (keep the city identifier like "de madrid", "de bilbao")
            suffixes = [' fc', ' afc', ' cf', ' ud', ' united', ' city', ' albion']
            for suffix in suffixes:
                if name.endswith(suffix):
                    name = name[:-len(suffix)].strip()

            # Re-check alias map after stripping (catches "fc barcelona" → "barcelona" → alias)
            if name in _TEAM_ALIASES:
                return _TEAM_ALIASES[name]

            return name

        target_match_odds = None
        home_normalized = normalize_team_name(home_team)
        away_normalized = normalize_team_name(away_team)

        self.logger.info(f"DEBUG: Looking for normalized match: '{home_normalized}' vs '{away_normalized}'")
        self.logger.info(f"DEBUG: Total API events returned: {len(odds_data_from_api)}")
        if odds_data_from_api:
            self.logger.info(f"DEBUG: Sample API teams (first 3): {[(e.get('home_team'), e.get('away_team')) for e in odds_data_from_api[:3]]}")

        for event in odds_data_from_api:
            event_home_normalized = normalize_team_name(event.get('home_team', ''))
            event_away_normalized = normalize_team_name(event.get('away_team', ''))

            # Try exact match first, then substring match
            home_match = (home_normalized == event_home_normalized) or \
                        (home_normalized in event_home_normalized) or \
                        (event_home_normalized in home_normalized)
            away_match = (away_normalized == event_away_normalized) or \
                        (away_normalized in event_away_normalized) or \
                        (event_away_normalized in away_normalized)

            if home_match and away_match:
                target_match_odds = event
                self.logger.info(f"✅ DataAgent: Matched API event '{event['home_team']} vs {event['away_team']}' for DB match '{home_team} vs {away_team}'.")
                break
            else:
                self.logger.debug(f"DEBUG: No match - API event: '{event_home_normalized}' vs '{event_away_normalized}' | DB teams: '{home_normalized}' vs '{away_normalized}'")

        if not target_match_odds:
            self.logger.warning(f"❌ DataAgent: Could not find odds for '{home_team} vs {away_team}' in API response.")
            self.logger.info(f"   League: {league_name} | Sport Key: {odds_api_sport}")
            self.logger.info(f"   API returned {len(odds_data_from_api)} matches but none matched the team names.")
            self.logger.info(f"   This match may not have live odds available from The Odds API yet.")
            return None

        # 5. Extract H2H odds and store them
        odds_to_store = {"home_team_odds": None, "draw_odds": None, "away_team_odds": None} # Use DB column names

        bookmakers = target_match_odds.get("bookmakers", [])
        if not bookmakers:
            self.logger.warning(f"No bookmakers found for match {home_team} vs {away_team} in API response.")
            return None

        # Take odds from the first bookmaker that provides complete H2H odds
        for bookmaker in bookmakers:
            for market in bookmaker.get("markets", []):
                if market.get("key") == "h2h":
                    temp_odds = {"home": None, "draw": None, "away": None}
                    for outcome in market.get("outcomes", []):
                        name = outcome.get("name", "").lower()
                        price = outcome.get("price")

                        # Use normalized names for matching outcomes
                        outcome_normalized = normalize_team_name(name)

                        if outcome_normalized == home_normalized or home_normalized in outcome_normalized or outcome_normalized in home_normalized:
                            temp_odds["home"] = price
                        elif outcome_normalized == away_normalized or away_normalized in outcome_normalized or outcome_normalized in away_normalized:
                            temp_odds["away"] = price
                        elif name == "draw":
                            temp_odds["draw"] = price
                    
                    # Check if we have complete H2H odds for the specific sport
                    if temp_odds["home"] is not None and temp_odds["away"] is not None:
                        if sport_type_from_db == "football" and temp_odds["draw"] is None:
                            continue # Football needs draw odds, if missing, check next bookmaker
                        
                        # We found a suitable set of odds
                        odds_to_store["home_team_odds"] = temp_odds["home"]
                        odds_to_store["away_team_odds"] = temp_odds["away"]
                        odds_to_store["draw_odds"] = temp_odds["draw"] # Will be None for non-draw sports
                        
                        # Store these odds in the database
                        conn_store = sqlite3.connect(self.db_path, check_same_thread=False)
                        cursor_store = conn_store.cursor()
                        try:
                            cursor_store.execute(
                                '''INSERT INTO odds (match_id, bookmaker, bet_type, home_team_odds, draw_odds, away_team_odds, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?)''',
                                (match_id, bookmaker.get("title", "Unknown Bookmaker"), "h2h",
                                 odds_to_store["home_team_odds"], odds_to_store["draw_odds"],
                                 odds_to_store["away_team_odds"], datetime.now().isoformat())
                            )
                            conn_store.commit()
                            self.logger.info(f"Stored H2H odds from {bookmaker.get('title', 'Unknown')} for match ID {match_id}.")
                        except Exception as e:
                            self.logger.error(f"Error storing odds for match ID {match_id}: {e}")
                        finally:
                            conn_store.close()

                        self.logger.info(f"✅ DataAgent: Extracted and stored odds for '{home_team} vs {away_team}': {odds_to_store}")
                        return odds_to_store

        self.logger.warning(f"Could not find complete H2H odds for '{home_team} vs {away_team}' from any bookmaker "
                            f"in the API response for sport key '{odds_api_sport}'.")
        return None

    # --- PLACEHOLDERS (Cleaned up) ---
    def fetch_stats(self, match_id: int):
        # This function might eventually fetch live stats if you add another API agent for it
        self.logger.info(f"Fetching stats for match ID {match_id} (placeholder).")
        return None
    
    def store_odds(self, match_id, data):
        # This function is now implicitly handled within fetch_odds if new odds are retrieved
        self.logger.debug(f"Called store_odds for match_id {match_id}, but handled internally by fetch_odds.")
        pass
    
    def store_stats(self, match_id, data):
        self.logger.info(f"Storing stats for match ID {match_id} (placeholder).")
        pass
    
    def refresh_data_for_match(self, match_id):
        self.logger.info(f"Refreshing data for match ID {match_id} (placeholder).")
        # In a real scenario, this would trigger fetch_matches, fetch_stats, fetch_odds
        # and store them.
        pass

    def get_recent_matches(self, team_id: int, limit: int = 5) -> List[Dict]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''SELECT * FROM matches WHERE (home_team_id = ? OR away_team_id = ?) AND (status = 'FINISHED' OR status = 'completed' OR status = 'Match Finished') ORDER BY match_date DESC LIMIT ?''', (team_id, team_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]