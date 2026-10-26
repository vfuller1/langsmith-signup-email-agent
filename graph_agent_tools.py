"""
Signup Email Agent — LangGraph version with tool calling
A copy of graph_agent.py with one extra step at the front: the model decides
to call a (fake) CRM tool, get_account_status, and a ToolNode runs it.

  lookup ⇄ tools → add_account_info → classify → draft → judge → human approval → send

Everything after add_account_info is reused from graph_agent.py unchanged.

Usage:
    python graph_agent_tools.py --case victor           # existing customer
    python graph_agent_tools.py --case alex             # free trial
    python graph_agent_tools.py --case john             # no account found
    python graph_agent_tools.py --resume last approve   # or: reject / edit --body "..."
    python graph_agent_tools.py --diagram
"""

import argparse
import json
import uuid
from typing import Annotated

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command

# Importing graph_agent also loads .env and turns on LangSmith tracing
import graph_agent as base

CHECKPOINT_DB = base.HERE / "checkpoints_tools.sqlite"
LAST_THREAD = base.HERE / "last_thread_tools.txt"


# ── The fake tool ─────────────────────────────────────────────────────────────
# Stands in for a CRM or billing lookup. Keyed by email domain.
FAKE_ACCOUNTS = {
    "acmecorp.com": {"status": "active_customer", "plan": "Team", "seats": 40, "account_owner": "Dana (sales)"},
    "startupco.com": {"status": "free_trial", "plan": "Trial", "trial_days_left": 9},
    "techcorp.com": {"status": "churned", "plan": "none", "cancelled": "2026-08"},
}


@tool
def get_account_status(email: str) -> str:
    """Look up whether the signup's company already has a Glop account, by email address.

    Returns the account status (active_customer, free_trial, churned, or no_account) and plan details.
    """
    domain = email.split("@")[-1].lower().strip()
    return json.dumps({"domain": domain, **FAKE_ACCOUNTS.get(domain, {"status": "no_account"})})


TOOLS = [get_account_status]

# One extra email rule so the drafts use what the tool found. Changed here only,
# so graph_agent.py keeps its tested prompt.
base.EMAIL_RULES += """- If the signup has an "account:" line, use it: an active customer → say their company already
  uses Glop, so they're joining the team's existing workspace, and name the account owner as their
  contact for questions; a free trial → mention the days left;
  churned → welcome them back; no account → say nothing about accounts
"""


# ── State: the original fields, plus the tool conversation ───────────────────
class ToolSignupState(base.SignupState, total=False):
    messages: Annotated[list, add_messages]  # model and tool messages for the lookup loop
    account_info: str


# ── New steps ─────────────────────────────────────────────────────────────────
LOOKUP_PROMPT = """
You prepare signups for a welcome email. Before anything else, check whether the
person's company already has a Glop account: call get_account_status with their email.
If there is no email, don't call the tool.
After you have the result, reply with ONE line summarizing the account, for example:
"account: active customer on the Team plan (40 seats), owner Dana (sales)".
"""

_lookup_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).bind_tools(TOOLS)


def lookup(state: ToolSignupState) -> dict:
    messages = state.get("messages") or [
        SystemMessage(content=LOOKUP_PROMPT),
        HumanMessage(content=f"Signup:\n{state['signup']}"),
    ]
    reply = _lookup_llm.invoke(messages)
    # First call: save the starting messages too, so the next turn has the full conversation
    return {"messages": [reply] if state.get("messages") else [*messages, reply]}


def add_account_info(state: ToolSignupState) -> dict:
    summary = state["messages"][-1].content.strip()
    # Appending to the signup means classify, draft and judge see it with no changes
    return {"account_info": summary, "signup": f"{state['signup']}\n{summary}"}


