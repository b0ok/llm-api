"""Groq vs Ollama: same 4 questions x 3 runs per model. python compare.py > compare.log"""
import sys, time, re
sys.stdout.reconfigure(encoding="utf-8")
from math_agent import build_agent

def has(*vals):  # final answer mentions any accepted form
    return lambda t: any(v in t.replace(",", "").replace("{}", "") for v in vals)

TASKS = [
    ("add 25 and 15, then multiply by 2", has("80")),
    ("What is the population of Canada? Multiply it by 0.75", has("31125000", "31.125", "31.1 million", "31.13")),
    ("Divide 10 by 0, then add 5", lambda t: bool(re.search(r"zero|undefined|cannot|can't|not possible", t, re.I))),
    ("How tall is Mount Everest in metres? Divide it by 2", has("4424.5", "4,424.5", "4424")),
]
BACKENDS = [("groq gpt-oss-120b", None), ("ollama qwen2.5:7b", "qwen2.5:7b"), ("ollama qwen2.5:14b", "qwen2.5:14b")]
RUNS = 3

for name, local in BACKENDS:
    agent = build_agent(local)
    for q, ok in TASKS:
        for r in range(RUNS):
            t0 = time.time()
            try:
                msgs = agent.invoke({"messages": [("human", q)]})["messages"]
                calls = [c["name"] + str(c["args"]) for m in msgs for c in (getattr(m, "tool_calls", None) or [])]
                final = msgs[-1].content
                verdict = "PASS" if ok(final) else "FAIL"
            except Exception as e:
                calls, final, verdict = [], repr(e)[:150], "ERR"
            print(f"{name} | {q[:30]} | run{r+1} | {verdict} | {time.time()-t0:.1f}s | {calls} | {final[-160:]!r}", flush=True)
