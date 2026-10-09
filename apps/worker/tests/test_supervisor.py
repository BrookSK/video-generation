"""Supervisor contra uma API interna falsa em httpx.MockTransport, sem rede nem modelo real."""

import hashlib
import io
import json
import logging
import subprocess
import sys
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from PIL import Image
from test_video import video_case as video_case

from avatar_worker import supervisor, video
from avatar_worker.asset_prepare import PREVIEWS, PrepareInputError, prepare_avatar
from avatar_worker.cutout import CutoutError
from avatar_worker.supervisor import Config, Supervisor, load_config, main

TASK_ID = "11111111-1111-1111-1111-111111111111"
ATTEMPT_ID = "22222222-2222-2222-2222-222222222222"
SOURCE_ID = "33333333-3333-3333-3333-333333333333"
TOKEN = "segredo-do-worker"
STAGE_RGB = (0x1F, 0x1C, 0x3F)
CONFIG = Config(
    api_url="http://api", token=TOKEN, worker_id="w1", kinds=("asset_prepare",), poll_seconds=0
)


def _png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _alpha_png():
    """PNG 200x400 transparente com uma pessoa opaca de 100x300 no meio."""
    image = Image.new("RGBA", (200, 400), (0, 0, 0, 0))
    image.paste((200, 50, 50, 255), (50, 50, 150, 350))
    return _png(image)


def _no_cutout(model_name):
    raise AssertionError("o recorte não pode ser chamado para PNG com alfa")


class FakeApi:
    """API interna falsa: registra cada chamada e responde conforme o cenário do teste."""

    def __init__(self, heartbeat_status=200, lease_seconds=120, claims=1):
        self.calls = []
        self.uploads = {}
        self.completed = None
        self.failed = None
        self.claims_left = claims
        self.heartbeat_status = heartbeat_status
        self.lease_seconds = lease_seconds
        self.heartbeat_seen = threading.Event()
        self.lock = threading.Lock()

    def claim_body(self):
        lease_until = datetime.now(UTC) + timedelta(seconds=self.lease_seconds)
        return {
            "kind": "asset_prepare",
            "id": TASK_ID,
            "attempt_id": ATTEMPT_ID,
            "lease_generation": 3,
            "lease_until": lease_until.isoformat(),
            "heartbeat_interval_seconds": 0.01,
            "payload": {"avatar_id": "a", "source_file_id": SOURCE_ID},
        }

    def __call__(self, request):
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        path = request.url.path
        with self.lock:
            self.calls.append((request.method, path))
        if path == "/internal/v1/claim":
            if self.claims_left == 0:
                return httpx.Response(204)
            self.claims_left -= 1
            return httpx.Response(200, json=self.claim_body())
        if path.endswith("/heartbeat"):
            self.heartbeat_seen.set()
            if self.heartbeat_status == 409:
                return httpx.Response(409, json={"error": {"code": "STALE_ATTEMPT"}})
            if self.heartbeat_status != 200:
                return httpx.Response(self.heartbeat_status)
            lease_until = datetime.now(UTC) + timedelta(seconds=self.lease_seconds)
            return httpx.Response(200, json={"lease_until": lease_until.isoformat()})
        if path == f"/internal/v1/files/{SOURCE_ID}":
            return httpx.Response(200, content=self.source)
        if request.method == "PUT":
            return self.upload(request)
        if path.endswith("/complete"):
            self.completed = request.read()
            return httpx.Response(200, json={"id": TASK_ID, "status": "concluido"})
        if path.endswith("/fail"):
            self.failed = httpx.Response(200, content=request.read()).json()
            return httpx.Response(200, json={"id": TASK_ID, "status": "falhou", "attempt": 1})
        return httpx.Response(404)

    def upload(self, request):
        name = request.url.path.rsplit("/", 1)[1]
        body = request.read()
        content_type = request.headers["Content-Type"]
        form = _multipart(body, content_type)
        with self.lock:
            self.uploads[name] = form
        return httpx.Response(201, json={"id": f"id-{name}"})

    def after_heartbeat_409(self):
        index = self.calls.index(("POST", f"/internal/v1/asset-tasks/{TASK_ID}/heartbeat"))
        return self.calls[index + 1 :]


