"""
support_core.py - the ENGINE of the factory customer support bot (used by the web app).

- build_team(customer_name): manager + 5 department agents in a SelectorGroupChat.
  The data tools are made FOR ONE CUSTOMER, so a customer only sees their own POs/invoices.
- ask_bot(question, customer_name): runs one question and returns the answer.
- Ticket helpers for the TEAM HEAD page (web version of human-in-the-loop):
  unknown question -> OPEN ticket -> head answers on the head page -> customer sees it.

All data is SAMPLE data in the data/ folder. API key only from ANTHROPIC_API_KEY.
"""

import csv
import re
from datetime import datetime
from pathlib import Path

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import (MaxMessageTermination, SourceMatchTermination,
                                          TextMentionTermination)
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.teams import SelectorGroupChat
from autogen_ext.models.anthropic import AnthropicChatCompletionClient

DATA_DIR = Path(__file__).parent / "data"
TICKETS = DATA_DIR / "web_tickets.csv"
LEARNED_FAQ = DATA_DIR / "learned_faq.csv"
TICKET_HEADER = ["ticket", "time", "customer", "department", "question", "head_answer", "status"]
DEPARTMENTS = ["sales_agent", "production_agent", "quality_agent",
               "accounts_agent", "compliance_agent"]


# ---------- CSV helpers ----------
def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def append_row(path: Path, header: list[str], row: dict) -> None:
    new_file = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def _clean(number: str) -> str:
    return number.upper().replace("PO", "").replace("#", "").replace(":", "").strip()


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


# ---------- Login ----------
def check_customer_login(code: str, password: str) -> str | None:
    """Return the customer name if code + password match data/customers.csv."""
    for row in read_csv(DATA_DIR / "customers.csv"):
        if row["customer_code"].lower() == code.strip().lower() and row["password"] == password:
            return row["customer_name"]
    return None


# ---------- Tickets (web human-in-the-loop) ----------
def create_ticket(customer: str, department: str, question: str) -> str:
    ticket = f"W-{len(read_csv(TICKETS)) + 1:04d}"
    append_row(TICKETS, TICKET_HEADER, {
        "ticket": ticket, "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "customer": customer, "department": department, "question": question,
        "head_answer": "", "status": "OPEN"})
    return ticket


def tickets_for_customer(customer: str) -> list[dict]:
    return [t for t in read_csv(TICKETS) if t["customer"] == customer]


def open_tickets() -> list[dict]:
    return [t for t in read_csv(TICKETS) if t["status"] == "OPEN"]


def answer_ticket(ticket: str, answer: str, save_as_faq: bool) -> None:
    rows = read_csv(TICKETS)
    for t in rows:
        if t["ticket"] == ticket:
            t["head_answer"] = answer
            t["status"] = "ANSWERED"
            if save_as_faq:
                append_row(LEARNED_FAQ, ["question", "answer", "department", "date"], {
                    "question": t["question"], "answer": answer,
                    "department": t["department"], "date": datetime.now().strftime("%Y-%m-%d")})
    write_csv(TICKETS, TICKET_HEADER, rows)


# ---------- Model client (with the 2 fixes from the terminal version) ----------
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


def make_model_client() -> AnthropicChatCompletionClient:
    client = AnthropicChatCompletionClient(
        model="claude-haiku-5-5",
        max_tokens=1024,
        model_info={"vision": True, "function_calling": True, "json_output": True,
                    "structured_output": True, "family": "unknown"},
    )
    original_create = client._client.messages.create

    def safe_create(**kwargs):
        kwargs.pop("temperature", None)                       # Haiku 5.5 refuses temperature
        kwargs["messages"] = _clean_messages(kwargs.get("messages", []))   # no empty text blocks
        return original_create(**kwargs)

    client._client.messages.create = safe_create
    return client


