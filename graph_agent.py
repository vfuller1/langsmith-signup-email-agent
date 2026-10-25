"""
Signup Email Agent — LangGraph version
Same job as agent.py, rebuilt as a graph with a human in the loop:

  classify → draft (tone picked by ICP fit) → judge → [one revision max] → human approval → send

The run pauses at human approval and is checkpointed to SQLite, so it can be
resumed later from a separate process. "send" only writes to outbox.jsonl.

Usage:
    python graph_agent.py --case alex --weak-first-draft     # run until approval
    python graph_agent.py --resume <thread_id> approve        # or: reject
    python graph_agent.py --resume <thread_id> edit --body "New email body"
    python graph_agent.py --signup "email: a@b.com
first_name: Ann"                                              # any custom signup
    python graph_agent.py --diagram                           # print Mermaid diagram
"""

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel

# Importing agent.py also loads .env and turns on LangSmith tracing
from agent import judge_personalization

HERE = Path(__file__).parent
CHECKPOINT_DB = HERE / "checkpoints.sqlite"
OUTBOX = HERE / "outbox.jsonl"
MAX_REVISIONS = 1


# ── State passed between steps ────────────────────────────────────────────────
class SignupState(TypedDict, total=False):
    signup: str                 # raw signup fields, one "key: value" per line
    weak_first_draft: bool      # demo flag: force a generic first draft
    icp_fit: str
    reason: str
    subject: str
    body: str
    judge_score: int | str      # 1, 0 or "n/a"
    judge_feedback: str
    revision_count: int
    decision: str               # approve, edit or reject


# ── Prompts ───────────────────────────────────────────────────────────────────
CLASSIFY_PROMPT = """
You classify signups for a dev tool SaaS called 'Glop' by ICP fit.

- high:    engineering/product leader at a tech or SaaS company, 50+ employees
- medium:  developer or technical role at any company
- low:     non-technical role or very small company (<10 employees)
- unknown: insufficient information to classify

Give a one-sentence reason.
"""

EMAIL_RULES = """
You write the welcome email for a new signup to a dev tool SaaS called 'Glop'.

- Subject: specific to the person's role or company, not just "Welcome to Glop"
- Opening: if first_name is provided, ALWAYS start the body with "Hi <first_name>,"; otherwise start with "Hi there,"
- Body: in 2–3 short sentences, connect Glop's value to their specific role and company context
- Closing: one simple next-step CTA (e.g. "Explore your dashboard" or "Check out our quick-start guide")
- Tone: concise, professional, human — no buzzwords, no filler phrases
- Under 120 words total
- Do NOT mention details absent from the input
- Do NOT confuse 'Glop' with the user's company name
"""

# One draft node per tone; the conditional edge after classify picks which runs
TONES = {
    "draft_high": "Emphasize team productivity, scaling, and engineering velocity.",
    "draft_medium": "Emphasize individual developer workflow and speed.",
    "draft_low": "Keep it warm and simple, no jargon.",
}

# Used only with --weak-first-draft, so the judge fails it and the revise loop runs
WEAK_FIRST_DRAFT_PROMPT = """
Write a short, generic welcome email for a SaaS called 'Glop'.
Do not use the person's name, role, or company.
"""


# ── Steps ─────────────────────────────────────────────────────────────────────
class Classification(BaseModel):
    icp_fit: Literal["high", "medium", "low", "unknown"]
    reason: str


class Email(BaseModel):
    subject: str
    body: str


_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


def classify(state: SignupState) -> dict:
    result = _llm.with_structured_output(Classification).invoke([
        SystemMessage(content=CLASSIFY_PROMPT),
        HumanMessage(content=f"Signup:\n{state['signup']}"),
    ])
    return {"icp_fit": result.icp_fit, "reason": result.reason, "revision_count": 0}


def make_draft_node(tone: str):
    def draft(state: SignupState) -> dict:
        revising = "judge_feedback" in state
        if state.get("weak_first_draft") and not revising:
            system = WEAK_FIRST_DRAFT_PROMPT
        else:
            system = f"{EMAIL_RULES}\nTone: {tone}"

        user = f"Signup:\n{state['signup']}\n\nICP fit: {state['icp_fit']}"
        if revising:
            user += (
                f"\n\nYour previous draft failed review:\n{state['body']}"
                f"\n\nReviewer feedback: {state['judge_feedback']}"
                "\n\nRewrite the email to fix this."
            )

        email = _llm.with_structured_output(Email).invoke([
            SystemMessage(content=system),
            HumanMessage(content=user),
        ])
        return {
            "subject": email.subject,
            "body": email.body,
            "revision_count": state["revision_count"] + int(revising),
        }
    return draft


def route_by_tone(state: SignupState) -> str:
    return {"high": "draft_high", "medium": "draft_medium"}.get(state["icp_fit"], "draft_low")


def judge(state: SignupState) -> dict:
    judgment = judge_personalization(state["signup"], state["body"])
    return {"judge_score": judgment["score"], "judge_feedback": judgment["reason"]}


def route_after_judge(state: SignupState) -> str:
    if state["judge_score"] == 0 and state["revision_count"] < MAX_REVISIONS:
        return route_by_tone(state)
    return "human_approval"


def human_approval(state: SignupState) -> dict:
    # Pauses the run here; the value passed to Command(resume=...) comes back as reply
    reply = interrupt({
        "subject": state["subject"],
        "body": state["body"],
        "icp_fit": state["icp_fit"],
        "judge_score": state["judge_score"],
        "revision_count": state["revision_count"],
    })
    update = {"decision": reply["action"]}
    if reply["action"] == "edit":
        update["body"] = reply["body"]
    return update