def _multipart(body, content_type):
    boundary = content_type.split("boundary=")[1].encode()
    fields = {}
    for part in body.split(b"--" + boundary):
        head, _, value = part.partition(b"\r\n\r\n")
        if b'name="' not in head:
            continue
        name = head.split(b'name="')[1].split(b'"')[0].decode()
        fields[name] = value.removesuffix(b"\r\n")
    return fields


def _supervisor(api, prepare=None, waits=None, wait=None):
    client = httpx.Client(base_url="http://api", transport=httpx.MockTransport(api))
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    recorded = [] if waits is None else waits
    return Supervisor(
        CONFIG,
        client,
        prepare=prepare or (lambda source: prepare_avatar(source, session_factory=_no_cutout)),
        wait=wait or (lambda seconds, interrupt: recorded.append(seconds)),
    )


def _waiting_for_heartbeat(api, prepare):
    def wrapped(source):
        assert api.heartbeat_seen.wait(5)
        return prepare(source)

    return wrapped


def test_claim_heartbeat_download_upload_complete_with_alpha_png_skipping_cutout():
    api = FakeApi()
    api.source = _alpha_png()
    worker = _supervisor(
        api,
        prepare=_waiting_for_heartbeat(
            api, lambda source: prepare_avatar(source, session_factory=_no_cutout)
        ),
    )

    assert worker.process_next() is True

    paths = [path for _, path in api.calls if not path.endswith("/heartbeat")]
    upload_base = f"/internal/v1/asset-tasks/{TASK_ID}/attempts/{ATTEMPT_ID}/files"
    assert paths == [
        "/internal/v1/claim",
        f"/internal/v1/files/{SOURCE_ID}",
        f"{upload_base}/prepared.png",
        f"{upload_base}/preview-9x16.png",
        f"{upload_base}/preview-16x9.png",
        f"/internal/v1/asset-tasks/{TASK_ID}/complete",
    ]
    assert ("POST", f"/internal/v1/asset-tasks/{TASK_ID}/heartbeat") in api.calls
    for form in api.uploads.values():
        assert form["sha256"].decode() == hashlib.sha256(form["file"]).hexdigest()
        assert form["lease_generation"] == b"3"
    complete = httpx.Response(200, content=api.completed).json()
    assert complete == {
        "attempt_id": ATTEMPT_ID,
        "lease_generation": 3,
        "prepared_file_id": "id-prepared.png",
        "preview_9x16_file_id": "id-preview-9x16.png",
        "preview_16x9_file_id": "id-preview-16x9.png",
    }
    assert api.failed is None


def test_empty_queue_returns_false_and_run_polls_until_stop():
    api = FakeApi(claims=0)
    waits = []

    def stop_after_second_poll(seconds, interrupt):
        waits.append(seconds)
        if len(waits) == 2:
            worker.request_stop()

    worker = _supervisor(api, wait=stop_after_second_poll)

    assert worker.process_next() is False
    assert waits == []
    worker.run()
    assert waits == [0, 0]


def test_heartbeat_409_stops_attempt_without_upload_complete_or_fail():
    api = FakeApi(heartbeat_status=409)
    api.source = _alpha_png()
    released = threading.Event()

    def prepare_after_409(source):
        assert api.heartbeat_seen.wait(5)
        released.wait(0.2)
        return prepare_avatar(source, session_factory=_no_cutout)

    worker = _supervisor(api, prepare=prepare_after_409)

    assert worker.process_next() is True

    methods = [(method, path.rsplit("/", 1)[-1]) for method, path in api.after_heartbeat_409()]
    assert all(method != "PUT" for method, _ in methods)
    assert all(name not in ("complete", "fail") for _, name in methods)
    assert api.uploads == {} and api.completed is None and api.failed is None


