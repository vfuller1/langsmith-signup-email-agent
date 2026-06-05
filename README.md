# 🚀 Signup Email Agent

A LangChain agent that processes new user signups, classifies ICP fit, and generates personalized welcome emails — with full LangSmith tracing, a golden eval dataset, and a custom LLM-as-a-Judge scoring pipeline.

![End to end overview](images/Email%20Agent%20Eval%20end%20to%20end.jpg)

## 💡 Use Cases

This agent is a template for any SaaS product that wants to **automatically qualify and engage new signups** without manual effort. Real-world applications include:

- **PLG (Product-Led Growth) onboarding** — trigger a personalized welcome email the moment someone signs up, with messaging tuned to their role and company size
- **Sales prioritization** — route high-ICP signups to a sales rep immediately, low-ICP to a self-serve nurture sequence
- **Marketing automation** — feed ICP scores into your CRM (HubSpot, Salesforce) to segment campaigns without a human reviewing every lead
- **Founder-led sales at early-stage startups** — get a concise "who just signed up and should I reach out?" summary for every new user, automatically

Swap out the Glop branding and ICP criteria for your own product, and this pipeline is ready to wire into a real signup webhook.

---

## ⚠️ The Problem With Shipping AI Without Evals

Most AI agents get shipped with vibes-based quality control. You run it a few times, it looks good, you push to prod. Then three weeks later someone notices the emails sound generic, the classifications are wrong, and nobody knows when it broke.

"Simple" agents still fail in subtle ways:
- A VP of Engineering gets a generic "leverage our tools" email
- A user with no first name gets "Hi ,"
- A CEO at an 8-person startup gets classified the same as a developer at a 500-person company

These aren't crashes. They're quality failures — and without an eval pipeline, you'll never know they're happening. This project shows how to build the eval layer that catches them.

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

![Multi-Model Judge Architecture](images/Multi-Model%20Judge%20Architechture.png)

User data streams in → the Agent Orchestrator (LLM Chain) processes it through a Pydantic structured output definition → results are captured for LangSmith tracing → a second LLM-as-a-Judge call scores personalization quality (0 / 1 / n/a) in real time.

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

Raw webhook JSON is first passed through a Pydantic model that validates, capitalizes, and maps fields into a clean structured format before classification runs:

![Data Payload Transformation](images/Data%20Payload%20Transformation.png)

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

### 3. LLM-as-a-Judge
After each email is generated, a second LLM call scores personalization quality. The judge sits between the primary LLM and the production trace monitor, scoring every output before it lands in LangSmith:

![Multi-Model LLM-as-a-Judge Flow](images/Multi-Model%20LLM-as-a-Judge%20Flow.png)

```
Score 1   → name used + role/company referenced + context-specific value prop
Score 0   → generic greeting when name available, or role/company ignored
Score n/a → no personalizable data existed in the input (not a failure)
```

---

## 🧪 Evaluation Strategy: Online vs Offline

This project implements both types of eval that matter in production AI systems.

### Offline Eval — run manually before shipping a prompt change

```powershell
# Option 1: agent.py golden dataset (custom LLM judge, runs locally)
python agent.py

# Option 2: eval.py DeepEval suite (pulls from LangSmith dataset, uses DeepEval metrics)
python eval.py
```

**What it is:** A batch evaluation that runs the agent against all 6 golden dataset test cases and scores each output with a custom `judge_personalization()` function — an LLM call that returns 1 (pass), 0 (fail), or n/a.

**Purpose:** Give you a reproducible, before/after comparison when you change the prompt. These are essentially unit/integration tests for your agent — run them before every deployment to catch regressions.

The golden dataset lives in LangSmith and contains all 6 test cases with their reference outputs:

![LangSmith Golden Dataset](images/LangSmith%20golden-dataset.png)

**Result: 5/5 ✅** (1 n/a excluded)

### Online Eval — no command needed, runs automatically

```
# Nothing to run — just invoke the agent normally and LangSmith scores it automatically.
python agent.py          # or any production invocation (webhook, API call, etc.)
```

Results appear in the **LangSmith dashboard** under your project's traces — not in the terminal.

**What it is:** A LangSmith Online Evaluator (`personalization_quality`) configured to run on traces from the `langsmith-signup-email-agent` project. After every agent run, LangSmith automatically scores the output and attaches a `true/false` feedback tag to the trace.

**Sampling rate:** Set to 100% for development. In production, **10% is recommended** — this gives statistically significant quality metrics without paying for an evaluator LLM call on every single user interaction.

**LangSmith configuration:**
- **Evaluator:** OnlineEval → `personalization_quality`
- **Feedback key:** `personalization_quality` (Boolean)
- **Sampling rate:** 100% (dev) → 10% (production recommended)
- **Source:** `langsmith-signup-email-agent` project, all Runs

Two evaluators are configured in LangSmith — one for online production monitoring (`personalization_quality`) and one for prompt injection detection:

![LangSmith Evaluators](images/LangSmith%20evaluators.png)

The full telemetry flow — from the production webhook through LangSmith's sampling controller to the automated quality evaluator:

![LangSmith Telemetry Capture](images/The%20LangSmith%20Telemetry%20Capture.png)

### Why you need both

