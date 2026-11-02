"""
Week 5 - Day 2: AutoGen Weather News Agent

The user types a city. The agent calls a search TOOL (DuckDuckGo via ddgs, no key)
to get today's weather news, then replies in exactly 3 short lines.

Model: Claude (Anthropic) instead of OpenAI -> AnthropicChatCompletionClient.
The API key is read ONLY from the ANTHROPIC_API_KEY environment variable.
"""

import asyncio
from ddgs import DDGS
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
from autogen_ext.models.anthropic import AnthropicChatCompletionClient


# 1. The TOOL: a normal Python function.
#    The agent reads its NAME, TYPE HINTS and DOCSTRING to decide when to call it.
def search_weather_news(city: str) -> str:
    """Search the web for TODAY'S weather news and forecast for one city.

    Use this tool whenever the user asks about today's weather, rain, heat,
    storms or weather alerts in a city. Do NOT use it for general trivia,
    history or facts about the city.

    Args:
        city: Name of the city only, for example "Chennai".

    Returns:
        Up to 5 recent news results (title, date, source, short summary).
    """
    results = []
    # Try today's news first ("d"), then this week's ("w") if nothing is found
    for limit in ("d", "w"):
        try:
            found = DDGS().news(query=f"{city} weather today", region="in-en",
                                timelimit=limit, max_results=10)
        except Exception:
            found = []
        # Keep only results that really mention the city (removes noise)
        results = [r for r in found
                   if city.lower() in (r.get("title", "") + r.get("body", "")).lower()]
        if results:
            break

    if not results:
        return f"No recent weather news found for {city}."

    # Send only the useful fields -> fewer tokens, cleaner input for Claude
    lines = []
    for r in results[:5]:
        lines.append(f"- {r.get('title', '')} | {r.get('date', '')} | "
                     f"{r.get('source', '')} | {r.get('body', '')[:200]}")
    return "\n".join(lines)


# 2. Ask the user for a city
city = input("Which city? ").strip()
while not city:
    city = input("Please type a city name: ").strip()

# 3. Brain: Claude Haiku (no temperature: Haiku 5.5 gives a 400 error with it)
model_client = AnthropicChatCompletionClient(
    model="claude-haiku-5-5",
    max_tokens=1024,
    model_info={
        "vision": True,
        "function_calling": True,   # needed so the agent can call tools
        "json_output": True,
        "structured_output": True,
        "family": "unknown",
    },
)

# 3b. Fix: AutoGen always adds temperature=1.0, but the new anthropic package
#     and Claude Haiku 5.5 don't accept it -> remove it before each request.
_original_create = model_client._client.messages.create

def _create_without_temperature(**kwargs):
    kwargs.pop("temperature", None)
    return _original_create(**kwargs)

model_client._client.messages.create = _create_without_temperature

# 4. The agent: gets the tool + reflect_on_tool_use=True
agent = AssistantAgent(
    name="weather_news",
    model_client=model_client,
    tools=[search_weather_news],
    system_message=(
        "You are a weather news reporter. For any city, ALWAYS call the "
        "search_weather_news tool first. Answer ONLY from the search results, "
        "never guess. Reply in exactly 3 short lines (max 15 words each), "
        "no title, no bullets, no markdown, no extra text. "
        "If no weather news is found, say so in the 3 lines."
    ),
    reflect_on_tool_use=True,   # agent writes an answer from the results (not raw output)
)


# 5. Run: show tool call + reply with Console, then always close the client
async def main():
    try:
        await Console(agent.run_stream(
            task=f"What is today's weather news for {city}? Reply in exactly 3 short lines."
        ))
    finally:
        await model_client.close()


asyncio.run(main())