def test_lease_expired_without_renewal_publishes_nothing():
    api = FakeApi(heartbeat_status=503, lease_seconds=0.3)
    api.source = _alpha_png()

    def prepare_past_lease(source):
        assert api.heartbeat_seen.wait(5)
        time.sleep(0.5)
        return prepare_avatar(source, session_factory=_no_cutout)

    worker = _supervisor(api, prepare=prepare_past_lease)

    assert worker.process_next() is True

    assert api.uploads == {} and api.completed is None and api.failed is None


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (PrepareInputError("Nenhuma pessoa encontrada na imagem."), "INVALID_SOURCE", False),
        (CutoutError("modelo de recorte ausente em /models/x.onnx"), "CUTOUT_UNAVAILABLE", False),
        (RuntimeError("inesperado"), "PREPARE_ERROR", True),
    ],
)
def test_prepare_errors_become_fail_with_code_and_retry_flag(error, code, retryable):
    api = FakeApi()
    api.source = b"qualquer"

    def failing(source):
        raise error

    worker = _supervisor(api, prepare=failing)

    assert worker.process_next() is True

    assert api.failed["error_code"] == code
    assert api.failed["retryable"] is retryable
    assert api.failed["attempt_id"] == ATTEMPT_ID
    assert "/models" not in api.failed["error_message"]
    assert api.uploads == {} and api.completed is None


def test_unreadable_source_is_invalid_source_not_retryable():
    api = FakeApi()
    api.source = b"isto nao e imagem"
    worker = _supervisor(api)

    worker.process_next()

    assert api.failed["error_code"] == "INVALID_SOURCE"
    assert api.failed["retryable"] is False


def test_network_errors_retry_with_backoff_from_1_to_30_seconds():
    api = FakeApi(claims=0)
    failures = {"left": 7}

    def flaky(request):
        if failures["left"]:
            failures["left"] -= 1
            raise httpx.ConnectError("sem rede", request=request)
        return api(request)

    waits = []
    worker = _supervisor(flaky, waits=waits)

    assert worker.process_next() is False
    assert waits == [1, 2, 4, 8, 16, 30, 30]


def test_network_error_during_upload_retries_same_attempt():
    api = FakeApi()
    api.source = _alpha_png()
    failures = {"left": 1}

    def flaky(request):
        if request.method == "PUT" and failures["left"]:
            failures["left"] -= 1
            raise httpx.ReadTimeout("lento", request=request)
        return api(request)

    waits = []
    worker = _supervisor(flaky, waits=waits)

    worker.process_next()

    assert waits == [1]
    assert len(api.uploads) == 3 and api.completed is not None


def test_stop_during_item_finishes_it_and_claims_nothing_more():
    api = FakeApi(claims=2)
    api.source = _alpha_png()

    def prepare_and_stop(source):
        worker.request_stop()
        return prepare_avatar(source, session_factory=_no_cutout)

    worker = _supervisor(api, prepare=prepare_and_stop)
    worker.run()

    assert api.completed is not None
    assert [path for _, path in api.calls].count("/internal/v1/claim") == 1


def test_missing_worker_token_exits_with_code_2(capsys):
    assert main({}) == 2
    assert "WORKER_TOKEN" in capsys.readouterr().err


def test_unknown_worker_kind_is_refused():
    with pytest.raises(supervisor.ConfigError):
        load_config({"WORKER_TOKEN": "t", "WORKER_KINDS": "audio"})


# --- prepare_avatar ---------------------------------------------------------------------


def test_prepare_avatar_crops_to_alpha_box_and_builds_both_previews():
    files = prepare_avatar(_alpha_png(), session_factory=_no_cutout)

    assert set(files) == {"prepared.png", *PREVIEWS}
    prepared = Image.open(io.BytesIO(files["prepared.png"]))
    assert prepared.mode == "RGBA"
    assert prepared.size == (100, 300)
    for name, (size, _) in PREVIEWS.items():
        preview = Image.open(io.BytesIO(files[name])).convert("RGB")
        assert preview.size == size
        assert preview.getpixel((0, 0)) == STAGE_RGB


def test_prepare_avatar_cuts_opaque_photo_through_session_factory(monkeypatch):
    calls = []

    def fake_remove(image, session):
        calls.append(session)
        cut = image.convert("RGBA")
        cut.putalpha(0)
        cut.paste((10, 20, 30, 255), (10, 10, 30, 50))
        return cut

    monkeypatch.setattr("avatar_worker.cutout.remove", fake_remove)
    photo = _png(Image.new("RGB", (60, 80), (255, 255, 255)))

    files = prepare_avatar(photo, session_factory=lambda name: f"sessao-{name}")

    assert calls == ["sessao-birefnet-portrait"]
    assert Image.open(io.BytesIO(files["prepared.png"])).size == (20, 40)


