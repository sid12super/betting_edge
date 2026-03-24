# /utils.py (Conceptual - assuming these are your existing util functions)

import streamlit as st
import pandas as pd
import sqlite3
import os
from data_agent import DataAgent # Import DataAgent directly
from typing import Optional, List, Dict, Any

# --- New/Modified: init_data_agent to handle Odds API key and DataAgent instance ---
def init_data_agent(sport_type: str = "football"):
    openai_api_key = os.getenv("OPENAI_API_KEY")
    odds_api_key = os.getenv("ODDS_API_KEY")

    if not openai_api_key:
        st.error("OPENAI_API_KEY not found in environment variables.")
        st.stop()

    # Check if DataAgent is already initialized for the current sport_type
    # Add a check for st.session_state.data_agent being None *before* trying to access its attributes
    if "data_agent" not in st.session_state or \
       (st.session_state.data_agent is None) or \
       (st.session_state.data_agent.sport_type != sport_type):

        if odds_api_key is None:
            st.warning("ODDS_API_KEY not found in environment variables. Live odds fetching will be disabled.")

        try:
            st.session_state.data_agent = DataAgent(
                sport_type=sport_type,
                db_path="betting_edge.db",
                odds_api_key=odds_api_key
            )
            st.session_state.current_sport_type = sport_type
            st.success(f"DataAgent initialized for {sport_type}.")
        except ValueError as e:
            # Log the specific error from DataAgent.__init__
            st.error(f"Failed to initialize DataAgent for {sport_type}. Error: {e}")
            st.session_state.data_agent = None
            st.session_state.current_sport_type = None
            st.stop() # Stop the app if DataAgent cannot be initialized
    return st.session_state.data_agent

def get_db_connection():
    # This might be used by other parts of the app for direct DB access
    return sqlite3.connect("betting_edge.db", check_same_thread=False)


def fetch_matches_from_db(sport_type: str, team_name: Optional[str] = None,
                          away_team_name: Optional[str] = None,
                          league_name: Optional[str] = None, season: Optional[int] = None,
                          year: Optional[int] = None) -> pd.DataFrame:
    conn = get_db_connection()
    query = "SELECT * FROM matches WHERE sport_type = ?"
    params = [sport_type]

    if team_name and away_team_name:
        # Fixture query: match where team A vs team B in either home/away order
        query += (
            " AND ("
            "(home_team_name LIKE ? AND away_team_name LIKE ?) OR "
            "(home_team_name LIKE ? AND away_team_name LIKE ?)"
            ")"
        )
        params.extend([
            f"%{team_name}%", f"%{away_team_name}%",
            f"%{away_team_name}%", f"%{team_name}%",
        ])
    elif team_name:
        query += " AND (home_team_name LIKE ? OR away_team_name LIKE ?)"
        params.extend([f"%{team_name}%", f"%{team_name}%"])

    if league_name and league_name != "All Leagues":
        query += " AND league_name LIKE ?"
        params.append(f"%{league_name}%")
    
    # Handle season/year based on sport_type (as per your DataAgent logic)
    if sport_type == "football" and season is not None:
        query += " AND season = ?"
        params.append(season)
    elif sport_type in ["college_football", "basketball"] and year is not None:
        query += " AND season = ?" # Assuming college sports also use 'season' column
        params.append(year)

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

# --- REMOVED: direct fetch_match_stats and fetch_odds from utils ---
# These functions will now be called by the respective agents internally
# via their DataAgent instance.
# If you still need a utility to get detailed stats/odds *from the DB only*,
# you could keep a version that directly queries the DB.
# However, for the pipeline's logic flow, the agents themselves are now responsible
# for deciding when to hit the DB vs. the live API for odds/stats.

# Example if you *still* needed to fetch DB-only odds for some reason,
# but it's redundant with DataAgent's fetch_odds now.
# def fetch_odds_from_db_only(match_id: int) -> pd.DataFrame:
#     conn = get_db_connection()
#     df = pd.read_sql_query("SELECT * FROM odds WHERE match_id = ? ORDER BY last_updated DESC LIMIT 1", conn, params=(match_id,))
#     conn.close()
#     return df

# def fetch_match_stats_from_db_only(match_id: int) -> pd.DataFrame:
#     conn = get_db_connection()
#     df = pd.read_sql_query("SELECT * FROM match_stats WHERE match_id = ?", conn, params=(match_id,))
#     conn.close()
#     return df



def get_unique_leagues(sport_type: str) -> list[str]:
    """Get all unique leagues for the selected sport_type from the DB."""
    if not os.path.exists("betting_edge.db"):
        return ["All Leagues"]
    conn = get_db_connection()
    query = "SELECT DISTINCT league_name FROM matches WHERE sport_type = ? ORDER BY league_name"
    try:
        df = pd.read_sql_query(query, conn, params=(sport_type,))
        conn.close()
        return ["All Leagues"] + df["league_name"].tolist()
    except Exception as e:
        print(f"Error getting unique leagues for sport_type {sport_type}: {e}")
        conn.close()
        return ["All Leagues"]