def route_after_approval(state: SignupState) -> str:
    return END if state["decision"] == "reject" else "send"


def send(state: SignupState, config: RunnableConfig) -> dict:
    # Stub: nothing is really sent
    to = next(
        (line.split(":", 1)[1].strip() for line in state["signup"].splitlines()
         if line.lower().startswith("email:")),
        "unknown",
    )
    record = {
        "thread_id": config["configurable"]["thread_id"],
        "to": to,
        "subject": state["subject"],
        "body": state["body"],
        "decision": state["decision"],
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(OUTBOX, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return {}


# ── Graph ─────────────────────────────────────────────────────────────────────
def build_graph(checkpointer=None):
    graph = StateGraph(SignupState)
    graph.add_node("classify", classify)
    for name, tone in TONES.items():
        graph.add_node(name, make_draft_node(tone))
    graph.add_node("judge", judge)
    graph.add_node("human_approval", human_approval)
    graph.add_node("send", send)

    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", route_by_tone, list(TONES))
    for name in TONES:
        graph.add_edge(name, "judge")
    graph.add_conditional_edges("judge", route_after_judge, [*TONES, "human_approval"])
    graph.add_conditional_edges("human_approval", route_after_approval, ["send", END])
    graph.add_edge("send", END)
    return graph.compile(checkpointer=checkpointer)


# ── CLI ───────────────────────────────────────────────────────────────────────
CASES = {
    "victor": """email: victor@acmecorp.com
first_name: Victor
company_name: Acme Corp
role: VP of Engineering
industry: SaaS
company_size: 500""",
    "no-name": """email: user@techcorp.com
company_name: TechCorp
role: Software Engineer
industry: SaaS
company_size: 200""",
    "john": """email: john.smith@gmail.com
first_name: John
role: Developer""",
    "alex": """email: alex@startupco.com
first_name: Alex
company_name: StartupCo
role: Associate
company_size: 25""",
    "maya": """email: founder@stealth.io
first_name: Maya
role: CEO
company_size: 8""",
    "minimal": """email: someone@company.com""",
}


def indent(text: str) -> str:
    return "\n".join(f"    {line}" for line in text.splitlines())


def print_step(node: str, out: dict) -> None:
    if node == "classify":
        print(f"▶ classify        ICP fit: {out['icp_fit']} — {out['reason']}")
    elif node in TONES:
        label = "revised draft" if out["revision_count"] else "first draft"
        print(f"▶ {node:<15} {label}\n    Subject: {out['subject']}\n{indent(out['body'])}")
    elif node == "judge":
        icon = {1: "✅", 0: "❌"}.get(out["judge_score"], "⏭️ ")
        print(f"▶ judge           {icon} score {out['judge_score']} — {out['judge_feedback']}")
    elif node == "human_approval":
        print(f"▶ human_approval  decision: {out['decision']}")
    elif node == "send":
        print(f"▶ send            written to {OUTBOX.name}")


def stream(app, payload, config) -> None:
    for update in app.stream(payload, config, stream_mode="updates"):
        for node, out in update.items():
            if node != "__interrupt__":
                print_step(node, out or {})

    state = app.get_state(config)
    thread_id = config["configurable"]["thread_id"]
    if state.next:
        print(f"\n⏸  Paused for human approval (thread_id: {thread_id})")
        print(f"   Approve: python graph_agent.py --resume {thread_id} approve")
        print(f"   Edit:    python graph_agent.py --resume {thread_id} edit --body \"...\"")
        print(f"   Reject:  python graph_agent.py --resume {thread_id} reject")
    else:
        print(f"\n✔  Done (thread_id: {thread_id}, decision: {state.values.get('decision')})")


def make_config(thread_id: str, run_name: str) -> dict:
    # thread_id in metadata groups the start and resume traces into one LangSmith thread
    return {
        "configurable": {"thread_id": thread_id},
        "run_name": run_name,
        "metadata": {"thread_id": thread_id},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Signup email agent as a LangGraph graph")
    parser.add_argument("--case", choices=CASES, default="victor", help="built-in signup to process")
    parser.add_argument("--signup", help="custom signup text instead of --case")
    parser.add_argument("--weak-first-draft", action="store_true",
                        help="force a generic first draft to demo the judge-and-revise loop")
    parser.add_argument("--resume", nargs=2, metavar=("THREAD_ID", "ACTION"),
                        help="resume a paused run with approve, edit or reject")
    parser.add_argument("--body", help="replacement email body, used with edit")
    parser.add_argument("--diagram", action="store_true", help="print the graph as Mermaid")
    args = parser.parse_args()

    if args.diagram:
        print(build_graph().get_graph().draw_mermaid())
        return

    with SqliteSaver.from_conn_string(str(CHECKPOINT_DB)) as checkpointer:
        app = build_graph(checkpointer)

        if args.resume:
            thread_id, action = args.resume
            if action not in ("approve", "edit", "reject"):
                parser.error("ACTION must be approve, edit or reject")
            if action == "edit" and not args.body:
                parser.error("edit needs --body")
            config = make_config(thread_id, "signup-graph-resume")
            if not app.get_state(config).next:
                print(f"No run is waiting for approval on thread {thread_id}")
                return
            reply = {"action": action, "body": args.body}
            stream(app, Command(resume=reply), config)
        else:
            name = "custom" if args.signup else args.case
            thread_id = f"signup-{name}-{uuid.uuid4().hex[:6]}"
            signup = args.signup or CASES[args.case]
            print(f"Processing signup ({name}):\n{indent(signup)}\n")
            payload = {"signup": signup, "weak_first_draft": args.weak_first_draft}
            stream(app, payload, make_config(thread_id, "signup-graph"))


if __name__ == "__main__":
    main()
