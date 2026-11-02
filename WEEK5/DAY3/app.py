"""
app.py - Streamlit WEB APP for the factory customer support bot.

Two logins (left sidebar):
  1. Customer   -> chat with the support bot; sees ONLY their own orders/invoices;
                   "My tickets" shows questions sent to a team head + the head's answer.
  2. Team head  -> sees OPEN tickets, types the answer, approves, can save it as a FAQ.

Run:   streamlit run app.py
Needs: ANTHROPIC_API_KEY and HEAD_PASSWORD environment variables.
"""

import asyncio
import os

import streamlit as st

from support_core import (answer_ticket, ask_bot, check_customer_login, open_tickets,
                          tickets_for_customer)

DEPT_NAMES = {"sales_agent": "Sales", "production_agent": "Production & Dispatch",
              "quality_agent": "Quality", "accounts_agent": "Accounts",
              "compliance_agent": "Compliance", "manager": "Front desk"}

st.set_page_config(page_title="ABC Sheet Metal - Customer Support", page_icon="🏭")
st.title("🏭 ABC Sheet Metal Works - Customer Support")
st.caption("AI assistant (sample data). Questions it cannot answer go to our team head.")

if not os.environ.get("ANTHROPIC_API_KEY"):
    st.error("ANTHROPIC_API_KEY is not set. Set it in the terminal and run streamlit again.")
    st.stop()

# ---------- Sidebar: login ----------
with st.sidebar:
    st.header("Login")
    if "role" not in st.session_state:
        role = st.radio("I am a", ["Customer", "Team head"])
        if role == "Customer":
            code = st.text_input("Customer code")
            pwd = st.text_input("Password", type="password")
            if st.button("Login"):
                name = check_customer_login(code, pwd)
                if name:
                    st.session_state.update(role="customer", customer=name, chat=[])
                    st.rerun()
                else:
                    st.error("Wrong customer code or password.")
        else:
            pwd = st.text_input("Team head password", type="password")
            if st.button("Login"):
                if os.environ.get("HEAD_PASSWORD") and pwd == os.environ["HEAD_PASSWORD"]:
                    st.session_state.update(role="head")
                    st.rerun()
                else:
                    st.error("Wrong password (or HEAD_PASSWORD not set).")
    else:
        who = st.session_state.get("customer", "Team head")
        st.success(f"Logged in: {who}")
        if st.button("Logout"):
            st.session_state.clear()
            st.rerun()

if "role" not in st.session_state:
    st.info("👈 Please log in from the left sidebar.")
    st.stop()


# ---------- CUSTOMER PAGE ----------
if st.session_state.role == "customer":
    customer = st.session_state.customer

    for msg in st.session_state.chat:                       # show earlier messages
        with st.chat_message(msg["role"]):
            if msg.get("dept"):
                st.caption(f"Answered by: {msg['dept']}")
            st.write(msg["text"])

    question = st.chat_input("Type your question (order status, invoice, quality, MTC, quote...)")
    if question:
        st.session_state.chat.append({"role": "user", "text": question})
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"):
            with st.spinner("Our support team is checking..."):
                try:
                    reply = asyncio.run(ask_bot(question, customer))
                except Exception as e:
                    print("ERROR:", e)                    # full error only in the terminal
                    reply = {"department": "manager", "steps": [],
                             "answer": "Sorry, something went wrong. Please try again in a minute."}
            dept = DEPT_NAMES.get(reply["department"], reply["department"])
            st.caption(f"Answered by: {dept}")
            st.write(reply["answer"])
            with st.expander("How the AI team handled it"):
                st.write(" → ".join(reply["steps"]))
        st.session_state.chat.append({"role": "assistant", "text": reply["answer"], "dept": dept})

    st.divider()
    st.subheader("📋 My tickets (questions sent to a team head)")
    my = tickets_for_customer(customer)
    if not my:
        st.write("No tickets yet.")
    for t in reversed(my):
        icon = "✅" if t["status"] == "ANSWERED" else "⏳"
        with st.expander(f"{icon} {t['ticket']} | {t['department']} | {t['status']}"):
            st.write(f"**Question:** {t['question']}")
            st.write(f"**Team head answer:** {t['head_answer'] or 'Waiting for the team head...'}")
    if st.button("🔄 Refresh tickets"):
        st.rerun()


# ---------- TEAM HEAD PAGE ----------
else:
    st.subheader("🔔 Open tickets - please answer")
    tickets = open_tickets()
    if not tickets:
        st.success("No open tickets. 👍")
    for t in tickets:
        with st.form(key=t["ticket"]):
            st.write(f"**{t['ticket']}** | {t['time']} | **{t['customer']}** | department: **{t['department']}**")
            st.write(t["question"])
            answer = st.text_area("Your answer", key=f"a_{t['ticket']}")
            save = st.checkbox("Save as FAQ (bot answers this itself next time)", value=True,
                               key=f"s_{t['ticket']}")
            if st.form_submit_button("✅ Approve and send to customer"):
                if answer.strip():
                    answer_ticket(t["ticket"], answer.strip(), save)
                    st.success(f"{t['ticket']} answered.")
                    st.rerun()
                else:
                    st.warning("Please type an answer first.")
    if st.button("🔄 Refresh"):
        st.rerun()