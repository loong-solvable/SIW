"""Persistent product-job storage for the SIW web workspace."""

from pathlib import Path

from siw_intent_brain.job_store import JobStore


def test_create_job_is_queued_and_scoped_to_owner(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "siw.sqlite3")

    created = store.create_job(
        owner_id="session-a",
        kind="score",
        input_summary="Need a cheaper monitoring tool",
    )

    assert created["status"] == "queued"
    assert created["kind"] == "score"
    assert store.get_job(created["id"], owner_id="session-a") == created
    assert store.get_job(created["id"], owner_id="session-b") is None


def test_successful_job_persists_result_and_artifacts(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "siw.sqlite3")
    created = store.create_job(
        owner_id="session-a",
        kind="pipeline",
        input_summary="3 leads from r/SaaS",
    )

    running = store.mark_running(created["id"])
    completed = store.mark_succeeded(
        created["id"],
        result={"count": 3, "stats": {"tier_counts": {"A": 1}}},
        artifacts={"pdf": "reports/job.pdf", "jsonl": "reports/job.jsonl"},
    )

    assert running["status"] == "running"
    assert completed["status"] == "succeeded"
    assert completed["result"]["count"] == 3
    assert completed["artifacts"]["pdf"] == "reports/job.pdf"
    assert completed["finished_at"] is not None


def test_list_jobs_returns_only_owner_history_newest_first(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "siw.sqlite3")
    first = store.create_job("session-a", "score", "first")
    second = store.create_job("session-a", "pipeline", "second")
    store.create_job("session-b", "score", "private")

    jobs = store.list_jobs(owner_id="session-a", limit=10)

    assert [job["id"] for job in jobs] == [second["id"], first["id"]]
    assert all(job["input_summary"] != "private" for job in jobs)


def test_failed_job_keeps_user_safe_error_fields(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "siw.sqlite3")
    created = store.create_job("session-a", "pipeline", "bad input")

    failed = store.mark_failed(
        created["id"],
        error_code="E_UPSTREAM_TIMEOUT",
        error_message="模型响应超时，请稍后重试",
    )

    assert failed["status"] == "failed"
    assert failed["error_code"] == "E_UPSTREAM_TIMEOUT"
    assert failed["error_message"] == "模型响应超时，请稍后重试"
    assert failed["result"] is None


def test_startup_recovery_closes_only_interrupted_jobs(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "siw.sqlite3")
    queued = store.create_job("session-a", "score", "queued")
    running = store.create_job("session-a", "pipeline", "running")
    store.mark_running(running["id"])
    complete = store.create_job("session-a", "score", "complete")
    store.mark_running(complete["id"])
    store.mark_succeeded(complete["id"], result={"ok": True})

    assert store.recover_interrupted_jobs() == 2

    recovered_queued = store.get_job(queued["id"], "session-a")
    recovered_running = store.get_job(running["id"], "session-a")
    completed = store.get_job(complete["id"], "session-a")
    assert recovered_queued is not None
    assert recovered_running is not None
    assert completed is not None
    assert recovered_queued["status"] == "failed"
    assert recovered_running["status"] == "failed"
    assert recovered_running["error_code"] == "E_PROCESS_RESTARTED"
    assert completed["status"] == "succeeded"