# ---------- The team, built for ONE logged-in customer ----------
def build_team(customer: str, model_client) -> SelectorGroupChat:

    def get_order_status(po_number: str) -> str:
        """Look up production and dispatch status of ONE order of this customer.
        Use when the customer asks about order status, delivery or dispatch. Input: PO number, e.g. "4512"."""
        po = _clean(po_number)
        for row in read_csv(DATA_DIR / "orders.csv"):
            if row["po_number"] == po:
                if row["customer"] != customer:
                    return f"PO {po} is not linked to this customer's account."   # privacy
                return (f"PO {po} | {row['item']} | qty {row['qty']} | status: {row['status']} | "
                        f"dispatch date: {row['dispatch_date']}")
        return f"PO {po} not found in the order list."

    def get_invoice_details(invoice_or_po: str) -> str:
        """Look up amount, due date and payment status of ONE invoice of this customer.
        Input: invoice number (e.g. "INV-2026-1101") or PO number (e.g. "4525")."""
        key = _clean(invoice_or_po)
        for row in read_csv(DATA_DIR / "invoices.csv"):
            if key in (row["invoice_number"], row["po_number"]):
                if row["customer"] != customer:
                    return f"{invoice_or_po} is not linked to this customer's account."  # privacy
                return (f"{row['invoice_number']} | PO {row['po_number']} | amount Rs {row['amount_inr']} | "
                        f"due {row['due_date']} | payment: {row['payment_status']}")
        return f"No invoice found for {invoice_or_po}."

    def search_learned_faq(question: str) -> str:
        """Search answers our team heads gave earlier for similar questions.
        Use when the answer is NOT in your facts or data tool, BEFORE creating a ticket."""
        asked = _words(question)
        best = [(len(asked & _words(r["question"])), r) for r in read_csv(LEARNED_FAQ)]
        best = sorted([b for b in best if b[0] >= 2], key=lambda b: b[0], reverse=True)
        if not best:
            return "No matching learned answer."
        return "\n".join(f"Q: {r['question']} | A (approved by {r['department']} head): {r['answer']}"
                         for _, r in best[:2])

    def ask_team_head(department: str, question: str) -> str:
        """Send the question to the department TEAM HEAD when the answer is NOT in your facts,
        data tool or learned FAQ. Never guess. department: sales, production, quality,
        accounts or compliance. Returns the ticket number."""
        ticket = create_ticket(customer, department, question)
        return (f"Ticket {ticket} sent to the {department} team head. Tell the customer the head "
                f"will answer soon and they can see it under 'My tickets' with ticket {ticket}.")

    hitl = [search_learned_faq, ask_team_head]

    rules = (
        f"You work for ABC Sheet Metal Works (sample company), a sheet-metal and fabrication factory "
        f"(laser cutting, bending, welding, powder coating). You are talking to the customer "
        f"{customer}. Answer politely in at most 5 short lines, plain text, no markdown. "
        "Use ONLY the facts below and your tools. Never invent prices, dates or numbers. "
        "If the answer is NOT in your facts or data tool: first call search_learned_faq; if still "
        "no answer, call ask_team_head and give the customer the ticket number. If you need missing "
        "details (PO no., lot no., drawing), just ask the customer."
    )

    manager = AssistantAgent(
        name="manager", model_client=model_client,
        description="Front-desk manager. Always speaks first and decides which department handles the question.",
        system_message=(
            "You are the customer support front-desk manager of ABC Sheet Metal Works. "
            "Departments: sales_agent (quotes, prices, new enquiries, MOQ, lead time, new services), "
            "production_agent (order status, delivery, dispatch), "
            "quality_agent (defects, rejections, complaints, inspection, testing, 8D), "
            "accounts_agent (invoices, payments, GST, credit notes), "
            "compliance_agent (material test certificates MTC, PPAP, ISO, RoHS, NDA). "
            "Do NOT answer yourself. Reply with ONE line: 'Routing to <department_agent>: <short reason>'. "
            "If the question has nothing to do with our factory or its orders, reply with one polite "
            "line saying it is outside customer support, and end with the word OUT_OF_SCOPE."),
    )

    def dept(name, description, facts, extra_tools=()):
        return AssistantAgent(
            name=name, model_client=model_client, description=description,
            tools=list(extra_tools) + hitl, reflect_on_tool_use=True, max_tool_iterations=3,
            system_message=rules + " " + facts)

    agents = [
        manager,
        dept("sales_agent", "Sales: quotations, prices, new enquiries, MOQ, lead time, new services.",
             "You are Sales. Facts: Quotation within 24 hours after drawing (PDF/DXF/STEP) + quantity + "
             "material. MOQ 100 nos. Lead time 2-3 weeks after PO; samples 7-10 days. Materials: MS, "
             "SS304, SS316, aluminium, GI. Enquiries: sales@abcsheetmetal.example."),
        dept("production_agent", "Production and dispatch: order status, delivery date, dispatch, LR details.",
             "You are Production & Dispatch. ALWAYS use get_order_status when a PO number is given; if "
             "no PO number, ask for it. Facts: dispatch Monday-Saturday by road; LR number shared on "
             "dispatch day.", [get_order_status]),
        dept("quality_agent", "Quality: defects, rejections, burrs, dimensions, complaints, testing, 8D.",
             "You are Quality. Facts: complaint number + acknowledgement within 4 hours; share photos, PO "
             "no., lot no., rejected qty; containment within 24 hours; 8D within 7 days; rejected parts "
             "replaced/reworked free after confirmation; PDIR sent with every dispatch."),
        dept("accounts_agent", "Accounts: invoices, payments, due dates, GST, credit notes.",
             "You are Accounts. ALWAYS use get_invoice_details when an invoice or PO number is given. "
             "Facts: payment terms 30 days from invoice date; GST invoice + e-way bill with every "
             "dispatch; credit note within 3 working days after confirmed rejection or price difference.",
             [get_invoice_details]),
        dept("compliance_agent", "Compliance: MTC, PPAP, ISO 9001, RoHS/REACH, NDA, audits.",
             "You are Compliance. Facts: ISO 9001:2015 certified; MTC available for every lot, sent within "
             "1 working day (need PO + lot no.); PPAP level 3 in 2 weeks; RoHS/REACH declarations on "
             "request; NDA before drawings; customer audits with 7 days notice."),
    ]

    def manager_first(messages):
        return "manager" if messages[-1].source == "user" else None

    return SelectorGroupChat(
        agents,
        model_client=model_client,
        selector_prompt=("You are routing a factory customer support chat.\nAgents:\n{roles}\n\n"
                         "Conversation:\n{history}\n\nSelect the ONE department agent the manager named "
                         "in its last 'Routing to ...' line. Choose only from {participants}. "
                         "Return ONLY the agent name."),
        selector_func=manager_first,
        allow_repeated_speaker=False,
        termination_condition=(SourceMatchTermination(DEPARTMENTS)
                               | TextMentionTermination("OUT_OF_SCOPE")
                               | MaxMessageTermination(6)),
    )


async def ask_bot(question: str, customer: str) -> dict:
    """Run ONE customer question. Returns {'department': ..., 'answer': ..., 'steps': [...]}."""
    model_client = make_model_client()
    try:
        team = build_team(customer, model_client)
        result = await team.run(task=question)
    finally:
        await model_client.close()

    steps, department, answer = [], "manager", ""
    for m in result.messages:
        if m.source == "user":
            continue
        steps.append(f"{m.source}: {type(m).__name__}")
        if isinstance(m, TextMessage) or type(m).__name__ == "ToolCallSummaryMessage":
            department, answer = m.source, str(m.content)
    answer = answer.replace("OUT_OF_SCOPE", "").strip()
    return {"department": department, "answer": answer, "steps": steps}