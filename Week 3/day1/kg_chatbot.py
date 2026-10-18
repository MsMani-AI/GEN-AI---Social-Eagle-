"""
Week 3 - Day 1: Knowledge Graph RAG chatbot - Tamil Nadu schemes
Question -> Claude writes Cypher -> Neo4j returns facts -> Claude answers ONLY from facts.
Run:  streamlit run kg_chatbot.py
Keys only from environment variables.
"""
import re
import streamlit as st
from langchain_anthropic import ChatAnthropic
from langchain_neo4j import Neo4jGraph

SOURCE = "https://www.tn.gov.in/scheme_list.php?dep_id=Mg=="
SCHEMA = """
Nodes (all have a 'name' property):
  Scheme, Department, Sector, BenefitType, Beneficiary, Crop, Program
Relationships:
  (Scheme)-[:BELONGS_TO]->(Department)
  (Scheme)-[:IN_SECTOR]->(Sector)
  (Scheme)-[:PROVIDES]->(BenefitType)
  (Scheme)-[:FOR]->(Beneficiary)
  (Scheme)-[:FOR_CROP]->(Crop)
  (Scheme)-[:LINKED_TO]->(Program)
"""
# Guardrail: any of these words = the query tries to change the database -> block it
BLOCKED = re.compile(r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|LOAD|CALL)\b", re.IGNORECASE)


@st.cache_resource
def connect():
    graph = Neo4jGraph(refresh_schema=False)
    llm = ChatAnthropic(model="claude-haiku-5-5", max_tokens=1024)
    # Real names in the graph, so Claude uses exact values (e.g. "Pulses", "Subsidy")
    values = {}
    for label in ["Department", "Sector", "BenefitType", "Beneficiary", "Crop", "Program"]:
        rows = graph.query(f"MATCH (n:{label}) RETURN n.name AS name ORDER BY name")
        values[label] = [r["name"] for r in rows]
    return graph, llm, values


def make_cypher(llm, question, values):
    prompt = f"""You write ONE read-only Neo4j Cypher query to answer a question
about Tamil Nadu government schemes.
Graph schema:{SCHEMA}
Exact values in the graph: {values}
Rules:
- Use only MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY, LIMIT, count().
- Never use CREATE, MERGE, SET, DELETE, REMOVE, CALL.
- To find a scheme by words, use toLower(s.name) CONTAINS toLower('word').
- When listing schemes, return s.name. Use LIMIT 100.
- If the question is NOT about these schemes, output exactly: NONE
- Output only the Cypher. No explanation, no ``` fences.
Question: {question}"""
    cypher = llm.invoke(prompt).text.strip()
    return cypher.replace("```cypher", "").replace("```", "").strip()


def make_answer(llm, question, rows):
    prompt = f"""Answer the question using ONLY these facts from the knowledge graph.
If the facts are empty or do not answer the question, reply exactly:
Not found in the schemes data.
Do not add eligibility, amounts or dates that are not in the facts.
Use simple English. For lists, use bullet points and give the total count.
Question: {question}
Facts: {rows}"""
    return llm.invoke(prompt).text


# ---------------- Streamlit page ----------------
st.set_page_config(page_title="TN Schemes KG Chatbot", page_icon="🌾")
st.title("🌾 TN Schemes – Knowledge Graph Chatbot")
st.caption(f"Data: Agriculture - Farmers Welfare Department scheme list · {SOURCE}")

graph, llm, values = connect()

with st.sidebar:
    st.subheader("Try asking")
    st.markdown(
        "- List all schemes for Pulses\n"
        "- How many schemes give Subsidy?\n"
        "- Which schemes are for Micro & Small Enterprises?\n"
        "- Which schemes are linked to ISOPOM?\n"
        "- Which sector has the most schemes?\n"
        "- Who won the IPL? *(guardrail test)*"
    )

if "messages" not in st.session_state:
    st.session_state.messages = []
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

question = st.chat_input("Ask about the TN schemes...")
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching the knowledge graph..."):
            cypher = make_cypher(llm, question, values)
            rows = []
            if cypher.strip().upper() == "NONE":
                answer = "I can only answer questions about the Tamil Nadu schemes in this list."
            elif BLOCKED.search(cypher):
                answer = "⚠️ Blocked: the generated query tried to change the database."
            else:
                try:
                    rows = graph.query(cypher)
                    answer = make_answer(llm, question, rows)
                except Exception as e:
                    answer = "Sorry, I could not run the graph query. Please ask in a different way."
                    rows = [{"error": str(e)}]
        st.markdown(answer)
        with st.expander("🔍 How I found this (Cypher query + graph facts)"):
            st.code(cypher, language="cypher")
            st.write(rows)
    st.session_state.messages.append({"role": "assistant", "content": answer})
    