# ── Graph ─────────────────────────────────────────────────────────────────────
def build_graph(checkpointer=None):
    graph = StateGraph(ToolSignupState)
    graph.add_node("lookup", lookup)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_node("add_account_info", add_account_info)
    graph.add_node("classify", base.classify)
    for name, tone in base.TONES.items():
        graph.add_node(name, base.make_draft_node(tone))
    graph.add_node("judge", base.judge)
    graph.add_node("human_approval", base.human_approval)
    graph.add_node("send", base.send)

    graph.add_edge(START, "lookup")
    # tools_condition: did the model ask for a tool? yes → ToolNode, no → carry on
    graph.add_conditional_edges("lookup", tools_condition, {"tools": "tools", END: "add_account_info"})
    graph.add_edge("tools", "lookup")
    graph.add_edge("add_account_info", "classify")
    graph.add_conditional_edges("classify", base.route_by_tone, list(base.TONES))
    for name in base.TONES:
        graph.add_edge(name, "judge")
    graph.add_conditional_edges("judge", base.route_after_judge, [*base.TONES, "human_approval"])
    graph.add_conditional_edges("human_approval", base.route_after_approval, ["send", END])
    graph.add_edge("send", END)
    return graph.compile(checkpointer=checkpointer)


# ── CLI ───────────────────────────────────────────────────────────────────────
def print_tool_step(node: str, out: dict) -> bool:
    """Print the lookup loop; return False for nodes the base printer handles."""
    if node == "lookup":
        msg = out["messages"][-1]
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for call in msg.tool_calls:
                args = ", ".join(f"{k}={v!r}" for k, v in call["args"].items())
                print(f"▶ lookup          model asks for tool: {call['name']}({args})")
        else:
            print(f"▶ lookup          model's summary: {msg.content}")
        return True
    if node == "tools":
        for msg in out["messages"]:
            if isinstance(msg, ToolMessage):
                print(f"▶ tools           ToolNode ran {msg.name} → {msg.content}")
        return True
    if node == "add_account_info":
        print(f"▶ add_account_info  added to the signup: {out['account_info']}")
        return True
    return False


def stream(app, payload, config) -> None:
    for update in app.stream(payload, config, stream_mode="updates"):
        for node, out in update.items():
            if node != "__interrupt__" and not print_tool_step(node, out or {}):
                base.print_step(node, out or {})

    state = app.get_state(config)
    thread_id = config["configurable"]["thread_id"]
    if state.next:
        LAST_THREAD.write_text(thread_id, encoding="utf-8")
        print(f"\n⏸  Paused for human approval (thread_id: {thread_id})")
        print("   Approve: python graph_agent_tools.py --resume last approve")
        print("   Reject:  python graph_agent_tools.py --resume last reject")
    else:
        print(f"\n✔  Done (thread_id: {thread_id}, decision: {state.values.get('decision')})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Signup email agent with a tool-calling lookup step")
    parser.add_argument("--case", choices=base.CASES, default="victor", help="built-in signup to process")
    parser.add_argument("--resume", nargs=2, metavar=("THREAD_ID", "ACTION"),
                        help="resume a paused run with approve, edit or reject; THREAD_ID can be 'last'")
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
            if thread_id == "last":
                if not LAST_THREAD.exists():
                    print("No paused run yet. Start one first, e.g. python graph_agent_tools.py --case victor")
                    return
                thread_id = LAST_THREAD.read_text(encoding="utf-8").strip()
            if action not in ("approve", "edit", "reject"):
                parser.error("ACTION must be approve, edit or reject")
            if action == "edit" and not args.body:
                parser.error("edit needs --body")
            config = base.make_config(thread_id, "signup-tools-graph-resume")
            if not app.get_state(config).next:
                print(f"No run is waiting for approval on thread {thread_id}")
                return
            stream(app, Command(resume={"action": action, "body": args.body}), config)
        else:
            thread_id = f"tools-{args.case}-{uuid.uuid4().hex[:6]}"
            signup = base.CASES[args.case]
            print(f"Processing signup ({args.case}):\n{base.indent(signup)}\n")
            stream(app, {"signup": signup}, base.make_config(thread_id, "signup-tools-graph"))


if __name__ == "__main__":
    main()
