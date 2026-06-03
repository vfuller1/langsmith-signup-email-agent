"""
Offline Evaluation (Step 2)
Runs DeepEval metrics against the golden dataset stored in LangSmith.

Metrics:
  - icp_fit_evaluator : ExactMatchMetric  — exact match on icp_fit field
  - email_evaluator   : GEval             — LLM-as-a-judge on email quality

Usage:
    python eval.py
"""

import json
from dotenv import load_dotenv

load_dotenv()

from agent import agent
from langsmith import Client
from deepeval.metrics import ExactMatchMetric, GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams   # SingleTurnParams replaces deprecated LLMTestCaseParams

# ── Fetch golden dataset from LangSmith ───────────────────────────────────────
ls = Client()
DATASET_NAME = "golden-dataset"

examples = list(ls.list_examples(dataset_name=DATASET_NAME))
print(f"Loaded {len(examples)} examples from '{DATASET_NAME}'")
print("Sample input keys: ", examples[0].inputs.keys())
print("Sample output keys:", examples[0].outputs.keys())

# ── Define evaluators ─────────────────────────────────────────────────────────
icp_fit_evaluator = ExactMatchMetric(threshold=1.0)
icp_fit_evaluator.include_reason = True

email_evaluator = GEval(
    name="Email Quality",
    criteria=(
        "Evaluate if the email is professional, personalized "
        "(uses the person's name/role/company), concise (under 150 words), "
        "and does not hallucinate facts not present in the input."
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
    result = agent.invoke(input_payload)
    actual = result["structured_response"]

    # Handle potential 'outputs_1' nesting from LangSmith dataset format
    expected = ex.outputs.get("outputs_1", ex.outputs)

    # ICP fit — exact match
    icp_fit_tc = LLMTestCase(
        input=json.dumps(input_payload),
        actual_output=actual.icp_fit,
        expected_output=expected.get("icp_fit", ""),
    )
    icp_fit_evaluator.measure(icp_fit_tc)
    icp_fit_scores.append(icp_fit_evaluator.score)

    # Email quality — LLM judge
    email_tc = LLMTestCase(
        input=json.dumps(input_payload),
        actual_output=actual.body,
        expected_output=expected.get("body", ""),
    )
    email_evaluator.measure(email_tc)
    email_scores.append(email_evaluator.score)
    print(f"  Email reason: {email_evaluator.reason}")

# ── Results ───────────────────────────────────────────────────────────────────
print("\n── Results ──────────────────────────────────────────")
print(f"icp_fit exact match rate : {sum(icp_fit_scores) / len(icp_fit_scores):.2f}")
print(f"email avg score          : {sum(email_scores) / len(email_scores):.2f}")
