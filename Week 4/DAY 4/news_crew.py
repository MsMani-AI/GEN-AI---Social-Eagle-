"""
Week 4 - Day 4: Two-Agent Crew for a Tech Newsletter

Researcher (with SerperDevTool web search) finds today's top 3 tech news stories.
Writer (NO tools) turns them into an exactly 5-line newsletter.
Tasks run sequentially; the Writer gets the Researcher's output through context=[find].

Model: Claude (Anthropic) instead of OpenAI.
Keys come ONLY from environment variables:
    ANTHROPIC_API_KEY, SERPER_API_KEY, MODEL (anthropic/claude-haiku-5-5)
"""

import os
from datetime import date
from crewai import Agent, Task, Crew, Process, LLM
from crewai_tools import SerperDevTool

# Brain (no temperature: Claude Haiku 5.5 gives a 400 error with it)
llm = LLM(model=os.environ.get("MODEL", "anthropic/claude-haiku-5-5"), max_tokens=1500)

# The AI does not know today's date, so we give it
today = date.today().strftime("%d %B %Y")

# Web search tool (reads SERPER_API_KEY from the environment), news results only
search = SerperDevTool(search_type="news", n_results=10)

# Agent 1: Researcher - HAS the search tool
researcher = Agent(
    role="Tech News Researcher",
    goal="Find today's top 3 technology news stories from reliable news sources.",
    backstory=("You are a careful technology journalist. You only report stories you found "
               "in the search results, you check that they are recent, you pick 3 different "
               "topics, and you always give the source link. You never invent news."),
    tools=[search],
    llm=llm,
    verbose=True,
    max_iter=5,
)

# Agent 2: Writer - has NO tools (so it writes instead of researching again)
writer = Agent(
    role="Tech Newsletter Writer",
    goal="Turn research notes into a clear newsletter of exactly 5 lines.",
    backstory=("You write for busy engineers and factory managers who read the news in one "
               "minute. You use simple English, one line per idea, and you never add facts "
               "that are not in the research notes."),
    tools=[],
    llm=llm,
    verbose=True,
)

# Task 1: find the stories (clean shape, so the Writer gets tidy input)
find = Task(
    description=("Today is {today}. Search the web for the top 3 technology news stories "
                 "from today or the last 24 hours. Choose 3 different topics. "
                 "Use only what you find in the search results."),
    expected_output=("Exactly 3 numbered stories and nothing else. Each on one line:\n"
                     "Title | one-line summary (max 20 words) | source URL"),
    agent=researcher,
)

# Task 2: write the newsletter - context hands over the Researcher's output
write = Task(
    description=("Using ONLY the 3 stories from the research, write a short tech newsletter "
                 "for busy readers. Do not add any new facts."),
    expected_output=("Exactly 5 lines and nothing else:\n"
                     "Line 1: Tech in 5 lines - {today}\n"
                     "Line 2: 1. <first story in one line>\n"
                     "Line 3: 2. <second story in one line>\n"
                     "Line 4: 3. <third story in one line>\n"
                     "Line 5: Why it matters: <one line>\n"
                     "No blank lines, no introduction, no closing text."),
    agent=writer,
    context=[find],
)

# The crew: two agents in a line
crew = Crew(
    agents=[researcher, writer],
    tasks=[find, write],
    process=Process.sequential,
    verbose=True,
)

result = crew.kickoff(inputs={"today": today})

print("\n========== Newsletter ==========")
print(result)