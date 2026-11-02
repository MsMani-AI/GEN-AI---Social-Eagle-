"""
Week 5 - Day 1: AutoGen HR Assistant Agent

An AssistantAgent with system_message "You are an HR assistant." writes a
5-line job description for a Junior Python Developer.

Model: Claude (Anthropic) instead of OpenAI.
We use OpenAIChatCompletionClient (as the assignment asks), pointed at
Anthropic's OpenAI-compatible endpoint. (AutoGen's own Anthropic client sends
'temperature', which the new Anthropic library rejects.)
The API key is read ONLY from the ANTHROPIC_API_KEY environment variable.
AutoGen runs on asyncio, so the work is inside an async main() function.
"""

import os
import asyncio
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient

# 1. Brain: Claude Haiku through the OpenAI-compatible endpoint. No temperature.
#    model_info tells AutoGen what this (non-OpenAI) model can do.
model_client = OpenAIChatCompletionClient(
    model="claude-haiku-5-5",
    base_url="https://api.anthropic.com/v1/",
    api_key=os.environ["ANTHROPIC_API_KEY"],   # from env, never hard-coded
    max_tokens=1024,
    model_info={
        "vision": True,
        "function_calling": True,
        "json_output": True,
        "structured_output": True,
        "family": "unknown",
    },
)

# 2. The agent: name + the exact system message from the assignment
agent = AssistantAgent(
    name="hr_assistant",
    model_client=model_client,
        system_message="You are an HR assistant.",
)

# 3. The task: "5 lines" made exact = one title line, then exactly 5 numbered lines
TASK = (
    "Write a job description for a Junior Python Developer.\n"
    "Format exactly like this and nothing else:\n"
    "Junior Python Developer\n"
    "1. <one sentence>\n"
    "2. <one sentence>\n"
    "3. <one sentence>\n"
    "4. <one sentence>\n"
    "5. <one sentence>\n"
    "Each numbered line is one short sentence (max 15 words). "
    "No introduction, no closing text, no blank lines, no markdown."
)


# 4. Run: show the reply with Console, then always close the client
async def main():
    try:
        await Console(agent.run_stream(task=TASK))
    finally:
        await model_client.close()   # unclosed client = script can hang


asyncio.run(main())


