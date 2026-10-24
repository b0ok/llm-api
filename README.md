# llm-api

Calling LLMs from Python with the `openai` client, then building a tool-using coding agent on top of free models.

This started as a course exercise on calling the OpenAI API from Python. Instead of paying for OpenAI, I kept the `openai` client and moved to open-weight models: Groq's free cloud tier (mainly OpenAI's open-weight `gpt-oss-120b`) and Ollama for running models like `qwen2.5` locally. Gemini and OpenRouter free tiers are wired in too. The same `OpenAI()` client talks to all of them by swapping `base_url`.

## Files

| File | What it does |
|---|---|
| `all_free.py` | Sends one prompt to every configured provider at temperature 0 and 1.0 to compare models and randomness |
| `agent.py` | Terminal coding agent: 12 tools, approvals for every edit and command, sandboxed file access |
| `evals.py` | Scores the agent on 11 fixed tasks and logs results to `eval_log.txt` |
| `langchain-math-agent/` | The same agent idea built with LangChain's `create_agent`: arithmetic tools + Wikipedia lookup ([README](langchain-math-agent/README.md)) |
| `agent_skeleton.py` | Build-it-yourself version: the 8 parts of an agent as stubs, with a checker that tells you the next step |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # add your free keys
python all_free.py
python agent.py
```

## The agent

A model + tools + loop. The model picks a tool, the code runs it, the result goes back, repeat until it answers.

**Tools:** `list_files`, `read_file`, `search_files`, `edit_file`, `write_file`, `run_command`, `ask_user`, `save_note`, `calculator`, `get_time`, `web_fetch`, `web_search`

**Safety**
- Edits and commands show a diff / the command and wait for `y`; rejecting with a reason lets the agent adjust
- File access is limited to `AGENT_ROOT`; `.env` files are always blocked
- Commands run without API keys in their environment; commands touching `.env`, `..` or outside paths are refused
- Calculator parses math with `ast` instead of `eval`

**Reliability**
- Context budget sized for Groq's free tier (~8K input tokens/min): oversized tool results are cut, old turns are dropped
- A failed turn is rolled back so one error doesn't break the session
- Malformed tool calls are fed back to the model to retry
- Notes saved with `save_note` are loaded into the next session

Run the built-in checks: `python agent.py --test`

## Hand-rolled vs. LangChain

`agent.py` builds the loop by hand. `langchain-math-agent/` uses `create_agent`. Both run on the same Groq model and key.

| | `agent.py` (hand-rolled) | `langchain-math-agent` |
|---|---|---|
| Tool schemas | Written as JSON by hand | Generated from `@tool` type hints and docstrings |
| The loop | Own `while` loop over `chat.completions` | `create_agent` (LangGraph) runs it |
| Size | ~345 lines, 12 tools | ~100 lines, 5 tools |
| Approvals, sandbox, context budget, rollback | Built in | Not included; you'd add them as middleware |

LangChain removes the boilerplate: schemas, the message loop and argument validation. The parts that make an agent safe to run on your machine (approvals, path sandboxing, secret blocking) are still yours to write. Most of `agent.py` is that work, not the loop.

## Evals

```bash
python evals.py                       # default model
python evals.py qwen/qwen3.8-27b      # compare another Groq model
```

Tasks cover math, dates, code search, file reading, web search, create-and-test, editing, bug fixing, asking when unclear, refusing to show secrets, and staying in the sandbox. Edits and commands are auto-approved, simulating a careless user, which is how the evals caught the agent using `run_command` to read a file `read_file` had refused.

| Model | Score |
|---|---|
| `qwen/qwen3.8-27b` | 9/11 |
| `openai/gpt-oss-120b` | 10/11, 9/11 (faster: 1–3s per task) |

Scores vary between runs of the same model, so one run is a sample, not a verdict.