| | Offline (agent.py) | Online (LangSmith) |
|---|---|---|
| **When it runs** | Manually, before shipping a change | Automatically on every invocation |
| **What it catches** | Prompt regressions before they ship | Production drift and live failures |
| **Output** | Aggregate pass rate in terminal | Per-run score in LangSmith traces |
| **Best for** | Iterating on the prompt confidently | Monitoring quality over time |

Offline eval tells you if your changes made things better or worse before you ship. Online eval tells you if things break in production. You need both.

---

## 🔄 The Continuous Improvement Loop

```
01 DEVELOPMENT
   Run offline evals in agent.py against the golden dataset
        ↓
02 DEPLOYMENT
   Deploy agent (e.g. webhook, Cloud Run, API)
        ↓
03 MONITORING
   LangSmith Online Evaluator scores live traces automatically
   Recommended sampling rate: 10% in production
        ↓
04 REFINEMENT
   Export production failures → add to golden dataset
   Fix prompt → re-run offline evals → confirm improvement
        ↓ (loop)
```

**Key insight:** Errors identified in production traces should be exported back into the golden dataset. This creates a feedback loop where your offline test suite gets stronger every time something breaks in prod.

---

## 🛡️ Safety Evaluators

Beyond quality, three additional online evaluators run automatically in LangSmith:

| Evaluator | What it flags | Response |
|-----------|--------------|----------|
| **PII Leakage** | Sensitive personal data appearing in agent input | Routes trace to human review queue via LangSmith Automation |
| **Prompt Injection** | Attempts to hijack the agent via malicious input | Flags trace with `prompt_injection: true` |
| **Code Injection** | Code-based attack patterns in input | Flags trace with `code_injection: true` |

When `pii_leakage: true` fires, the trace automatically routes to a human review queue — no manual monitoring required.

Safety and quality are separate concerns. Build separate evaluators for each; don't combine them into one judge.

---

## 💡 Key Takeaways

1. **Evals aren't optional for production AI.** Without them, you're flying blind — no way to know if your agent is getting better or worse as you iterate.

2. **Start with a golden dataset.** Even 5–6 examples covering your known edge cases catches most regressions. Add to it every time something breaks in prod.

3. **Online + offline evals serve different purposes.** Offline tells you if your changes made things better before you ship. Online tells you if things break after you ship. You need both.

4. **LLM-as-a-Judge beats exact match.** Reference outputs get stale. A well-prompted judge that evaluates against clear criteria is more robust and easier to maintain.

5. **Safety and quality are separate concerns.** Build separate evaluators for each — don't try to combine them into one judge.

---

## 🛠️ Troubleshooting

### LangSmith 403 Forbidden
The API key is not set in the current terminal session. Fix:
```powershell
$env:LANGSMITH_API_KEY="your_key_here"
python agent.py
```

### KeyError in LangSmith Evaluator
A common error where the evaluator expects a specific JSON key (e.g. `outputs_one`) that doesn't match the actual trace structure. Fix: open a failing trace in LangSmith, inspect the raw JSON output, and verify the top-level key names match what your evaluator prompt references via `{{output}}`.

### Simulating Failures to Test the Feedback Loop
Two reliable ways to generate failures for testing:
- **Prompt degradation** — temporarily weaken the system prompt (e.g. remove the name/role instructions) to produce generic emails that score 0
- **Data edge cases** — introduce malformed inputs (missing name, generic domain, incomplete context) into the test set — these are already covered in the golden dataset

### Dataset Count Mismatch
If your local example count doesn't match what LangSmith shows, this is likely a caching or sync issue. Refresh the LangSmith dataset page and re-run to force a fresh fetch.

---

## 🌐 Framework Compatibility

This project uses **LangChain + LangSmith**, which are tightly coupled and the recommended pairing for LangChain-based agents.

For teams using other frameworks:

| Framework | Observability | Offline Eval |
|-----------|--------------|--------------|
| LangChain | LangSmith (native) | `judge_personalization()` in agent.py |
| Google ADK | OpenTelemetry | DeepEval (native ADK integration) |
| Custom agents | LangSmith or LangFuse via OpenTelemetry | DeepEval |

**Recommendation:** Choose an observability platform that actively tracks the release cycle of your underlying framework. For LangChain users, LangSmith is the natural choice.

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
| **Eval score** | 4/6 (before prompt fix) | 5/5 ✅ |

---

## 📏 Evaluation Metrics

| Metric | Type | Tool | Result |
|--------|------|------|--------|
| ICP fit classification | Structured output | Pydantic + GPT-4o-mini | ✅ All cases correct |
| ICP fit quality | GEval LLM judge | DeepEval + GPT-4o-mini | 0.78 avg ✅ |
| Personalization quality (offline) | LLM-as-a-Judge (0/1/n/a) | `judge_personalization()` in agent.py | 5/5 ✅ |
| Email quality | GEval LLM judge | DeepEval + GPT-4o-mini | 0.73 avg ✅ |
| Personalization quality (online) | Boolean (true/false) | LangSmith OnlineEval | ✅ Active, 100% sampling |
| PII leakage detection | Online evaluator | LangSmith | ✅ Active |
| Prompt injection detection | Online evaluator | LangSmith | ✅ Active |
| Tracing & observability | Online traces | LangSmith | ✅ Active |

---

## 🔗 Get the Code

The full project is open source. If you're building AI agents and haven't thought about evals yet, this is a good place to start.

👉 [github.com/vfuller1/langsmith-signup-email-agent](https://github.com/vfuller1/langsmith-signup-email-agent)

