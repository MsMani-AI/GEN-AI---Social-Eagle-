"""
Week 5 - Day 3: Factory Customer Support Chatbot (AutoGen SelectorGroupChat)

A customer types a question. The MANAGER agent (front desk) reads it and names
the right department. SelectorGroupChat then picks that department agent, which
answers the customer. 5 departments: Sales, Production, Quality, Accounts, Compliance.

Data sources (all SAMPLE data, no real customers):
  - Each department has a short FAQ in its system message
  - production_agent has a tool that reads data/orders.csv
  - accounts_agent has a tool that reads data/invoices.csv
  - HUMAN IN THE LOOP: if the answer is not in the data, the agent first checks
    data/learned_faq.csv (earlier team-head answers). If still not found, it asks the
    TEAM HEAD (human, in the terminal), uses the head's answer, logs a ticket in
    data/tickets.csv, and can save the answer as a new FAQ for next time.

Model: Claude (Anthropic) -> AnthropicChatCompletionClient.
The API key is read ONLY from the ANTHROPIC_API_KEY environment variable.
Run:  python support_bot.py   (type 'exit' to quit)
"""

import asyncio
import csv
import re
import time
from datetime import datetime
from pathlib import Path

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import (MaxMessageTermination, SourceMatchTermination,
                                          TextMentionTermination)
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.models.anthropic import AnthropicChatCompletionClient

DATA_DIR = Path(__file__).parent / "data"
DEPARTMENTS = ["sales_agent", "production_agent", "quality_agent",
               "accounts_agent", "compliance_agent"]


# ---------- 1. TOOLS (read sample CSV files) ----------
def _read_csv(file_name: str) -> list[dict]:
    with open(DATA_DIR / file_name, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _clean(number: str) -> str:
    """'PO #4512' -> '4512', 'inv-2026-1101' -> 'INV-2026-1101'."""
    return number.upper().replace("PO", "").replace("#", "").replace(":", "").strip()


def get_order_status(po_number: str) -> str:
    """Look up the production and dispatch status of ONE customer order.

    Use this tool when a customer asks about order status, delivery date,
    dispatch or where their order is. Input is the PO number, e.g. "4512".
    """
    po = _clean(po_number)
    for row in _read_csv("orders.csv"):
        if row["po_number"] == po:
            return (f"PO {row['po_number']} | {row['customer']} | {row['item']} | "
                    f"qty {row['qty']} | status: {row['status']} | "
                    f"dispatch date: {row['dispatch_date']}")
    return f"PO {po} not found in the order list."


def get_invoice_details(invoice_or_po: str) -> str:
    """Look up invoice amount, due date and payment status.

    Use this tool when a customer asks about an invoice, payment, due date or
    amount. Input is an invoice number (e.g. "INV-2026-1101") or a PO number (e.g. "4525").
    """
    key = _clean(invoice_or_po)
    for row in _read_csv("invoices.csv"):
        if key in (row["invoice_number"], row["po_number"]):
            return (f"{row['invoice_number']} | PO {row['po_number']} | {row['customer']} | "
                    f"amount Rs {row['amount_inr']} | invoice date {row['invoice_date']} | "
                    f"due {row['due_date']} | payment: {row['payment_status']}")
    return f"No invoice found for {invoice_or_po}."


# ---------- 1b. HUMAN-IN-THE-LOOP TOOLS (team head + learned FAQ) ----------
LEARNED_FAQ = DATA_DIR / "learned_faq.csv"
TICKETS = DATA_DIR / "tickets.csv"


def _append_row(path: Path, header: list[str], row: list[str]) -> None:
    new_file = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(header)
        writer.writerow(row)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def search_learned_faq(question: str) -> str:
    """Search answers that our team heads gave earlier for similar customer questions.

    Use this tool when the answer is NOT in your facts or your other tool,
    BEFORE asking the team head. Input is the customer's question.
    """
    if not LEARNED_FAQ.exists():
        return "No learned answers yet."
    asked = _words(question)
    best = []
    for row in _read_csv("learned_faq.csv"):
        score = len(asked & _words(row["question"]))
        if score >= 2:
            best.append((score, row))
    if not best:
        return "No matching learned answer."
    best.sort(key=lambda x: x[0], reverse=True)
    return "\n".join(f"Q: {r['question']} | A (approved by {r['department']} head): {r['answer']}"
                     for _, r in best[:2])


def ask_team_head(department: str, question: str) -> str:
    """Ask the department TEAM HEAD (a human) when the answer is NOT in your facts,
    your tool data or the learned FAQ. Never guess - use this tool instead.
    department: sales, production, quality, accounts or compliance.
    Returns the head's answer (to use in your reply) or that the head is not available.
    """
    time.sleep(0.5)   # let the screen finish printing before the alert
    count = len(_read_csv("tickets.csv")) if TICKETS.exists() else 0
    ticket = f"T-{count + 1:04d}"
    print("\n" + "=" * 60)
    print(f"*** TEAM HEAD ALERT - {department.upper()} *** ticket {ticket}")
    print(f"Customer asks: {question}")
    print("=" * 60)
    answer = input("TEAM HEAD answer (press Enter if not available now): ").strip()

    if not answer:
        _append_row(TICKETS, ["ticket", "time", "department", "question", "head_answer", "status"],
                    [ticket, datetime.now().strftime("%Y-%m-%d %H:%M"), department, question, "", "OPEN"])
        return (f"Team head not available now. Ticket {ticket} created. "
                "Tell the customer the team will reply within 24 hours with this ticket number.")

    save = input("Save this as a FAQ for next time? (Y/n): ").strip().lower() or "y"
    _append_row(TICKETS, ["ticket", "time", "department", "question", "head_answer", "status"],
                [ticket, datetime.now().strftime("%Y-%m-%d %H:%M"), department, question, answer, "ANSWERED"])
    if save == "y":
        _append_row(LEARNED_FAQ, ["question", "answer", "department", "date"],
                    [question, answer, department, datetime.now().strftime("%Y-%m-%d")])
    return f"Team head answer (ticket {ticket}): {answer}"


HITL_TOOLS = [search_learned_faq, ask_team_head]


# ---------- 2. BRAIN: Claude Haiku ----------
model_client = AnthropicChatCompletionClient(
    model="claude-haiku-5-5",
    max_tokens=1024,
    model_info={"vision": True, "function_calling": True, "json_output": True,
                "structured_output": True, "family": "unknown"},
)

# 2b. Fix for AutoGen + new Claude models, applied before EVERY request:
#     (1) AutoGen always adds temperature=1.0 -> Claude Haiku 5.5 refuses it -> remove it.
#     (2) After a tool call AutoGen may send an EMPTY text block -> Claude gives
#         "text content blocks must be non-empty" -> remove empty text blocks.
def _is_empty_text(block):
    kind = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
    text = block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
    return kind == "text" and not str(text).strip()


def _clean_messages(messages):
    cleaned = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str) and not content.strip():
            m = {**m, "content": "(empty)"}
        elif isinstance(content, list):
            blocks = [b for b in content if not _is_empty_text(b)]
            m = {**m, "content": blocks or [{"type": "text", "text": "(empty)"}]}
        cleaned.append(m)
    return cleaned


