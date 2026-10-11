"""
Week 2 - Day 4: Multi-PDF RAG App with Sources
Run with:  streamlit run rag_app.py

Changes from the assignment example (same idea, my setup):
- Chat model : Claude (ChatAnthropic) instead of ChatOpenAI  -> my credit is on the Claude Console
- Embeddings : free local model all-MiniLM-L6-v2 instead of OpenAIEmbeddings
               (Anthropic has no embedding model; same model I used on Day 3)
- Page number: PyPDFLoader counts pages from 0, so I add 1 -> matches the page you see in the PDF
- Source     : the original file name (Streamlit saves uploads as temp files with random names)

The API key is read ONLY from the environment variable ANTHROPIC_API_KEY.
"""

import os
import tempfile

import streamlit as st
from langchain_anthropic import ChatAnthropic
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ---------------- Settings (change these while testing) ----------------
CHUNK_SIZE = 800      # characters per chunk
CHUNK_OVERLAP = 100   # characters shared between neighbour chunks
TOP_K = 4             # how many chunks to retrieve for each question
NOT_FOUND = "Not found in the uploaded documents."

st.set_page_config(page_title="Multi-PDF RAG", page_icon="📚")
st.title("📚 Multi-PDF RAG App with Sources")
st.caption("Upload several PDFs, ask a question, and every answer shows file name + page number.")

# ---------------- API key from environment variable ----------------
if not os.environ.get("ANTHROPIC_API_KEY"):
    st.error("ANTHROPIC_API_KEY is not set. In the terminal run:  $env:ANTHROPIC_API_KEY=\"your-key\"  then restart the app.")
    st.stop()


@st.cache_resource
def get_embeddings():
    # Free local embedding model (downloads once, then runs on your computer)
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


@st.cache_resource
def get_llm():
    return ChatAnthropic(model="claude-haiku-5-5", max_tokens=1024, 
                         )


# ---------------- Step 2: upload many PDFs and index them into ONE store ----------------
files = st.file_uploader("Upload PDFs", type="pdf", accept_multiple_files=True)

if files:
    file_names = sorted(f.name for f in files)

    # Build the store once; rebuild only if the set of uploaded files changes
    if "store" not in st.session_state or st.session_state.get("file_names") != file_names:
        splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        chunks = []
        with st.spinner("Reading, splitting and embedding the PDFs..."):
            for f in files:
                # Save the upload to a temp file, because PyPDFLoader needs a file path
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(f.getvalue())
                    tmp_path = tmp.name

                pages = PyPDFLoader(tmp_path).load()   # 1 document per page, metadata has 'page'
                os.remove(tmp_path)

                for p in pages:
                    p.metadata["source"] = f.name                    # real file name, not temp name
                    p.metadata["page"] = p.metadata.get("page", 0) + 1  # human page number (starts at 1)

                chunks.extend(splitter.split_documents(pages))      # metadata survives the split

            st.session_state.store = FAISS.from_documents(chunks, get_embeddings())
            st.session_state.file_names = file_names
            st.session_state.chunk_count = len(chunks)

    st.write("**Uploaded:** " + ", ".join(st.session_state.file_names))
    st.success(f"Indexed {st.session_state.chunk_count} chunks.")

# ---------------- Step 3: answer with sources ----------------
PROMPT = """You answer questions using ONLY the document excerpts below.
Each excerpt starts with its source in square brackets: [file name - page N].

Rules:
1. Use only the excerpts. Do not use outside knowledge and do not guess.
2. If the excerpts do not contain the answer, reply exactly: {not_found}
3. If two excerpts give DIFFERENT answers (for example different numbers or rules),
   do NOT pick one. Start your answer with "⚠️ The documents disagree:" and list
   what each document says, with its [file name - page N].
4. Otherwise give a short, clear answer and put the [file name - page N] after each fact.

Excerpts:
{context}

Question: {question}
Answer:"""

if "store" in st.session_state:
    question = st.text_input("Ask a question about your PDFs")

    if question:
        retriever = st.session_state.store.as_retriever(search_kwargs={"k": TOP_K})
        docs = retriever.invoke(question)

        context = "\n\n".join(
            f"[{d.metadata['source']} - page {d.metadata['page']}]\n{d.page_content}" for d in docs
        )

        with st.spinner("Claude is reading the chunks..."):
            answer = get_llm().invoke(
                PROMPT.format(not_found=NOT_FOUND, context=context, question=question)
            ).text  # .text = only the written answer

        st.markdown("**A:** " + answer)

        # Sources: file + page from the chunk metadata (duplicates removed, order kept)
        if NOT_FOUND not in answer:
            sources = list(dict.fromkeys(f"{d.metadata['source']} - page {d.metadata['page']}" for d in docs))
            st.caption("Sources: " + " | ".join(sources))

            # Think-it-through check: too many different pages for one answer?
            if len(sources) >= 4:
                st.info(f"This answer pulled chunks from {len(sources)} different pages. "
                        "If that keeps happening, try a different CHUNK_SIZE or TOP_K.")

        with st.expander("See the retrieved chunks"):
            for i, d in enumerate(docs, start=1):
                st.markdown(f"**{i}. {d.metadata['source']} - page {d.metadata['page']}**")
                st.text(d.page_content)
else:
    st.info("Upload one or more PDFs to start.")
