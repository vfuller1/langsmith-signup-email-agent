# 🚀 Signup Email Agent

A LangChain agent that processes new user signups, classifies ICP fit, and generates personalized welcome emails — with full LangSmith tracing, a golden eval dataset, and a custom LLM-as-a-Judge scoring pipeline.

## 💡 Use Cases

This agent is a template for any SaaS product that wants to **automatically qualify and engage new signups** without manual effort. Real-world applications include:

- **PLG (Product-Led Growth) onboarding** — trigger a personalized welcome email the moment someone signs up, with messaging tuned to their role and company size
- **Sales prioritization** — route high-ICP signups to a sales rep immediately, low-ICP to a self-serve nurture sequence
- **Marketing automation** — feed ICP scores into your CRM (HubSpot, Salesforce) to segment campaigns without a human reviewing every lead
- **Founder-led sales at early-stage startups** — get a concise "who just signed up and should I reach out?" summary for every new user, automatically

Swap out the Glop branding and ICP criteria for your own product, and this pipeline is ready to wire into a real signup webhook.

---

**Stack:** LangChain · LangSmith · OpenAI gpt-4o-mini · Python 3.10+

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-0.3+-green?logo=chainlink&logoColor=white)
![LangSmith](https://img.shields.io/badge/LangSmith-Tracing-orange?logo=langchain&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-purple?logo=openai&logoColor=white)

---

## 📁 Project Structure

```
langsmith-signup-email-agent/
├── agent.py          # Agent definition, structured output schema,
│                     # golden dataset, and LLM-as-a-Judge
├── requirements.txt
├── .env.example      # Copy to .env and fill in keys
├── .env              # Your real keys — git-ignored
└── .gitignore
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      agent.py                           │
│                                                         │
│  ┌─────────────┐    ┌──────────────┐   ┌────────────┐  │
│  │  Signup     │───▶│   _Agent     │──▶│ LangSmith  │  │
│  │  Input      │    │  (LLM Chain) │   │  Tracing   │  │
│  └─────────────┘    └──────┬───────┘   └────────────┘  │
│                            │                            │
│                     ┌──────▼───────┐                    │
│                     │  Structured  │                    │
│                     │   Output     │                    │
│                     │  (Pydantic)  │                    │
│                     └──────┬───────┘                    │
│                            │                            │
│          ┌─────────────────┼──────────────────┐         │
│          ▼                 ▼                  ▼         │
│       icp_fit           subject             body        │
│   (high/med/low/       (role-           (personalized   │
│      unknown)          specific)           email)       │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │       LLM-as-a-Judge: Personalization Quality    │   │
│  │   Score: 0 (fail) | 1 (pass) | n/a (no data)    │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## ⚙️ Setup

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

## 🚀 Usage

**Run the agent + full eval suite**
```bash
# Set your LangSmith key in the session first (Windows PowerShell)
$env:LANGSMITH_API_KEY="your_key_here"
python agent.py
```

This runs all 6 golden dataset test cases, prints each email, and scores each one with the LLM-as-a-Judge.

**Expected output:**
```
============================================================
TEST: Baseline - High ICP
============================================================
ICP Fit:  high
Subject:  Welcome to Glop, Sarah! Elevate Your Engineering Team
Body:
  Hi Sarah, Welcome to Glop! As the VP of Engineering at Acme Corp...

⚖️  Personalization Score: 1 — Addresses user by name, role, and company context.

...

PERSONALIZATION SCORE SUMMARY
✅  Baseline - High ICP: 1
✅  Edge: Missing first name: 1
✅  Edge: Generic email domain: 1
✅  Edge: Unclear role: 1
✅  Edge: Stealth company: 1
⏭️   Edge: Incomplete context: n/a

Total: 5/5 (excluding n/a cases)
```

---

## 🧠 How It Works

### 1. ICP Classification
**ICP** stands for **Ideal Customer Profile** — a description of the type of company or person most likely to get value from your product and become a long-term customer. In a SaaS context, ICP fit is used to prioritize sales and marketing effort: high-fit signups get white-glove outreach, low-fit signups get a lighter touch.

This agent scores each signup against Glop's ICP at the time of signup, so the welcome email can be tailored accordingly — before any human ever looks at the lead.

The agent classifies each signup into one of four tiers:

| Tier | Criteria |
|------|----------|
| `high` | Engineering/product leader at a tech or SaaS company, 50+ employees |
| `medium` | Developer or technical role at any company |
| `low` | Non-technical role or company < 10 employees |
| `unknown` | Insufficient information |

### 2. Email Generation
Emails are generated with ICP-tier-specific value props:
- **High** → team productivity, scaling, engineering velocity
- **Medium** → individual developer workflow and speed
- **Low** → warm, simple, no jargon — always uses first name if provided
- **Unknown** → generic and inviting

---

## 🧪 Evaluation Strategy: Online vs Offline

This project implements both types of eval that matter in production AI systems.

### Online Eval (runs in `agent.py`, on every invocation)

**What it is:** After the agent generates each email, a second LLM call immediately scores it for personalization quality — scoring 1 (pass), 0 (fail), or n/a (no data to personalize against).

**Purpose:** Catch quality regressions in real time. In a production system this would run on every real signup, with scores sent to LangSmith so you can monitor trends over time — e.g. "did this prompt change cause more 0s in the last 24 hours?"

```
Score 1  → name used + role/company referenced + context-specific value prop
Score 0  → generic greeting when name available, or role/company ignored
Score n/a → no personalizable data existed in the input (not a failure)
```

### Offline Eval (runs in `eval.py`, before shipping a prompt change)

**What it is:** A batch evaluation that pulls the full golden dataset from LangSmith, reruns the agent on every example, and scores results with two [DeepEval](https://github.com/confident-ai/deepeval) metrics:
- `ExactMatchMetric` — checks that `icp_fit` classification exactly matches the expected label
- `GEval` — an LLM judge that scores email quality holistically (personalization, conciseness, no hallucination)

**Purpose:** Give you a reproducible, before/after comparison when you change the prompt. You run this locally, see whether your scores went up or down across the whole dataset, and only ship if they improved (or at least didn't regress).

### Why you need both

| | Online | Offline |
|---|---|---|
| **When it runs** | Every live invocation | Before shipping a change |
| **What it catches** | Production drift, live regressions | Prompt changes that hurt quality |
| **Output** | Per-run score in LangSmith traces | Aggregate pass rate across dataset |
| **File** | `agent.py` (`judge_personalization`) | `eval.py` |

Online eval tells you if things break in production. Offline eval tells you if your changes made things better or worse before you ship. You need both — one without the other leaves you either flying blind in prod, or unable to iterate confidently on your prompt.

---

## 📊 Eval Results

### Personalization Score: 5/5 ✅
*(1 n/a case excluded — no personalizable data in input)*

| Test Case | ICP Fit | Score | Notes |
|-----------|---------|-------|-------|
| Baseline — High ICP (Sarah, VP Eng) | high | ✅ 1 | Name + role + company used |
| Missing first name | medium | ✅ 1 | Fell back to role + company |
| Generic email domain (gmail) | medium | ✅ 1 | Used first name + role |
| Unclear role (Associate, 25 ppl) | low | ✅ 1 | Used first name, warm tone |
| Stealth company (CEO, 8 ppl) | low | ✅ 1 | Used first name |
| Incomplete context (email only) | unknown | ⏭️ n/a | No data to personalize |

---

## 📈 Before vs After Prompt Improvement

| | Before | After |
|---|---|---|
| **Subject** | "Welcome to Glop, Sarah!" | "Welcome to Glop, Sarah! Elevate Your Engineering Team" |
| **Body** | Generic "leverage our tools" | Role-specific: engineering velocity, scaling |
| **CTA** | "Feel free to reach out" | "Explore your dashboard to get started" |
| **Word limit** | 150 words | 120 words |
| **Low ICP fallback** | Dropped name | Always uses first name if provided |
| **Eval score** | Not measured | 5/5 ✅ |

---

## 🔄 The Production Feedback Loop

```
Agent runs on new signups
        ↓
LangSmith traces every run (inputs, outputs, latency, cost)
        ↓
LLM-as-a-Judge scores personalization quality
        ↓
Failures identified → added to golden dataset
        ↓
Prompt improved → agent re-run
        ↓
Before/after comparison confirms improvement
        ↓ (loop)
```

---

## 📏 Evaluation Metrics

| Metric | Type | Tool | Result |
|--------|------|------|--------|
| ICP fit classification | Structured output | Pydantic + GPT-4o-mini | ✅ All cases correct |
| Personalization quality | LLM-as-a-Judge (0/1/n/a) | Custom judge | 5/5 ✅ |
| Tracing & observability | Online traces | LangSmith | ✅ Active |

---

## 📝 Reflection

This project implements the **continuous improvement loop** for AI agents:

1. **Baseline** — ran the agent, reviewed traces in LangSmith
2. **Prompt improvement** — added ICP-tier-specific guidance, tighter word limit, required CTA
3. **Golden dataset** — 6 test cases covering happy path and real-world edge cases
4. **LLM-as-a-Judge** — automated scoring for personalization quality (0/1/n/a)
5. **Iteration** — fixed low ICP fallback, added n/a handling for incomplete context

**Key insight:** Without evals, you're guessing whether your prompt got better. With a golden dataset and a judge, you have a repeatable, objective measure of improvement.
