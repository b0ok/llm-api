"""Build your own agent in 8 steps. Fill in each TODO from top to bottom.

Run `python agent_skeleton.py` any time: it checks your work and tells you which step is next.
Stuck? agent.py is the answer key. Search it for the same function name.
"""
import json, os, sys
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")
ROOT = HERE.parent  # the only folder the agent may touch


# ---------------------------------------------------------------------------
# STEP 1: MODEL. The brain that decides what to do next.
# ---------------------------------------------------------------------------
MODEL = ""  # TODO: a Groq model that supports tools, e.g. "openai/gpt-oss-120b"


def make_client():
    # TODO: return OpenAI(...) pointed at Groq: api_key from GROQ_API_KEY, base_url https://api.groq.com/openai/v1
    raise NotImplementedError("Step 1: create the client")


# ---------------------------------------------------------------------------
# STEP 2: TOOLS. Python functions + descriptions the model reads to pick one.
# ---------------------------------------------------------------------------
def calculator(expression):
    # TODO: evaluate math safely. Never use eval() on model output. Hint: the ast module.
    raise NotImplementedError("Step 2: calculator")


def read_file(path):
    # TODO: return the file's text. After step 4, route the path through safe_path() first.
    raise NotImplementedError("Step 2: read_file")


TOOLS = [
    # TODO: one schema per tool, shaped like:
    # {"type": "function", "function": {"name": "calculator", "description": "...",
    #   "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}}}
]
FUNCS = {"calculator": calculator, "read_file": read_file}  # name -> function, used by the loop


# ---------------------------------------------------------------------------
# STEP 3: LOOP. Model asks for tools -> run them -> send results back -> repeat.
# ---------------------------------------------------------------------------
def run_turn(client, messages):
    # TODO:
    #   for up to N rounds:
    #     msg = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS).choices[0].message
    #     no msg.tool_calls?  -> append the reply as an assistant message and return msg.content
    #     else append the assistant message WITH its tool_calls, then for each call:
    #       run FUNCS[name](**json.loads(arguments)), catch errors as text,
    #       append {"role": "tool", "tool_call_id": ..., "content": str(result)}
    #   always cap the rounds so a confused model can't loop forever
    raise NotImplementedError("Step 3: the agent loop")


# ---------------------------------------------------------------------------
# STEP 4: PERMISSIONS. What it may do alone vs. what needs your yes.
# ---------------------------------------------------------------------------
def safe_path(path):
    # TODO: resolve ROOT / path; raise ValueError if it escapes ROOT or the filename starts with ".env"
    raise NotImplementedError("Step 4: safe_path")


def approve(action):
    # TODO: print the action, ask input("Allow? [y/N] "), return True only for "y"
    raise NotImplementedError("Step 4: approve")


# ---------------------------------------------------------------------------
# STEP 5: MEMORY & CONTEXT. What the model knows, and keeping it under budget.
# ---------------------------------------------------------------------------
NOTES = HERE / "notes.md"
MAX_CHARS = 15000  # Groq free tier: ~8K input tokens/min


def system_prompt():
    # TODO: return SYSTEM, plus the last lines of NOTES if that file exists (long-term memory)
    raise NotImplementedError("Step 5: system_prompt")


def trim(messages):
    # TODO: while len(json.dumps(messages)) > MAX_CHARS, delete the oldest whole turn
    #       (a user message through everything before the next user message). Never delete messages[0].
    raise NotImplementedError("Step 5: trim")


# ---------------------------------------------------------------------------
# STEP 6: VERIFICATION. Let it run code so it can check its own work.
# ---------------------------------------------------------------------------
def run_command(command):
    # TODO: if approve(command): subprocess.run(..., cwd=ROOT, capture_output=True, text=True, timeout=120)
    #       return exit code + output. Rejected? return "user rejected". Then add it to TOOLS and FUNCS.
    raise NotImplementedError("Step 6: run_command")


# ---------------------------------------------------------------------------
# STEP 7: PLANNING. Rules that shape how it works, not just what it knows.
# ---------------------------------------------------------------------------
SYSTEM = ""  # TODO: who it is, when to use which tool, "make a numbered plan for 3+ step tasks", "verify before done"


