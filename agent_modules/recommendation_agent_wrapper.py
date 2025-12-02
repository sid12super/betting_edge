from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.llms import OpenAI
import os
from typing import Dict, Any


class RecommendationAgentLC:
    def __init__(self):
        self.llm = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.7,
            max_tokens=750,
        )

        # 🔁 UPDATED PROMPT – now uses behavior bucket & risk factor
        self.prompt = PromptTemplate.from_template("""
            You are an AI sports betting analyst. Your goal is to provide a concise, clear, and ethical betting recommendation
            based on the provided analysis and the user's behavior profile.

            --- Match Details ---
            Home Team: {home_team_name}
            Away Team: {away_team_name}
            Match Date: {match_date}
            Sport Type: {sport_type}
            Match Status: {match_status}
            {score_line_if_available}
            Historical Flag (True = match already finished in real life): {is_historical}

            --- Prediction Model Output ---
            Predicted Winner (Model's Highest Probability): {predicted_winner_model}
            Home Win Probability: {home_win_probability:.2%}
            Draw Probability: {draw_probability:.2%}
            Away Win Probability: {away_win_probability:.2%}

            --- Value Verification Output ---
            Raw Value Edge: {raw_value_edge:.4f}
            Value Edge Rating: {value_edge_rating}
            Recommended Bet Side (by value logic): {recommended_bet_side}
            Confidence Level: {confidence_level}

            --- Behavior Policy & User Risk Profile ---
            Behavior Action Code: {behavior_action}
            Behavior Risk Factor (0 = ultra conservative, 1 = very aggressive): {behavior_risk_factor:.2f}

            Interpret the action code as:
            - "SAFE_PICK": user prefers conservative bets; emphasize capital preservation, lower stakes, and skipping marginal edges.
            - "VALUE_BET": user accepts moderate risk when there is a strong value edge; focus on disciplined staking and clear reasoning.
            - "HIGH_RISK": user is comfortable with high variance; if you still recommend a bet, stress very small stakes and the high downside.
            - "EXPLANATION_ONLY": user wants analysis only; do NOT recommend placing any bet, only explain what the models and odds say.

            --- CRITICAL SAFETY RULES ---
            1. If is_historical is True (the match is already finished), you MUST NOT recommend placing any bet at all.
               - Treat this as a retrospective analysis only.
               - You may discuss what the model and odds would have suggested before kick-off.
               - Clearly say that no betting action is possible and you are only providing post-match insight.

            2. If behavior_action is "EXPLANATION_ONLY", DO NOT recommend placing a bet even if the match is in the future.

            3. If the value edge is very small or confidence is low, lean toward passing or very cautious framing, especially for SAFE_PICK.

            --- Task ---
            Use ALL of the above to produce a tailored response:

            A. Briefly restate the match context and predicted winner.
            B. Explain the value edge and why the recommended side (if any) has or does not have an advantage.
            C. Respect the behavior profile and the historical flag:
               - If is_historical is True -> explanation only, explicitly say this is not an actionable bet.
               - If behavior_action is "EXPLANATION_ONLY" -> explanation only, no bet.
               - Otherwise, adapt tone and aggressiveness to the behavior_action and risk factor.
            D. Always enforce responsible gambling: remind the user not to bet more than they can afford to lose.
            E. If there is no meaningful value edge or the situation is unclear, recommend *not betting*.

            Final Recommendation (max 250 words):
        """)


        self.chain = self.prompt | self.llm | StrOutputParser()

    def invoke(self, inputs: Dict[str, Any]) -> Dict[str, str]:
        match_details = inputs.get("match", {})
        prediction_output = inputs.get("prediction_output", {})
        verification_output = inputs.get("verification_output", {})
        behavior_output = inputs.get("behavior_output", {})

        # --- Match status / score handling (same as before) ---
        fixture_status_info = match_details.get("fixture", {})
        match_status = fixture_status_info.get("status", "N/A")

        home_score_info = match_details.get("goals", {})
        home_score = home_score_info.get("home")
        away_score = home_score_info.get("away")

        score_line = ""
        if (
            match_status
            and match_status.lower() in ['finished', 'ft', 'full-time', 'match finished', 'completed']
            and home_score is not None and away_score is not None
        ):
            home_team_name_score = match_details.get('teams', {}).get('home', {}).get('name', 'Home Team')
            away_team_name_score = match_details.get('teams', {}).get('away', {}).get('name', 'Away Team')
            score_line = f"Final Score: {home_team_name_score} {home_score} - {away_score} {away_team_name_score}"
        elif match_status and match_status.lower() not in ['not started', 'tba', 'scheduled']:
            score_line = f"Match Status: {match_status.replace('_', ' ').title()}"
        else:
            score_line = "Match not yet started."

        # --- Historical vs future match flag (NEW) ---
        status_lower = (match_status or "").lower()
        is_historical = status_lower in [
            "finished",
            "ft",
            "full-time",
            "match finished",
            "completed",
            "postponed",   # optional; remove if you want postponed to still be "future"
        ]

        # --- Behavior action + risk factor extraction (NEW) ---
        behavior_action = "neutral_analysis"
        behavior_risk_factor = 0.5

        if isinstance(behavior_output, dict):
            # Prefer explicit "action" field, fall back to "bucket" if you use that naming
            behavior_action = behavior_output.get("action") or behavior_output.get("bucket") or "neutral_analysis"
            behavior_risk_factor = behavior_output.get("risk_factor", 0.5)
        elif isinstance(behavior_output, str):
            behavior_action = behavior_output

        # --- Prompt inputs ---
        prompt_inputs = {
            "home_team_name": match_details.get("teams", {}).get("home", {}).get("name", "N/A"),
            "away_team_name": match_details.get("teams", {}).get("away", {}).get("name", "N/A"),
            "match_date": match_details.get("fixture", {}).get("date", "N/A")[:10],
            "sport_type": match_details.get("sport_type", "N/A"),
            "match_status": match_status,
            "score_line_if_available": score_line,
            "is_historical": is_historical,  

            "predicted_winner_model": prediction_output.get("predicted_winner_model", "N/A"),
            "home_win_probability": prediction_output.get("home_win_probability", 0.0),
            "draw_probability": prediction_output.get("draw_probability", 0.0),
            "away_win_probability": prediction_output.get("away_win_probability", 0.0),

            "raw_value_edge": verification_output.get("raw_value_edge", 0.0),
            "value_edge_rating": verification_output.get("value_edge", "None"),
            "recommended_bet_side": verification_output.get("recommended_bet_side", "None"),
            "confidence_level": verification_output.get("confidence", "Low"),

            "behavior_action": behavior_action,
            "behavior_risk_factor": behavior_risk_factor,
        }

        recommendation_text = self.chain.invoke(prompt_inputs)
        return {"recommendation_text": recommendation_text}
