"""
Offline Evaluation (Step 2)
Runs DeepEval metrics against the golden dataset stored in LangSmith.

Metrics:
  - icp_fit_evaluator : GEval — LLM judge on ICP fit classification quality
  - email_evaluator   : GEval — LLM judge on email quality (no reference needed)

Usage:
    python eval.py
"""

from dotenv import load_dotenv
load_dotenv()

from agent import agent
from langsmith import Client
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

# ── Fetch golden dataset from LangSmith ───────────────────────────────────────
ls = Client()
DATASET_NAME = "golden-dataset-signup-agent"

examples = list(ls.list_examples(dataset_name=DATASET_NAME))
print(f"Loaded {len(examples)} examples from '{DATASET_NAME}'")

# ── Define evaluators ─────────────────────────────────────────────────────────

icp_fit_evaluator = GEval(
    name="ICP Fit Quality",
    criteria=(
        "Given the signup input, evaluate whether the ICP fit classification "
        "is reasonable and well-justified using these rules: "
        "- high: engineering/product leader at tech or SaaS company, 50+ employees. "
        "- medium: developer or technical role at any company. "
        "- low: non-technical role or company under 10 employees. "
        "- unknown: insufficient information to classify. "
        "Score 1.0 if the classification is correct and justified. "
        "Score 0.0 if the classification is clearly wrong."
    ),
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model="gpt-4o-mini",
    threshold=0.5,
)
icp_fit_evaluator.include_reason = True

email_evaluator = GEval(
    name="Email Quality",
    criteria=(
        "Evaluate the welcome email against these four criteria: "
        "1. PERSONALIZATION: uses the person's first name if provided in the input; "
        "references their role or company if provided; connects Glop's value to their specific context. "
        "2. CONCISENESS: under 120 words, no filler phrases or buzzwords. "
        "3. ACCURACY: does not mention details absent from the input; "
        "does not confuse the product name Glop with the user's company name. "
        "4. CTA: ends with a clear next-step call to action. "
        "Score 1.0 if all criteria are met. Deduct proportionally for each failure."
    ),
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    model="gpt-4o-mini",
    threshold=0.5,
)
email_evaluator.include_reason = True

# ── Run evals ─────────────────────────────────────────────────────────────────
icp_fit_scores = []
email_scores = []

for ex in examples:
    input_payload = ex.inputs

    # Build clean text string for agent and judge
    input_text = "\n".join(f"{k}: {v}" for k, v in input_payload.items())

    # Invoke agent in the correct messages format
    result = agent.invoke({
        "messages": [{
            "role": "user",
            "content": f"Process this signup:\n{input_text}"
        }]
    })
    actual = result["structured_response"]

    print(f"\n{'='*50}")
    print(f"Input:   {input_text[:80]}...")
    print(f"ICP Fit: {actual.icp_fit}")

    # Score ICP fit
    icp_tc = LLMTestCase(
        input=input_text,
        actual_output=f"icp_fit: {actual.icp_fit}\nreason: {actual.reason}",
    )
    icp_fit_evaluator.measure(icp_tc)
    icp_fit_scores.append(icp_fit_evaluator.score)
    print(f"ICP Score:   {icp_fit_evaluator.score:.2f} — {icp_fit_evaluator.reason}")

    # Score email quality
    email_tc = LLMTestCase(
        input=input_text,
        actual_output=actual.body,
    )
    email_evaluator.measure(email_tc)
    email_scores.append(email_evaluator.score)
    print(f"Email Score: {email_evaluator.score:.2f} — {email_evaluator.reason}")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print("── Results ──────────────────────────────────────────")
print(f"ICP fit avg score  : {sum(icp_fit_scores) / len(icp_fit_scores):.2f}")
print(f"Email avg score    : {sum(email_scores) / len(email_scores):.2f}")
print(f"Cases evaluated    : {len(examples)}")