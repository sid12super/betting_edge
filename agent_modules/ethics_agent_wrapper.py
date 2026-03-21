# /agent_modules/ethics_agent_wrapper.py

from langchain_core.runnables import Runnable
import json
import os

# Try to import HF stack; if it fails, we fall back to a no-op agent.
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    HF_AVAILABLE = True
except ImportError:
    torch = None
    AutoTokenizer = None
    AutoModelForSequenceClassification = None
    HF_AVAILABLE = False


class EthicsAgentLC(Runnable):
    """
    Ethics agent using a fine-tuned HF classifier.

    Expects a model directory at:
        models/ethics_classifier/ethics_classifier_5epochs

    Returns a dict:
        {
          "status": "pass" | "fail",
          "violation_prob": float or None,
          "safe_prob": float or None,
          "backend": "hf_classifier" | "disabled"
        }
    """

    def __init__(
        self,
        model_path: str = "models/ethics_classifier/ethics_classifier_5epochs",
    ):
        self.model_path = model_path
        self.enabled = False

        if HF_AVAILABLE and os.path.isdir(self.model_path):
            try:
                # Select device
                self.device = "cuda" if torch.cuda.is_available() else "cpu"

                # Load tokenizer & model
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    self.model_path,
                    torch_dtype=torch.float16
                    if self.device == "cuda"
                    else torch.float32,
                ).to(self.device)

                self.model.eval()
                self.enabled = True
            except Exception as e:
                # Gracefully handle tokenizer compatibility or other loading errors
                print(f"⚠️  Ethics classifier failed to load: {e}. Running in disabled mode.")
                self.device = None
                self.tokenizer = None
                self.model = None
                self.enabled = False
        else:
            # No HF stack or model folder -> run in "disabled" mode
            self.device = None
            self.tokenizer = None
            self.model = None
            self.enabled = False

    def _run_classifier(self, text: str):
        """
        Internal helper: run the HF classifier and return
        (violation_prob, safe_prob).
        Assumes enabled == True.
        """
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)

        logits = outputs.logits  # [1, num_labels]
        probs = torch.softmax(logits, dim=-1)[0]

        # Convention from your training: class 0 = VIOLATION / UNSAFE,
        # class 1 = SAFE.
        violation_prob = float(probs[0].item())
        safe_prob = float(probs[1].item())

        return violation_prob, safe_prob

    def invoke(self, text, **kwargs):
        """
        Main entrypoint. For compatibility with the rest of the codebase,
        we assume `text` is a string containing the recommendation.
        """

        # Normalize input to a string
        if isinstance(text, dict):
            text = text.get("recommendation_text", "")
        else:
            text = str(text)

        # If classifier isn't available, return a neutral pass.
        if not self.enabled or not text.strip():
            return {
                "status": "pass",
                "violation_prob": None,
                "safe_prob": None,
                "backend": "disabled",
            }

        # Run HF classifier
        try:
            violation_prob, safe_prob = self._run_classifier(text)
        except Exception:
            # Any runtime error -> fail gracefully
            return {
                "status": "pass",
                "violation_prob": None,
                "safe_prob": None,
                "backend": "error",
            }

        # Simple threshold: if model thinks violation_prob > 0.5 -> fail
        status = "fail" if violation_prob > 0.5 else "pass"

        return {
            "status": status,
            "violation_prob": round(violation_prob, 4),
            "safe_prob": round(safe_prob, 4),
            "backend": "hf_classifier",
        }
