"""
Week 4 - Day 5 Buildathon: Multi-Agent Customer Support (CrewAI + Streamlit)

3 agents run one after another (sequential):
  1. Assistant             - answers from its own knowledge (no tools)
  2. Web Search Assistant  - searches the web (SerperDevTool) and answers from results
  3. Entry Agent           - saves query + both answers to answers.txt and returns both

Model: Claude (Anthropic) instead of OpenAI.
Keys come ONLY from environment variables:
    ANTHROPIC_API_KEY, SERPER_API_KEY, MODEL (anthropic/claude-haiku-5-5)
Run:  streamlit run app.py
"""

import os
from datetime import datetime

import streamlit as st
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool
from crewai_tools import SerperDevTool

ANSWERS_FILE = "answers.txt"

# ---------- Page ----------
st.set_page_config(page_title="Support Crew", page_icon="🤝")
st.title("🤝 Multi-Agent Customer Support")
st.caption("Assistant → Web Search Assistant → Entry Agent (CrewAI, sequential)")

# Stop early if a key is missing (keys are never written in this file)
missing = [k for k in ("ANTHROPIC_API_KEY", "SERPER_API_KEY") if not os.environ.get(k)]
if missing:
    st.error(f"Missing environment variables: {', '.join(missing)}. "
             "Set them in the terminal, then run streamlit again.")
    st.stop()


# ---------- Tool for the Entry Agent: append one entry to answers.txt ----------
@tool("Save support entry")
def save_support_entry(query: str, assistant_answer: str, web_answer: str) -> str:
    """Save the user's query, the Assistant answer and the Web Search answer
    into answers.txt (adds a new entry with date and time, old entries are kept)."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ANSWERS_FILE, "a", encoding="utf-8") as f:
        f.write(f"===== {stamp} =====\n"
                f"QUERY: {query}\n\n"
                f"ANSWER 1 (Assistant):\n{assistant_answer}\n\n"
                f"ANSWER 2 (Web Search Assistant):\n{web_answer}\n\n")
    return f"Saved to {ANSWERS_FILE} at {stamp}"


# ---------- The crew ----------
def build_crew():
    # No temperature (Claude Haiku 5.5 gives a 400 error with it)
    llm = LLM(model=os.environ.get("MODEL", "anthropic/claude-haiku-5-5"), max_tokens=3000)
    search = SerperDevTool(n_results=5)

    assistant = Agent(
        role="Customer Support Assistant",
        goal="Answer the customer's query clearly from your own knowledge.",
        backstory=("You are a friendly, experienced support agent. You explain in simple "
                   "steps, in at most 150 words. You have no internet access, so if you "
                   "are not sure about something, you say so."),
        tools=[],
        llm=llm,
        verbose=True,
    )

    web_assistant = Agent(
        role="Web Search Support Assistant",
        goal="Search the web for the customer's query and answer only from the search results.",
        backstory=("You are a careful researcher. You use only what the search results say, "
                   "answer in at most 150 words, and end with 1-2 source links. "
                   "If nothing useful is found, you say so."),
        tools=[search],          # ONLY this agent can search
        llm=llm,
        verbose=True,
        max_iter=5,
    )

    entry_agent = Agent(
        role="Support Entry Agent",
        goal="Save the query and both answers to the answers file, then return both answers.",
        backstory=("You are a careful record keeper. You copy answers word for word "
                   "and never change, shorten or add to them."),
        tools=[save_support_entry],
        llm=llm,
        verbose=True,
        max_iter=3,
    )

    t1 = Task(
        description="Customer query: {query}\nAnswer it directly from your own knowledge.",
        expected_output="A clear answer in simple steps, at most 150 words.",
        agent=assistant,
    )

    t2 = Task(
        description="Customer query: {query}\nSearch the web and answer using only the search results.",
        expected_output="An answer of at most 150 words, ending with 'Sources:' and 1-2 URLs.",
        agent=web_assistant,
    )

    t3 = Task(
        description=("Customer query: {query}\n"
                     "You have the Assistant answer and the Web Search answer from the previous tasks. "
                     "Call the 'Save support entry' tool ONCE with the query and both answers "
                     "copied word for word. Then return both answers."),
        expected_output=("The tool's confirmation line, then:\n"
                         "ANSWER 1 (Assistant): <answer 1>\n"
                         "ANSWER 2 (Web Search): <answer 2>"),
        agent=entry_agent,
        context=[t1, t2],        # hands BOTH earlier answers to the Entry Agent
    )

    return Crew(
        agents=[assistant, web_assistant, entry_agent],
        tasks=[t1, t2, t3],
        process=Process.sequential,
        verbose=True,
    )


# ---------- UI ----------
with st.form("query_form"):
    query = st.text_input("Your question or task", placeholder="How do I reset my password?")
    submitted = st.form_submit_button("Ask the support crew")

if submitted:
    if not query.strip():
        st.warning("Please type a question first.")
        st.stop()

    with st.spinner("3 agents working: Assistant → Web Search → Entry Agent (about 30-90 seconds)..."):
        try:
            result = build_crew().kickoff(inputs={"query": query.strip()})
        except Exception as e:
            st.error(f"The crew stopped with an error: {e}")
            st.stop()

    outputs = result.tasks_output      # one output per task, in order

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🧠 Answer 1 - Assistant")
        st.write(outputs[0].raw)
    with col2:
        st.subheader("🌐 Answer 2 - Web Search")
        st.write(outputs[1].raw)

    st.success("Entry Agent finished. Query and both answers saved to answers.txt")

    with st.expander("📄 Entry Agent output and answers.txt"):
        st.text(outputs[2].raw)
        if os.path.exists(ANSWERS_FILE):
            with open(ANSWERS_FILE, encoding="utf-8") as f:
                st.download_button("Download answers.txt", f.read(), file_name="answers.txt")