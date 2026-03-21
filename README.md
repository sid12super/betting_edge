# ⚽ Betting Edge

AI-powered sports betting analysis. Ask a question in plain English, get back a probability-driven recommendation with a risk profile, value edge calculation, and an ethics check — all in one pipeline.

Supports **Soccer (Football)**, **College Football**, and **College Basketball**.



---

## ⚡ Before You Test — Avoid Cold Start

Streamlit Cloud sleeps the app after inactivity. On a cold start the first query can be slow or time out before the agent is ready. Follow these steps every time you open the app:

### Step 1 — Wake & Initialize
1. Open the app URL
2. In the **left sidebar**, select your sport (Soccer / College Football / Basketball)
3. Click **🔌 Initialize Agent** — wait for the green success message
   > This warms up the DataAgent, connects to the database, and loads the Odds API client. Do not skip this step.

### Step 2 — Fetch Match Data (first time or after a long gap)
If the Dashboard shows low match counts, pull fresh data before querying:
1. In the sidebar, expand **🛠️ Manual Data Tools**
2. Select the league and season you want
3. Click **📥 Fetch Matches** — wait for the stored count confirmation
   > Fetched matches are saved to the local database and persist across sessions.

### Step 3 — Run a Query
1. Go to the **🤖 AI Assistant** tab
2. Set your **Risk Tolerance** slider (Low / Medium / High)
3. Type your query and click **🚀 Run Initial Query**
4. Select a match from the results
5. Click **▶️ Run Deep Analysis**

---

## How It Works

A query goes through 6 agents in sequence:

```
Your question → Query Parser → Prediction → Verification → Behavior → Recommendation → Ethics Check
```

### 1. Query Parser (NLP)
Converts your natural-language question into structured parameters the pipeline can use.
See the **[Accepted Query Formats](#-accepted-query-formats)** section below.

### 2. Prediction Model (XGBoost)
Outputs three probabilities for the selected match:

| Metric | What it means |
|---|---|
| **Home Win %** | Probability the home team wins |
| **Draw %** | Probability the match ends level |
| **Away Win %** | Probability the away team wins |
| **Predicted Winner** | The outcome with the highest probability |

### 3. Value Verification
Compares the model's probabilities against live bookmaker odds.

| Metric | What it means |
|---|---|
| **Raw Value Edge** | `model probability − market implied probability`. Positive = the model thinks the market is underpricing that outcome |
| **Rating** | Low / Medium / High — how significant the edge is |
| **Confidence** | How strongly the model and market agree |
| **Recommended Bet Side** | The outcome with the best value given your risk setting |

### 4. Behavior Agent (DQN)
Uses your **Risk Tolerance** slider to classify how you should approach the bet.

| Bucket | Meaning |
|---|---|
| **SAFE_PICK** | Back the most probable outcome — lower return, lower risk |
| **VALUE_BET** | Back the highest-edge outcome — balanced risk/return |
| **HIGH_RISK** | Aggressive edge bet — small stake, high potential return |
| **EXPLANATION_ONLY** | No bet suggested — analysis only |

**Risk Factor** is a 0–1 score derived from the match edge and your risk profile. Higher = more aggressive action.

**Suggested Stake** scales your per-pick budget by the bucket's fraction:
- SAFE_PICK → 50% of budget
- VALUE_BET → 35%
- HIGH_RISK → 15%
- EXPLANATION_ONLY → $0

### 5. Final Recommendation (LLM)
GPT-4o-mini writes a concise summary (≤250 words) combining prediction, edge, and behavior guidance into plain English.

### 6. Ethics & Safety Check
A fine-tuned DistilBERT classifier screens the recommendation text.

| Result | Meaning |
|---|---|
| **PASS** | Recommendation is safe to display |
| **FAIL** | Potential responsible-gambling violation detected — bet suggestion is blocked automatically |

---

## 💬 Accepted Query Formats

The query parser accepts plain English. You do not need to use exact team names or league codes.

### Single team queries
```
Liverpool matches
Arsenal Premier League games
Bayern Munich this season
Real Madrid la liga 2023
```

### Head-to-head fixture queries
```
Arsenal vs Liverpool
Man City against Chelsea
Bayern vs Dortmund
PSG vs Real Madrid
```

### With league or competition
```
Liverpool Premier League matches
Barcelona La Liga
Chelsea Champions League
Man City UEFA Champions League fixtures
```

### With time / season
```
Liverpool matches last season
Arsenal 2023
Bayern this season
Real Madrid last year
```

### College sports
```
Alabama college football 2024
Duke basketball games
Michigan Wolverines last season
```

### What the parser handles automatically
- **Abbreviations** — "Man City" → Manchester City FC, "PSG" → Paris Saint-Germain FC, "Barca" → FC Barcelona
- **Partial names** — "Bayern" → FC Bayern München, "Atletico" → Club Atlético de Madrid
- **League aliases** — "La Liga" → Primera Division, "Champions League" → UEFA Champions League, "PL" → Premier League
- **Typos & fuzzy matches** — close spellings are matched against the actual team database
- **Temporal expressions** — "last season", "this year", "2023" are resolved to the correct season year
- **Fixture direction** — "Arsenal vs Liverpool" and "Liverpool vs Arsenal" both find the same match

---

## 🚀 Quick Start

**1. Clone and install**
```bash
git clone https://github.com/BettingApp-hcai/betting_edge.git
cd betting_edge
python3 -m venv betenv
source betenv/bin/activate   # Windows: betenv\Scripts\activate
pip install -r requirements.txt
```

**2. Create a `.env` file**
```
API_KEY_FOOTBALL=<football-data.org key>
API_KEY_CFB=<college football data key>
API_KEY_BASKETBALL=<college basketball data key>
OPENAI_API_KEY=<OpenAI key>
ODDS_API_KEY=<The Odds API key>
```

**3. Run**
```bash
streamlit run streamlit_app.py
```

---

## 📁 Project Structure

```
betting_edge/
├── agent_modules/
│   ├── prediction_agent_wrapper.py   # XGBoost probabilities
│   ├── verification_agent_wrapper.py # Odds & value edge
│   ├── behavior_agent_wrapper.py     # DQN risk profiling
│   ├── recommendation_agent_wrapper.py
│   └── ethics_agent_wrapper.py       # DistilBERT safety check
├── pipelines/
│   └── pipeline.py                   # Orchestrates all agents
├── models/
│   ├── dqn_model.pth
│   └── ethics_classifier/
├── session_logs/                     # Per-session JSON analysis logs
├── data_agent.py                     # Fetches & stores match data
├── odds_agent.py                     # The Odds API integration
├── query_agent.py                    # NLP query parser
├── utils.py
├── streamlit_app.py
└── requirements.txt
```

---

## ⚙️ API Keys Required

| Key | Source |
|---|---|
| `API_KEY_FOOTBALL` | [football-data.org](https://www.football-data.org) |
| `API_KEY_CFB` | [collegefootballdata.com](https://collegefootballdata.com) |
| `API_KEY_BASKETBALL` | [collegebasketballdata.com](https://collegebasketballdata.com) |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) |
| `ODDS_API_KEY` | [the-odds-api.com](https://the-odds-api.com) |
