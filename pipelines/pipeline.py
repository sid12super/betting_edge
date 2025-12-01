# /pipelines/pipeline.py (DEFINITIVE FIX - Correcting __init__ for TypeError)

import os
import json
from typing import Dict, Any, List, Optional

# No direct Streamlit imports here!

# Import functions/classes from their respective modules
from query_agent import parse_user_query
from agent_modules.prediction_agent_wrapper import PredictionAgentLC
from agent_modules.verification_agent_wrapper import VerificationAgentLC
from agent_modules.behavior_agent_wrapper import BehaviorAgentLC
from agent_modules.recommendation_agent_wrapper import RecommendationAgentLC
from agent_modules.ethics_agent_wrapper import EthicsAgentLC

# Import from utils.py.
from utils import (
    fetch_matches_from_db,
    init_data_agent, # We need this to ensure the DataAgent is in session_state
    # get_db_connection # Not directly used in the pipeline class itself, can be removed if not needed elsewhere
)

# Import DataAgent directly (if agents need to be explicitly passed it, but not for Pipeline's __init__)
from data_agent import DataAgent 

class BettingEdgePipeline:
    def __init__(self): # REMOVED 'data_agent' parameter
        # The query_agent is just a function, not a class instance itself
        self.query_agent_func = parse_user_query
        
        # Initialize agents that don't depend on sport_type during their creation
        # (or where their DataAgent dependency is handled internally/later)
        self.prediction_agent = PredictionAgentLC()
        self.behavior_agent = BehaviorAgentLC()
        self.recommendation_agent = RecommendationAgentLC()
        self.ethics_agent = EthicsAgentLC()
        
        # VerificationAgentLC needs `sport_type` for its internal DataAgent init.
        # This will be instantiated or re-instantiated in run_deep_analysis
        # once the sport_type is known.
        self.verification_agent: Optional[VerificationAgentLC] = None


    def run(self, user_query: str):
        parsed_query_obj = self.query_agent_func(user_query)
        query_dict = parsed_query_obj.dict()
        
        sport_type = query_dict.get("sport_type")
        team_name = query_dict.get("team_name")
        competition_code = query_dict.get("competition_code")
        season = query_dict.get("season")

        if not sport_type:
            return {"status": "query_error", "message": "Could not determine sport type from your query."}

        # Initialize the DataAgent for the session. This will store it in st.session_state.
        # It handles getting the ODDS_API_KEY from the environment and passing to DataAgent.
        # This DataAgent instance will be used by other agents if they need to access DB/live data.
        current_data_agent: DataAgent = init_data_agent(sport_type) # This will return the instance

        if sport_type == "football":
            all_matches_df = fetch_matches_from_db(
                sport_type=sport_type,
                league_name=competition_code,
                team_name=team_name,
                season=season
            )
        elif sport_type in ["college_football", "basketball"]:
            all_matches_df = fetch_matches_from_db(
                sport_type=sport_type,
                year=season, # Assuming 'season' from query maps to 'year' for college sports
                team_name=team_name
            )
        else:
            return {"status": "error", "message": f"Unsupported sport type: {sport_type}"}

        if all_matches_df.empty:
            query_season_display = season if season else 'any season'
            return {"status": "no_matches", "message": f"No matches found for '{team_name or 'any team'}' in {sport_type} for season {query_season_display}."}

        # Convert DataFrame to a list of dicts for JSON serialization
        filtered_matches_list = all_matches_df.to_dict(orient="records")

        # Transform the flat DataFrame rows into the expected nested match JSON structure
        transformed_matches = []
        for match_row in filtered_matches_list:
            transformed_matches.append({
                "fixture": {
                    "id": match_row.get("match_id"),
                    "date": match_row.get("match_date"),
                    "status": match_row.get("status")
                },
                "league": {
                    "name": match_row.get("league_name"),
                    "season": match_row.get("season")
                },
                "teams": {
                    "home": {"id": match_row.get("home_team_id"), "name": match_row.get("home_team_name")},
                    "away": {"id": match_row.get("away_team_id"), "name": match_row.get("away_team_name")}
                },
                "goals": {
                    "home": match_row.get("home_score"),
                    "away": match_row.get("away_score")
                },
                "score": {
                    "fulltime": {"home": match_row.get("home_score"), "away": match_row.get("away_score")}
                },
                "sport_type": sport_type # Crucial for deep analysis
            })

        return {
            "status": "ok",
            "message": f"Found {len(transformed_matches)} matches. Select one for deep analysis.",
            "filtered_matches": transformed_matches,
            "original_query_params": parsed_query_obj.dict()
        }

    def run_deep_analysis(
        self,
        selected_match: dict,
        user_context: Optional[Dict[str, Any]] = None,
    ):
        """
        Runs the deep analysis pipeline for a single selected match.
        Optionally takes a user_context dict with fields like:
            {
                "risk_tolerance": "Low" | "Medium" | "High",
                "user_id": "some-identifier"
            }
        """
        match_id = selected_match["fixture"]["id"]
        sport_type = selected_match.get("sport_type")  # Get sport_type from the transformed match

        if not sport_type:
            return {"status": "error", "message": "Sport type not found in selected match for deep analysis."}

        # 0. User context defaults
        user_risk_tolerance = "Medium"
        user_id = "default_user"
        if user_context:
            user_risk_tolerance = user_context.get("risk_tolerance", user_risk_tolerance)
            user_id = user_context.get("user_id", user_id)

        # 1. Re-initialize VerificationAgentLC here with the correct sport_type
        #    This ensures its internal DataAgent is correctly configured for the sport.
        self.verification_agent = VerificationAgentLC(sport_type=sport_type)

        # 2. Prediction Agent
        prediction_output = self.prediction_agent.invoke(selected_match)

        # 3. Verification Agent
        verification_output = self.verification_agent.invoke({
            "match": selected_match,
            "prediction": prediction_output,
        })

        # 4. Behavior Agent (DQN-based user behavior)
        behavior_input = {
            # Core value signal
            "raw_value_edge": verification_output.get("raw_value_edge", 0.0),
            "confidence": verification_output.get("confidence", "Low"),
            "value_edge_rating": verification_output.get("value_edge", "Low"),
            "recommended_bet_side": verification_output.get("recommended_bet_side", "None"),
            "all_value_edges": verification_output.get("all_value_edges", {}),

            # Model probabilities (for state construction)
            "model_home_prob": prediction_output.get("home_win_probability", 0.0),
            "model_draw_prob": prediction_output.get("draw_probability", 0.0),
            "model_away_prob": prediction_output.get("away_win_probability", 0.0),

            # User personalization
            "user_risk_tolerance": user_risk_tolerance,
            "user_id": user_id,
        }
        behavior_action = self.behavior_agent.invoke(behavior_input)

        # 5. Recommendation Agent (Synthesis)
        recommendation_output = self.recommendation_agent.invoke({
            "match": selected_match,
            "prediction_output": prediction_output,
            "verification_output": verification_output,
            "behavior_output": behavior_action,
        })

        # 6. Ethics Agent (Final Gate)
        ethics_output = self.ethics_agent.invoke(
            recommendation_output.get("recommendation_text", "")
        )

        # 7. Optional: extra match context for display
        current_data_agent = init_data_agent(sport_type)
        match_context = current_data_agent.get_full_match_context(match_id)

        detailed_stats_data = match_context.get("home_team_stats", {})
        detailed_odds_data = match_context.get("latest_odds", {})

        # 8. Extract behavior profile & bucket for logging / export
        behavior_profile = None
        behavior_bucket = None
        if isinstance(behavior_action, dict):
            behavior_profile = behavior_action.get("user_profile")
            behavior_bucket = behavior_action.get("bucket_label") or behavior_action.get("action")

        return {
            "status": "ok",
            "message": "Deep analysis complete.",
            "prediction": prediction_output,
            "verification": verification_output,
            "action": behavior_action,
            "behavior_user_profile": behavior_profile,   # 🔹 explicit
            "behavior_bucket": behavior_bucket,          # 🔹 explicit
            "recommendation": recommendation_output,
            "ethics": ethics_output,
            "detailed_stats": [detailed_stats_data] if detailed_stats_data else [],
            "detailed_odds": [detailed_odds_data] if detailed_odds_data else [],
            "match": selected_match,
        }
