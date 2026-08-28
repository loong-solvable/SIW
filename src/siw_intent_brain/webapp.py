"""Tiny HTTP app for running the SIW Intent Brain pipeline online."""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .brain import IntentBrain
from .harvester import RedditHarvester
from .job_store import JobStore
from .report import compute_stats, render_report, select_top


APP_TITLE = "SIW Intent Brain"
MAX_TEXT_CHARS = 12000
MAX_HARVEST_LIMIT = 20
SESSION_COOKIE = "siw_session"
SESSION_ID_RE = re.compile(r"^[a-f0-9]{32}$")
JOB_ROUTE_RE = re.compile(
    r"^/api/jobs/(?P<job_id>job_[a-f0-9]{32})"
    r"(?:/artifacts/(?P<artifact>pdf|jsonl))?$"
)
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'self'"
)


def _data_dir() -> Path:
    path = Path(os.getenv("SIW_DATA_DIR", "data")).expanduser().resolve()
    (path / "reports").mkdir(parents=True, exist_ok=True)
    return path


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _safe_sort(value: Any) -> str:
    sort = str(value or "new").strip().lower()
    return sort if sort in {"new", "hot", "top"} else "new"


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False, default=_json_default))
            fh.write("\n")


def _job_store() -> JobStore:
    return JobStore(_data_dir() / "siw.sqlite3")


def _health_response(path: str) -> tuple[dict[str, Any], HTTPStatus] | None:
    if path == "/api/health":
        return (
            {"ok": True, "service": "siw-intent-brain"},
            HTTPStatus.OK,
        )
    if path == "/health/live":
        return (
            {"status": "ok", "service": "siw-intent-brain"},
            HTTPStatus.OK,
        )
    if path != "/health/ready":
        return None

    checks = {"job_store": "ok", "model_config": "ok"}
    try:
        _job_store().list_jobs("__health__", limit=1)
    except Exception:
        checks["job_store"] = "error"
    try:
        IntentBrain.from_env()
    except Exception:
        checks["model_config"] = "error"

    ready = all(value == "ok" for value in checks.values())
    return (
        {
            "status": "ok" if ready else "degraded",
            "service": "siw-intent-brain",
            "checks": checks,
        },
        HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
    )


