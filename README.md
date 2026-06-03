# Signup Email Agent

A LangChain agent that processes new user signups, classifies ICP fit, and generates personalized welcome emails. Evaluated with DeepEval (offline) and LangSmith (online).

**Stack:** LangChain · LangSmith · DeepEval · OpenAI gpt-4o-mini

---

## Project Structure

```
langsmith-signup-email-agent/
├── agent.py          # Agent definition + structured output schema
├── eval.py           # Offline evaluation with DeepEval
├── requirements.txt
├── .env.example      # Copy to .env and fill in keys
├── .env              # Your real keys — git-ignored
└── .gitignore
```

---

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Configure environment**
```bash
cp .env.example .env
# Edit .env and fill in your keys
```

Your `.env` should look like:
```
OPENAI_API_KEY=sk-...
LANGSMITH_API_KEY=lsv2_pt_...
LANGCHAIN_PROJECT=langsmith-signup-email-agent
```

---

## Usage

**Run the agent (smoke test)**
```bash
python agent.py
```

**Run offline evaluations**

First, upload `golden_dataset.jsonl` to LangSmith:
1. Go to [smith.langchain.com](https://smith.langchain.com)
2. Click **Datasets & Experiments** → **+ New Dataset**
3. Name it `golden-dataset` and upload the file

Then run:
```bash
python eval.py
```

---

## The Production Feedback Loop

```
Agent runs on new signups
        ↓
LangSmith traces + online eval scores
        ↓
Failures flagged automatically
        ↓
Add failing cases to golden dataset
        ↓
Re-run offline eval (DeepEval)
        ↓
Fix prompt / agent → redeploy
        ↓ (loop)
```

---

## Evaluation Metrics

| Metric | Type | Tool | Target |
|---|---|---|---|
| ICP fit accuracy | Exact match | DeepEval | 1.0 |
| Email quality | LLM-as-a-judge (GEval) | DeepEval | > 0.5 |
| Online eval | Prebuilt evaluator | LangSmith | Pass |
