# ================================================
# Hybrid RAG on Spotify Architecture PDF
# Load -> BM25 + Vector -> RRF -> Claude -> Streamlit
# ================================================
import os
import re

import numpy as np
from pypdf import PdfReader
from rank_bm25 import BM25Okapi

# ---------- SETTINGS ----------
PDF_PATH = "spotify_web_app_architecture.pdf"
CHUNK_SIZE = 600      # characters in one chunk
CHUNK_OVERLAP = 100   # characters shared between 2 chunks
EMBED_MODEL = "all-MiniLM-L6-v2"   # free local embedding model
TOP_K = 4             # chunks sent to Claude
RRF_K = 60            # standard RRF constant
CLAUDE_MODEL = "claude-haiku-5-5"


# ---------- STEP 1: LOAD + CHUNK ----------
def load_chunks(pdf_path):
    reader = PdfReader(pdf_path)
    chunks = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            piece = text[start:end].strip()
            if piece:
                chunks.append({"id": len(chunks), "page": page_no, "text": piece})
            if end >= len(text):
                break
            start = end - CHUNK_OVERLAP
    return chunks


# ---------- STEP 2: BM25 (KEYWORD SEARCH) ----------
def tokenize(text):
    return re.findall(r"[a-z0-9_]+", text.lower())


def build_bm25(chunks):
    return BM25Okapi([tokenize(c["text"]) for c in chunks])


def bm25_search(bm25, query, k):
    scores = bm25.get_scores(tokenize(query))
    order = np.argsort(scores)[::-1][:k]
    return [(int(i), float(scores[i])) for i in order]


# ---------- STEP 3: VECTOR (MEANING SEARCH) ----------
def build_vectors(chunks, embedder):
    vecs = embedder.encode([c["text"] for c in chunks], normalize_embeddings=True)
    return np.array(vecs)


def vector_search(vectors, embedder, query, k):
    q = embedder.encode([query], normalize_embeddings=True)[0]
    scores = vectors @ q          # cosine similarity
    order = np.argsort(scores)[::-1][:k]
    return [(int(i), float(scores[i])) for i in order]


# ---------- STEP 4: HYBRID = RRF FUSION ----------
def rrf_fuse(result_lists, k):
    """Reciprocal Rank Fusion: score = sum of 1 / (RRF_K + rank)"""
    fused = {}
    for results in result_lists:
        for rank, (idx, _) in enumerate(results, start=1):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (RRF_K + rank)
    order = sorted(fused.items(), key=lambda x: x[1], reverse=True)
    return order[:k]


# ---------- STEP 5: ASK CLAUDE ----------
SYSTEM_PROMPT = (
    "You answer questions about a Spotify-like web app architecture document. "
    "Use ONLY the excerpts given. Cite pages like (p.2). "
    "If the answer is not in the excerpts, reply exactly: "
    "'Not found in the architecture document.'"
)


def ask_claude(question, chunks, fused):
    import anthropic

    context = "\n\n".join(
        f"[Excerpt {n} | page {chunks[i]['page']}]\n{chunks[i]['text']}"
        for n, (i, _) in enumerate(fused, start=1)
    )
    client = anthropic.Anthropic()            # reads ANTHROPIC_API_KEY
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user",
                   "content": f"Excerpts:\n{context}\n\nQuestion: {question}"}],
    )
    # keep only the text blocks (skip any "thinking" blocks)
    return "".join(b.text for b in msg.content if b.type == "text")


# ---------- STREAMLIT WEB PAGE ----------
def main():
    import streamlit as st
    from sentence_transformers import SentenceTransformer

    st.set_page_config(page_title="Hybrid RAG - Spotify Architecture", page_icon="🎵")
    st.title("🎵 Hybrid RAG – Spotify Architecture")
    st.caption("BM25 (keyword) + Vector (meaning) → RRF fusion → Claude answer")
    
    # ---------- PASSWORD (only when APP_PASSWORD is set, e.g. on VPS) ----------
    app_password = os.environ.get("APP_PASSWORD")
    if app_password:
        typed = st.text_input("🔒 Password", type="password")
        if typed != app_password:
            st.info("Enter the password to use the app.")
            st.stop()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("ANTHROPIC_API_KEY is not set. Set it in the terminal and restart.")
        st.stop()

    @st.cache_resource
    def build_index():
        chunks = load_chunks(PDF_PATH)
        embedder = SentenceTransformer(EMBED_MODEL)
        return chunks, build_bm25(chunks), embedder, build_vectors(chunks, embedder)

    chunks, bm25, embedder, vectors = build_index()
    st.success(f"Indexed {len(chunks)} chunks from {PDF_PATH}")

    question = st.text_input("Ask a question about the architecture:")
    if not question:
        return

    bm25_res = bm25_search(bm25, question, TOP_K)
    vec_res = vector_search(vectors, embedder, question, TOP_K)
    fused = rrf_fuse([bm25_res, vec_res], TOP_K)

    with st.spinner("Claude is answering..."):
        answer = ask_claude(question, chunks, fused)

    st.subheader("Answer")
    st.write(answer)

    st.subheader("How each search ranked the chunks")
    col1, col2, col3 = st.columns(3)
    for col, title, res in [(col1, "🔤 BM25 (keyword)", bm25_res),
                            (col2, "🧠 Vector (meaning)", vec_res),
                            (col3, "⚡ Hybrid (RRF)", fused)]:
        with col:
            st.markdown(f"**{title}**")
            for rank, (i, score) in enumerate(res, start=1):
                st.write(f"{rank}. chunk {i} · p.{chunks[i]['page']} · {score:.3f}")

    st.subheader("Sources sent to Claude")
    for i, _ in fused:
        with st.expander(f"Chunk {i} – page {chunks[i]['page']}"):
            st.text(chunks[i]["text"])


if __name__ == "__main__":
    main()