def _public_job(job: dict[str, Any], *, include_result: bool = True) -> dict[str, Any]:
    public = dict(job)
    public.pop("owner_id", None)
    if not include_result:
        public.pop("result", None)
    public["artifact_urls"] = {
        kind: f"/api/jobs/{job['id']}/artifacts/{kind}"
        for kind in job.get("artifacts", {})
    }
    public.pop("artifacts", None)
    return public


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>SIW Intent Brain</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f5f1e8;
        --ink: #171a1f;
        --muted: #656b74;
        --line: #ded5c8;
        --panel: #fffdf8;
        --accent: #0f766e;
        --accent-2: #9a3412;
        --ok: #166534;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: var(--ink);
        background: var(--bg);
      }
      main { max-width: 1200px; margin: 0 auto; padding: 24px 18px 56px; }
      header { display: flex; justify-content: space-between; gap: 24px; align-items: end; margin-bottom: 16px; }
      h1 { font-size: clamp(30px, 5vw, 54px); line-height: 1; margin: 0; letter-spacing: 0; }
      h2 { font-size: 20px; margin: 0 0 10px; }
      h3 { font-size: 15px; margin: 0; }
      p { margin: 0; color: var(--muted); }
      .hero {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        margin-bottom: 16px;
      }
      .start {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: center;
        background: #fffdf8;
        border: 2px solid var(--ink);
        border-radius: 8px;
        padding: 14px;
      }
      .start strong { display: block; font-size: 18px; }
      .start button { flex: 0 0 auto; min-width: 132px; }
      .grid { display: grid; grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr); gap: 16px; }
      section {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 18px;
        box-shadow: 0 18px 40px rgba(23, 26, 31, 0.08);
      }
      label { display: block; font-size: 13px; font-weight: 800; color: var(--ink); margin: 14px 0 6px; }
      textarea, input, select {
        width: 100%;
        border: 1px solid var(--line);
        border-radius: 6px;
        background: white;
        color: var(--ink);
        padding: 10px 11px;
        font: inherit;
      }
      textarea { min-height: 170px; resize: vertical; }
      .row { display: grid; grid-template-columns: 1fr 1fr 110px; gap: 10px; }
      button {
        border: 0;
        border-radius: 6px;
        background: var(--accent);
        color: white;
        font-weight: 800;
        padding: 11px 14px;
        cursor: pointer;
      }
      button.secondary { background: var(--ink); }
      button.ghost { background: var(--accent-2); }
      button:disabled { opacity: 0.55; cursor: wait; }
      .result-output {
        min-height: 420px;
        max-height: 720px;
        overflow: auto;
        padding: 14px;
        border-radius: 6px;
        background: #111418;
        color: #e8f3ef;
      }
      .result-output h3 { font-size: 18px; margin: 0 0 12px; }
      .result-output p { color: #d4e3de; margin: 8px 0; }
      .result-output strong { color: white; }
      .result-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 8px;
        margin: 12px 0;
      }
      .result-metric {
        border: 1px solid #35433f;
        border-radius: 6px;
        padding: 10px;
        background: #18201e;
      }
      .result-metric small { display: block; color: #9fb4ad; }
      .result-metric b { display: block; margin-top: 3px; font-size: 18px; }
      .result-output ul { margin: 8px 0; padding-left: 20px; color: #d4e3de; }
      .result-output details { margin-top: 16px; border-top: 1px solid #35433f; padding-top: 12px; }
      .result-output summary { cursor: pointer; color: #9fb4ad; }
      .result-output pre {
        white-space: pre-wrap;
        word-break: break-word;
        margin: 10px 0 0;
        font-size: 12px;
      }
      .actions { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }
      .pill { display: inline-flex; border: 1px solid var(--line); border-radius: 999px; padding: 6px 10px; font-size: 12px; color: var(--muted); background: rgba(255,255,255,0.62); }
      .hint { color: var(--ok); font-weight: 800; margin-top: 8px; }
      .links a { color: var(--accent-2); font-weight: 800; margin-right: 14px; }
      .runtime-status { min-height: 1.5em; margin-top: 10px; font-weight: 700; color: var(--muted); }
      .history { display: grid; gap: 8px; margin-top: 12px; }
      .history-item {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 12px;
        align-items: center;
        border-top: 1px solid var(--line);
        padding: 12px 0 4px;
      }
      .history-item:first-child { border-top: 0; }
      .history-item small { display: block; color: var(--muted); margin-top: 3px; }
      .history-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: end; }
      .history-actions a, .history-actions button { font-size: 12px; padding: 7px 9px; }
      .empty { color: var(--muted); padding: 10px 0 2px; }
      button:focus-visible, a:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible {
        outline: 3px solid rgba(15, 118, 110, 0.35);
        outline-offset: 2px;
      }
      @media (max-width: 860px) {
        header, .grid, .hero { display: block; }
        .start { margin-top: 10px; }
        section { margin-top: 14px; }
        .row { grid-template-columns: 1fr; }
        .result-grid { grid-template-columns: 1fr 1fr; }
      }
    </style>
  </head>
  <body>
    <main>
      <header>
        <div>
          <span class="pill">Real SIW pipeline</span>
          <h1>SIW Intent Brain</h1>
        </div>
        <p>这里就是操作台：可以单条评分，也可以批量跑线索并生成 PDF 报告。</p>
      </header>
      <div class="hero">
        <div class="start">
          <div>
            <strong>入口 1：单条意图评分</strong>
            <p>把帖子、评论、客户原话粘进去，点右侧按钮。</p>
          </div>
          <button data-scroll="#scorePanel">去评分</button>
        </div>
        <div class="start">
          <div>
            <strong>入口 2：批量生成报告</strong>
            <p>输入线索或关键词，跑完整流水线，下载 PDF/JSONL。</p>
          </div>
          <button class="ghost" data-scroll="#pipelinePanel">去生成报告</button>
        </div>
      </div>
      <div class="grid">
        <div>
          <section id="scorePanel">
            <h2>入口 1：单条评分</h2>
            <p>用于判断一段文本是不是值得跟进的需求线索。结果会返回 tier、置信度、痛点、购买意图和建议动作。</p>
            <label for="text">在这里粘贴要分析的文本</label>
            <textarea id="text">ToolX is $59/mo and I need a cheaper way to monitor a few subreddits for mentions. Any alternatives?</textarea>
            <label for="context">可选：上下文 JSON</label>
            <input id="context" value='{"subreddit":"SaaS","title":"Cheaper alternative?"}' />
            <p class="hint">操作：填文本 -> 点“开始评分” -> 右侧看结果。</p>
            <div class="actions">
              <button id="scoreBtn">开始评分</button>
            </div>
          </section>
          <section id="pipelinePanel">
            <h2>入口 2：批量线索流水线</h2>
            <p>可以抓 Reddit，也可以直接使用下面的手动线索。系统会逐条评分，筛选高意图线索，并生成 PDF 报告。</p>
            <div class="row">
              <div>
                <label for="subreddit">Reddit 板块</label>
                <input id="subreddit" placeholder="例如 SaaS；留空则只处理手动线索" />
              </div>
              <div>
                <label for="query">搜索关键词</label>
                <input id="query" placeholder="可选；仅在填写 Reddit 板块时使用" />
              </div>
              <div>
                <label for="limit">抓取数量</label>
                <input id="limit" type="number" min="1" max="20" value="3" />
              </div>
            </div>
            <label for="sort">排序</label>
            <select id="sort">
              <option value="new">new</option>
              <option value="hot">hot</option>
              <option value="top">top</option>
            </select>
            <label for="manualItems">手动线索（一行一条，网络抓取不可用时也能跑）</label>
            <textarea id="manualItems" style="min-height: 110px">ToolX is too expensive for a small SaaS team. Looking for a cheaper Reddit monitoring alternative.
We need a lightweight way to find posts asking for CRM alternatives before competitors reply.</textarea>
            <p class="hint">操作：填线索/关键词 -> 点“运行流水线并生成报告” -> 下方下载 PDF。</p>
            <div class="actions">
              <button class="secondary" id="pipelineBtn">运行流水线并生成报告</button>
            </div>
            <p class="links" id="links"></p>
            <p class="runtime-status" id="runtimeStatus" role="status" aria-live="polite">等待开始。</p>
          </section>
        </div>
        <section>
          <h2>运行结果</h2>
          <div class="result-output" id="output">
            <p>准备好了。左侧选择入口，然后点按钮运行。</p>
          </div>
        </section>
      </div>
      <section id="historyPanel" style="margin-top: 16px">
        <h2>最近任务</h2>
        <p>任务只对当前浏览器会话可见。刷新页面后仍可找回结果与报告。</p>
        <div class="history" id="historyList" aria-live="polite"></div>
      </section>
    </main>
    <script>
      const out = document.getElementById("output");
      const links = document.getElementById("links");
      const runtimeStatus = document.getElementById("runtimeStatus");
      const historyList = document.getElementById("historyList");
      const appendText = (tag, text, className = "") => {
        const node = document.createElement(tag);
        node.textContent = text;
        if (className) node.className = className;
        out.appendChild(node);
        return node;
      };
      const appendMetrics = (metrics) => {
        const grid = document.createElement("div");
        grid.className = "result-grid";
        metrics.forEach(([label, value]) => {
          const item = document.createElement("div");
          item.className = "result-metric";
          const caption = document.createElement("small");
          caption.textContent = label;
          const number = document.createElement("b");
          number.textContent = String(value);
          item.append(caption, number);
          grid.appendChild(item);
        });
        out.appendChild(grid);
      };
      const appendList = (title, values) => {
        if (!Array.isArray(values) || values.length === 0) return;
        const heading = document.createElement("p");
        const headingText = document.createElement("strong");
        headingText.textContent = title;
        heading.appendChild(headingText);
        out.appendChild(heading);
        const list = document.createElement("ul");
        values.forEach((value) => {
          const item = document.createElement("li");
          item.textContent = String(value);
          list.appendChild(item);
        });
        out.appendChild(list);
      };
      const appendRaw = (value) => {
        const details = document.createElement("details");
        const summary = document.createElement("summary");
        summary.textContent = "查看原始 JSON";
        const raw = document.createElement("pre");
        raw.textContent = JSON.stringify(value, null, 2);
        details.append(summary, raw);
        out.appendChild(details);
      };
      const write = (value) => {
        out.replaceChildren();
        if (typeof value === "string") {
          appendText("p", value);
          return;
        }
        const card = value?.card || value?.result?.card || value?.job?.result?.card;
        const stats = value?.stats || value?.result?.stats || value?.job?.result?.stats;
        if (card) {
          appendText("h3", `意图等级 ${card.lead_tier || "-"}`);
          appendMetrics([
            ["置信度", card.confidence ?? "-"],
            ["紧迫度", card.scores?.urgency ?? "-"],
            ["购买相关度", card.scores?.commercial_relevance ?? "-"],
          ]);
          if (card.extracted_signals?.problem_summary) {
            const line = appendText("p", "");
            const label = document.createElement("strong");
            label.textContent = "需求：";
            line.append(label, document.createTextNode(card.extracted_signals.problem_summary));
          }
          if (card.rationale) {
            const line = appendText("p", "");
            const label = document.createElement("strong");
            label.textContent = "判断依据：";
            line.append(label, document.createTextNode(card.rationale));
          }
          if (card.recommended_next_step) {
            const line = appendText("p", "");
            const label = document.createElement("strong");
            label.textContent = "建议动作：";
            line.append(label, document.createTextNode(card.recommended_next_step));
          }
          appendList("限制条件", card.extracted_signals?.constraints);
          appendList("预算线索", card.extracted_signals?.budget_hints);
        } else if (stats) {
          appendText("h3", "批量分析完成");
          appendMetrics([
            ["总线索", stats.total ?? value?.count ?? "-"],
            ["有效结果", stats.valid ?? "-"],
            ["S / A 级", `${stats.tier_counts?.S ?? 0} / ${stats.tier_counts?.A ?? 0}`],
          ]);
          const source = value?.source || value?.result?.source || value?.job?.result?.source;
          if (source?.error) {
            appendText("p", `网络抓取未完成：${source.error}；手动线索已正常处理。`);
          }
        } else {
          appendText("p", "任务已完成，详细数据见下方原始 JSON。");
        }
        appendRaw(value);
      };
      const setStatus = (value) => { runtimeStatus.textContent = value; };
      document.querySelectorAll("[data-scroll]").forEach((button) => {
        button.onclick = () => document.querySelector(button.dataset.scroll).scrollIntoView({ behavior: "smooth", block: "start" });
      });
      const request = async (url, payload = null, method = "POST") => {
        const options = { method, headers: {} };
        if (payload !== null) {
          options.headers["content-type"] = "application/json";
          options.body = JSON.stringify(payload);
        }
        const res = await fetch(url, options);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || `Request failed: ${res.status}`);
        return data;
      };
      const loadHistory = async () => {
        const data = await request("/api/jobs", null, "GET");
        historyList.textContent = "";
        if (!data.jobs.length) {
          const empty = document.createElement("p");
          empty.className = "empty";
          empty.textContent = "还没有任务。先完成一次评分或报告生成。";
          historyList.appendChild(empty);
          return;
        }
        data.jobs.forEach((job) => {
          const row = document.createElement("article");
          row.className = "history-item";
          const copy = document.createElement("div");
          const title = document.createElement("strong");
          title.textContent = `${job.kind === "score" ? "单条评分" : "批量报告"} · ${job.status}`;
          const summary = document.createElement("small");
          summary.textContent = `${job.input_summary} · ${new Date(job.created_at).toLocaleString()}`;
          copy.append(title, summary);
          const actions = document.createElement("div");
          actions.className = "history-actions";
          const detail = document.createElement("button");
          detail.className = "secondary";
          detail.textContent = "查看结果";
          detail.onclick = async () => {
            try {
              write((await request(`/api/jobs/${job.id}`, null, "GET")).job);
              setStatus("已打开历史任务。 ");
            } catch (err) {
              setStatus(String(err.message || err));
            }
          };
          actions.appendChild(detail);
          Object.entries(job.artifact_urls || {}).forEach(([kind, url]) => {
            const link = document.createElement("a");
            link.href = url;
            link.textContent = kind === "pdf" ? "PDF" : "JSONL";
            link.target = "_blank";
            link.rel = "noopener";
            actions.appendChild(link);
          });
          row.append(copy, actions);
          historyList.appendChild(row);
        });
      };
      document.getElementById("scoreBtn").onclick = async (event) => {
        event.target.disabled = true;
          links.replaceChildren();
        try {
          const contextText = document.getElementById("context").value.trim();
          const context = contextText ? JSON.parse(contextText) : {};
          write("正在评分...");
          setStatus("正在评分，请稍候。");
          write(await request("/api/score", { text: document.getElementById("text").value, context }));
          setStatus("评分完成，已保存到最近任务。");
          await loadHistory();
        } catch (err) {
          write(String(err.message || err));
          setStatus(String(err.message || err));
        } finally {
          event.target.disabled = false;
        }
      };
      document.getElementById("pipelineBtn").onclick = async (event) => {
        event.target.disabled = true;
        links.replaceChildren();
        try {
          write("正在运行：抓取/读取线索 -> 意图评分 -> 生成 PDF 报告...");
          setStatus("流水线运行中。页面会在报告准备好后显示下载入口。");
          const data = await request("/api/pipeline", {
            subreddit: document.getElementById("subreddit").value,
            query: document.getElementById("query").value,
            limit: Number(document.getElementById("limit").value || 3),
            sort: document.getElementById("sort").value,
            top: 10,
            manual_items: document.getElementById("manualItems").value.split(/\\n+/).map(text => text.trim()).filter(Boolean)
          });
          [
            [data.report_url, "下载 PDF 报告"],
            [data.jsonl_url, "下载 JSONL 数据"],
          ].forEach(([url, label]) => {
            if (typeof url !== "string" || !url.startsWith("/api/jobs/")) return;
            const link = document.createElement("a");
            link.href = url;
            link.target = "_blank";
            link.rel = "noopener";
            link.textContent = label;
            links.appendChild(link);
          });
          write(data);
          setStatus("报告已生成，任务与下载入口已保存。");
          await loadHistory();
        } catch (err) {
          write(String(err.message || err));
          setStatus(String(err.message || err));
        } finally {
          event.target.disabled = false;
        }
      };
      loadHistory().catch((err) => {
        historyList.textContent = "暂时无法读取任务历史。";
        setStatus(String(err.message || err));
      });
    </script>
  </body>
</html>
"""


class SIWHandler(BaseHTTPRequestHandler):
    server_version = "SIWIntentBrain/0.1"

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._session_id()
            self._send_headers(len(INDEX_HTML.encode("utf-8")), "text/html; charset=utf-8")
            return
        health = _health_response(parsed.path)
        if health is not None:
            payload, status = health
            data = json.dumps(payload).encode("utf-8")
            self._send_headers(
                len(data),
                "application/json; charset=utf-8",
                status,
            )
            return
        match = JOB_ROUTE_RE.match(parsed.path)
        if match and match.group("artifact"):
            self._serve_job_artifact(
                match.group("job_id"),
                match.group("artifact"),
                head_only=True,
            )
            return
        self._send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._session_id()
            self._send_bytes(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        health = _health_response(parsed.path)
        if health is not None:
            payload, status = health
            self._send_json(payload, status)
            return
        if parsed.path == "/api/jobs":
            jobs = _job_store().list_jobs(self._session_id(), limit=50)
            self._send_json({
                "ok": True,
                "jobs": [_public_job(job, include_result=False) for job in jobs],
            })
            return
        match = JOB_ROUTE_RE.match(parsed.path)
        if match:
            if match.group("artifact"):
                self._serve_job_artifact(
                    match.group("job_id"),
                    match.group("artifact"),
                )
                return
            job = _job_store().get_job(match.group("job_id"), self._session_id())
            if job is None:
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            self._send_json({"ok": True, "job": _public_job(job)})
            return
        self._send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not self._is_trusted_browser_origin():
            self._send_error(HTTPStatus.FORBIDDEN, "请求来源不受信任")
            return
        try:
            payload = self._read_json_body()
            if parsed.path == "/api/score":
                self._handle_score(payload)
                return
            if parsed.path == "/api/pipeline":
                self._handle_pipeline(payload)
                return
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
        except ValueError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            print(f"request failed path={parsed.path} error={type(exc).__name__}")
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "服务暂时不可用，请稍后重试",
            )

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _is_trusted_browser_origin(self) -> bool:
        """Reject cross-site browser writes while keeping CLI requests usable."""
        origin = self.headers.get("origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        request_host = (self.headers.get("host") or "").lower()
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.netloc)
            and parsed.netloc.lower() == request_host
        )

    def _session_id(self) -> str:
        cached = getattr(self, "_cached_session_id", None)
        if cached:
            return cached

        session_id = ""
        cookie_header = self.headers.get("cookie", "")
        if cookie_header:
            try:
                cookies = SimpleCookie()
                cookies.load(cookie_header)
                morsel = cookies.get(SESSION_COOKIE)
                if morsel and SESSION_ID_RE.match(morsel.value):
                    session_id = morsel.value
            except ValueError:
                session_id = ""

        if not session_id:
            session_id = uuid.uuid4().hex
            self._set_session_cookie = True

        self._cached_session_id = session_id
        return session_id

    def _serve_job_artifact(
        self,
        job_id: str,
        artifact: str,
        *,
        head_only: bool = False,
    ) -> None:
        job = _job_store().get_job(job_id, self._session_id())
        if job is None:
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        relative_path = job.get("artifacts", {}).get(artifact)
        if not isinstance(relative_path, str):
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        data_dir = _data_dir()
        artifact_path = (data_dir / relative_path).resolve()
        try:
            artifact_path.relative_to(data_dir)
        except ValueError:
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        if not artifact_path.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_type = (
            "application/pdf"
            if artifact == "pdf"
            else "application/x-ndjson; charset=utf-8"
        )
        extra_headers = {
            "content-disposition": f'attachment; filename="{job_id}.{artifact}"',
            "cache-control": "private, no-store",
        }
        if head_only:
            self._send_headers(
                artifact_path.stat().st_size,
                content_type,
                extra_headers=extra_headers,
            )
            return
        self._send_bytes(
            artifact_path.read_bytes(),
            content_type,
            extra_headers=extra_headers,
        )

    def _read_json_body(self) -> dict[str, Any]:
        length = _safe_int(self.headers.get("content-length"), 0, 0, 1_000_000)
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _handle_score(self, payload: dict[str, Any]) -> None:
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("text is required")
        if len(text) > MAX_TEXT_CHARS:
            raise ValueError(f"text is too long; max {MAX_TEXT_CHARS} characters")
        context = payload.get("context") or {}
        if not isinstance(context, dict):
            raise ValueError("context must be an object")
        store = _job_store()
        job = store.create_job(
            self._session_id(),
            "score",
            text.replace("\n", " ")[:160],
        )
        store.mark_running(job["id"])
        try:
            card = IntentBrain.from_env().score(text, context)
            if card.get("ok") is False:
                meta = card.get("meta") if isinstance(card.get("meta"), dict) else {}
                failed = store.mark_failed(
                    job["id"],
                    error_code=str(meta.get("error_code") or "E_SCORE_FAILED"),
                    error_message="评分失败，请检查输入或稍后重试",
                )
                self._send_json(
                    {"ok": False, "job": _public_job(failed), "card": card},
                    HTTPStatus.BAD_GATEWAY,
                )
                return
            completed = store.mark_succeeded(job["id"], result={"card": card})
            self._send_json({"ok": True, "job": _public_job(completed), "card": card})
        except Exception:
            failed = store.mark_failed(
                job["id"],
                error_code="E_SCORE_FAILED",
                error_message="评分服务暂时不可用，请稍后重试",
            )
            self._send_json(
                {"ok": False, "job": _public_job(failed), "error": failed["error_message"]},
                HTTPStatus.BAD_GATEWAY,
            )

    def _handle_pipeline(self, payload: dict[str, Any]) -> None:
        subreddit = str(payload.get("subreddit") or "").strip().strip("/")
        subreddit = re.sub(r"^r/", "", subreddit, flags=re.IGNORECASE)
        has_manual_input = bool(payload.get("manual_items") or payload.get("texts"))
        if not subreddit and not has_manual_input:
            raise ValueError("subreddit or manual_items is required")
        if subreddit and not re.match(r"^[A-Za-z0-9_]{2,32}$", subreddit):
            raise ValueError("subreddit must be 2-32 letters, numbers, or underscores")
        source_name = subreddit or "manual"

        query = str(payload.get("query") or "").strip() or None
        limit = _safe_int(payload.get("limit"), 5, 1, MAX_HARVEST_LIMIT)
        sort = _safe_sort(payload.get("sort"))
        top = _safe_int(payload.get("top"), 10, 1, MAX_HARVEST_LIMIT)

        store = _job_store()
        job = store.create_job(
            self._session_id(),
            "pipeline",
            f"{source_name}: {query or 'no query'}; limit={limit}",
        )
        store.mark_running(job["id"])

        try:
            harvest_items: list[dict[str, Any]] = []
            harvest_skipped = 0
            harvest_error: str | None = None
            if subreddit:
                harvest = RedditHarvester().fetch_posts(
                    subreddit,
                    query=query,
                    limit=limit,
                    sort=sort,
                )
                harvest_items = harvest.items
                harvest_skipped = harvest.skipped_count
                harvest_error = harvest.error_message

            manual_items = self._manual_items(payload, source_name)
            brain = IntentBrain.from_env()
            items: list[dict[str, Any]] = []
            records: list[dict[str, Any]] = []

            for source in [*harvest_items, *manual_items]:
                card = brain.score(text=source["text"], context=source["context"])
                records.append(card)
                items.append({
                    "card": card,
                    "source_meta": source.get("_meta", {}),
                    "source_context": source.get("context", {}),
                })

            report_dir = _data_dir() / "reports"
            jsonl_path = report_dir / f"{job['id']}.jsonl"
            pdf_path = report_dir / f"{job['id']}.pdf"
            _write_jsonl(jsonl_path, items)

            stats = compute_stats(records, [])
            top_cards = select_top(records, top)
            render_report(
                records=top_cards,
                stats=stats,
                invalid_lines=[],
                out_path=str(pdf_path),
                input_filename=jsonl_path.name,
            )

            source_result = {
                "subreddit": subreddit,
                "query": query,
                "limit": limit,
                "sort": sort,
                "skipped": harvest_skipped,
                "error": harvest_error,
                "manual_items": len(manual_items),
            }
            result_summary = {
                "source": source_result,
                "count": len(items),
                "stats": stats,
            }
            completed = store.mark_succeeded(
                job["id"],
                result=result_summary,
                artifacts={
                    "pdf": f"reports/{job['id']}.pdf",
                    "jsonl": f"reports/{job['id']}.jsonl",
                },
            )

            self._send_json({
                "ok": True,
                "run_id": job["id"],
                "job": _public_job(completed),
                "source": source_result,
                "count": len(items),
                "stats": stats,
                "items": items,
                "report_url": f"/api/jobs/{job['id']}/artifacts/pdf",
                "jsonl_url": f"/api/jobs/{job['id']}/artifacts/jsonl",
            })
        except Exception as exc:
            print(f"pipeline failed job={job['id']} error={type(exc).__name__}")
            failed = store.mark_failed(
                job["id"],
                error_code="E_PIPELINE_FAILED",
                error_message="流水线运行失败，请稍后重试",
            )
            self._send_json(
                {"ok": False, "job": _public_job(failed), "error": failed["error_message"]},
                HTTPStatus.BAD_GATEWAY,
            )

    def _manual_items(self, payload: dict[str, Any], subreddit: str) -> list[dict[str, Any]]:
        raw_items = payload.get("manual_items") or payload.get("texts") or []
        if isinstance(raw_items, str):
            candidates = [line.strip() for line in raw_items.splitlines()]
        elif isinstance(raw_items, list):
            candidates = []
            for item in raw_items:
                if isinstance(item, str):
                    candidates.append(item.strip())
                elif isinstance(item, dict):
                    text = str(item.get("text") or "").strip()
                    title = str(item.get("title") or "Manual input").strip()
                    if text:
                        candidates.append(json.dumps({"text": text, "title": title}, ensure_ascii=False))
        else:
            candidates = []

        items: list[dict[str, Any]] = []
        for idx, candidate in enumerate(candidates[:MAX_HARVEST_LIMIT], start=1):
            if not candidate:
                continue
            title = f"Manual input {idx}"
            text = candidate
            if candidate.startswith("{"):
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict):
                        text = str(obj.get("text") or "").strip()
                        title = str(obj.get("title") or title).strip() or title
                except json.JSONDecodeError:
                    pass
            if not text:
                continue
            items.append({
                "text": text[:MAX_TEXT_CHARS],
                "context": {
                    "subreddit": subreddit,
                    "title": title,
                    "author": "manual",
                    "permalink": "",
                },
                "_meta": {
                    "id": f"manual-{idx}",
                    "score": 0,
                    "num_comments": 0,
                    "url": "",
                },
            })
        return items

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
        self._send_bytes(data, "application/json; charset=utf-8", status)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"ok": False, "error": message}, status)

    def _send_bytes(
        self,
        data: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._send_headers(
            len(data),
            content_type,
            status,
            extra_headers=extra_headers,
        )
        self.wfile.write(data)

    def _send_headers(
        self,
        length: int,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        headers = {key.lower(): value for key, value in (extra_headers or {}).items()}
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(length))
        self.send_header("content-security-policy", CONTENT_SECURITY_POLICY)
        self.send_header("x-content-type-options", "nosniff")
        self.send_header("x-frame-options", "DENY")
        self.send_header("referrer-policy", "same-origin")
        self.send_header("permissions-policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "cache-control",
            headers.pop(
                "cache-control",
                "no-store" if content_type.startswith("application/json") else "public, max-age=60",
            ),
        )
        if getattr(self, "_set_session_cookie", False):
            cookie_secure = os.getenv(
                "SIW_SESSION_COOKIE_SECURE",
                os.getenv("SIW_COOKIE_SECURE", "true"),
            )
            secure = "; Secure" if cookie_secure.lower() != "false" else ""
            self.send_header(
                "set-cookie",
                f"{SESSION_COOKIE}={self._cached_session_id}; Path=/; Max-Age=31536000; "
                f"HttpOnly; SameSite=Lax{secure}",
            )
            self._set_session_cookie = False
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the SIW Intent Brain web app")
    parser.add_argument("--host", default=os.getenv("SIW_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("SIW_PORT", "8080")))
    args = parser.parse_args(argv)

    recovered = _job_store().recover_interrupted_jobs()
    if recovered:
        print(f"recovered interrupted jobs count={recovered}")
    server = ThreadingHTTPServer((args.host, args.port), SIWHandler)
    print(f"{APP_TITLE} listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
