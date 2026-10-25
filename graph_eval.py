"""
Offline Evaluation for the LangGraph agent
Runs graph_agent.py against the golden dataset in LangSmith, up to the human
approval step, and records the results as a LangSmith experiment.

Metrics:
  - icp_fit_match      : classify step matches the dataset's reference icp_fit
  - personalization    : final judge score after the revise loop (n/a is skipped)
  - needed_revision    : 1 if the first draft failed the judge and was rewritten
  - paused_for_approval: run stopped at human_approval and sent nothing

Usage:
    python graph_eval.py
"""

import uuid

from langgraph.checkpoint.memory import InMemorySaver
from langsmith import Client

# Importing graph_agent also loads .env and turns on LangSmith tracing
from graph_agent import build_graph

DATASET_NAME = "golden-dataset-signup-agent"

# In-memory checkpointer: each example gets its own thread and nothing is kept on disk
app = build_graph(InMemorySaver())


# ── Target: run the graph until it pauses for approval ────────────────────────
def run_graph(inputs: dict) -> dict:
    signup = "\n".join(f"{k}: {v}" for k, v in inputs.items())
    config = {"configurable": {"thread_id": f"eval-{uuid.uuid4().hex[:6]}"}}
    app.invoke({"signup": signup}, config)
    state = app.get_state(config)
    values = state.values
    return {
        "icp_fit": values["icp_fit"],
        "subject": values["subject"],
        "body": values["body"],
        "judge_score": values["judge_score"],
        "revision_count": values["revision_count"],
        "paused_at": list(state.next),
    }


# ── Evaluators ────────────────────────────────────────────────────────────────
def icp_fit_match(outputs: dict, reference_outputs: dict) -> dict:
    expected = reference_outputs["icp_fit"]
    return {
        "key": "icp_fit_match",
        "score": int(outputs["icp_fit"] == expected),
        "comment": f"got {outputs['icp_fit']}, expected {expected}",
    }


def personalization(outputs: dict) -> dict:
    score = outputs["judge_score"]
    if score == "n/a":
        return {"key": "personalization", "score": None, "comment": "n/a: nothing to personalize"}
    return {"key": "personalization", "score": int(score)}


def needed_revision(outputs: dict) -> dict:
    return {"key": "needed_revision", "score": int(outputs["revision_count"] > 0)}


def paused_for_approval(outputs: dict) -> dict:
    return {"key": "paused_for_approval", "score": int(outputs["paused_at"] == ["human_approval"])}


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    results = Client().evaluate(
        run_graph,
        data=DATASET_NAME,
        evaluators=[icp_fit_match, personalization, needed_revision, paused_for_approval],
        experiment_prefix="graph-agent",
        max_concurrency=3,
    )

    rows = []
    for r in results:
        inputs = r["example"].inputs
        scores = {e.key: e.score for e in r["evaluation_results"]["results"]}
        rows.append((inputs.get("first_name") or inputs.get("role") or inputs["email"], r["run"].outputs, scores))

    def icon(score):
        return {1: "✅", 0: "❌", None: "⏭️ "}.get(score, "?")

    print(f"\n{'='*72}")
    print(f"{'Signup':<20}{'ICP fit':<20}{'Personal.':<12}{'Revised':<10}{'Paused'}")
    print('='*72)
    for name, out, s in rows:
        print(f"{name:<20}{icon(s['icp_fit_match'])} {out['icp_fit']:<17}{icon(s['personalization']):<11}"
              f"{'yes' if s['needed_revision'] else 'no':<10}{icon(s['paused_for_approval'])}")

    def total(key):
        scored = [s[key] for _, _, s in rows if s[key] is not None]
        return f"{sum(scored)}/{len(scored)}"

    print(f"\nICP fit correct     : {total('icp_fit_match')}")
    print(f"Personalization     : {total('personalization')} (excluding n/a)")
    print(f"Needed a revision   : {total('needed_revision')}")
    print(f"Paused for approval : {total('paused_for_approval')}")
    print(f"\nExperiment in LangSmith: {results.experiment_name}")
