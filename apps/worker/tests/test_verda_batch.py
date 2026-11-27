import json
import threading
from uuid import uuid4

import httpx
import pytest

from avatar_worker import verda_batch


@pytest.mark.parametrize(
    ("path", "render_error", "status", "exit_code"),
    [("/render?", False, 200, 0), ("/wrong?", False, 404, 1), ("/render?", True, 500, 1)],
)
def test_replica_replies_to_health_then_exits_after_owning_a_job(
    monkeypatch, path, render_error, status, exit_code
):
    dispatch = str(uuid4())
    job = str(uuid4())
    calls = []

    def render(_config, dispatch_id, job_id):
        calls.append((dispatch_id, job_id))
        if render_error:
            raise KeyError("models")
        return True

    monkeypatch.setattr(verda_batch, "run_video", render)
    config = {"WORKER_TOKEN": "test", "WORKER_KINDS": "video"}
    with verda_batch.BatchServer(0, config) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        with httpx.Client(base_url=base, timeout=5, trust_env=False) as client:
            assert client.get("/health").status_code == 200
            assert calls == []
            response = client.post(path, json={"dispatch_id": dispatch, "job_id": job})
            assert response.status_code == status
            assert response.json() == {"dispatch_id": None if status == 404 else dispatch}
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert server.exit_code == exit_code
        assert calls == ([] if status == 404 else [(dispatch, job)])


def test_complete_cache_is_reused_for_the_same_manifest(monkeypatch, tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"components": []}))
    models = tmp_path / "cache"
    calls = []
    monkeypatch.setattr(verda_batch, "_load_checked", lambda _: {})
    monkeypatch.setattr(verda_batch, "pull", lambda _, root: calls.append(root))
    verda_batch.seed_cache(path, models)
    verda_batch.seed_cache(path, models)
    assert calls == [models]
