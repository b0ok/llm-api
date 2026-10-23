"""AI Math Assistant: LangChain create_agent + arithmetic tools + Wikipedia lookup.

python math_agent.py "What is the population of Canada? Multiply it by 0.75"
python math_agent.py --test    # tool self-check, no API calls
"""
import os, sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv(Path(__file__).parent.parent / ".env")  # shared llm-api .env (GROQ_API_KEY)

MODEL = "openai/gpt-oss-120b"  # won ../evals.py; free Groq tier


@tool
def add_numbers(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


@tool
def new_subtract_numbers(a: float, b: float) -> float:
    """Subtract b from a."""
    return a - b


@tool
def multiply_numbers(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b


@tool
def divide_numbers(a: float, b: float) -> float | str:
    """Divide a by b."""
    return "Error: division by zero" if b == 0 else a / b


@tool
def search_wikipedia(query: str) -> str:
    """Look up a topic on Wikipedia and return the intro of the best-matching article."""
    params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": query,
              "gsrlimit": 1, "prop": "extracts", "exintro": 1, "explaintext": 1}
    r = httpx.get("https://en.wikipedia.org/w/api.php", params=params, timeout=15,
                  headers={"User-Agent": "math-agent-lab/1.0 (https://github.com/b0ok)"})  # Wikimedia 403s UAs without contact info
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", {})
    if not pages:
        return f"No Wikipedia article found for {query!r}."
    page = next(iter(pages.values()))
    return f"{page['title']}: {page['extract'][:2000]}"


tools_updated = [add_numbers, new_subtract_numbers, multiply_numbers, divide_numbers, search_wikipedia]


def build_agent():
    llm_ai = ChatOpenAI(model=MODEL, api_key=os.getenv("GROQ_API_KEY"),
                        base_url="https://api.groq.com/openai/v1", timeout=60)
    return create_agent(
        model=llm_ai,
        tools=tools_updated,
        system_prompt="You are a helpful assistant that can perform various mathematical operations and look up information. Use the tools precisely and explain your reasoning clearly.",
    )


def test():
    assert add_numbers.invoke({"a": 25, "b": 15}) == 40
    assert new_subtract_numbers.invoke({"a": 10, "b": 4}) == 6
    assert multiply_numbers.invoke({"a": 40, "b": 2}) == 80
    assert divide_numbers.invoke({"a": 9, "b": 3}) == 3
    assert "zero" in divide_numbers.invoke({"a": 1, "b": 0})
    assert "Canada" in search_wikipedia.invoke({"query": "Canada"})
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        sys.exit(test())
    sys.stdout.reconfigure(encoding="utf-8")  # model output has non-cp1252 chars (e.g. 202f)
    query = " ".join(sys.argv[1:]) or "What is the population of Canada? Multiply it by 0.75"
    response = build_agent().invoke({"messages": [("human", query)]})

    print("\nMessage sequence:")
    for i, msg in enumerate(response["messages"]):
        print(f"\n--- Message {i+1} ---")
        print(f"Type: {type(msg).__name__}")
        print(f"Content: {msg.content}")
        if getattr(msg, "name", None):
            print(f"Name: {msg.name}")
        if getattr(msg, "tool_calls", None):
            print(f"Tool calls: {msg.tool_calls}")
