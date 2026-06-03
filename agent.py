"""
Signup Email Agent
Processes new user signups: classifies ICP fit and generates a personalized welcome email.
"""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from typing import Literal

# ── Load keys from .env ───────────────────────────────────────────────────────
load_dotenv()

os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_PROJECT"] = os.getenv(
    "LANGCHAIN_PROJECT", "langsmith-signup-email-agent"
)


# ── Structured output schema ──────────────────────────────────────────────────
class SignupEmailOutput(BaseModel):
    to: str = Field(description="Email address")
    icp_fit: Literal["high", "medium", "low", "unknown"] = Field(
        description="ICP fit classification"
    )
    reason: str = Field(description="Brief reasoning for classification")
    subject: str = Field(description="Email subject line")
    body: str = Field(description="Email body text")


# ── System prompt (feel free to edit) ────────────────────────────────────────
SYSTEM_PROMPT = """
Process this signup to your dev tool SaaS called 'Glop'.
Return icp_fit, reason and welcome email.

ICP fit guidance:
- high:    engineering/product leader at a tech or SaaS company, 50+ employees
- medium:  developer or technical role at any company
- low:     non-technical role or very small company (<10 employees)
- unknown: insufficient information to classify

Welcome email rules:
- Mention the user's first name, role, and company when provided.
- Be concise (under 150 words), conversational, and professional.
- Do NOT mention details that are not present in the input.
- Do NOT confuse the product name 'Glop' with the user's company name.
"""

# ── LLM with structured output ────────────────────────────────────────────────
_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(
    SignupEmailOutput
)


class _Agent:
    """
    Wraps the LLM so the rest of the codebase can use:
        result = agent.invoke({"messages": [{"role": "user", "content": "..."}]})
        output = result["structured_response"]
    """

    def invoke(self, payload: dict) -> dict:
        messages = payload.get("messages", [])
        lc_messages = [SystemMessage(content=SYSTEM_PROMPT)]
        for m in messages:
            if m["role"] == "user":
                lc_messages.append(HumanMessage(content=m["content"]))
        structured_response = _llm.invoke(lc_messages)
        return {"structured_response": structured_response}


agent = _Agent()


# ── Quick smoke test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    result = agent.invoke({
        "messages": [{
            "role": "user",
            "content": """Process this signup:
email: sarah@acmecorp.com
first_name: Sarah
company_name: Acme Corp
role: VP of Engineering
industry: SaaS
company_size: 500""",
        }]
    })

    output = result["structured_response"]
    print(f"ICP Fit:  {output.icp_fit}")
    print(f"Reason:   {output.reason}")
    print(f"Subject:  {output.subject}")
    print(f"Body:\n{output.body}")
