# /agent_modules/verification_agent_wrapper.py

from langchain_core.runnables import Runnable
from data_agent import DataAgent
import math
import os # Import os to get environment variables for DataAgent
from typing import Dict, Any, Optional

class VerificationAgentLC(Runnable):
    """
    Verification Agent: Calculates the mathematical Value Edge by comparing
    Model Probability vs. Market Implied Probability (IP).
    """

    def __init__(self, sport_type: str = "football"):
        # The DataAgent needs to be initialized with the sport_type
        # and the odds_api_key. These must be passed to the constructor of this wrapper.
        self.sport_type = sport_type
        
        # We need to get the ODDS_API_KEY here because DataAgentLC won't pass it directly
        # to the VerificationAgentLC's init. The pipeline usually constructs agents.
        # So, VerificationAgentLC has to retrieve it from the environment itself,
        # or the pipeline should explicitly pass it down. For robustness,
        # we'll grab it from the environment.
        odds_api_key = os.getenv("ODDS_API_KEY", "KEY_NOT_FOUND")
        if odds_api_key == "KEY_NOT_FOUND":
            # This will raise an error when DataAgent tries to init its OddsAgent
            # It's better to let DataAgent handle its own key validation.
            print("WARNING: ODDS_API_KEY not found in environment. DataAgent might fail initialization.")

        try:
            # Initialize DataAgent with required parameters
            self.data_agent = DataAgent(
                sport_type=self.sport_type,
                db_path="betting_edge.db", # Assuming this path is consistent
                odds_api_key=odds_api_key
            )
        except ValueError as e:
            print(f"ERROR: VerificationAgentLC failed to initialize DataAgent: {e}")
            self.data_agent = None # Set to None to prevent further errors
        except Exception as e:
            print(f"ERROR: An unexpected error occurred initializing DataAgent in VerificationAgentLC: {e}")
            self.data_agent = None


    def _calculate_value(self, prediction_probs: Dict, market_odds: Dict, match_details: Dict) -> Dict:
        """
        Calculates the raw numerical value edge for Home, Draw, and Away,
        and assigns a qualitative rating based on the highest positive edge.
        
        CRITICAL CHANGE: Now also takes match_details to correctly map odds to teams.
        """
        
        actual_home_team_name = match_details.get("teams", {}).get("home", {}).get("name", "Home Team")
        actual_away_team_name = match_details.get("teams", {}).get("away", {}).get("name", "Away Team")

        # 1. Convert Market Odds to Implied Probability (IP = 1 / Decimal Odds)
        market_prob_home = 1 / market_odds.get('home_team_odds', 1000000) # Ensure you use the correct key from `fetch_odds`
        market_prob_away = 1 / market_odds.get('away_team_odds', 1000000) # Ensure you use the correct key from `fetch_odds`
        market_prob_draw = 1 / market_odds.get('draw_odds', 1000000)
        
        # 2. Get Model Probabilities
        model_prob_home = prediction_probs.get('home_win_probability', 0.0)
        model_prob_away = prediction_probs.get('away_win_probability', 0.0)
        model_prob_draw = prediction_probs.get('draw_probability', 0.0)
        
        # 3. Calculate Value Edge (Value = Model Prob - Market IP) for all outcomes
        value_home = model_prob_home - market_prob_home
        value_away = model_prob_away - market_prob_away
        value_draw = model_prob_draw - market_prob_draw

        all_value_edges = {
            f"{actual_home_team_name}_win": value_home,
            "Draw": value_draw,
            f"{actual_away_team_name}_win": value_away
        }
        
        # 4. Determine the best bet_side based on the highest positive edge
        best_bet_side = "None"
        max_positive_edge = 0.0
        
        for outcome_label, edge_value in all_value_edges.items():
            if edge_value > max_positive_edge:
                max_positive_edge = edge_value
                best_bet_side = outcome_label
        
        # 5. Assign Qualitative Rating based on the *max_positive_edge*
        # (Using the same thresholds as before)
        confidence_rating = "Low" # Changed variable name to avoid confusion with pipeline 'confidence'
        if max_positive_edge > 0.2:
            confidence_rating = "High"
        elif max_positive_edge > 0.15:
            confidence_rating = "Medium"
            
        return {
            "value_edge_raw": float(round(max_positive_edge, 4)),
            "confidence_rating": confidence_rating, # Return the rating specifically
            "bet_side": best_bet_side,
            "all_value_edges": {k: float(round(v, 4)) for k, v in all_value_edges.items()}
        }

    def invoke(self, inputs: Dict[str, Any], **kwargs) -> Dict:
        """
        Performs the verification step.
        Input: {'match': match_details, 'prediction': prediction_data}
        """
        match_details = inputs.get('match')
        prediction_data = inputs.get('prediction')

        if self.data_agent is None:
            return {"value_edge": "Low", "confidence": "Low", "message": "DataAgent not initialized, cannot fetch odds.", "raw_value_edge": 0.0, "recommended_bet_side": "None"}

        if not match_details or match_details.get('status') == 'error':
            return {"value_edge": "Low", "confidence": "Low", "message": "Match details missing.", "raw_value_edge": 0.0, "recommended_bet_side": "None"}
            
        match_id = match_details['fixture']['id']

        # 2. Get Real-Time Odds from DataAgent
        # DataAgent's fetch_odds should handle fetching from DB or live API.
        market_odds = self.data_agent.fetch_odds(match_id)
        
        # Ensure market_odds is a dictionary and contains the necessary keys
        if not market_odds or market_odds.get('home_team_odds') is None: # Use correct key here
            print(f"DEBUG: Market odds unavailable or incomplete for match_id {match_id}. "
                  f"Returned: {market_odds}")
            return {"value_edge": "Low", "confidence": "Low", "message": "Market odds unavailable for comparison.", "raw_value_edge": 0.0, "recommended_bet_side": "None"}

        # 3. Calculate Value - PASS MATCH_DETAILS TO THE CALCULATION
        value_analysis = self._calculate_value(prediction_data, market_odds, match_details)
        
        # 4. Final Output (matching the required pipeline format)
        return {
            "value_edge": value_analysis['confidence_rating'], # Use the specific rating
            "confidence": value_analysis['confidence_rating'], # Use rating for both for now
            "raw_value_edge": value_analysis['value_edge_raw'],
            "recommended_bet_side": value_analysis['bet_side'],
            "message": "Verification complete.",
            "all_value_edges": value_analysis['all_value_edges']
        }