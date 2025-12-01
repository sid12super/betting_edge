# /agent_modules/behavior_agent_wrapper.py

from typing import Dict, Any
import os
import logging

import numpy as np
import torch
import torch.nn as nn
from langchain_core.runnables import Runnable

# ---- DQN config (same as notebook) ----

ACTIONS = {
    0: "SAFE_PICK",
    1: "VALUE_BET",
    2: "HIGH_RISK",
    3: "EXPLANATION_ONLY",
}

STATE_DIM = 15
N_ACTIONS = len(ACTIONS)


class DQN(nn.Module):
    def __init__(self, state_dim: int, n_actions: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, n_actions),
        )

    def forward(self, x):
        return self.net(x)


class BehaviorAgentLC(Runnable):
    """
    RL-based behavior agent using a trained DQN.

    - Keeps the same interface as the old placeholder:
      invoke(inputs: Dict[str, Any]) -> {"action": str, "risk_factor": float, ...}
    - If the DQN model fails to load, falls back to the old neutral behavior.
    """

    def __init__(
        self,
        model_path: str = "models/dqn_model.pth",
        device: str | None = None,
        seed: int = 2025,
    ):
        # Logging setup
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            )

        # Device
        if device is not None:
            self.device = torch.device(device)
        else:
            self.device = torch.device(
                "cuda" if torch.cuda.is_available() else "cpu"
            )

        self.rng = np.random.default_rng(seed)

        # Per-"user" in-memory state (profile + interaction)
        self.user_state: Dict[str, Dict[str, Dict[str, float]]] = {}

        # Load model (with safe fallback)
        self.model: DQN | None = None
        self._load_model(model_path)

    # ------------------------------------------------------------------
    # Model loading / fallback
    # ------------------------------------------------------------------

    def _load_model(self, model_path: str) -> None:
        if not os.path.exists(model_path):
            self.logger.warning(
                f"DQN model file not found at '{model_path}'. "
                "BehaviorAgentLC will fall back to neutral outputs."
            )
            self.model = None
            return

        try:
            model = DQN(STATE_DIM, N_ACTIONS).to(self.device)
            state_dict = torch.load(model_path, map_location=self.device)
            model.load_state_dict(state_dict)
            model.eval()
            self.model = model
            self.logger.info(
                f"DQN behavior model loaded successfully from '{model_path}' "
                f"on device '{self.device}'."
            )
        except Exception as e:
            self.logger.error(f"Failed to load DQN model from '{model_path}': {e}")
            self.model = None

    # ------------------------------------------------------------------
    # User profile + interaction context (lightweight version of notebook)
    # ------------------------------------------------------------------

    def _init_user_if_needed(self, user_id: str, risk_bucket: str) -> None:
        if user_id in self.user_state:
            return

        profile = self._default_user_profile(risk_bucket)
        inter_ctx = self._initial_interaction_context(profile)
        self.user_state[user_id] = {
            "profile": profile,
            "interaction": inter_ctx,
        }

    def _default_user_profile(self, risk_bucket: str) -> Dict[str, float]:
        """
        Lightweight stand-in for sample_user_profile() from the notebook.

        We map risk_bucket ("Low" / "Medium" / "High") to a compact set of
        normalized features that match the 7 user_profile keys used in build_state.
        """
        bucket = str(risk_bucket).strip().lower()
        if bucket == "low":
            risk_score = 0.2
            volatility_score = 0.2
        elif bucket == "high":
            risk_score = 0.8
            volatility_score = 0.8
        else:
            # "Medium" or unknown
            risk_score = 0.5
            volatility_score = 0.5

        return {
            "risk_score": risk_score,
            "volatility_score": volatility_score,
            "chase_tendency": 0.3 if bucket == "low" else 0.6 if bucket == "medium" else 0.8,
            "conservativeness": 1.0 - risk_score,
            "engagement_depth": 0.5,
            "convert_rate": 0.4,
            "team_loyalty": 0.5,
        }

    def _initial_interaction_context(self, profile: Dict[str, float]) -> Dict[str, float]:
        """
        Lightweight stand-in for initial_interaction_context() from the notebook.
        """
        return {
            "recent_win_rate": 0.5,
            "recent_risk_mean": float(profile["risk_score"]),
            "frustration_score": 0.2,
            "last_action_type": 0.0,  # encoded as a numeric feature
        }

    # ------------------------------------------------------------------
    # State construction (mirrors build_state() from the notebook)
    # ------------------------------------------------------------------

    def _build_state(
        self,
        user_profile: Dict[str, float],
        match_context: Dict[str, float],
        interaction_context: Dict[str, float],
    ) -> np.ndarray:
        vec: list[float] = []

        # 7 dims from user_profile
        for key in [
            "risk_score",
            "volatility_score",
            "chase_tendency",
            "conservativeness",
            "engagement_depth",
            "convert_rate",
            "team_loyalty",
        ]:
            vec.append(float(user_profile[key]))

        # 4 dims from match_context
        for key in [
            "pred_win_prob",
            "odds_spread",
            "implied_edge",
            "game_importance",
        ]:
            vec.append(float(match_context[key]))

        # 4 dims from interaction_context
        for key in [
            "recent_win_rate",
            "recent_risk_mean",
            "frustration_score",
            "last_action_type",
        ]:
            vec.append(float(interaction_context[key]))

        return np.asarray(vec, dtype=np.float32)

    # ------------------------------------------------------------------
    # Derive a minimal match_context from pipeline inputs
    # ------------------------------------------------------------------

    def _derive_match_context(
        self,
        inputs: Dict[str, Any],
    ) -> Dict[str, float]:
        """
        Construct a 4-dim match_context that aligns with what the DQN was trained on.

        Uses, in order of preference:
        - model_home_prob / model_draw_prob / model_away_prob to derive a max(pred prob)
        - falls back to confidence bucket mapping if those are missing.
        """

        raw_edge = float(inputs.get("raw_value_edge", 0.0) or 0.0)

        # Confidence bucket as a string
        conf_str = str(inputs.get("confidence", "Low") or "Low").strip().lower()
        conf_map = {
            "low": 0.45,
            "medium": 0.60,
            "high": 0.80,
        }

        # Prefer actual model probabilities if they were passed in
        home_p = inputs.get("model_home_prob")
        draw_p = inputs.get("model_draw_prob")
        away_p = inputs.get("model_away_prob")

        if isinstance(home_p, (int, float)) and isinstance(draw_p, (int, float)) and isinstance(away_p, (int, float)):
            pred_win_prob = float(max(home_p, draw_p, away_p))
        else:
            # Fallback: derive a proxy from the confidence bucket
            pred_win_prob = float(conf_map.get(conf_str, 0.55))

        # TODO (future): derive from actual odds spread (home vs away prices)
        odds_spread = 0.0

        # Approximate game importance from confidence + edge magnitude
        base_importance = 0.4 if conf_str == "low" else 0.6 if conf_str == "medium" else 0.8
        # Slightly bump importance if the edge magnitude is big
        edge_mag = abs(raw_edge)
        if edge_mag > 0.25:
            base_importance += 0.1
        elif edge_mag > 0.15:
            base_importance += 0.05
        game_importance = min(base_importance, 1.0)

        return {
            "pred_win_prob": float(pred_win_prob),
            "odds_spread": float(odds_spread),
            "implied_edge": float(raw_edge),
            "game_importance": float(game_importance),
        }


    # ------------------------------------------------------------------
    # Public LangChain entrypoint
    # ------------------------------------------------------------------

    def invoke(self, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Main entry point. `inputs` is what the pipeline passes in:

            {
                "raw_value_edge": float,
                "confidence": "Low" | "Medium" | "High",
                "user_risk_tolerance": "Low" | "Medium" | "High",
                # optional:
                "user_id": "some identifier"
            }

        Returns a dict with at least:
            {
                "action": <str>,        # used by RecommendationAgent
                "risk_factor": <float>, # used by UI / future logic
                ...
            }
        """

        # If model isn't available, fall back to old neutral behavior
        if self.model is None:
            self.logger.warning(
                "BehaviorAgentLC: DQN model not loaded; returning neutral_analysis."
            )
            return {
                "action": "neutral_analysis",
                "risk_factor": 0.5,
            }

        # Parse basic fields from inputs
        user_id = str(inputs.get("user_id", "default_user"))
        risk_bucket = str(inputs.get("user_risk_tolerance", "Medium")).strip()

        # Ensure user profile + interaction context exist
        self._init_user_if_needed(user_id, risk_bucket)
        user_profile = self.user_state[user_id]["profile"]
        interaction_context = self.user_state[user_id]["interaction"]

        # Derive match_context from verification / pipeline inputs
        match_context = self._derive_match_context(inputs)

        # Build 15-dim state vector
        state_vec = self._build_state(
            user_profile=user_profile,
            match_context=match_context,
            interaction_context=interaction_context,
        )

        # Run through DQN
        with torch.no_grad():
            state_t = torch.tensor(
                state_vec, dtype=torch.float32, device=self.device
            ).unsqueeze(0)
            q_vals = self.model(state_t)
            action_index = int(torch.argmax(q_vals, dim=1).item())

        action_tag = ACTIONS.get(action_index, "SAFE_PICK")

        # Simple mapping from action -> scalar risk_factor (0..1)
        risk_factor_map = {
            0: 0.2,  # SAFE_PICK
            1: 0.5,  # VALUE_BET
            2: 0.9,  # HIGH_RISK
            3: 0.1,  # EXPLANATION_ONLY
        }
        risk_factor = float(risk_factor_map.get(action_index, 0.5))

        # Human-friendly bucket labels & descriptions
        bucket_labels = {
            "SAFE_PICK": "Safe Pick (Conservative)",
            "VALUE_BET": "Value Bet (Balanced)",
            "HIGH_RISK": "High-Risk Shot",
            "EXPLANATION_ONLY": "Explanation Only (No Bet Recommended)",
        }

        bucket_descriptions = {
            "SAFE_PICK": "Focus on lower-risk opportunities, even if the edge is modest.",
            "VALUE_BET": "Take bets where the model sees a solid positive edge with controlled risk.",
            "HIGH_RISK": "Aggressive spots with high upside but significant variance.",
            "EXPLANATION_ONLY": "Explain the situation without nudging toward a bet.",
        }

        bucket_label = bucket_labels.get(action_tag, action_tag)
        bucket_description = bucket_descriptions.get(action_tag, "")

        # NOTE: For now we are not updating interaction_context here,
        # since we don't have reward feedback in the live app loop yet.
        # That can be added later if you start logging outcomes.

        return {
            "action": action_tag,                 # consumed by RecommendationAgent
            "risk_factor": risk_factor,           # available for UI / filtering
            "action_index": action_index,         # extra metadata
            "bucket_label": bucket_label,
            "bucket_description": bucket_description,
            "match_context": match_context,       # debug / inspection
            "user_profile": user_profile,         # debug / future personalization
        }
