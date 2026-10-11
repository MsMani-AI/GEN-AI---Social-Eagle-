# Week 2 · Day 3 – Trace a LangChain App with LangSmith

A small LangChain app that sends 3 prompts to an LLM and prints each answer.
Tracing to **LangSmith** is switched on **only with environment variables** – there is no tracing code in the file.

## Tools
- Python, LangChain (`langchain`, `langchain-anthropic`)
- Model: Claude (`claude-haiku-5-5`) via LangChain's `ChatAnthropic`
  *(The assignment example uses `ChatOpenAI`; I used `ChatAnthropic` because my API credit is on the Claude Console. Tracing works exactly the same.)*
- LangSmith for tracing

## How to run (Windows PowerShell)
```powershell
python -m venv venv
venv\Scripts\activate
pip install langchain langchain-anthropic

$env:ANTHROPIC_API_KEY="your-claude-key"
$env:LANGSMITH_TRACING="true"
$env:LANGSMITH_API_KEY="your-langsmith-key"
$env:LANGSMITH_PROJECT="caie-week2"

python traced_app.py
```

## Final output (LangSmith project: `caie-week2`)

| Run | Prompt | Latency | Tokens |
|---|---|---|---|
| 1 | "What is LangChain? Answer in one sentence." | 2.20s | 77 |
| 2 | "Give 3 simple tips for writing a good prompt for an AI model." | 1.99s | 250 |
| 3 | "Explain step by step how a RAG app works … about 300 words." | 5.19s | 996 ← the expensive one |

## Think it through
**How do I check tracing is actually on?**
Before running the app I printed the 4 environment variables (showing only SET / MISSING, never the keys).
All were SET, with `LANGSMITH_TRACING=true` and `LANGSMITH_PROJECT=caie-week2`.

**Which prompt is expensive, and is it for a good reason?**
Run 3 (RAG) – 996 tokens (about 13× run 1) and the slowest (5.19s).
Yes, for a good reason: it asks for a ~300-word step-by-step explanation with an example,
so most of the tokens are the long answer I asked for. More output tokens = more time and more cost.

## Learning
Nothing in `traced_app.py` mentions LangSmith. The environment variables do all of it.
