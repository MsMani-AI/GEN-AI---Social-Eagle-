"""
Week 3 - Day 1: Test connection to Neo4j Aura and Claude
Keys are read only from environment variables (never written in code).
"""
import os
from langchain_neo4j import Neo4jGraph
from langchain_anthropic import ChatAnthropic

# 1. Check the keys are set (prints SET / MISSING, never the value)
for name in ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "ANTHROPIC_API_KEY"]:
    print(f"{name}: {'SET' if os.getenv(name) else 'MISSING'}")

# 2. Connect to Neo4j (reads NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD automatically)
graph = Neo4jGraph(refresh_schema=False)
print(graph.query("RETURN 'Connected to Neo4j Aura!' AS message"))

# 3. Test Claude
llm = ChatAnthropic(model="claude-haiku-5-5", max_tokens=100)
print(llm.invoke("Say 'Vanakkam' and one short line about Tamil Nadu.").text)