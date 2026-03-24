# /streamlit_app.py
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from utils import (
    fetch_matches_from_db,
    init_data_agent,
    get_db_connection,
    get_unique_leagues,
    #fetch_match_stats,
    #fetch_odds # This can likely be removed if DataAgent.fetch_odds is used directly
)
import os
from data_agent import DataAgent
from dotenv import load_dotenv
from typing import Optional
import uuid
import json
from pathlib import Path
from datetime import datetime

# Existing query agent import (still used inside the pipeline)
from query_agent import parse_user_query

# New unified multi agent flow
from pipelines.pipeline import BettingEdgePipeline

# NEW: Odds API agent
from odds_agent import OddsAgent

# Scan Mode — direct agent access for batching
from agent_modules.prediction_agent_wrapper import PredictionAgentLC
from agent_modules.verification_agent_wrapper import VerificationAgentLC

load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Betting Edge",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Design System ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
html,body,[class*="css"]{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}

/* Header */
.be-header{font-size:2.6rem;font-weight:800;background:linear-gradient(135deg,#00D2FF,#7B2FFF,#FF0080);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;text-align:center;
  letter-spacing:-0.5px;margin-bottom:4px;}
.be-subtitle{text-align:center;color:#8B8F97;font-size:.9rem;margin-bottom:1.4rem;}

/* Gradient card */
.gc-wrapper{padding:2px;border-radius:14px;margin-bottom:1.1rem;
  display:flex;flex-direction:column;}
.gc-inner{background:rgba(14,17,23,.97);border-radius:12px;padding:22px 26px;
  flex:1;display:flex;flex-direction:column;}
.card-title{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:1.3px;
  color:#8B8F97;margin-bottom:14px;border-bottom:1px solid rgba(255,255,255,.07);padding-bottom:10px;}

/* Equal-height cards inside Streamlit column rows */
div[data-testid="stHorizontalBlock"]{align-items:stretch!important;}
div[data-testid="column"]{display:flex!important;flex-direction:column!important;}
div[data-testid="column"]>div[data-testid="stVerticalBlock"]{flex:1!important;display:flex!important;flex-direction:column!important;}
div[data-testid="column"] .gc-wrapper{flex:1!important;}

/* Metric rows */
.card-metric-row{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:10px;}
.card-metric{flex:1;min-width:110px;}
.cm-label{font-size:.68rem;color:#8B8F97;text-transform:uppercase;letter-spacing:.8px;margin-bottom:4px;}
.cm-value{font-size:1.75rem;font-weight:700;color:#fff;line-height:1.05;}
.cm-value.xl{font-size:2.1rem;}
.cm-value.pos{color:#00E676;}
.cm-value.neg{color:#FF5252;}
.cm-value.warn{color:#FFB300;}
.cm-value.mute{color:#8B8F97;}
.cm-sub{font-size:.7rem;color:#8B8F97;margin-top:3px;}

/* Tags */
.ctag{display:inline-block;padding:3px 11px;border-radius:100px;font-size:.7rem;font-weight:600;letter-spacing:.4px;}
.ctag-safe{background:rgba(0,230,118,.13);color:#00E676;}
.ctag-value{background:rgba(255,179,0,.13);color:#FFB300;}
.ctag-high{background:rgba(255,82,82,.13);color:#FF5252;}
.ctag-blocked{background:rgba(255,82,82,.18);color:#FF5252;}
.ctag-pass{background:rgba(0,230,118,.13);color:#00E676;}
.ctag-fail{background:rgba(255,82,82,.13);color:#FF5252;}
.ctag-neutral{background:rgba(139,143,151,.13);color:#8B8F97;}
.ctag-info{background:rgba(0,210,255,.13);color:#00D2FF;}

/* Recommendation text */
.rec-text{font-size:.95rem;line-height:1.7;color:#E8EAED;}
.info-strip{background:rgba(0,210,255,.07);border-left:3px solid #00D2FF;
  padding:10px 16px;border-radius:0 8px 8px 0;color:#8B8F97;font-size:.83rem;margin:8px 0;}

/* VS badge */
.vs-badge{font-size:1.5rem;font-weight:800;text-align:center;
  background:linear-gradient(135deg,#00D2FF,#7B2FFF);-webkit-background-clip:text;
  -webkit-text-fill-color:transparent;}

/* Stat strip */
.stat-strip{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px;}
.stat-item{flex:1;min-width:110px;padding:14px 18px;background:rgba(255,255,255,.04);
  border-radius:10px;border:1px solid rgba(255,255,255,.07);}
.stat-num{font-size:1.9rem;font-weight:700;color:#fff;}
.stat-lbl{font-size:.68rem;color:#8B8F97;text-transform:uppercase;letter-spacing:.8px;}

/* Buttons */
.stButton>button{border-radius:10px!important;font-weight:600!important;
  letter-spacing:.3px!important;transition:opacity .2s!important;}
.stButton>button:hover{opacity:.85!important;}

/* Metric widget tweak */
div[data-testid="stMetric"]{background:rgba(255,255,255,.03);border-radius:10px;
  padding:12px 16px;border:1px solid rgba(255,255,255,.06);}

/* Hide hamburger menu and Streamlit footer for clean public-facing UI */
#MainMenu{visibility:hidden;}
footer{visibility:hidden;}
</style>
""", unsafe_allow_html=True)


# ── Gradient card helper ───────────────────────────────────────────────────────
import textwrap as _tw

def render_card(title: str, content_html: str,
                gradient: str = "linear-gradient(135deg,#00D2FF 0%,#7B2FFF 55%,#FF0080 100%)",
                icon: str = ""):
    # Strip leading indentation + surrounding whitespace so Streamlit's markdown
    # parser never sees 4-space-indented lines and misinterprets them as code blocks.
    content_html = _tw.dedent(content_html).strip()
    title_block = (
        f'<div class="card-title">{icon + " " if icon else ""}{title}</div>'
        if title else ""
    )
    html = (
        f'<div class="gc-wrapper" style="background:{gradient};">'
        f'<div class="gc-inner">{title_block}{content_html}</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

# Initialize session state from environment variables
if "api_key_football" not in st.session_state:
    st.session_state.api_key_football = os.getenv("API_KEY_FOOTBALL", "KEY_NOT_FOUND")
if "api_key_cfb" not in st.session_state:
    st.session_state.api_key_cfb = os.getenv("API_KEY_CFB", "KEY_NOT_FOUND")
if "api_key_basketball" not in st.session_state:
    st.session_state.api_key_basketball = os.getenv("API_KEY_BASKETBALL", "KEY_NOT_FOUND")
# Ensure Odds API key is loaded for OddsAgent
if "odds_api_key" not in st.session_state:
    st.session_state.odds_api_key = os.getenv("ODDS_API_KEY", "KEY_NOT_FOUND")

if "data_agent" not in st.session_state:
    st.session_state.data_agent = None
if "sport_type" not in st.session_state:
    st.session_state.sport_type = "football"
if "db_initialized" not in st.session_state:
    st.session_state.db_initialized = False
# NEW: cache OddsAgent - This is still good.
if "odds_agent" not in st.session_state:
    st.session_state.odds_agent = None

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "scan_results" not in st.session_state:
    st.session_state.scan_results = None
if "scan_league_label" not in st.session_state:
    st.session_state.scan_league_label = ""


# NEW: helper to map our sport_type -> Odds API sport key
# This mapping should ideally *mirror* the more detailed mapping in DataAgent
# or be moved to a common config/utility file.
# For simplicity here, I'll keep it as a direct map.
def map_sport_to_odds_api(sport_type: str) -> str:
    # This is a basic mapping for the `Odds` tab.
    # The `DataAgent` has a more sophisticated mapping including leagues.
    # For the `Odds` tab, we generally query broader categories.
    mapping = {
        "football": "soccer", # Use a broader category for general display
        "college_football": "americanfootball_ncaaf",
        "basketball": "basketball_ncaab", # Assuming college basketball for now
    }
    # Provide a more general fallback if a specific sport_type is added later
    return mapping.get(sport_type, "soccer")


# NEW: helper to lazily init OddsAgent
def get_odds_agent() -> Optional[OddsAgent]:
    if st.session_state.odds_agent is None:
        try:
            # Pass the API key to the OddsAgent constructor
            if st.session_state.odds_api_key == "KEY_NOT_FOUND":
                st.error("Odds API Key not found. Please set ODDS_API_KEY in your .env file.")
                return None
            st.session_state.odds_agent = OddsAgent(api_key=st.session_state.odds_api_key)
        except ValueError as e: # Catch the specific ValueError from OddsAgent
            st.error(f"Failed to initialize Odds API: {e}")
            st.session_state.odds_agent = None
        except Exception as e:
            st.error(f"An unexpected error occurred initializing Odds API: {e}")
            st.session_state.odds_agent = None
    return st.session_state.odds_agent


# NEW: transform Odds API JSON into a DataFrame
def build_odds_dataframe(odds_data):
    if not odds_data:
        return pd.DataFrame()

    rows = []
    for event in odds_data:
        try:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            # Prefer 'sport_title' for readability, fallback to 'sport_key'
            league = event.get("sport_title", event.get("sport_key", ""))
            commence = event.get("commence_time", "")
            try:
                dt = datetime.fromisoformat(commence.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_str = commence

            bookmakers = event.get("bookmakers", [])
            if not bookmakers:
                continue

            # Use first bookmaker with h2h market
            home_odds = draw_odds = away_odds = None
            bookmaker_name = "N/A" # Default bookmaker name

            # Iterate through bookmakers to find the first one with h2h odds
            for bookmaker in bookmakers:
                bookmaker_name = bookmaker.get("title") or bookmaker.get("key", "Unknown Bookmaker")
                for market in bookmaker.get("markets", []):
                    if market.get("key") == "h2h":
                        for outcome in market.get("outcomes", []):
                            name = outcome.get("name", "")
                            price = outcome.get("price", None)
                            if name == home:
                                home_odds = price
                            elif name == away:
                                away_odds = price
                            elif name.lower() == "draw":
                                draw_odds = price
                        # If we found h2h outcomes, use this bookmaker and break
                        if home_odds is not None and away_odds is not None:
                            break # Break from markets loop
                if home_odds is not None and away_odds is not None:
                    break # Break from bookmakers loop


            rows.append(
                {
                    "Date/Time": date_str,
                    "League": league,
                    "Home Team": home,
                    "Away Team": away,
                    "Bookmaker": bookmaker_name,
                    "Home Odds": home_odds,
                    "Draw Odds": draw_odds,
                    "Away Odds": away_odds,
                }
            )
        except Exception as e:
            st.error(f"Error processing odds event: {e}")
            continue

    return pd.DataFrame(rows)


# ── App Header ────────────────────────────────────────────────────────────────
st.markdown('<div class="be-header">⚽ Betting Edge</div>', unsafe_allow_html=True)
st.markdown('<div class="be-subtitle">AI-Powered Sports Intelligence · Prediction · Verification · Ethics</div>', unsafe_allow_html=True)
st.divider()

# Sidebar configuration
with st.sidebar:
    st.header("⚙️ Configuration")

    sport_type = st.radio(
        "Select Sport",
        options=["football", "college_football", "basketball"],
        format_func=lambda x: {
            "football": "⚽ Soccer (Football-Data.org)",
            "college_football": "🏈 College Football",
            "basketball": "🏀 College Basketball",
        }.get(x),
        index=["football", "college_football", "basketball"].index(
            st.session_state.sport_type
        ),
    )

    # API Key Display
    api_key_map = {
        "football": st.session_state.api_key_football,
        "college_football": st.session_state.api_key_cfb,
        "basketball": st.session_state.api_key_basketball,
    }
    current_key = api_key_map.get(sport_type, "KEY_NOT_FOUND")
    st.text_input(
        "Data Source API Key",
        value="****" + current_key[-8:]
        if current_key != "KEY_NOT_FOUND"
        else "Not Set",
        disabled=True,
    )
    # Display Odds API Key separately
    st.text_input(
        "Odds API Key (TheOddsAPI)",
        value="****" + st.session_state.odds_api_key[-8:]
        if st.session_state.odds_api_key != "KEY_NOT_FOUND"
        else "Not Set",
        disabled=True,
    )

    st.subheader("💵 Bet Budget per Pick")
    bet_budget = st.slider(
        "Max amount to stake on a single recommendation ($)",
        min_value=0,
        max_value=100,
        value=20,
        step=5,
    )
    st.session_state.bet_budget = bet_budget


    if st.button("🔌 Initialize Agent"):
        with st.spinner(f"Initializing {sport_type.replace('_', ' ').title()} Agent..."):
            # Call the init_data_agent from utils.py
            # init_data_agent will now also initialize OddsAgent internally
            initialized_agent = init_data_agent(sport_type)

            if initialized_agent:
                st.session_state.data_agent = initialized_agent
                st.session_state.sport_type = sport_type
                st.session_state.db_initialized = True
                st.success(f"✅ {sport_type.replace('_', ' ').title()} Agent Connected!")
                st.rerun()
            else:
                st.session_state.data_agent = None
                st.session_state.db_initialized = False
                st.error("Failed to initialize agent. Check API key and logs.")

    st.divider()

    # Database status
    st.subheader("📊 Database Status")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Check tables exist before querying — on fresh deployment the file
        # exists but tables are created only after the first agent init
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='matches'"
        )
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) FROM matches")
            match_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM match_stats"
                if cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='match_stats'").fetchone()
                else "SELECT 0"
            )
            stats_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM odds"
                if cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='odds'").fetchone()
                else "SELECT 0"
            )
            odds_count = cursor.fetchone()[0]
            conn.close()
            st.metric("Matches", match_count)
            st.metric("Statistics", stats_count)
            st.metric("Odds Entries", odds_count)
        else:
            conn.close()
            st.info("Click 'Initialize Agent' to set up the database.")
    except Exception:
        st.info("Database not yet initialized")

    st.divider()
    st.subheader("📁 Session & Export")

    session_id = st.session_state.get("session_id", "unknown_session")
    log_dir = Path("session_logs")
    log_path = log_dir / f"session_{session_id}.json"

    if log_path.exists():
        with open(log_path, "r") as f:
            session_json_bytes = f.read().encode("utf-8")

        st.text(f"Session ID: {session_id[:8]}...")
        st.download_button(
            label="⬇️ Download Session JSON",
            data=session_json_bytes,
            file_name=f"betting_edge_session_{session_id}.json",
            mime="application/json",
        )
    else:
        st.info("No deep analysis runs logged yet for this session.")

    st.divider()

    # Manual data fetching
    if st.session_state.data_agent:
        with st.expander("🛠️ Manual Data Tools"):
            st.subheader("Fetch Data Manually")

            if st.session_state.sport_type == "football":
                league_options = {
                    "Premier League": 39,
                    "La Liga": 140,
                    "Serie A": 135,
                    "Bundesliga": 78,
                    "Ligue 1": 61,
                    "Champions League": 2001,
                }
                selected_league = st.selectbox(
                    "Select League", options=list(league_options.keys())
                )
                season = st.number_input(
                    "Season", min_value=2020, max_value=2026, value=2023
                )

                if st.button("📥 Fetch Matches"):
                    with st.spinner("Fetching..."):
                        try:
                            league_id = league_options[selected_league]
                            matches = st.session_state.data_agent.fetch_matches(
                                league_id=league_id, season=season
                            )
                            if matches:
                                count = 0
                                for m in matches:
                                    st.session_state.data_agent.store_match(m)
                                    count += 1
                                st.success(f"Stored {count} matches!")
                                st.rerun() # Rerun to update dashboard counts
                            else:
                                st.warning("No matches found.")
                        except Exception as e:
                            st.error(f"Error: {e}")

            else: # College Football/Basketball
                year = st.number_input(
                    "Year", min_value=2020, max_value=2026, value=2024
                )
                if st.button("📥 Fetch Games"):
                    with st.spinner("Fetching..."):
                        try:
                            matches = st.session_state.data_agent.fetch_matches(
                                year=year
                            )
                            if matches:
                                count = 0
                                for m in matches:
                                    st.session_state.data_agent.store_match(m)
                                    count += 1
                                st.success(f"Stored {count} games!")
                                st.rerun() # Rerun to update dashboard counts
                            else:
                                st.warning("No games found.")
                        except Exception as e:
                            st.error(f"Error: {e}")


# Main content
if not st.session_state.data_agent:
    st.info("👋 Welcome! Please select a sport and click 'Initialize Agent' in the sidebar to begin.")
else:
    tab1, tab2, tab3, tab4 = st.tabs(
        ["🤖 AI Assistant", "🏠 Dashboard", "📊 Statistics", "💰 Odds"]
    )

    # AI Assistant tab using unified pipeline
    with tab1:
        st.header("🤖 AI Sports Assistant")
        st.markdown(
            "Use natural language to query the multi agent flow. "
            "The system will parse your request, fetch data, run prediction, verification, behavior selection, recommendation, and ethics checks."
        )

        if st.session_state.sport_type == "football":
            assistant_mode = st.radio(
                "Mode",
                ["Query Mode", "Scan Mode"],
                horizontal=True,
                key="assistant_mode",
            )
        else:
            assistant_mode = "Query Mode"

        # ── SCAN MODE ─────────────────────────────────────────────────────────
        if assistant_mode == "Scan Mode":
            render_card(
                "League Scanner",
                """
                <div class="card-metric-row">
                  <div class="card-metric">
                    <div class="cm-label">How it works</div>
                    <div class="cm-sub">Pick a league → hit Scan. The system fetches all upcoming fixtures
                    from the database, runs XGBoost + value verification on every match, then ranks
                    by value edge. Use the sidebar Manual Data Tools to fetch the latest fixtures first.</div>
                  </div>
                </div>
                """,
                icon="🔍",
                gradient="linear-gradient(135deg,#00D2FF 0%,#7B2FFF 100%)",
            )

            _SCAN_LEAGUES = {
                "Premier League": "Premier League",
                "La Liga": "Primera Division",
                "Bundesliga": "Bundesliga",
                "Serie A": "Serie A",
                "Ligue 1": "Ligue 1",
                "Champions League": "UEFA Champions League",
            }

            sc_col1, sc_col2, sc_col3 = st.columns([2, 1, 1])
            with sc_col1:
                scan_league_label = st.selectbox(
                    "Select League to Scan",
                    options=list(_SCAN_LEAGUES.keys()),
                    key="scan_league_select",
                )
            with sc_col2:
                scan_min_edge = st.select_slider(
                    "Min Edge Filter",
                    options=["All", "5%+", "10%+", "15%+"],
                    value="All",
                    key="scan_min_edge",
                )
            with sc_col3:
                scan_positive_only = st.checkbox(
                    "Positive edge only",
                    value=False,
                    key="scan_positive_only",
                )

            if st.button("Scan League", key="scan_run_btn", type="primary"):
                _scan_league_db = _SCAN_LEAGUES[scan_league_label]
                _conn = get_db_connection()
                _scan_df = pd.read_sql_query(
                    """SELECT match_id, match_date, home_team_id, home_team_name,
                              away_team_id, away_team_name, league_name, season, status, sport_type
                       FROM matches
                       WHERE sport_type = 'football'
                         AND league_name = ?
                         AND status NOT IN (
                             'FINISHED','COMPLETED','MATCH FINISHED','Match Finished',
                             'finished','completed','Match Cancelled'
                         )
                         AND match_date >= datetime('now', '-1 day')
                         AND match_id IS NOT NULL
                         AND home_team_name IS NOT NULL AND home_team_name != ''
                         AND away_team_name IS NOT NULL AND away_team_name != ''
                       ORDER BY match_date ASC
                       LIMIT 20""",
                    _conn,
                    params=(_scan_league_db,),
                )
                _conn.close()

                if _scan_df.empty:
                    st.warning(
                        f"No upcoming {scan_league_label} fixtures found in the database. "
                        "Use the **Manual Data Tools** expander in the sidebar to fetch the latest matches first."
                    )
                    st.session_state.scan_results = None
                else:
                    _pred_agent = PredictionAgentLC()
                    _verif_agent = VerificationAgentLC(sport_type="football")
                    _scan_results = []
                    _prog = st.progress(0, text="Starting scan…")
                    for _idx, (_, _row) in enumerate(_scan_df.iterrows()):
                        _match_dict = {
                            "fixture": {
                                "id": int(_row["match_id"]) if pd.notna(_row["match_id"]) else 0,
                                "date": str(_row["match_date"]),
                                "status": str(_row["status"]),
                            },
                            "league": {
                                "name": str(_row["league_name"]),
                                "season": int(_row["season"]) if pd.notna(_row["season"]) else 2025,
                            },
                            "teams": {
                                "home": {"id": int(_row["home_team_id"]) if pd.notna(_row["home_team_id"]) else 0, "name": str(_row["home_team_name"])},
                                "away": {"id": int(_row["away_team_id"]) if pd.notna(_row["away_team_id"]) else 0, "name": str(_row["away_team_name"])},
                            },
                            "goals": {"home": None, "away": None},
                            "score": {"fulltime": {"home": None, "away": None}},
                            "sport_type": "football",
                        }
                        _pred = _pred_agent.invoke(_match_dict)
                        _verif = _verif_agent.invoke({"match": _match_dict, "prediction": _pred})
                        _raw_edge = _verif.get("raw_value_edge")
                        if not isinstance(_raw_edge, (int, float)):
                            _raw_edge = 0.0
                        _scan_results.append({
                            "match": _match_dict,
                            "prediction": _pred,
                            "verification": _verif,
                            "raw_edge": float(_raw_edge),
                        })
                        _prog.progress(
                            (_idx + 1) / len(_scan_df),
                            text=f"Scanning {_idx + 1}/{len(_scan_df)}: "
                                 f"{_row['home_team_name']} vs {_row['away_team_name']}",
                        )

                    _scan_results.sort(key=lambda x: x["raw_edge"], reverse=True)
                    st.session_state.scan_results = _scan_results
                    st.session_state.scan_league_label = scan_league_label
                    _prog.empty()
                    st.rerun()

            # ── Render cached scan results ─────────────────────────────────────
            if st.session_state.get("scan_results"):
                _results = st.session_state.scan_results
                _cached_league = st.session_state.get("scan_league_label", "")

                # Apply filters
                _filtered = _results
                if scan_positive_only:
                    _filtered = [r for r in _filtered if r["raw_edge"] > 0]
                if scan_min_edge == "5%+":
                    _filtered = [r for r in _filtered if r["raw_edge"] >= 0.05]
                elif scan_min_edge == "10%+":
                    _filtered = [r for r in _filtered if r["raw_edge"] >= 0.10]
                elif scan_min_edge == "15%+":
                    _filtered = [r for r in _filtered if r["raw_edge"] >= 0.15]

                _top = _filtered[:7]
                st.markdown(f"### Top Opportunities — {_cached_league}")
                st.caption(
                    f"Showing {len(_top)} of {len(_filtered)} matches · sorted by value edge · "
                    f"{len(_results)} total scanned"
                )

                if not _top:
                    st.info("No matches meet the current filter criteria.")
                else:
                    for _rank, _r in enumerate(_top, 1):
                        _m = _r["match"]
                        _pred = _r["prediction"]
                        _verif = _r["verification"]
                        _raw_edge = _r["raw_edge"]

                        _home = _m["teams"]["home"]["name"]
                        _away = _m["teams"]["away"]["name"]
                        _kickoff = str(_m["fixture"]["date"])[:16].replace("T", " ")
                        _winner = _pred.get("predicted_winner_model", "N/A")
                        _conf = _verif.get("confidence", "--")
                        _rec = _verif.get("recommended_bet_side") or "None"

                        if _rec.lower() == "draw":
                            _rec_display = "Draw"
                        elif "_win" in _rec:
                            _rec_display = _rec.replace("_win", "")
                        else:
                            _rec_display = _rec

                        if _raw_edge >= 0.15:
                            _grad = "linear-gradient(135deg,#00C853 0%,#1B5E20 100%)"
                            _edge_tag = '<span class="ctag ctag-safe">HIGH EDGE</span>'
                        elif _raw_edge >= 0.05:
                            _grad = "linear-gradient(135deg,#FFB300 0%,#E65100 100%)"
                            _edge_tag = '<span class="ctag ctag-value">MED EDGE</span>'
                        else:
                            _grad = "linear-gradient(135deg,#455A64 0%,#263238 100%)"
                            _edge_tag = '<span class="ctag ctag-neutral">LOW EDGE</span>'

                        _edge_display = f"{_raw_edge:.2%}" if _raw_edge != 0.0 else "N/A"
                        _edge_cls = "pos" if _raw_edge > 0 else ("neg" if _raw_edge < 0 else "mute")
                        _h_prob = _pred.get("home_win_probability", 0.0)
                        _d_prob = _pred.get("draw_probability", 0.0)
                        _a_prob = _pred.get("away_win_probability", 0.0)

                        render_card(
                            f"#{_rank} · {_home} vs {_away}",
                            icon="⚽",
                            gradient=_grad,
                            content_html=f"""
                            <div class="card-metric-row">
                              <div class="card-metric" style="flex:2;min-width:150px;">
                                <div class="cm-label">Kickoff</div>
                                <div class="cm-value" style="font-size:1rem;">{_kickoff}</div>
                              </div>
                              <div class="card-metric">
                                <div class="cm-label">Value Edge</div>
                                <div class="cm-value xl {_edge_cls}">{_edge_display}</div>
                                <div class="cm-sub">{_edge_tag}</div>
                              </div>
                              <div class="card-metric">
                                <div class="cm-label">Predicted Winner</div>
                                <div class="cm-value" style="font-size:1.1rem;">{_winner}</div>
                              </div>
                              <div class="card-metric">
                                <div class="cm-label">Confidence</div>
                                <div class="cm-value" style="font-size:1.1rem;">{_conf}</div>
                              </div>
                              <div class="card-metric">
                                <div class="cm-label">Bet Side</div>
                                <div class="cm-value" style="font-size:1.1rem;">{_rec_display}</div>
                              </div>
                            </div>
                            <div class="card-metric-row" style="margin-top:2px;">
                              <div class="card-metric">
                                <div class="cm-label">Home {_home[:18]}</div>
                                <div style="font-size:.9rem;color:#8B8F97;">{_h_prob:.1%}</div>
                              </div>
                              <div class="card-metric">
                                <div class="cm-label">Draw</div>
                                <div style="font-size:.9rem;color:#8B8F97;">{_d_prob:.1%}</div>
                              </div>
                              <div class="card-metric">
                                <div class="cm-label">Away {_away[:18]}</div>
                                <div style="font-size:.9rem;color:#8B8F97;">{_a_prob:.1%}</div>
                              </div>
                            </div>
                            """,
                        )

        # ── QUERY MODE ────────────────────────────────────────────────────────
        else:
            # ── Betting Profile card ───────────────────────────────────────────────
            render_card(
                "Your Betting Profile",
                """
                <div class="card-metric-row">
                  <div class="card-metric" style="flex:0 0 auto;">
                    <div class="cm-label">Risk Mode</div>
                    <div class="cm-value" id="risk-badge" style="font-size:1.1rem;">▼ set below</div>
                  </div>
                  <div class="card-metric">
                    <div class="cm-label">Low Risk</div>
                    <div class="cm-sub">Prefer safer, higher-probability picks</div>
                  </div>
                  <div class="card-metric">
                    <div class="cm-label">Medium Risk</div>
                    <div class="cm-sub">Balance between safety and value edge</div>
                  </div>
                  <div class="card-metric">
                    <div class="cm-label">High Risk</div>
                    <div class="cm-sub">Aggressive bets with higher return potential</div>
                  </div>
            </div>
            <div style="margin-top:10px;padding:10px 0 0;border-top:1px solid rgba(255,255,255,.07);">
              <span class="ctag ctag-info" style="margin-right:8px;">💡 Try</span>
              <span style="color:#8B8F97;font-size:.82rem;">
                "Fetch Premier League matches for Liverpool" &nbsp;·&nbsp;
                "Get 2024 college basketball games for Duke"
              </span>
            </div>
            """,
            icon="👤",
        )

            col_profile_1, col_profile_2 = st.columns([1, 2])
            with col_profile_1:
                risk_tolerance = st.select_slider(
                    "Risk tolerance",
                    options=["Low", "Medium", "High"],
                    value=st.session_state.get("user_risk_tolerance", "Medium"),
                )
                st.session_state.user_risk_tolerance = risk_tolerance

            user_query_tab1 = st.text_input(
                "Ask the Assistant:", placeholder="Type your request here...", key="user_query_tab1"
            )

            if "pipeline_results" not in st.session_state:
                st.session_state.pipeline_results = None
            if "deep_analysis_results" not in st.session_state:
                st.session_state.deep_analysis_results = None

            selected_match_for_analysis = None

            if st.button("🚀 Run Initial Query") and user_query_tab1:
                # Pass the initialized data_agent to the pipeline
                pipeline = BettingEdgePipeline()

                with st.spinner("Running initial query and data agent..."):
                    result = pipeline.run(user_query_tab1)
                    st.session_state.pipeline_results = result
                    st.session_state.deep_analysis_results = None
                st.experimental_rerun()

            if st.session_state.pipeline_results:
                initial_query_result = st.session_state.pipeline_results

                if initial_query_result.get("status") == "ok":
                    st.success(initial_query_result.get("message", "Initial query successful."))

                    filtered_matches = initial_query_result.get("filtered_matches", [])
                    if filtered_matches:
                        st.subheader("Select a Match for Deep Analysis:")
                        match_options = {
                            f"{m['teams']['home']['name']} vs {m['teams']['away']['name']} on {m['fixture']['date'][:10]} (ID: {m['fixture']['id']})": m
                            for m in filtered_matches
                        }
                        selected_match_key = st.selectbox(
                            "Choose a match:",
                            options=list(match_options.keys()),
                            key="match_selector"
                        )

                        if selected_match_key:
                            selected_match_for_analysis = match_options[selected_match_key]

                            if st.button("▶️ Run Deep Analysis for Selected Match", key="run_deep_analysis_button"):
                                # Build user context for behavior agent
                                user_context = {
                                    "risk_tolerance": st.session_state.get("user_risk_tolerance", "Medium"),
                                    "user_id": "default_user",
                                }

                                pipeline = BettingEdgePipeline()
                                with st.spinner("Running prediction, verification, behavior, recommendation, and ethics agents..."):
                                    deep_analysis_results = pipeline.run_deep_analysis(
                                        selected_match_for_analysis,
                                        user_context=user_context,
                                    )
                                    st.session_state.deep_analysis_results = deep_analysis_results

                                    # 🔹 NEW: persist this analysis to a per-session JSON log
                                    try:
                                        session_id = st.session_state.get("session_id", "unknown_session")
                                        log_dir = Path("session_logs")
                                        log_dir.mkdir(exist_ok=True)

                                        log_path = log_dir / f"session_{session_id}.json"

                                        # Load existing log (if any)
                                        existing_entries = []
                                        if log_path.exists():
                                            try:
                                                with open(log_path, "r") as f:
                                                    existing_entries = json.load(f)
                                                if not isinstance(existing_entries, list):
                                                    existing_entries = [existing_entries]
                                            except Exception:
                                                existing_entries = []

                                        # Build new entry
                                        new_entry = {
                                            "timestamp": datetime.utcnow().isoformat(),
                                            "user_context": user_context,
                                            "behavior_user_profile": deep_analysis_results.get("behavior_user_profile"),
                                            "behavior_bucket": deep_analysis_results.get("behavior_bucket"),
                                            "analysis": deep_analysis_results,
                                        }

                                        existing_entries.append(new_entry)

                                        with open(log_path, "w") as f:
                                            json.dump(existing_entries, f, indent=2, default=str)
                                    except Exception as e:
                                        st.warning(f"Warning: Failed to write session log: {e}")

                                st.experimental_rerun()

                    else:
                        st.warning(initial_query_result.get("message", "Agent understood the query, but found no matches."))

                elif initial_query_result.get("status") == "query_error":
                    st.error(initial_query_result.get("message", "Query agent could not parse that request."))
                elif initial_query_result.get("status") == "no_matches":
                    st.warning(initial_query_result.get("message", "No matches found from data agent for that sport/season."))
                else:
                    st.error(initial_query_result.get("message", "An unexpected error occurred during the initial query phase."))

            if 'deep_analysis_results' in st.session_state and st.session_state.deep_analysis_results:
                deep_analysis_result = st.session_state.deep_analysis_results

                if deep_analysis_result.get("status") == "ok":
                    st.success("Deep Analysis Complete!")

                    # Optional: past-match notice
                    selected_match = deep_analysis_result.get("match") or selected_match_for_analysis or {}
                    status = (selected_match.get("fixture", {}).get("status") or "").lower()
                    if status in ["finished", "ft", "full-time", "match finished", "completed"]:
                        st.markdown(
                            '<div class="info-strip">ℹ️ This is a <strong>past match</strong>. '
                            'The assistant will provide retrospective analysis only — no betting advice.</div>',
                            unsafe_allow_html=True,
                        )

                    st.markdown("---")

                    # ── helpers for card rendering ─────────────────────────────
                    def _prob_cls(p):
                        if isinstance(p, float):
                            return "pos" if p >= 0.5 else ("warn" if p >= 0.3 else "mute")
                        return "mute"

                    # -------- ROW 1: Prediction + Value --------
                    col1, col2 = st.columns(2)

                    with col1:
                        pred = deep_analysis_result.get('prediction', {})
                        h_prob = pred.get('home_win_probability', 0.0)
                        d_prob = pred.get('draw_probability', 0.0)
                        a_prob = pred.get('away_win_probability', 0.0)
                        winner = pred.get('predicted_winner_model', 'N/A')
                        render_card(
                            "Prediction Model Output", icon="📊",
                            content_html=f"""
                            <div class="card-metric-row">
                              <div class="card-metric">
                                <div class="cm-label">Predicted Winner</div>
                                <div class="cm-value" style="font-size:1.2rem;">{winner}</div>
                                <div class="cm-sub">Model top pick</div>
                              </div>
                            </div>
                            <div class="card-metric-row">
                              <div class="card-metric">
                                <div class="cm-label">Home Win</div>
                                <div class="cm-value xl {_prob_cls(h_prob)}">{h_prob:.1%}</div>
                              </div>
                              <div class="card-metric">
                                <div class="cm-label">Draw</div>
                                <div class="cm-value xl {_prob_cls(d_prob)}">{d_prob:.1%}</div>
                              </div>
                              <div class="card-metric">
                                <div class="cm-label">Away Win</div>
                                <div class="cm-value xl {_prob_cls(a_prob)}">{a_prob:.1%}</div>
                              </div>
                            </div>
                            """,
                        )

                    with col2:
                        verify = deep_analysis_result.get('verification', {})
                        raw_value_edge = verify.get('raw_value_edge')
                        raw_value_edge_display = (
                            f"{raw_value_edge:.2%}"
                            if isinstance(raw_value_edge, (int, float))
                            else "N/A"
                        )
                        edge_cls = (
                            "pos" if isinstance(raw_value_edge, float) and raw_value_edge > 0
                            else ("neg" if isinstance(raw_value_edge, float) and raw_value_edge < 0
                                  else "mute")
                        )
                        # Get risk-aware recommendation (not just value-based)
                        recommendation = deep_analysis_result.get('recommendation', {})
                        risk_aware_bet_side = recommendation.get('recommended_bet_side', 'None')
                        recommendation_strategy = recommendation.get('recommendation_strategy', 'SAFE')

                        # Format display (handle Draw, Home win, Away win)
                        if risk_aware_bet_side and risk_aware_bet_side.lower() == "draw":
                            bet_side_display = "🔄 Draw"
                        elif risk_aware_bet_side and "_win" in risk_aware_bet_side:
                            team_name = risk_aware_bet_side.replace("_win", "")
                            bet_side_display = f"✓ {team_name}"
                        else:
                            bet_side_display = risk_aware_bet_side

                        # Add strategy indicator
                        if recommendation_strategy == "BLOCKED":
                            strategy_emoji = "⛔"
                            bet_side_display = "NONE"
                            strat_tag_cls = "ctag-blocked"
                        elif recommendation_strategy == "VALUE":
                            strategy_emoji = "💰"
                            strat_tag_cls = "ctag-value"
                        else:
                            strategy_emoji = "🛡️"
                            strat_tag_cls = "ctag-safe"

                        conf = verify.get('confidence', 'Low')
                        conf_cls = "ctag-pass" if conf == "High" else ("ctag-value" if conf == "Medium" else "ctag-neutral")
                        edge_rating = verify.get('value_edge_rating', 'N/A')
                        rating_cls = "ctag-pass" if edge_rating == "High" else ("ctag-value" if edge_rating == "Medium" else "ctag-neutral")

                        render_card(
                            "Value Verification", icon="🔍",
                            content_html=f"""
                            <div class="card-metric-row">
                              <div class="card-metric">
                                <div class="cm-label">Raw Value Edge</div>
                                <div class="cm-value xl {edge_cls}">{raw_value_edge_display}</div>
                                <div class="cm-sub"><span class="ctag {rating_cls}">Rating: {edge_rating}</span></div>
                              </div>
                              <div class="card-metric">
                                <div class="cm-label">Confidence</div>
                                <div class="cm-value" style="font-size:1.2rem;">{conf}</div>
                                <div class="cm-sub"><span class="ctag {conf_cls}">{conf}</span></div>
                              </div>
                            </div>
                            <div style="margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,.07);">
                              <div class="cm-label">Risk-Aware Recommendation</div>
                              <div style="margin-top:6px;display:flex;align-items:center;gap:8px;">
                                <span style="font-size:1.3rem;font-weight:700;color:#fff;">{strategy_emoji} {bet_side_display}</span>
                                <span class="ctag {strat_tag_cls}">{recommendation_strategy}</span>
                              </div>
                            </div>
                            """,
                        )

                    # -------- ROW 2: Behavior + Ethics --------
                    st.divider()
                    beh_col, eth_col = st.columns([2, 1])

                    # ---- Behavior column ----
                    with beh_col:
                        action_output = deep_analysis_result.get('action', {})

                        if isinstance(action_output, str):
                            action_tag = action_output
                            bucket_name = action_output
                            bucket_description = ""
                            risk_factor_display = "N/A"
                            risk_factor = None
                            user_profile_display = None
                        else:
                            action_tag = action_output.get("action", "SAFE_PICK")
                            bucket_name = action_output.get("bucket_label") or action_tag
                            bucket_description = action_output.get("bucket_description", "")
                            risk_factor = action_output.get("risk_factor", None)
                            risk_factor_display = (
                                f"{risk_factor:.2f}"
                                if isinstance(risk_factor, (int, float))
                                else "N/A"
                            )
                            user_profile_display = action_output.get("user_profile")

                        # Budget-based suggested stake
                        bet_budget = st.session_state.get("bet_budget", 0)
                        stake_fraction_map = {
                            "SAFE_PICK": 0.5,
                            "VALUE_BET": 0.35,
                            "HIGH_RISK": 0.15,
                            "EXPLANATION_ONLY": 0.0,
                        }
                        stake_fraction = stake_fraction_map.get(action_tag, 0.0)
                        suggested_stake = round(bet_budget * stake_fraction, 2)

                        recommendation = deep_analysis_result.get("recommendation", {})
                        recommended_side = recommendation.get("recommended_bet_side", "None")
                        recommendation_strategy = recommendation.get("recommendation_strategy", "SAFE")
                        safest_bet = recommendation.get("safest_bet_side", "N/A")
                        safest_prob = recommendation.get("safest_probability", 0.0)

                        if recommended_side and recommended_side.lower() == "draw":
                            bet_display = "🔄 Draw"
                        elif recommended_side and "_win" in recommended_side:
                            team_name = recommended_side.replace("_win", "")
                            bet_display = f"✓ {team_name}"
                        else:
                            bet_display = recommended_side

                        strategy_emoji = "🛡️" if recommendation_strategy == "SAFE" else "💰"
                        strategy_label = "Safer bet" if recommendation_strategy == "SAFE" else "Value bet"

                        bkt_tag_cls = {
                            "SAFE_PICK": "ctag-safe",
                            "VALUE_BET": "ctag-value",
                            "HIGH_RISK": "ctag-high",
                            "EXPLANATION_ONLY": "ctag-neutral",
                        }.get(action_tag, "ctag-neutral")

                        rf_cls = "mute"
                        if isinstance(risk_factor, float):
                            rf_cls = "pos" if risk_factor < 0.4 else ("warn" if risk_factor < 0.7 else "neg")

                        if bet_budget > 0 and suggested_stake > 0:
                            stake_html = (
                                f'<div style="margin-top:8px;">'
                                f'<span class="cm-label">Suggested Stake</span><br>'
                                f'<span style="font-size:1.4rem;font-weight:700;color:#fff;">${suggested_stake:.2f}</span>'
                                f' <span style="color:#8B8F97;font-size:.82rem;">on <strong style="color:#E8EAED;">{bet_display}</strong>'
                                f' {strategy_emoji} {strategy_label}</span>'
                                + (f'<div class="cm-sub" style="margin-top:4px;">📊 Safest: {safest_bet} ({safest_prob:.1%})</div>'
                                   if safest_bet != "N/A" else "")
                                + f'<div class="cm-sub">from ${bet_budget:.2f} per-pick budget</div></div>'
                            )
                        elif bet_budget > 0:
                            stake_html = '<div class="info-strip" style="margin-top:8px;">No stake — this bucket recommends <strong>explanation only</strong>.</div>'
                        else:
                            stake_html = '<div class="info-strip" style="margin-top:8px;">Set a budget in the sidebar to see stake suggestions.</div>'

                        render_card(
                            "Behavior Action", icon="🧠",
                            content_html=f"""
                            <div class="card-metric-row">
                              <div class="card-metric">
                                <div class="cm-label">Behavior Bucket</div>
                                <div class="cm-value" style="font-size:1.2rem;">{bucket_name}</div>
                                <div class="cm-sub"><span class="ctag {bkt_tag_cls}">{action_tag}</span></div>
                              </div>
                              <div class="card-metric">
                                <div class="cm-label">Risk Factor</div>
                                <div class="cm-value xl {rf_cls}">{risk_factor_display}</div>
                              </div>
                            </div>
                            {('<div class="cm-sub" style="margin-bottom:8px;color:#8B8F97;">' + bucket_description + '</div>') if bucket_description else ''}
                            {stake_html}
                            """,
                        )

                        if user_profile_display:
                            with st.expander("View Behavior User Profile (DQN Inputs)"):
                                st.json(user_profile_display)

                    # ---- Ethics column ----
                    with eth_col:
                        ethics_output = deep_analysis_result.get("ethics", {})
                        ethics_status = ethics_output.get("status", "pending")
                        viol_prob = ethics_output.get("violation_prob")
                        safe_prob = ethics_output.get("safe_prob")
                        backend = ethics_output.get("backend", "unknown")

                        eth_tag = "ctag-pass" if ethics_status == "pass" else ("ctag-fail" if ethics_status == "fail" else "ctag-neutral")
                        eth_icon = "✅" if ethics_status == "pass" else ("⛔" if ethics_status == "fail" else "⏳")

                        scores_html = ""
                        if isinstance(viol_prob, (int, float)) and isinstance(safe_prob, (int, float)):
                            scores_html = f"""
                            <div class="card-metric-row" style="margin-top:10px;">
                              <div class="card-metric">
                                <div class="cm-label">Violation Prob</div>
                                <div class="cm-value {'neg' if viol_prob > 0.4 else 'pos'}" style="font-size:1.3rem;">{viol_prob:.1%}</div>
                              </div>
                              <div class="card-metric">
                                <div class="cm-label">Safe Prob</div>
                                <div class="cm-value {'pos' if safe_prob > 0.6 else 'warn'}" style="font-size:1.3rem;">{safe_prob:.1%}</div>
                              </div>
                            </div>
                            <div class="cm-sub">Backend: <code style="color:#8B8F97;">{backend}</code></div>
                            """

                        render_card(
                            "Ethics & Safety", icon="⚖️",
                            gradient="linear-gradient(135deg,#00D2FF 0%,#0066CC 100%)",
                            content_html=f"""
                            <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
                              <span style="font-size:1.6rem;">{eth_icon}</span>
                              <div>
                                <div class="cm-label">Status</div>
                                <span class="ctag {eth_tag}" style="font-size:.85rem;">{ethics_status.upper()}</span>
                              </div>
                            </div>
                            {scores_html}
                            """,
                        )

                    st.divider()
                    recommendation_output = deep_analysis_result.get('recommendation', {})
                    rec_text = recommendation_output.get("recommendation_text", "No recommendation text available.")
                    render_card(
                        "Final Recommendation — LLM Synthesis", icon="📝",
                        gradient="linear-gradient(135deg,#7B2FFF 0%,#FF0080 100%)",
                        content_html=f'<div class="rec-text">{rec_text}</div>',
                    )

                    with st.expander("Debugging & Raw Agent Output"):
                        st.subheader("Full Prediction Output")
                        st.json(deep_analysis_result.get("prediction", {}))

                        st.subheader("Full Verification Output")
                        st.json(deep_analysis_result.get("verification", {}))

                        st.subheader("Full Behavior Output")
                        st.json(deep_analysis_result.get("action", {}))

                        st.subheader("Behavior User Profile (top-level)")
                        st.json(
                            deep_analysis_result.get(
                                "behavior_user_profile",
                                deep_analysis_result.get("action", {}).get("user_profile", {}),
                            )
                        )

                        st.subheader("Raw selected_match passed to agents")
                        st.json(deep_analysis_result.get("match", {}))

                        st.subheader("Full Recommendation Output")
                        st.json(deep_analysis_result.get("recommendation", {}))

                        st.subheader("Full Ethics Output")
                        st.json(deep_analysis_result.get("ethics", {}))

                        st.subheader("Raw Value Edges (All Outcomes)")
                        st.json(deep_analysis_result.get("verification", {}).get("all_value_edges", {}))

                else:
                    st.error(deep_analysis_result.get("message", "Deep analysis failed for an unknown reason."))

            if st.session_state.pipeline_results and st.session_state.pipeline_results.get("status") != "ok" and not st.session_state.deep_analysis_results:
                if st.session_state.pipeline_results.get("status") == "query_error":
                    st.error(st.session_state.pipeline_results.get("message", "Query agent could not parse that request."))
                elif st.session_state.pipeline_results.get("status") == "no_matches":
                    st.warning(st.session_state.pipeline_results.get("message", "Agent understood the query, but found no matches involving that team or criteria."))
                else:
                    st.error(st.session_state.pipeline_results.get("message", "An unexpected error occurred during the initial query phase."))


    # Dashboard tab (No changes needed, uses existing data_agent and DB functions)
    with tab2:
        st.header(
            f"Dashboard Overview ({st.session_state.sport_type.replace('_', ' ').title()})"
        )

        if os.path.exists("betting_edge.db"):
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT COUNT(*) FROM matches WHERE match_date >= datetime('now', '-7 days') AND sport_type = ?",
                (st.session_state.sport_type,),
            )
            recent_matches = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM matches WHERE match_date >= datetime('now') "
                "AND status NOT IN ('Match Finished', 'Match Cancelled', 'completed') "
                "AND sport_type = ?",
                (st.session_state.sport_type,),
            )
            upcoming_matches = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(DISTINCT m.match_id) "
                "FROM odds o JOIN matches m ON o.match_id = m.match_id "
                "WHERE m.sport_type = ?",
                (st.session_state.sport_type,),
            )
            matches_with_odds = cursor.fetchone()[0]
            conn.close()

            render_card(
                "Database Overview", icon="📊",
                content_html=f"""
                <div class="stat-strip">
                  <div class="stat-item">
                    <div class="stat-num">{recent_matches}</div>
                    <div class="stat-lbl">Recent Matches (7d)</div>
                  </div>
                  <div class="stat-item">
                    <div class="stat-num" style="color:#00D2FF;">{upcoming_matches}</div>
                    <div class="stat-lbl">Upcoming Matches</div>
                  </div>
                  <div class="stat-item">
                    <div class="stat-num" style="color:#7B2FFF;">{matches_with_odds}</div>
                    <div class="stat-lbl">Matches with Odds</div>
                  </div>
                </div>
                """,
            )

            # ── Session Log Analytics ──────────────────────────────────────────
            st.divider()
            st.subheader("📈 Analysis Activity")

            _log_dir = Path("session_logs")
            _all_entries = []
            if _log_dir.exists():
                for _lf in sorted(_log_dir.glob("session_*.json")):
                    try:
                        with open(_lf) as _f:
                            _raw = json.load(_f)
                        if isinstance(_raw, list):
                            _all_entries.extend(_raw)
                        elif isinstance(_raw, dict):
                            _all_entries.append(_raw)
                    except Exception:
                        pass

            if not _all_entries:
                st.info("No analysis sessions logged yet. Run a deep analysis in the AI Assistant tab to start tracking.")
            else:
                from collections import Counter as _Counter

                # ── Metrics ───────────────────────────────────────────────────
                _total = len(_all_entries)

                _edges = []
                for _e in _all_entries:
                    try:
                        _edges.append(float(_e.get("analysis", {}).get("verification", {}).get("raw_value_edge")))
                    except (TypeError, ValueError):
                        pass
                _avg_edge = sum(_edges) / len(_edges) if _edges else None

                _ethics_list = [_e.get("analysis", {}).get("ethics", {}).get("status") for _e in _all_entries]
                _pass_rate = sum(1 for s in _ethics_list if s == "pass") / len(_ethics_list) if _ethics_list else 0

                _teams = []
                for _e in _all_entries:
                    _m = (_e.get("analysis") or {}).get("match") or {}
                    _ht = (_m.get("teams") or {}).get("home", {}).get("name")
                    _at = (_m.get("teams") or {}).get("away", {}).get("name")
                    if _ht and _ht not in ("None", ""):
                        _teams.append(_ht)
                    if _at and _at not in ("None", ""):
                        _teams.append(_at)
                _top_team = _Counter(_teams).most_common(1)[0][0] if _teams else "N/A"

                _buckets = []
                for _e in _all_entries:
                    _b = _e.get("behavior_bucket") or (_e.get("analysis") or {}).get("action", {}).get("bucket_label")
                    if _b:
                        _buckets.append(str(_b))
                _top_bucket = _Counter(_buckets).most_common(1)[0][0] if _buckets else "N/A"
                _top_bucket_short = _top_bucket.split("(")[0].strip() if _top_bucket != "N/A" else "N/A"

                _mc1, _mc2, _mc3, _mc4, _mc5 = st.columns(5)
                _mc1.metric("Total Analyses", _total)
                _mc2.metric("Avg Value Edge", f"{_avg_edge:.2%}" if _avg_edge is not None else "N/A")
                _mc3.metric("Ethics Pass Rate", f"{_pass_rate:.0%}")
                _mc4.metric("Top Team", _top_team[:22] if _top_team != "N/A" else "N/A")
                _mc5.metric("Top Bucket", _top_bucket_short)

                st.markdown("")

                import plotly.express as px

                # Shared dark layout applied to all charts (no legend key — set per chart)
                _dark_layout = dict(
                    paper_bgcolor="rgba(14,17,23,0)",
                    plot_bgcolor="rgba(14,17,23,0)",
                    font_color="#8B8F97",
                    margin=dict(l=0, r=0, t=28, b=0),
                )

                # Gradient palettes matching the card border theme
                _LEAGUE_COLORS = [
                    "#00D2FF", "#2BB8FF", "#569EFF", "#7B84FF",
                    "#9D6AFF", "#BF50FF", "#E036FF", "#FF0080",
                ]
                _BUCKET_COLORS = {
                    "SAFE_PICK":         "#00E676",
                    "Safe Pick":         "#00E676",
                    "Value Bet":         "#FFB300",
                    "VALUE_BET":         "#FFB300",
                    "High Risk":         "#FF5252",
                    "HIGH_RISK":         "#FF5252",
                    "Explanation Only":  "#8B8F97",
                    "EXPLANATION_ONLY":  "#8B8F97",
                }

                # ── Charts row ───────────────────────────────────────────────
                _ch1, _ch2 = st.columns(2)

                with _ch1:
                    st.markdown("**Analyses by League**")
                    _league_counts = _Counter(
                        ((_e.get("analysis") or {}).get("match") or {}).get("league", {}).get("name") or "Unknown"
                        for _e in _all_entries
                    )
                    _lg_items = sorted(_league_counts.items(), key=lambda x: -x[1])[:8]
                    _lg_labels = [x[0] for x in _lg_items]
                    _lg_values = [x[1] for x in _lg_items]
                    _lg_colors = [_LEAGUE_COLORS[i % len(_LEAGUE_COLORS)] for i in range(len(_lg_labels))]
                    _fig_lg = px.bar(
                        x=_lg_values, y=_lg_labels, orientation="h",
                        labels={"x": "Analyses", "y": ""},
                        color=_lg_labels,
                        color_discrete_sequence=_lg_colors,
                    )
                    _fig_lg.update_layout(**_dark_layout, showlegend=False)
                    _fig_lg.update_traces(marker_line_width=0)
                    _fig_lg.update_xaxes(gridcolor="rgba(255,255,255,0.05)", zeroline=False)
                    _fig_lg.update_yaxes(gridcolor="rgba(0,0,0,0)")
                    st.plotly_chart(_fig_lg, use_container_width=True)

                with _ch2:
                    st.markdown("**Behavior Bucket Distribution**")
                    if _buckets:
                        _bkt_counts = _Counter(_buckets)
                        _bkt_short = {}
                        for _k, _v in _bkt_counts.items():
                            _short = _k.split("(")[0].strip()
                            _bkt_short[_short] = _bkt_short.get(_short, 0) + _v
                        _bkt_labels = list(_bkt_short.keys())
                        _bkt_values = list(_bkt_short.values())
                        _bkt_clrs = [_BUCKET_COLORS.get(_l, "#7B2FFF") for _l in _bkt_labels]
                        _fig_bkt = px.bar(
                            x=_bkt_labels, y=_bkt_values,
                            labels={"x": "", "y": "Count"},
                            color=_bkt_labels,
                            color_discrete_sequence=_bkt_clrs,
                        )
                        _fig_bkt.update_layout(**_dark_layout, showlegend=False)
                        _fig_bkt.update_traces(marker_line_width=0)
                        _fig_bkt.update_xaxes(gridcolor="rgba(0,0,0,0)")
                        _fig_bkt.update_yaxes(gridcolor="rgba(255,255,255,0.05)", zeroline=False)
                        st.plotly_chart(_fig_bkt, use_container_width=True)

                # ── DB Coverage pie ───────────────────────────────────────────
                st.markdown("**Matches Stored in Database by League**")
                st.caption("Shows what's already fetched — gaps here = use Manual Data Tools to fill")
                _pie_conn = get_db_connection()
                _pie_df = pd.read_sql_query(
                    "SELECT league_name, COUNT(*) as matches FROM matches "
                    "WHERE sport_type = ? AND league_name IS NOT NULL "
                    "GROUP BY league_name ORDER BY matches DESC",
                    _pie_conn,
                    params=(st.session_state.sport_type,),
                )
                _pie_conn.close()
                if not _pie_df.empty:
                    _pie_colors = [_LEAGUE_COLORS[i % len(_LEAGUE_COLORS)] for i in range(len(_pie_df))]
                    _fig_pie = px.pie(
                        _pie_df, values="matches", names="league_name",
                        hole=0.45,
                        color_discrete_sequence=_pie_colors,
                    )
                    _fig_pie.update_traces(
                        textposition="outside",
                        textinfo="label+percent",
                        textfont_color="#E8EAED",
                        marker=dict(line=dict(color="rgba(14,17,23,1)", width=2)),
                    )
                    _fig_pie.update_layout(
                        **_dark_layout,
                        showlegend=True,
                        legend=dict(
                            font_color="#8B8F97",
                            orientation="v",
                        ),
                    )
                    st.plotly_chart(_fig_pie, use_container_width=True)
                else:
                    st.info("No matches in database yet for this sport type.")

            # ── Latest Matches ─────────────────────────────────────────────────
            st.divider()
            st.subheader("📅 Latest Matches")

            leagues = get_unique_leagues(st.session_state.sport_type)
            col_f1, col_f2, col_f3, col_f4 = st.columns([2, 1, 1, 2])

            with col_f1:
                selected_league_filter = st.selectbox(
                    "Filter by League",
                    options=leagues,
                    key="dash_league_filter",
                )
            with col_f2:
                filter_past = st.checkbox("Past", value=True, key="dash_past")
            with col_f3:
                filter_future = st.checkbox("Future", value=True, key="dash_future")
            with col_f4:
                show_count = st.slider("Show", 10, 100, 20)

            matches_df = fetch_matches_from_db(
                sport_type=st.session_state.sport_type,
                league_name=selected_league_filter,
                #include_past=filter_past,
                #include_future=filter_future,
                #limit=show_count,
            )

            if not matches_df.empty:
                matches_df["match_date"] = pd.to_datetime(
                    matches_df["match_date"]
                ).dt.strftime("%Y-%m-%d %H:%M")
                matches_df["Score"] = matches_df.apply(
                    lambda x: f"{int(x['home_score']) if pd.notna(x['home_score']) else 0} - "
                    f"{int(x['away_score']) if pd.notna(x['away_score']) else 0}",
                    axis=1,
                )
                st.dataframe(
                    matches_df[
                        [
                            "league_name",
                            "match_date",
                            "home_team_name",
                            "Score",
                            "away_team_name",
                            "status",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No matches in database. Use the AI Assistant or sidebar tools.")
        else:
            st.info("🔧 Database not found.")

    # Statistics tab
    with tab3:
        st.header("Team Statistics")
        if os.path.exists("betting_edge.db"):
            conn = get_db_connection()
            query = (
                "SELECT DISTINCT home_team_name as team_name, home_team_id as team_id "
                "FROM matches WHERE sport_type = ? "
                "UNION "
                "SELECT DISTINCT away_team_name, away_team_id FROM matches WHERE sport_type = ? "
                "ORDER BY team_name"
            )
            teams_df = pd.read_sql_query(
                query,
                conn,
                params=(st.session_state.sport_type, st.session_state.sport_type),
            )
            conn.close()

            if not teams_df.empty:
                selected_team = st.selectbox(
                    "Select Team", teams_df["team_name"].tolist(), key="stats_team_select"
                )
                if selected_team:
                    team_id = int(
                        teams_df[teams_df["team_name"] == selected_team]["team_id"].iloc[
                            0
                        ]
                    )
                    if not st.session_state.data_agent:
                        st.info("Initialize the agent in the sidebar to load recent matches.")
                    else:
                        recent = st.session_state.data_agent.get_recent_matches(team_id)
                        if not recent:
                            st.info(f"No finished matches found for {selected_team}.")
                        else:
                            wins = sum(
                                1
                                for m in recent
                                if (
                                    m["home_team_id"] == team_id
                                    and m["home_score"] > m["away_score"]
                                )
                                or (
                                    m["away_team_id"] == team_id
                                    and m["away_score"] > m["home_score"]
                                )
                            )
                            draws = sum(
                                1
                                for m in recent
                                if (
                                    m["home_team_id"] == team_id
                                    or m["away_team_id"] == team_id
                                )
                                and m["home_score"] == m["away_score"]
                            )
                            losses = len(recent) - wins - draws
                            win_rate = wins / len(recent)
                            wr_cls = "pos" if win_rate >= 0.5 else ("warn" if win_rate >= 0.3 else "neg")
                            render_card(
                                f"Recent Form — {selected_team}", icon="📈",
                                content_html=f"""
<div class="stat-strip">
<div class="stat-item"><div class="stat-num {wr_cls}">{win_rate:.0%}</div><div class="stat-lbl">Win Rate (Last {len(recent)})</div></div>
<div class="stat-item"><div class="stat-num" style="color:#00E676;">{wins}</div><div class="stat-lbl">Wins</div></div>
<div class="stat-item"><div class="stat-num" style="color:#8B8F97;">{draws}</div><div class="stat-lbl">Draws</div></div>
<div class="stat-item"><div class="stat-num" style="color:#FF5252;">{losses}</div><div class="stat-lbl">Losses</div></div>
</div>""",
                            )
                            recent_df = pd.DataFrame(recent)
                            cols_available = [
                                c for c in
                                ["match_date", "home_team_name", "home_score", "away_score", "away_team_name"]
                                if c in recent_df.columns
                            ]
                            if cols_available:
                                st.dataframe(recent_df[cols_available], use_container_width=True)

    # Odds tab
    with tab4:
        st.header("Betting Odds")

        odds_agent = get_odds_agent()
        if odds_agent is None:
            st.info("Unable to fetch live odds. Please ensure Odds API Key is set and agent initialized.")
        else:
            current_sport_type = st.session_state.sport_type
            sport_key = map_sport_to_odds_api(current_sport_type)

            render_card(
                "Live Odds Source", icon="💰",
                gradient="linear-gradient(135deg,#00D2FF 0%,#7B2FFF 100%)",
                content_html=f"""
                <div class="card-metric-row">
                  <div class="card-metric">
                    <div class="cm-label">Sport</div>
                    <div class="cm-value" style="font-size:1.1rem;">{current_sport_type.replace("_", " ").title()}</div>
                  </div>
                  <div class="card-metric">
                    <div class="cm-label">Odds API Key</div>
                    <div class="cm-value" style="font-size:1rem;"><code style="color:#00D2FF;">{sport_key}</code></div>
                  </div>
                </div>
                <div class="cm-sub">Select regions &amp; markets below, then fetch live odds.</div>
                """,
            )

            regions = st.multiselect(
                "Regions",
                options=["us", "uk", "eu", "au", "us2"], # Added us2 for more coverage
                default=["us", "eu"],
            )
            markets = st.multiselect(
                "Markets",
                options=["h2h", "spreads", "totals"], # Changed ou to totals for consistency with Odds API
                default=["h2h"],
            )

            if st.button("🔍 Fetch Latest Odds (Live)"):
                with st.spinner("Fetching odds from The Odds API..."):
                    try:
                        odds_data = odds_agent.get_upcoming_odds(
                            sport=sport_key,
                            regions=",".join(regions) if regions else "us",
                            markets=",".join(markets) if markets else "h2h"
                        )
                        if odds_data:
                            odds_df = build_odds_dataframe(odds_data)
                            if not odds_df.empty:
                                st.success("Odds fetched successfully!")
                                st.dataframe(odds_df, use_container_width=True)
                            else:
                                st.warning("No odds found for the selected criteria.")
                        else:
                            st.warning("No odds data returned from the API.")
                    except Exception as e:
                        st.error(f"Error fetching odds: {e}")
            
            st.markdown("### 🗄️ Stored Odds (Database)")
            conn = get_db_connection()
            query = """
                SELECT
                    m.league_name,
                    m.match_date,
                    m.home_team_name,
                    o.home_team_odds,
                    o.draw_odds,
                    o.away_team_odds,
                    m.away_team_name,
                    o.bookmaker
                FROM odds o
                JOIN matches m ON o.match_id = m.match_id
                WHERE m.sport_type = ?
                ORDER BY m.match_date DESC
                LIMIT 50;
            """
            stored_odds_df = pd.read_sql_query(query, conn, params=(st.session_state.sport_type,))
            conn.close()

            if not stored_odds_df.empty:
                st.dataframe(stored_odds_df, use_container_width=True)
            else:
                st.info("No odds stored in the database for the current sport type.")