def test_prepare_avatar_refuses_empty_alpha():
    empty = _png(Image.new("RGBA", (50, 50), (0, 0, 0, 0)))
    with pytest.raises(PrepareInputError, match="Nenhuma pessoa encontrada na imagem"):
        prepare_avatar(empty, session_factory=_no_cutout)


def test_prepare_avatar_refuses_unreadable_bytes():
    with pytest.raises(PrepareInputError):
        prepare_avatar(b"\x00\x01nao-imagem", session_factory=_no_cutout)


def test_prepare_avatar_propagates_cutout_error_without_model():
    def missing_model(name):
        raise CutoutError("modelo ausente")

    photo = _png(Image.new("RGB", (40, 40), (255, 255, 255)))
    with pytest.raises(CutoutError):
        prepare_avatar(photo, session_factory=missing_model)


class VideoApi(FakeApi):
    """Frente HTTP de teste; mídia gerada pelo pipeline é guardada e decodificada."""

    def __init__(self, payload, destination, **kwargs):
        super().__init__(**kwargs)
        self.payload = {**payload, "avatar_file_id": SOURCE_ID, "scene_file_id": None}
        self.destination = destination
        self.drop_final_ack = False
        self.final_sends = 0
        self.upload_error = None
        self.render_ready = None

    def claim_body(self):
        return {**super().claim_body(), "kind": "video", "payload": self.payload}

    def __call__(self, request):
        assert request.url.host == "api", "Conexão fora da API interna"
        if (
            request.url.path.endswith("/heartbeat")
            and self.render_ready is not None
            and self.render_ready.exists()
        ):
            self.heartbeat_status = 409
        return super().__call__(request)

    def upload(self, request):
        if self.upload_error:
            return httpx.Response(409, json={"error": {"code": self.upload_error}})
        response = super().upload(request)
        name = request.url.path.rsplit("/", 1)[1]
        form = self.uploads[name]
        assert form["sha256"].decode() == hashlib.sha256(form["file"]).hexdigest()
        (self.destination / name).write_bytes(form["file"])
        if name == "final.mp4":
            self.final_sends += 1
            if self.drop_final_ack:
                self.drop_final_ack = False
                # A API recebeu o corpo, mas a resposta se perdeu. Reenvio precisa ser inteiro.
                raise httpx.ReadTimeout("resposta perdida", request=request)
        return response


def _video_supervisor(api, runtime):
    config = replace(
        load_config({"API_URL": "http://api", "WORKER_TOKEN": TOKEN, "WORKER_KINDS": "video"}),
        video_runtime=runtime,
    )
    client = httpx.Client(
        base_url="http://api",
        transport=httpx.MockTransport(api),
        headers={"Authorization": f"Bearer {TOKEN}"},
        trust_env=False,
    )
    return Supervisor(config, client, wait=lambda seconds, interrupt: None)


def test_video_stream_retry_preserves_decodable_media_and_manifest(video_case, tmp_path):
    payload, inputs, _, runtime = video_case
    api = VideoApi(payload, tmp_path)
    api.source = inputs["avatar"].read_bytes()
    api.drop_final_ack = True

    assert _video_supervisor(api, runtime).process_next() is True

    assert api.completed is not None and api.failed is None
    assert api.final_sends == 2
    output = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(tmp_path / "final.mp4")],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    video = next(stream for stream in output["streams"] if stream["codec_type"] == "video")
    assert (video["width"], video["height"], video["codec_name"]) == (1080, 1920, "h264")
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["attempt_directory"] == f"jobs/{TASK_ID}/{ATTEMPT_ID}"
    assert (
        hashlib.sha256((tmp_path / "final.mp4").read_bytes()).hexdigest()
        == (manifest["files"]["final.mp4"])
    )


@pytest.mark.parametrize("code", ["FILE_EXISTS", "STALE_ATTEMPT"])
def test_file_conflict_is_failure_but_stale_attempt_cannot_even_fail(video_case, tmp_path, code):
    payload, inputs, _, runtime = video_case
    api = VideoApi(payload, tmp_path)
    api.source = inputs["avatar"].read_bytes()
    api.upload_error = code

    _video_supervisor(api, runtime).process_next()

    assert api.completed is None
    if code == "FILE_EXISTS":
        assert api.failed["error_code"] == "OUTPUT_INVALID"
        assert api.failed["retryable"] is False
    else:
        assert api.failed is None