# ---------------------------------------------------------------------------
# STEP 8: EVALS. A fixed exam so you know if a change helped or hurt.
# ---------------------------------------------------------------------------
TASKS = [
    # TODO: at least 3 (prompt, check) pairs, e.g.
    # ("What is 17% of 243? Just the number.", lambda reply: "41.31" in reply),
]


def run_evals(client):
    # TODO: for each task, run_turn on a fresh [system, user] conversation, check the reply, print PASS/FAIL + score
    raise NotImplementedError("Step 8: run_evals")


# ---------------------------------------------------------------------------
# Progress checker: tells you the next step. No need to edit below.
# ---------------------------------------------------------------------------
def check_progress():
    import builtins
    real_input = builtins.input

    def must_raise(fn, *args):
        try:
            fn(*args)
        except ValueError:
            return
        raise AssertionError(f"{fn.__name__}{args} should raise ValueError")

    def step1():
        if not MODEL:
            raise NotImplementedError("Step 1: set MODEL")
        assert isinstance(make_client(), OpenAI), "make_client() must return an OpenAI client"

    def step2():
        assert float(calculator("2+3*4")) == 14, "calculator('2+3*4') should be 14"
        must_raise(calculator, "__import__('os')")
        assert "STEP 2" in read_file(f"{HERE.name}/agent_skeleton.py"), "read_file should return file text"
        names = {t["function"]["name"] for t in TOOLS}
        assert {"calculator", "read_file"} <= names, f"TOOLS needs schemas for calculator and read_file, has {names}"

    def step3():
        reply = run_turn(make_client(), [{"role": "system", "content": "Use the calculator tool for math."},
                                         {"role": "user", "content": "What is 123*456? Use the calculator."}])
        assert "56088" in (reply or "").replace(",", ""), f"expected 56088 in reply, got: {reply!r}"

    def step4():
        must_raise(safe_path, "../../outside.txt")
        must_raise(safe_path, f"{HERE.name}/.env")
        must_raise(read_file, f"{HERE.name}/.env")  # read_file must use safe_path
        builtins.input = lambda *_: "n"
        assert approve("test") is False, "approve should be False unless the user types y"
        builtins.input = lambda *_: "y"
        assert approve("test") is True

    def step5():
        assert isinstance(system_prompt(), str)
        msgs = [{"role": "system", "content": "s"}]
        for i in range(30):
            msgs += [{"role": "user", "content": f"q{i}"}, {"role": "assistant", "content": "x" * 2000}]
        trim(msgs)
        assert len(json.dumps(msgs)) <= MAX_CHARS and msgs[0]["role"] == "system" and msgs[-2]["content"] == "q29"

    def step6():
        builtins.input = lambda *_: "y"
        assert "hi" in str(run_command("echo hi"))
        builtins.input = lambda *_: "n"
        assert "reject" in str(run_command("echo hi")).lower()
        assert "run_command" in FUNCS and "run_command" in {t["function"]["name"] for t in TOOLS}

    def step7():
        assert "plan" in SYSTEM.lower() and "verify" in SYSTEM.lower(), "SYSTEM should mention planning and verifying"

    def step8():
        assert len(TASKS) >= 3 and all(callable(c) for _, c in TASKS), "add at least 3 (prompt, check) tasks"

    steps = [("Model", step1), ("Tools", step2), ("Loop", step3), ("Permissions", step4),
             ("Memory & context", step5), ("Verification", step6), ("Planning", step7), ("Evals", step8)]
    try:
        for n, (name, check) in enumerate(steps, 1):
            try:
                check()
            except NotImplementedError as e:
                print(f"Step {n} ({name}): not started. {e}")
                return
            except Exception as e:
                print(f"Step {n} ({name}): not working yet. {e.__class__.__name__}: {e}")
                return
            finally:
                builtins.input = real_input
            print(f"Step {n} ({name}): done")
    finally:
        builtins.input = real_input
    print("\nAll 8 steps done. Run your agent, then: python agent_skeleton.py --evals")


if __name__ == "__main__":
    if "--evals" in sys.argv:
        run_evals(make_client())
    else:
        check_progress()
