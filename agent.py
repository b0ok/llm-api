import ast, difflib, html, json, operator, os, re, subprocess, sys, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path
import openai
from dotenv import load_dotenv
from openai import OpenAI

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

ROOT = Path(os.getenv("AGENT_ROOT", HERE.parent)).resolve()  # agent can only touch files inside here
NOTES = HERE / "notes.md"
MODEL = "openai/gpt-oss-120b"  # beat qwen/qwen3.8-27b on evals (see eval_log.txt); each model has its own daily quota
client = OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1", timeout=60)


# --- tools -----------------------------------------------------------------

def safe_path(path):
    full = (ROOT / path).resolve()
    if not full.is_relative_to(ROOT):
        raise ValueError(f"only files inside {ROOT} are allowed")
    if full.name.startswith(".env"):
        raise ValueError("secret files are off limits")  # contents would be sent to Groq
    return full


def list_files(path="."):
    return "\n".join(sorted(p.name + ("/" if p.is_dir() else "") for p in safe_path(path).iterdir())[:200])


def read_file(path):
    return safe_path(path).read_text(encoding="utf-8", errors="replace")[:20000]


SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}


def search_files(text, folder="."):
    hits = []
    for dirpath, dirs, files in os.walk(safe_path(folder)):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            p = Path(dirpath, name)
            if name.startswith(".env") or p.stat().st_size > 1_000_000:
                continue
            try:
                lines = p.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue  # binary or unreadable
            for n, line in enumerate(lines, 1):
                if text.lower() in line.lower():
                    hits.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()[:200]}")
                    if len(hits) >= 100:
                        return "\n".join(hits) + "\n(stopped at 100 matches, search a smaller folder)"
    return "\n".join(hits) or "no matches"


def ask_user(question):
    return input(f"\n  Agent asks: {question}\n  Your answer: ").strip() or "(no answer)"


def approve(full, new_text):
    """Show a diff and write only if the user types y. Keeps the file's line endings."""
    old_text = full.read_text(encoding="utf-8") if full.exists() else ""
    crlf = full.exists() and b"\r\n" in full.read_bytes()
    diff = "\n".join(difflib.unified_diff(old_text.splitlines(), new_text.splitlines(),
                                          f"{full.name} (before)", f"{full.name} (after)", lineterm=""))
    print(diff or "  (no changes)")
    if input(f"  Apply to {full}? [y/N] ").strip().lower() != "y":
        why = input("  Why not? (optional, tells the agent) ").strip()
        return "user rejected the change" + (f": {why}" if why else "")
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(new_text, encoding="utf-8", newline="\r\n" if crlf else "\n")
    return f"saved {full}"


def edit_file(path, old, new):
    full = safe_path(path)
    text = full.read_text(encoding="utf-8")
    count = text.count(old) if old else 0
    if count != 1:
        raise ValueError(f"'old' must appear exactly once in the file, found {count}. Re-read the file and copy the exact text.")
    return approve(full, text.replace(old, new))


def write_file(path, content):
    return approve(safe_path(path), content)


def run_command(command, folder="."):
    cwd = safe_path(folder)
    # ponytail: denylist, not airtight (a determined command can dodge it); your y/N approval is the real gate
    low = command.lower()
    if ".env" in low or ".." in low:
        raise ValueError("commands touching .env files or parent folders are blocked")
    for p in re.findall(r"[a-z]:[\\/][^\s\"'|&<>]*", low):
        if not Path(p).resolve().is_relative_to(ROOT):
            raise ValueError(f"{p} is outside {ROOT}, blocked")
    print(f"  $ {command}   (in {cwd})")
    if input("  Run it? [y/N] ").strip().lower() != "y":
        why = input("  Why not? (optional, tells the agent) ").strip()
        return "user rejected the command" + (f": {why}" if why else "")
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}  # keys stay out of command output
    try:
        p = subprocess.run(command, shell=True, cwd=cwd, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
    except subprocess.TimeoutExpired:
        return "error: command timed out after 120s"
    out = (p.stdout + p.stderr).strip()
    print("\n".join("  | " + line for line in out.splitlines()[-15:]))
    return f"exit code {p.returncode}\n{out[-8000:]}"


def save_note(text):
    with open(NOTES, "a", encoding="utf-8") as f:
        f.write(f"- {datetime.now():%Y-%m-%d %H:%M} {text}\n")
    return f"saved to {NOTES}"


OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg}


def calculator(expression):
    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            left, right = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(right) > 100:
                raise ValueError("exponent too large")
            return OPS[type(n.op)](left, right)
        if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.operand))
        raise ValueError("only numbers and + - * / ** % allowed")
    return round(ev(ast.parse(expression, mode="eval").body), 10)