_original_create = model_client._client.messages.create

def _safe_create(**kwargs):
    kwargs.pop("temperature", None)
    kwargs["messages"] = _clean_messages(kwargs.get("messages", []))
    return _original_create(**kwargs)

model_client._client.messages.create = _safe_create


# ---------- 3. AGENTS (description = what the selector reads) ----------
COMMON_RULES = (
    "You work for ABC Sheet Metal Works (sample company), a sheet-metal and fabrication "
    "factory (laser cutting, bending, welding, powder coating). "
    "Answer the CUSTOMER directly, politely, in at most 5 short lines, plain text, no markdown. "
    "Use ONLY the facts below and your tools. Never invent prices, dates or numbers. "
    "If the answer is NOT in your facts or data tool: first call search_learned_faq; "
    "if there is still no answer, call ask_team_head and use the head's answer exactly. "
    "If the head is not available, give the customer the ticket number and say the team "
    "will reply within 24 hours. If you need missing details from the customer (PO no., "
    "lot no., drawing), just ask the customer - do not call the team head for that."
)

manager = AssistantAgent(
    name="manager",
    model_client=model_client,
    description="Front-desk manager. Always speaks first and decides which department handles the question.",
    system_message=(
        "You are the customer support front-desk manager of ABC Sheet Metal Works. "
        "Departments: sales_agent (quotes, prices, new enquiries, MOQ, lead time), "
        "production_agent (order status, delivery, dispatch), "
        "quality_agent (defects, rejections, complaints, inspection reports, 8D), "
        "accounts_agent (invoices, payments, GST, credit notes), "
        "compliance_agent (material test certificates MTC, PPAP, ISO, RoHS, NDA). "
        "Do NOT answer the question yourself. Reply with ONE line only: "
        "'Routing to <department_agent>: <short reason>'. "
        "If the question has nothing to do with our factory or its orders, reply with one "
        "polite line saying it is outside customer support, and end with the word OUT_OF_SCOPE."
    ),
)

