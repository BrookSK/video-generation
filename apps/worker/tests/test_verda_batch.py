import json
import threading
from uuid import uuid4

import httpx

from avatar_worker import verda_batch
from avatar_worker.supervisor import load_config


def test_replica_replies_to_health_then_runs_one_video_and_exits(monkeypatch):
    dispatch = str(uuid4())
    job = str(uuid4())
    calls = []

    def render(_config, dispatch_id, job_id):
        calls.append((dispatch_id, job_id))
        return True

    monkeypatch.setattr(verda_batch, "run_video", render)
    config = load_config({"WORKER_TOKEN": "test", "WORKER_KINDS": "video"})
    with verda_batch.BatchServer(0, config) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        with httpx.Client(base_url=base, timeout=5, trust_env=False) as client:
            assert client.get("/health").status_code == 200
            assert calls == []
            response = client.post("/render", json={"dispatch_id": dispatch, "job_id": job})
            assert response.status_code == 200
            assert response.json() == {"dispatch_id": dispatch}
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert server.exit_code == 0
        assert calls == [(dispatch, job)]


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