def get_time():
    return datetime.now().strftime("%A %Y-%m-%d %H:%M")


def get_page(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    return urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")


def strip_tags(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def web_fetch(url):
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must start with http:// or https://")
    page = re.sub(r"(?s)<(script|style).*?</\1>", " ", get_page(url))
    return strip_tags(page)[:8000]  # ponytail: crude tag strip, fine for reading articles


def web_search(query):
    # ponytail: scrapes DuckDuckGo Lite (no key needed); switch to Tavily/Brave API if it starts getting blocked
    page = get_page("https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query))
    links = re.findall(r"href=\"[^\"]*uddg=([^&\"]+)[^\"]*\" class='result-link'>(.*?)</a>", page)
    snippets = re.findall(r"class='result-snippet'>(.*?)</td>", page, re.S)
    if not links:
        return "no results (search may be rate-limited; try again later, or web_fetch a known URL)"
    return "\n\n".join(f"{strip_tags(title)}\n{urllib.parse.unquote(url)}\n{strip_tags(snip)}"
                       for (url, title), snip in zip(links[:8], snippets + [""] * 8))


FUNCS = {f.__name__: f for f in (list_files, read_file, search_files, edit_file, write_file, run_command, ask_user,
                                  save_note, calculator, get_time, web_fetch, web_search)}


def tool(name, desc, **params):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": {k: {"type": "string", "description": v} for k, v in params.items()},
        "required": list(params)}}}


TOOLS = [
    tool("list_files", f"List files in a folder, relative to {ROOT}. Use '.' for the top.", path="folder path"),
    tool("read_file", f"Read a text file, path relative to {ROOT}.", path="file path"),
    tool("search_files", "Find every line containing some text (case-insensitive) across a folder's files. "
         "Use this to locate code before reading files one by one.", text="text to find", folder=f"folder relative to {ROOT}"),
    tool("edit_file", "Replace one exact snippet in an existing file. The user approves every edit. Read the file first.",
         path="file path", old="exact text to replace, must appear once", new="replacement text"),
    tool("write_file", "Create a new file, or fully overwrite one. The user approves it first.",
         path="file path", content="full file content"),
    tool("run_command", "Run a Windows cmd command (e.g. python file.py, pytest). The user approves each one.",
         command="the command", folder=f"folder to run in, relative to {ROOT}"),
    tool("ask_user", "Ask the user a clarifying question and wait for the answer. Use when the task is ambiguous.",
         question="the question"),
    tool("save_note", "Append a note to the user's notes file.", text="the note"),
    tool("calculator", "Evaluate a math expression exactly. Use for ANY arithmetic.", expression="e.g. 84*0.15"),
    tool("get_time", "Get the current local date and time."),
    tool("web_fetch", "Fetch a web page and return its text.", url="full https URL"),
    tool("web_search", "Search the web. Returns titles, URLs and snippets; web_fetch a URL to read more.",
         query="search query"),
]

SYSTEM = f"""You are T3's assistant. Use tools instead of guessing: calculator for math, get_time for dates,
list_files/read_file for anything in T3's projects folder ({ROOT}).
- Use search_files to find code, web_search for anything current or outside your knowledge.
- If a request is ambiguous, use ask_user instead of guessing.
- Always read a file before editing it; prefer edit_file over write_file for existing files.
- For tasks with 3+ steps, first reply with a short numbered plan, then work through it.
- After changing code, verify it with run_command (run the script or its tests) before saying it's done.
- If the user rejects a change or command, adjust based on their reason.
- Never use run_command to get around a blocked read_file (secret files, paths outside the projects folder).
- Save anything worth remembering across sessions with save_note.
Keep answers short."""

# Groq free tier allows ~8K input tokens per request/minute; tools+system use ~1.5K of that.
# ponytail: chars/3.5 ≈ tokens estimate, drop oldest turns; summarize them instead if long chats lose context
MAX_CHARS = 15000
MAX_RESULT = 5000  # per tool result


def system_prompt():
    notes = NOTES.read_text(encoding="utf-8").splitlines()[-30:] if NOTES.exists() else []
    return SYSTEM + ("\n\nYour notes from past sessions:\n" + "\n".join(notes) if notes else "")


def trim(messages):
    """Drop the oldest whole turns (user msg + its tool calls) until under budget. Keeps system + latest turn.
    If the latest turn alone is too big, shrink its oldest tool results."""
    while len(json.dumps(messages)) > MAX_CHARS:
        turns = [i for i, m in enumerate(messages) if m["role"] == "user"]
        if len(turns) >= 2:
            del messages[turns[0]:turns[1]]
            continue
        big = [m for m in messages if m["role"] == "tool" and len(m["content"]) > 300]
        if not big:
            break
        big[0]["content"] = big[0]["content"][:200] + "\n(trimmed to save space, re-run the tool if needed)"  # stays under 300


