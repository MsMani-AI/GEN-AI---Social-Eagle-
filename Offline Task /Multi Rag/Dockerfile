# 1. Start from a small Linux + Python 3.12 base
FROM python:3.12-slim

# 2. Work inside /app folder in the box
WORKDIR /app

# 3. Install CPU-only PyTorch first (much smaller than GPU version)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 4. Install our libraries
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Download the embedding model once, at build time
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# 6. Copy our code and the knowledge-base PDF
COPY hybrid_rag.py spotify_web_app_architecture.pdf ./

# 7. Open port 8501 and start Streamlit
EXPOSE 8501
CMD ["streamlit", "run", "hybrid_rag.py", "--server.address=0.0.0.0", "--server.port=8501"]