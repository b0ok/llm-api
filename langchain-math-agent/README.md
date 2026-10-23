# LangChain math agent

A small LangChain agent that answers math questions in plain English by calling arithmetic tools, and looks up real-world numbers on Wikipedia when a question needs them.

```
> What is the population of Canada? Multiply it by 0.75
search_wikipedia("Canada population")  ->  ~41.5 million (Q1 2026)
multiply_numbers(41500000, 0.75)       ->  31125000.0
Result: about 31.1 million
```

## Tools

| Tool | Does |
|------|------|
| `add_numbers` | a + b |
| `new_subtract_numbers` | a - b |
| `multiply_numbers` | a × b |
| `divide_numbers` | a ÷ b (returns an error message on divide by zero) |
| `search_wikipedia` | intro text of the best-matching Wikipedia article |

The agent is built with `langchain.agents.create_agent`. It runs on Groq's free `openai/gpt-oss-120b` model through `ChatOpenAI`, pointed at Groq's OpenAI-compatible endpoint.

## Setup

From the `llm-api` root:

```
pip install -r requirements.txt
```

It uses the same `GROQ_API_KEY` from `llm-api/.env` as `agent.py` (get a free key at https://console.groq.com).

## Run

```
python math_agent.py                                      # default: Canada population x 0.75
python math_agent.py "add 25 and 15, then multiply by 2"
python math_agent.py --test                               # tool self-check, no model calls
```

The script prints every message in the run (human, AI tool calls, tool results, final answer), so you can follow how the agent breaks a question into steps.

## Learnings

### Building effective tools for advanced LLMs

- **The docstring is the prompt.** `@tool` turns the function name, docstring and type hints into the schema the model reads. `"""Subtract b from a."""` tells the model the argument order. A vague docstring leads to wrong calls.
- **Type hints become the contract.** `a: float, b: float` produces a JSON schema, and LangChain validates the model's arguments against it before the function runs. Typed arguments beat one free-text `inputs: str` that you have to parse yourself.
- **Keep each tool small and give it one job.** Four arithmetic tools let the model chain steps (`add`, then `multiply`), and each step shows up in the trace. One `calculate(expression)` tool would hide the reasoning.
- **Return errors as text instead of raising.** `divide_numbers` returns `"Error: division by zero"`. The model reads that and can recover or explain it. An exception would end the run.
- **Bound what you return.** `search_wikipedia` cuts its result to 2,000 characters. Tool output goes back into the context window, and on free tiers (Groq allows about 8K tokens per minute) a full article would use up the budget.
- **Tools talk to the real world, so handle real-world failures.** Here that meant TLS certificate errors, Wikimedia's User-Agent policy and timeouts. Put a timeout on every network call.
- **Test tools without the model.** `--test` calls each tool directly with `.invoke({...})`. It's fast, free and repeatable, and it tells you whether a bug is in the tool or in the model.

### Building agents for dynamic tool use

- **The agent is a loop.** `create_agent` runs model → tool calls → tool results → model, until the model answers without calling a tool. The message sequence printed by `math_agent.py` shows that loop step by step:
  `HumanMessage` → `AIMessage(tool_calls)` → `ToolMessage` → … → final `AIMessage`.
- **The model plans the steps.** You never wrote "search first, then multiply". The model chose that order from the question and the tool descriptions. Better descriptions lead to better plans.
- **Tools compose across domains.** A lookup tool (Wikipedia) and a compute tool (multiply) together answer questions that neither can answer alone. That composition is the main reason to build an agent.
- **Let tools do the math.** LLMs make arithmetic mistakes on large numbers. Sending even simple math through a tool makes the result exact and auditable.
- **The system prompt sets the behavior.** "Use the tools precisely and explain your reasoning clearly" pushes the model to call tools instead of guessing and to show its work.
- **The model choice matters.** The model has to support tool calling and must not invent tool names. `gpt-oss-120b` scored best in the `../evals.py` runs, which is why this project uses it.
- **Read the trace.** When an answer is wrong, the message list shows whether the cause was a bad search, bad parsing of the result, or a bad tool call.

### Popular built-in tools in LangChain

You don't need to write every tool yourself. LangChain ships many ready-made ones, mostly in `langchain-community` or in their own partner packages:

| Tool | Package | Use |
|------|---------|-----|
| `TavilySearch` | `langchain-tavily` | Web search built for agents (API key, free tier) |
| `DuckDuckGoSearchRun` | `langchain-community` + `ddgs` | Web search, no key needed |
| `WikipediaQueryRun` | `langchain-community` + `wikipedia` | Built-in version of this project's `search_wikipedia` |
| `ArxivQueryRun` | `langchain-community` + `arxiv` | Search research papers |
| `PubmedQueryRun` | `langchain-community` | Search medical literature |
| `WolframAlphaQueryRun` | `langchain-community` | Advanced math and facts (API key) |
| `PythonREPLTool` | `langchain-experimental` | Runs Python code (powerful but unsafe; sandbox it) |
| `SQLDatabaseToolkit` | `langchain-community` | Query a SQL database in natural language |
| `RequestsToolkit` | `langchain-community` | HTTP GET/POST to APIs |
| `FileManagementToolkit` | `langchain-community` | Read and write local files |
| `YouTubeSearchTool` | `langchain-community` | Find videos |

Example of swapping in the built-in Wikipedia tool:

```python
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper

wiki = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper(top_k_results=1, doc_content_chars_max=2000))
tools = [add_numbers, multiply_numbers, wiki]
```

**Built-in or custom?** Use a built-in tool when it covers what you need. Write your own when you need to control the output size, error handling or dependencies. This project's `search_wikipedia` is about 10 lines and needs no extra package. Full list: https://docs.langchain.com/oss/python/integrations/tools

## Notes

- The Wikipedia request sends a User-Agent with contact info, because Wikimedia blocks requests without one (HTTP 403).
- Wikipedia is fetched with `httpx` instead of `urllib`, because `urllib` failed with an expired-certificate error on Windows.
- Output is forced to UTF-8 so the Windows console doesn't crash on special characters in model replies.
