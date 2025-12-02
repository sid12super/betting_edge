
# ⚽ Betting Edge – Multi-Agent Sports Betting Intelligence System

Betting Edge is a **multi-agent decision support system** that combines machine-learning models, rule-based logic, risk-profiling, and safety checks to generate **responsible, personalized betting recommendations** for football, college football, and basketball.

It provides:

* Model-driven win probability predictions
* Value-bet edge verification using real-time odds
* DQN-based user behavior profiling
* Ethics & safety classification via a fine-tuned transformer
* LLM-generated final recommendations
* Adjustable per-pick budgets and personalized stake suggestions
* Session-based logging for long-term user behavior analysis

---

## 🚀 Features Overview

### 🔮 1. Prediction Agent (XGBoost)

* Uses pre-trained XGBoost models to compute:

  * Home win probability
  * Draw probability
  * Away win probability
* Predicts the **most likely outcome** based on probabilistic outputs.

### 📈 2. Value Verification Agent

* Converts bookmaker odds → implied probabilities
* Computes **value edge**:
  `value_edge = model_prob - market_implied_prob`
* Identifies:

  * Recommended bet side
  * Confidence rating (Low / Medium / High)
  * Raw edge for each outcome

### 🧠 3. Behavior Agent (DQN)

* Loads a **Deep Q-Network** trained on synthetic betting behavior.
* User profile inputs:

  * Risk score
  * Conservativeness
  * Volatility
  * Chase tendency
  * Engagement depth
  * Team loyalty
* Outputs:

  * Behavior action bucket
  * Risk factor
  * Suggested stake (based on user budget)

### 🔐 4. Ethics & Safety Agent (Transformer Classifier)

* Fine-tuned DistilBERT classifier (HuggingFace)
* Evaluates:

  * Violation probability
  * Safe probability
* Ensures final recommendations follow responsible-gambling norms.

### 🧾 5. LLM-Based Final Recommendation

* GPT-4o-mini produces natural-language summarization including:

  * Match context
  * Prediction results
  * Value edge interpretation
  * Behavior-aligned guidance
  * Ethics warnings

### 🗂 6. Session Logging

Every deep analysis produces a JSON entry saved under:

```
session_logs/session_<timestamp>.json
```

These logs include **prediction, verification, behavior profile, ethics output, and final recommendation text**.

---

# 📦 Installation

### 1. Clone the repository

```bash
git clone https://github.com/BettingApp-hcai/betting_edge.git
cd betting_edge
```

### 2. Create a virtual environment

```bash
python3 -m venv betenv
source betenv/bin/activate    # Linux/Mac
betenv\Scripts\activate       # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create `.env` file

Inside the project root:

```
DATA_API_KEY=<your football data API key>
ODDS_API_KEY=<your odds API key>
OPENAI_API_KEY=<your OpenAI key>
```

---

# 🤖 Model Setup

This project uses three models:

### 1. **XGBoost Prediction Model**

Stored in repo:

```
xgb_model.json
```

### 2. **DQN Behavior Model**

Stored in:

```
models/dqn_model.pth
```

### 3. **Ethics Transformer Classifier**

Due to size, the archive is **NOT included** in Git.


---

# ▶️ Running the App

Start the Streamlit application:
```bash
streamlit run streamlit_app.py
```

Then open the browser URL shown (typically `localhost:8501`).

---


# 📁 Project Structure

```
betting_edge/
├── agent_modules/
│   ├── prediction_agent_wrapper.py
│   ├── verification_agent_wrapper.py
│   ├── behavior_agent_wrapper.py
│   └── ethics_agent_wrapper.py
├── pipelines/
│   └── pipeline.py
├── models/
│   ├── dqn_model.pth
│   └── ethics_classifier/ (user-provided)
├── session_logs/
├── data_agent.py
├── odds_agent.py
├── query_agent.py
├── llm_utils.py
├── utils.py
├── streamlit_app.py
├── requirements.txt
└── README.md
```

Pull requests are welcome.



