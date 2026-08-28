"""HTTP product-shell tests: session ownership, history, and artifacts."""

from __future__ import annotations

import http.client
import json
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from siw_intent_brain import webapp
from siw_intent_brain.job_store import JobStore


class FakeIntentBrain:
    @classmethod
    def from_env(cls):
        return cls()

    def score(self, text, context):
        return {
            "ok": True,
            "scores": {
                "urgency": 0.5,
                "pain_point_intensity": 0.7,
                "commercial_relevance": 0.8,
                "solution_seeking": 0.9,
            },
            "confidence": 0.85,
            "lead_tier": "A",
            "recommended_next_step": "draft_reply",
            "rationale": "The user is actively comparing paid options.",
            "extracted_signals": {
                "problem_summary": text[:80],
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
            "meta": {
                "model": "test-model",
                "provider": "openai_compatible",
                "latency_ms": 1,
                "retries": 0,
                "parser_mode": "strict",
                "schema_version": "lead_card.v1",
            },
        }


def test_workspace_html_exposes_history_and_accessible_runtime_status() -> None:
    assert 'id="historyList"' in webapp.INDEX_HTML
    assert 'id="runtimeStatus"' in webapp.INDEX_HTML
    assert 'aria-live="polite"' in webapp.INDEX_HTML
    assert 'request("/api/jobs"' in webapp.INDEX_HTML
    assert 'class="result-output" id="output"' in webapp.INDEX_HTML
    assert "查看原始 JSON" in webapp.INDEX_HTML
    assert 'placeholder="例如 SaaS；留空则只处理手动线索"' in webapp.INDEX_HTML
    assert 'id="subreddit" value="SaaS"' not in webapp.INDEX_HTML
    assert "links.innerHTML" not in webapp.INDEX_HTML
    assert "window.alert" not in webapp.INDEX_HTML


def test_browser_security_headers_and_cross_origin_posts_are_blocked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    with running_server(tmp_path, monkeypatch) as address:
        status, headers, _ = request(address, "GET", "/")
        assert status == 200
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert "default-src 'self'" in headers["content-security-policy"]

        connection = http.client.HTTPConnection(*address, timeout=3)
        connection.request(
            "POST",
            "/api/score",
            body=json.dumps({"text": "billable request"}),
            headers={
                "content-type": "application/json",
                "origin": "https://attacker.example",
            },
        )
        response = connection.getresponse()
        body = response.read()
        connection.close()

        assert response.status == 403
        assert b"billable request" not in body


def test_live_and_ready_health_endpoints_are_distinct(
    tmp_path: Path,
    monkeypatch,
) -> None:
    with running_server(tmp_path, monkeypatch) as address:
        live_status, _, live_body = request(address, "GET", "/health/live")
        ready_status, _, ready_body = request(address, "GET", "/health/ready")

        assert live_status == 200
        assert json.loads(live_body) == {
            "status": "ok",
            "service": "siw-intent-brain",
        }
        assert ready_status == 200
        assert json.loads(ready_body)["checks"] == {
            "job_store": "ok",
            "model_config": "ok",
        }


def test_unexpected_server_errors_do_not_leak_details(
    tmp_path: Path,
    monkeypatch,
) -> None:
    with running_server(tmp_path, monkeypatch) as address:
        monkeypatch.setattr(
            webapp.SIWHandler,
            "_handle_score",
            lambda *_: (_ for _ in ()).throw(RuntimeError("secret-token-value")),
        )
        status, _, body = request(
            address,
            "POST",
            "/api/score",
            payload={"text": "hello"},
        )

        assert status == 500
        assert b"secret-token-value" not in body
        assert "服务暂时不可用" in body.decode("utf-8")


@contextmanager
def running_server(tmp_path: Path, monkeypatch) -> Iterator[tuple[str, int]]:
    monkeypatch.setenv("SIW_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(webapp, "IntentBrain", FakeIntentBrain)
    server = ThreadingHTTPServer(("127.0.0.1", 0), webapp.SIWHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(address, method: str, path: str, *, cookie: str = "", payload=None):
    connection = http.client.HTTPConnection(*address, timeout=3)
    headers = {}
    body = None
    if cookie:
        headers["cookie"] = cookie
    if payload is not None:
        headers["content-type"] = "application/json"
        body = json.dumps(payload)
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    data = response.read()
    result = (response.status, dict(response.getheaders()), data)
    connection.close()
    return result


def test_score_creates_owned_history_and_a_fresh_browser_cannot_read_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    with running_server(tmp_path, monkeypatch) as address:
        status, headers, _ = request(address, "GET", "/")
        assert status == 200
        cookie = headers["set-cookie"].split(";", 1)[0]
        assert cookie.startswith("siw_session=")
        assert "HttpOnly" in headers["set-cookie"]
        assert "SameSite=Lax" in headers["set-cookie"]

        status, _, body = request(
            address,
            "POST",
            "/api/score",
            cookie=cookie,
            payload={"text": "Need a cheaper monitoring tool", "context": {}},
        )
        response = json.loads(body)
        assert status == 200
        assert response["job"]["status"] == "succeeded"
        assert response["card"]["lead_tier"] == "A"

        status, _, body = request(address, "GET", "/api/jobs", cookie=cookie)
        history = json.loads(body)
        assert status == 200
        assert [job["id"] for job in history["jobs"]] == [response["job"]["id"]]

        status, _, body = request(address, "GET", "/api/jobs")
        assert status == 200
        assert json.loads(body)["jobs"] == []


def test_job_artifact_download_requires_the_owning_browser_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    with running_server(tmp_path, monkeypatch) as address:
        _, headers, _ = request(address, "GET", "/")
        cookie = headers["set-cookie"].split(";", 1)[0]
        owner_id = cookie.split("=", 1)[1]

        report_dir = tmp_path / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "owned.pdf"
        report_path.write_bytes(b"%PDF-owned")

        store = JobStore(tmp_path / "siw.sqlite3")
        job = store.create_job(owner_id, "pipeline", "owned report")
        store.mark_running(job["id"])
        store.mark_succeeded(
            job["id"],
            result={"count": 1},
            artifacts={"pdf": "reports/owned.pdf"},
        )

        path = f"/api/jobs/{job['id']}/artifacts/pdf"
        status, download_headers, body = request(address, "GET", path, cookie=cookie)
        assert status == 200
        assert body == b"%PDF-owned"
        assert download_headers["content-type"] == "application/pdf"
        assert download_headers["content-disposition"].startswith("attachment;")

        status, _, _ = request(address, "GET", path)
        assert status == 404


def test_legacy_unscoped_report_route_is_not_exposed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report_dir = tmp_path / "reports"
    report_dir.mkdir(parents=True)
    (report_dir / "abcdef123456.pdf").write_bytes(b"%PDF-legacy")

    with running_server(tmp_path, monkeypatch) as address:
        status, _, body = request(address, "GET", "/reports/abcdef123456.pdf")

    assert status == 404
    assert b"%PDF-legacy" not in body