# --- agent loop ------------------------------------------------------------

def run_turn(messages):
    for _ in range(20):  # max tool rounds per question
        trim(messages)
        try:
            msg = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS).choices[0].message
        except openai.BadRequestError as e:
            if "tool_use_failed" not in str(e):
                raise
            # model wrote a broken tool call; tell it and let it retry (uses up one round)
            messages.append({"role": "user", "content": "[system] Your last tool call had invalid JSON arguments. "
                             "Try again with simpler arguments (avoid heredocs and heavy escaping)."})
            continue
        if not msg.tool_calls:
            messages.append({"role": "assistant", "content": msg.content or ""})
            return msg.content
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
                print(f"  [tool] {tc.function.name}({args})")
                result = str(FUNCS[tc.function.name](**args))
            except Exception as e:
                result = f"error: {e}"
            if len(result) > MAX_RESULT:
                result = result[:MAX_RESULT] + f"\n(cut off, {len(result) - MAX_RESULT} more chars; narrow the search or folder)"
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    return "(stopped: too many tool calls)"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles choke on → and emoji otherwise
    messages = [{"role": "system", "content": system_prompt()}]
    print(f"Agent on {MODEL}. Type 'exit' to quit.")
    while True:
        try:
            user = input("\nYou: ").strip()
        except EOFError:
            break
        if user.lower() in ("exit", "quit"):
            break
        if not user:
            continue
        start = len(messages)
        messages.append({"role": "user", "content": user})
        try:
            print("Agent:", run_turn(messages))
        except Exception as e:
            del messages[start:]  # drop the failed turn so one error doesn't break every later message
            print(f"Agent error: {e.__class__.__name__}: {str(e)[:300]}")


def selftest():
    me = HERE.name  # this project's folder, relative to ROOT
    assert calculator("84*0.15") == 12.6
    assert calculator("-2**3 + 10 % 3") == -7
    for bad in ("__import__('os')", "9**9**9"):
        try: calculator(bad); raise AssertionError(bad)
        except ValueError: pass
    for bad in ("../..", f"{me}/.env"):
        try: safe_path(bad); raise AssertionError(bad)
        except ValueError: pass
    assert "agent.py" in list_files(me)
    hits = search_files("groq_api_key", me)
    assert "agent.py:" in hits and ".env" not in hits  # finds code, never reads secrets

    import builtins
    tmp, real_input = HERE / "_selftest.txt", builtins.input
    try:
        tmp.write_bytes(b"a\r\nb\r\n")
        builtins.input = lambda *_: "n"
        assert "rejected" in edit_file(f"{me}/_selftest.txt", "b", "c") and tmp.read_bytes() == b"a\r\nb\r\n"
        builtins.input = lambda *_: "y"
        edit_file(f"{me}/_selftest.txt", "a\nb", "a\nc")  # multi-line match on a CRLF file
        assert tmp.read_bytes() == b"a\r\nc\r\n"  # line endings kept
        try: edit_file(f"{me}/_selftest.txt", "zzz", "x"); raise AssertionError("missing old")
        except ValueError: pass
        builtins.input = lambda *_: "n"
        assert "rejected" in run_command("echo hi", me)
        builtins.input = lambda *_: "y"
        assert run_command("echo hi", me).startswith("exit code 0\nhi")
        assert "GROQ_API_KEY" not in run_command("set", me)
        for bad in (r"type C:\Windows\win.ini", "type .env", r"type ..\..\x.txt", f"more {me}/.ENV"):
            try: run_command(bad, "."); raise AssertionError(bad)
            except ValueError: pass
        assert run_command(rf"dir {ROOT}\{me}", ".").startswith("exit code 0")  # absolute paths inside ROOT ok
    finally:
        builtins.input = real_input
        tmp.unlink(missing_ok=True)

    msgs = [{"role": "system", "content": "s"}]
    for i in range(50):
        msgs += [{"role": "user", "content": f"q{i}"}, {"role": "assistant", "content": "x" * 3000}]
    trim(msgs)
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user" and msgs[-2]["content"] == "q49"
    assert len(json.dumps(msgs)) <= MAX_CHARS
    one_turn = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}] + \
               [{"role": "tool", "tool_call_id": str(i), "content": "y" * 5000} for i in range(5)]
    trim(one_turn)
    assert len(json.dumps(one_turn)) <= MAX_CHARS and one_turn[-1]["content"] == "y" * 5000  # newest result kept
    print("selftest ok")


if __name__ == "__main__":
    selftest() if "--test" in sys.argv else main()
