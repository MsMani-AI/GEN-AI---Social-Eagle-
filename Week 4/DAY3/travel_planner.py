"""
Week 4 - Day 3: CrewAI Travel Planner Agent

The user types a city, and a Travel Planner agent suggests exactly 3 places to visit.
Model: Claude (Anthropic) instead of OpenAI.
The API key and model name come ONLY from environment variables:
    ANTHROPIC_API_KEY  and  MODEL (anthropic/claude-haiku-5-5)
"""

import os
from crewai import Agent, Task, Crew, LLM

# Brain of the agent: model name read from the MODEL env variable (key is read automatically)
# No temperature (Claude Haiku 5.5 gives a 400 error if temperature is set)
llm = LLM(model=os.environ.get("MODEL", "anthropic/claude-haiku-5-5"), max_tokens=1024)

# 1. Ask the user for a city
city = input("Which city? ").strip()
while not city:
    city = input("Please type a city name: ").strip()

# 2. The Agent: role, goal and backstory as real sentences
planner = Agent(
    role="Local Travel Planner",
    goal=("Suggest the 3 best places to visit in a city for a first-time visitor, "
          "each with one short practical tip."),
    backstory=("You are a friendly travel planner who has helped thousands of first-time visitors. "
               "Your travellers have only one day, so you choose famous, easy-to-reach places "
               "and give one useful tip for each, such as the best time to go. "
               "You write short and clear, never long stories."),
    llm=llm,
    verbose=True,
)

# 3. The Task: exactly 3 places, with the output shape we want back
task = Task(
    description=("Suggest exactly 3 places to visit in {city} for a first-time visitor "
                 "who has one day. Choose only real, well-known places in {city}."),
    expected_output=("Exactly 3 numbered lines and nothing else, in this format:\n"
                     "1. Place name - one short tip (max 12 words)\n"
                     "2. Place name - one short tip (max 12 words)\n"
                     "3. Place name - one short tip (max 12 words)\n"
                     "No introduction, no closing sentence, no extra text."),
    agent=planner,
)

# 4. The Crew: put agent + task together and run it
crew = Crew(agents=[planner], tasks=[task], verbose=True)
result = crew.kickoff(inputs={"city": city})   # {city} in the task is filled here

print("\n========== Final answer ==========")
print(f"Which city? {city}")
print(result)