"""Live Hermes agent Space: Britannica (1771-1797) vs Wikipedia.

Two parts in one process:
- A model proxy on 127.0.0.1:7861 (not exposed). Hermes talks to it with a random internal token.
  The proxy adds the Token Factory key (Space secret SUPER_API_KEY), caps max_tokens per call,
  counts usage tokens against the daily budget, and refuses calls when the budget is spent.
- A Gradio UI on 0.0.0.0:7860. Each question runs `hermes chat` once, with the team plugin and skill.

Caps (server side): 3 questions per browser session, MAX_TOKENS per model call, MAX_TOOL_CALLS per
question, DAILY_TOKENS per UTC day (counter in /tmp, reset on restart), CONCURRENCY running questions.
Keys are never printed, logged, or passed to Hermes.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
import time
from typing import Any

import gradio as gr
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

UPSTREAM = os.environ.get("SUPER_BASE_URL", "https://api.tokenfactory.nebius.com/v1").rstrip("/")
MODEL = "nvidia/Nemotron-3.5-Super-VL"
MAX_TOKENS = int(os.environ.get("CAP_MAX_TOKENS", "4000"))
MAX_TOOL_CALLS = int(os.environ.get("CAP_MAX_TOOL_CALLS", "12"))
MAX_QUESTIONS = int(os.environ.get("CAP_QUESTIONS_PER_SESSION", "3"))
DAILY_TOKENS = int(os.environ.get("CAP_DAILY_TOKENS", "5000000"))
CONCURRENCY = int(os.environ.get("CAP_CONCURRENCY", "2"))
QUESTION_TIMEOUT = int(os.environ.get("CAP_QUESTION_SECONDS", "300"))
BUDGET_FILE = Path("/tmp/agent_budget.json")
INTERNAL_KEY = secrets.token_urlsafe(32)  # Hermes uses this; it is not the Token Factory key
PROXY_PORT = 7861
APP_DIR = Path(__file__).resolve().parents[1]
HERMES_HOME = os.environ.get("HERMES_HOME", str(Path.home() / "hermes"))
ARCHIVE = "https://huggingface.co/spaces/nebius-build-week/britannica-across-time"
DATASET = "https://huggingface.co/datasets/nebius-build-week/britannica-wikipedia-drift"
GITHUB = "https://github.com/M-Ali-ML/Nebius-Hackathon"
BUDGET_MSG = f"Daily demo budget reached. See the saved runs in the archive Space: {ARCHIVE}"

# ---------- budget ----------

_lock = threading.Lock()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def budget() -> dict[str, Any]:
    with _lock:
        try:
            data = json.loads(BUDGET_FILE.read_text())
        except (OSError, ValueError):
            data = {}
        if data.get("date") != _today():
            data = {"date": _today(), "tokens": 0, "calls": 0, "questions": 0}
        return data


def add_usage(tokens: int = 0, calls: int = 0, questions: int = 0) -> None:
    data = budget()
    with _lock:
        data["tokens"] += int(tokens)
        data["calls"] += calls
        data["questions"] += questions
        BUDGET_FILE.write_text(json.dumps(data))


def budget_left() -> int:
    return DAILY_TOKENS - budget()["tokens"]


# ---------- model proxy (127.0.0.1 only) ----------

proxy = FastAPI()


def _authorized(request: Request) -> bool:
    return (request.client is not None and request.client.host in {"127.0.0.1", "::1"}
            and request.headers.get("authorization") == f"Bearer {INTERNAL_KEY}")


def _upstream_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ.get('SUPER_API_KEY', '')}", "Content-Type": "application/json"}


@proxy.get("/v1/models")
async def models(request: Request):
    if not _authorized(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{UPSTREAM}/models", headers=_upstream_headers())
    return JSONResponse(r.json(), status_code=r.status_code)


@proxy.post("/v1/chat/completions")
async def chat(request: Request):
    if not _authorized(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    if budget_left() <= 0:
        return JSONResponse({"error": {"message": BUDGET_MSG, "type": "budget"}}, status_code=429)
    body = await request.json()
    body["model"] = MODEL
    body["max_tokens"] = min(int(body.get("max_tokens") or MAX_TOKENS), MAX_TOKENS)
    if "max_completion_tokens" in body:
        body["max_completion_tokens"] = min(int(body["max_completion_tokens"] or MAX_TOKENS), MAX_TOKENS)
    if body.get("stream"):
        body["stream_options"] = {**(body.get("stream_options") or {}), "include_usage": True}

        async def relay():
            usage = 0
            async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=15)) as client:
                async with client.stream("POST", f"{UPSTREAM}/chat/completions", json=body,
                                         headers=_upstream_headers()) as r:
                    async for line in r.aiter_lines():
                        if line.startswith("data:") and '"usage"' in line:
                            try:
                                u = json.loads(line[5:]).get("usage") or {}
                                usage = max(usage, int(u.get("total_tokens") or 0))
                            except ValueError:
                                pass
                        yield line + "\n"
            add_usage(tokens=usage, calls=1)

        return StreamingResponse(relay(), media_type="text/event-stream")
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=15)) as client:
        r = await client.post(f"{UPSTREAM}/chat/completions", json=body, headers=_upstream_headers())
    data = r.json()
    add_usage(tokens=(data.get("usage") or {}).get("total_tokens") or 0, calls=1)
    return JSONResponse(data, status_code=r.status_code)


def start_proxy() -> None:
    config = uvicorn.Config(proxy, host="127.0.0.1", port=PROXY_PORT, log_level="warning", access_log=False)
    threading.Thread(target=uvicorn.Server(config).run, daemon=True).start()


# ---------- agent run ----------

def _child_env(tool_log: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in {"SUPER_API_KEY", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}}
    env.update({"HERMES_HOME": HERMES_HOME, "INTERNAL_PROXY_KEY": INTERNAL_KEY, "NEMOTRON_TOOL_LOG": tool_log,
                "NEMOTRON_REPO": str(APP_DIR), "NEMOTRON_MAIN": str(APP_DIR),
                "NEMOTRON_ARTIFACTS": str(APP_DIR / "artifacts"), "NEMOTRON_RETRIEVAL_MODE": "bm25_only",
                "NEMOTRON_SCAN_CACHE": "/tmp/scan_cache"})
    return env


def _short(value: Any, n: int = 400) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= n else text[:n] + " ..."


def _trace_md(calls: list[dict[str, Any]], note: str = "") -> str:
    lines = [f"**Tool calls: {len(calls)} / {MAX_TOOL_CALLS}**{note}"]
    for i, c in enumerate(calls, 1):
        lines.append(f"{i}. `{c['name']}` `{_short(c['input'], 200)}`")
        if c.get("output") is not None:
            lines.append(f"   - result: {_short(c['output'])}".replace("\n", " "))
    return "\n".join(lines)


def _images(tool_log: Path) -> list[tuple[str, str]]:
    out = []
    if not tool_log.exists():
        return out
    for line in tool_log.read_text().splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        res = rec.get("result") or {}
        if rec.get("tool") == "view_scan" and res.get("image_path"):
            out.append((res["image_path"], f"view_scan row {res.get('row_index')} bbox {res.get('bbox')}"))
        if rec.get("tool") == "view_neighbors":
            for n in res.get("neighbors", []):
                out.append((n["image_path"], f"view_neighbors {n['cite']} {n.get('running_head', '')}"))
    return out


def _status() -> str:
    b = budget()
    return (f"Budget today (UTC {b['date']}): {b['tokens']:,} / {DAILY_TOKENS:,} tokens used, "
            f"{b['questions']} questions. Counter resets when the Space restarts.")


def ask(question: str, history: list[dict[str, str]], asked: int):
    question = (question or "").strip()[:1000]
    if not question:
        yield history, asked, gr.update(), gr.update(), _status()
        return
    history = history + [{"role": "user", "content": question}]
    if asked >= MAX_QUESTIONS:
        history.append({"role": "assistant", "content": f"This demo allows {MAX_QUESTIONS} questions per session. "
                        f"See the saved runs in the archive Space: {ARCHIVE}"})
        yield history, asked, gr.update(), gr.update(), _status()
        return
    if budget_left() <= 0:
        history.append({"role": "assistant", "content": BUDGET_MSG})
        yield history, asked, gr.update(), gr.update(), _status()
        return
    asked += 1
    add_usage(questions=1)
    tool_log = Path(tempfile.mkstemp(prefix="tool-log-", suffix=".jsonl")[1])
    cmd = ["hermes", "chat", "-q", question, "--format", "stream-json", "-t", "nemotron_challenge",
           "-s", "britannica-compare", "--max-turns", str(MAX_TOOL_CALLS + 2)]
    history.append({"role": "assistant", "content": "Working: the agent is calling its tools ..."})
    yield history, asked, "", [], _status()
    calls: list[dict[str, Any]] = []
    final, error, note = "", "", ""
    proc = subprocess.Popen(cmd, env=_child_env(str(tool_log)), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.DEVNULL, text=True, cwd=str(APP_DIR))
    started = time.time()
    watchdog = threading.Timer(QUESTION_TIMEOUT, proc.kill)  # a silent process cannot hang the queue
    watchdog.start()
    try:
        for line in proc.stdout:
            if time.time() - started > QUESTION_TIMEOUT:
                note = f" (stopped: over {QUESTION_TIMEOUT} s)"
                proc.kill()
                break
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            kind = ev.get("type")
            if kind == "tool_use" and ev.get("name") not in {"tool_describe", "tool_search", "tool_call"}:
                calls.append({"name": ev.get("name"), "input": ev.get("input"), "output": None})
                if len(calls) > MAX_TOOL_CALLS:
                    note = f" (stopped: more than {MAX_TOOL_CALLS} tool calls)"
                    proc.kill()
                    break
                yield history, asked, _trace_md(calls), _images(tool_log), _status()
            elif kind == "tool_result":
                for c in reversed(calls):
                    if c["name"] == ev.get("name") and c["output"] is None:
                        c["output"] = ev.get("output")
                        break
            elif kind == "result":
                final = ev.get("text") or ""
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
    finally:
        watchdog.cancel()
    if not final and time.time() - started >= QUESTION_TIMEOUT:
        note = note or f" (stopped: over {QUESTION_TIMEOUT} s)"
    if not final:
        error = (proc.stderr.read() if proc.stderr else "")[-300:]
        final = ("The agent did not finish" + (note or "") + ". No answer is shown rather than a guess."
                 + ("\n\nDetail: " + error if error and "Bearer" not in error else ""))
    history[-1] = {"role": "assistant", "content": final}
    yield history, asked, _trace_md(calls, note), _images(tool_log), _status()


# ---------- UI ----------

EXAMPLES = [
    "What did the Britannica say about lightning, and how does Wikipedia explain it today? Did the language or the knowledge change?",
    "What does plate B:2077 show, and where in the Britannica is it explained?",
    "Which old terms in the Britannica have different modern names in Wikipedia? Give three examples with quotes from both sides.",
]

HEADER = f"""
# Britannica agent (live)