def test_video_lease_loss_kills_renderer_child_without_upload_or_fail(video_case, tmp_path):
    payload, inputs, _, runtime = video_case
    ready, lock = tmp_path / "render-ready", tmp_path / "gpu-resource.lock"
    child = tmp_path / "child.py"
    child.write_text(
        "import fcntl,pathlib,signal,sys\n"
        "with open(sys.argv[1],'w') as f:\n"
        "    fcntl.flock(f,fcntl.LOCK_EX)\n"
        "    pathlib.Path(sys.argv[2]).touch()\n"
        "    signal.pause()\n"
    )
    runtime.avatar_script.write_text(
        "import subprocess,sys\n"
        f"p=subprocess.Popen([sys.executable,{str(child)!r},{str(lock)!r},{str(ready)!r}])\n"
        "p.wait()\n"
    )
    api = VideoApi(payload, tmp_path)
    api.source = inputs["avatar"].read_bytes()
    api.render_ready = ready

    _video_supervisor(api, runtime).process_next()

    assert ready.exists()
    assert api.uploads == {} and api.completed is None and api.failed is None
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import fcntl,sys; f=open(sys.argv[1]); fcntl.flock(f,fcntl.LOCK_EX)",
            str(lock),
        ],
        check=True,
        timeout=3,
    )


def test_video_runtime_failure_does_not_leak_text_token_or_traceback(video_case, tmp_path, caplog):
    payload, inputs, _, runtime = video_case
    private_text = "Fala sensível usada só no teste."
    payload["script_text"] = private_text
    runtime.tts_script.write_text(
        f"import sys; print({(private_text + TOKEN)!r},file=sys.stderr); sys.exit(1)\n"
    )
    api = VideoApi(payload, tmp_path)
    api.source = inputs["avatar"].read_bytes()

    with caplog.at_level(logging.INFO, logger="avatar_worker.supervisor"):
        _video_supervisor(api, runtime).process_next()

    assert api.failed["error_code"] == "RENDER_FAILED"
    assert api.failed["retryable"] is False
    published = json.dumps(api.failed) + "\n".join(caplog.messages)
    assert private_text not in published and TOKEN not in published
    assert "Traceback" not in published
    assert api.uploads == {} and api.completed is None


def test_video_lease_loss_cancels_final_probe_group_before_publication(
    video_case, tmp_path, monkeypatch
):
    payload, inputs, _, runtime = video_case
    ready, lock = tmp_path / "probe-ready", tmp_path / "probe-resource.lock"
    child = tmp_path / "probe-child.py"
    child.write_text(
        "import fcntl,pathlib,signal,sys\n"
        "with open(sys.argv[1],'w') as f:\n"
        "    fcntl.flock(f,fcntl.LOCK_EX)\n"
        "    pathlib.Path(sys.argv[2]).touch()\n"
        "    signal.pause()\n"
    )
    blocker = tmp_path / "probe-blocker.py"
    blocker.write_text(
        "import subprocess,sys\n"
        f"p=subprocess.Popen([sys.executable,{str(child)!r},{str(lock)!r},{str(ready)!r}])\n"
        "p.wait()\n"
    )
    run = video.run_process

    def blocked_final_probe(argv, *args, **kwargs):
        if argv[0] == "ffprobe" and argv[-1].endswith("/final.mp4"):
            argv = [sys.executable, str(blocker)]
        return run(argv, *args, **kwargs)

    monkeypatch.setattr(video, "run_process", blocked_final_probe)
    api = VideoApi(payload, tmp_path)
    api.source = inputs["avatar"].read_bytes()
    api.render_ready = ready

    _video_supervisor(api, runtime).process_next()

    assert not api.uploads and api.completed is None and api.failed is None
    assert ready.exists()
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import fcntl,sys; f=open(sys.argv[1]); fcntl.flock(f,fcntl.LOCK_EX)",
            str(lock),
        ],
        check=True,
        timeout=3,
    )
