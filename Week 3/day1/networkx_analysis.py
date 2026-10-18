"""
Week 3 - Day 1 (extra): Analyse the same Knowledge Graph with NetworkX
Neo4j (cloud database) -> NetworkX (Python graph in memory) -> hubs, similar schemes, picture
"""
import networkx as nx
import matplotlib.pyplot as plt
from langchain_neo4j import Neo4jGraph

# 1. Read all relationships from Neo4j
graph = Neo4jGraph(refresh_schema=False)
rows = graph.query("""
MATCH (a)-[r]->(b)
RETURN a.name AS source, labels(a)[0] AS source_type,
       type(r) AS relation, b.name AS target, labels(b)[0] AS target_type
""")

# 2. Build the NetworkX graph
G = nx.DiGraph()
for r in rows:
    G.add_node(r["source"], type=r["source_type"])
    G.add_node(r["target"], type=r["target_type"])
    G.add_edge(r["source"], r["target"], relation=r["relation"])
print(f"NetworkX graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

# 3. Hubs = nodes linked to the most schemes
print("\nTop 10 hubs (most schemes connected):")
hubs = [(n, d) for n, d in G.in_degree() if G.nodes[n]["type"] != "Scheme"]
for n, d in sorted(hubs, key=lambda x: x[1], reverse=True)[:10]:
    print(f"  {n} ({G.nodes[n]['type']}): {d} schemes")

# 4. Similar schemes = share the most connections (crop, benefit, sector...)
target = "Distribution of Gypsum"
mine = set(G.successors(target))
scores = []
for s in G.nodes:
    if G.nodes[s]["type"] == "Scheme" and s != target:
        common = mine & set(G.successors(s))
        if len(common) >= 2:
            scores.append((s, len(common), sorted(common)))
print(f"\nSchemes similar to '{target}':")
for s, c, common in sorted(scores, key=lambda x: x[1], reverse=True)[:5]:
    print(f"  {s}  -> shares {c}: {common}")

# 5. Save a picture of the graph
colors = {"Scheme": "#4FC3F7", "Department": "#E57373", "Sector": "#81C784",
          "BenefitType": "#FFB74D", "Beneficiary": "#F48FB1", "Crop": "#FFF176",
          "Program": "#BA68C8"}
plt.figure(figsize=(16, 12))
pos = nx.spring_layout(G, k=0.6, seed=42)
nx.draw_networkx_nodes(G, pos,
    node_color=[colors.get(G.nodes[n]["type"], "grey") for n in G],
    node_size=[250 if G.nodes[n]["type"] == "Scheme" else 900 for n in G])
nx.draw_networkx_edges(G, pos, alpha=0.2, arrows=False)
nx.draw_networkx_labels(G, pos, {n: n for n in G if G.nodes[n]["type"] != "Scheme"}, font_size=9)
plt.title("TN Schemes Knowledge Graph (NetworkX) - blue dots = schemes")
plt.axis("off")
plt.savefig("networkx_graph.png", dpi=150, bbox_inches="tight")
print("\nPicture saved: networkx_graph.png")