Ask a question about the **Encyclopaedia Britannica, 1st edition (1771-1797)**, compared with current **Wikipedia**.
The agent is **Hermes Agent v0.22.2** running **{MODEL}** (Nebius Token Factory), with our plugin
(`search_sources`, `get_pair`, `find_drift`, `view_scan`, `view_neighbors`) and the `britannica-compare` skill.
Every claim is cited: `[B:row:n]` Britannica entry, `[R:row]` neighbor scan, `[W:page_id:revision_id]` Wikipedia.

**This Space runs without the Embed/Rerank GPU.** Search here is keyword BM25: Britannica over our 262 bundled entries,
Wikipedia over the live BM25 API (7.18M articles). The full pipeline used Nemotron Embed VL and Rerank VL to match entries;
those matches and comparisons are bundled and read by `get_pair` and `find_drift`.

Archive with all saved runs: [britannica-across-time]({ARCHIVE}) · Dataset: [britannica-wikipedia-drift]({DATASET}) · Code: [GitHub]({GITHUB})

Limits: {MAX_QUESTIONS} questions per session, {MAX_TOOL_CALLS} tool calls per question, {MAX_TOKENS:,} output tokens per
model call, {DAILY_TOKENS:,} tokens per day for everyone. A question takes 20 to 90 seconds.
"""


def build() -> gr.Blocks:
    with gr.Blocks(title="Britannica agent") as demo:
        gr.Markdown(HEADER)
        asked = gr.State(0)
        chat_box = gr.Chatbot(type="messages", height=480, label="Answer")
        question = gr.Textbox(label="Question", placeholder="Ask about an 18th-century Britannica topic", lines=2)
        send = gr.Button("Ask", variant="primary")
        gr.Examples(EXAMPLES, inputs=question)
        status = gr.Markdown(_status())
        with gr.Row():
            trace = gr.Markdown("Tool calls appear here.", label="Tool-call trace")
            gallery = gr.Gallery(label="Scans the agent looked at", height=420, columns=2)
        outs = [chat_box, asked, trace, gallery, status]
        send.click(ask, [question, chat_box, asked], outs, concurrency_limit=CONCURRENCY, concurrency_id="agent")
        question.submit(ask, [question, chat_box, asked], outs, concurrency_limit=CONCURRENCY, concurrency_id="agent")
    return demo


if __name__ == "__main__":
    for var in ("NO_PROXY", "no_proxy"):  # local calls (UI check, model proxy) must not go through an HTTP proxy
        os.environ[var] = ",".join(filter(None, [os.environ.get(var, ""), "127.0.0.1", "localhost"]))
    start_proxy()
    build().queue(default_concurrency_limit=CONCURRENCY).launch(
        server_name="0.0.0.0", server_port=7860, show_error=False, allowed_paths=[str(APP_DIR), "/tmp"])