sales_agent = AssistantAgent(
    name="sales_agent",
    model_client=model_client,
    description="Sales: quotations, prices, new enquiries, MOQ, lead time, new parts.",
    tools=HITL_TOOLS,
    reflect_on_tool_use=True,
    max_tool_iterations=3,
    system_message=COMMON_RULES + (
        " You are the Sales department. Facts: "
        "Quotation sent within 24 hours after drawing (PDF/DXF/STEP) + quantity + material are received. "
        "Minimum order quantity 100 nos. Normal lead time 2-3 weeks after PO; samples in 7-10 days. "
        "Materials: MS, SS304, SS316, aluminium, GI. Enquiries: sales@abcsheetmetal.example."
    ),
)

production_agent = AssistantAgent(
    name="production_agent",
    model_client=model_client,
    description="Production and dispatch: order status, delivery date, dispatch, LR details, schedule.",
    tools=[get_order_status] + HITL_TOOLS,
    reflect_on_tool_use=True,
    max_tool_iterations=3,
    system_message=COMMON_RULES + (
        " You are the Production & Dispatch department. ALWAYS use the get_order_status "
        "tool when a PO number is given. If no PO number is given, ask the customer for it. "
        "Facts: Dispatch Monday to Saturday, by road transport; LR number shared on dispatch day."
    ),
)

quality_agent = AssistantAgent(
    name="quality_agent",
    model_client=model_client,
    description="Quality: defects, rejections, burrs, dimension issues, complaints, 8D, inspection reports.",
    tools=HITL_TOOLS,
    reflect_on_tool_use=True,
    max_tool_iterations=3,
    system_message=COMMON_RULES + (
        " You are the Quality department. Facts: "
        "Every complaint gets a complaint number and acknowledgement within 4 hours. "
        "Please share photos, PO number, lot number and rejected quantity. "
        "Containment (100% check of stock) within 24 hours; 8D report within 7 days. "
        "Rejected parts are replaced or reworked free of cost after confirmation. "
        "Inspection report (PDIR) is sent with every dispatch."
    ),
)

accounts_agent = AssistantAgent(
    name="accounts_agent",
    model_client=model_client,
    description="Accounts: invoices, payments, due dates, GST, credit notes, amount mismatch.",
    tools=[get_invoice_details] + HITL_TOOLS,
    reflect_on_tool_use=True,
    max_tool_iterations=3,
    system_message=COMMON_RULES + (
        " You are the Accounts department. ALWAYS use the get_invoice_details tool when an "
        "invoice number or PO number is given. Facts: Payment terms 30 days from invoice date. "
        "GST invoice with e-way bill for every dispatch. Credit note issued within 3 working days "
        "after a confirmed rejection or price difference."
    ),
)

compliance_agent = AssistantAgent(
    name="compliance_agent",
    model_client=model_client,
    description="Compliance: material test certificates (MTC), PPAP, ISO 9001, RoHS/REACH, NDA, audits.",
    tools=HITL_TOOLS,
    reflect_on_tool_use=True,
    max_tool_iterations=3,
    system_message=COMMON_RULES + (
        " You are the Compliance department. Facts: "
        "ISO 9001:2015 certified. Mill test certificate (MTC) from the steel supplier is available "
        "for every lot and sent within 1 working day on request (give PO and lot number). "
        "PPAP level 3 documents prepared for new parts in 2 weeks. RoHS/REACH declarations "
        "available on request. NDA can be signed before receiving drawings. "
        "Customer audits can be booked with 7 days notice."
    ),
)


# ---------- 4. THE TEAM: SelectorGroupChat ----------
SELECTOR_PROMPT = """You are routing a factory customer support chat.
The available agents are:
{roles}

Conversation so far:
{history}

Read the manager's last 'Routing to ...' line and select the ONE department agent it named.
Choose only from {participants}. Return ONLY the agent name, nothing else."""


def manager_first(messages):
    """The manager always speaks right after the customer. Otherwise let the LLM choose."""
    if messages[-1].source == "user":
        return "manager"
    return None


termination = (
    SourceMatchTermination(DEPARTMENTS)          # stop as soon as a department has answered
    | TextMentionTermination("OUT_OF_SCOPE")     # manager says the question is off-topic
    | MaxMessageTermination(6)                   # safety stop
)

team = SelectorGroupChat(
    [manager, sales_agent, production_agent, quality_agent, accounts_agent, compliance_agent],
    model_client=model_client,
    selector_prompt=SELECTOR_PROMPT,
    selector_func=manager_first,
    allow_repeated_speaker=False,
    termination_condition=termination,
)


# ---------- 5. CHAT LOOP ----------
async def main():
    print("ABC Sheet Metal Works - Customer Support (type 'exit' to quit)")
    try:
        while True:
            question = input("\nYour question: ").strip()
            if question.lower() in ("exit", "quit"):
                break
            if not question:
                continue
            await team.reset()                       # fresh start for each new question
            await Console(team.run_stream(task=question))
    finally:
        await model_client.close()


if __name__ == "__main__":
    asyncio.run(main())