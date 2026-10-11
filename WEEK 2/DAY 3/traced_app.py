"""
Week 2 - Day 3: Trace a LangChain App with LangSmith

Model: Claude (Anthropic) through LangChain's ChatAnthropic.
(The assignment example uses ChatOpenAI; I use ChatAnthropic because my
API credit is on the Claude Console. The tracing works exactly the same.)

This file does NOT mention LangSmith anywhere.
Tracing is switched on only through environment variables:
    ANTHROPIC_API_KEY, LANGSMITH_TRACING, LANGSMITH_API_KEY, LANGSMITH_PROJECT
"""

from langchain_anthropic import ChatAnthropic

# The chat model (LangChain wrapper, not the Anthropic SDK directly)
llm = ChatAnthropic(model="claude-haiku-5-5", max_tokens=1024)

# Three different prompts: short, medium and long (the long one will cost the most tokens)
prompts = [
    "What is LangChain? Answer in one sentence.",
    "Give 3 simple tips for writing a good prompt for an AI model.",
    "Explain step by step how a Retrieval Augmented Generation (RAG) app works, "
    "with a small real-world example. Write about 300 words.",
]

for i, p in enumerate(prompts, start=1):
    print(f"\n========== Prompt {i} ==========")
    print(f"Q: {p}")
    answer = llm.invoke(p).content
    print(f"A: {answer}")

print("\nDone. Open https://smith.langchain.com and check your project for 3 runs.")
