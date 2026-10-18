"""
Week 3 - Day 1: Build a Knowledge Graph of Tamil Nadu schemes in Neo4j Aura
Source page: https://www.tn.gov.in/scheme_list.php?dep_id=Mg==  (saved as schemes.txt)
Claude (ChatAnthropic) classifies each scheme NAME -> saved as nodes + relationships.
Keys are read only from environment variables.
"""
from typing import List, Literal
from pydantic import BaseModel, Field
from langchain_anthropic import ChatAnthropic
from langchain_neo4j import Neo4jGraph

DEPARTMENT = "Agriculture - Farmers Welfare Department"
SOURCE = "https://www.tn.gov.in/scheme_list.php?dep_id=Mg=="
BATCH_SIZE = 18  # schemes sent to Claude in one call

# ---------- 1. Read scheme names from schemes.txt ----------
with open("schemes.txt", encoding="utf-8") as f:
    lines = [line.strip() for line in f if line.strip()]

start = lines.index(DEPARTMENT) + 1
end = next(i for i, l in enumerate(lines) if l.startswith("Content owned"))
scheme_names = list(dict.fromkeys(lines[start:end]))  # remove duplicates, keep order
print(f"Found {len(scheme_names)} schemes in schemes.txt")

# ---------- 2. The shape of Claude's answer (fixed choices = clean graph) ----------
Sector = Literal["Agriculture", "MSME & Industry", "Employment & Skills", "Rural Livelihood"]
Benefit = Literal["Training", "Seed Production", "Free Distribution", "Demonstration",
                  "Subsidy", "Tax & Stamp Duty Rebate", "Loan Support",
                  "Reservation & Preference", "Other"]
Beneficiary = Literal["Farmers", "Micro & Small Enterprises", "Industrial Estate Developers",
                      "Unemployed Youth", "Asset-less Persons", "MSME Associations"]
Crop = Literal["Paddy", "Maize", "Pulses", "Oilseeds", "Groundnut", "Millets", "Cotton"]

class SchemeInfo(BaseModel):
    id: int = Field(description="The number written before the scheme name")
    sector: Sector
    benefit_type: Benefit
    beneficiaries: List[Beneficiary] = Field(description="Who benefits, only if clear from the name")
    crops: List[Crop] = Field(description="Crops named in the scheme name; empty list if none")
    programs: List[str] = Field(description="Programs/agencies written in the name, e.g. ISOPOM, TNAU, "
                                            "TIIC, SIPCOT, TANSIDCO, NSIC, UYEGP, NEF; empty list if none")

class SchemeBatch(BaseModel):
    schemes: List[SchemeInfo]

RULES = """You classify Tamil Nadu government scheme NAMES for a knowledge graph.
Use ONLY the words in each scheme name. Do not guess eligibility, amounts or dates.
If something is not clear from the name, use "Other" (benefit_type) or an empty list.
Return exactly one item for EVERY id given."""

# ---------- 3. Claude classifies the schemes ----------
llm = ChatAnthropic(model="claude-haiku-5-5", max_tokens=4096)
extractor = llm.with_structured_output(SchemeBatch)

results = {}
for i in range(0, len(scheme_names), BATCH_SIZE):
    batch = list(enumerate(scheme_names[i:i + BATCH_SIZE], start=i))
    text = "\n".join(f"{n}. {name}" for n, name in batch)
    answer = extractor.invoke(f"{RULES}\n\nSchemes:\n{text}")
    for s in answer.schemes:
        results[s.id] = s
    print(f"Claude classified schemes {i + 1} to {i + len(batch)}")

# ---------- 4. Save into Neo4j ----------
graph = Neo4jGraph(refresh_schema=False)
graph.query("MATCH (n) DETACH DELETE n")  # start clean on every run

CYPHER = """
MERGE (s:Scheme {name: $name})
SET s.source = $source
MERGE (d:Department {name: $dept})      MERGE (s)-[:BELONGS_TO]->(d)
MERGE (sec:Sector {name: $sector})      MERGE (s)-[:IN_SECTOR]->(sec)
MERGE (b:BenefitType {name: $benefit})  MERGE (s)-[:PROVIDES]->(b)
FOREACH (x IN $beneficiaries | MERGE (p:Beneficiary {name: x}) MERGE (s)-[:FOR]->(p))
FOREACH (x IN $crops | MERGE (c:Crop {name: x}) MERGE (s)-[:FOR_CROP]->(c))
FOREACH (x IN $programs | MERGE (g:Program {name: x}) MERGE (s)-[:LINKED_TO]->(g))
"""

missing = []
for n, name in enumerate(scheme_names):  # use the ORIGINAL name, not Claude's copy
    info = results.get(n)
    if info is None:
        missing.append(name)
        graph.query("MERGE (s:Scheme {name:$name}) SET s.source=$source "
                    "MERGE (d:Department {name:$dept}) MERGE (s)-[:BELONGS_TO]->(d)",
                    {"name": name, "source": SOURCE, "dept": DEPARTMENT})
        continue
    graph.query(CYPHER, {
        "name": name, "source": SOURCE, "dept": DEPARTMENT,
        "sector": info.sector, "benefit": info.benefit_type,
        "beneficiaries": info.beneficiaries, "crops": info.crops, "programs": info.programs,
    })

# ---------- 5. Summary ----------
print("\nGraph saved in Neo4j Aura:")
for row in graph.query("MATCH (n) RETURN labels(n)[0] AS type, count(*) AS total ORDER BY total DESC"):
    print(f"  {row['type']}: {row['total']}")
rels = graph.query("MATCH ()-[r]->() RETURN count(r) AS total")[0]["total"]
print(f"  Relationships: {rels}")
if missing:
    print(f"\n⚠️ Claude skipped {len(missing)} schemes (saved with department only): {missing}")