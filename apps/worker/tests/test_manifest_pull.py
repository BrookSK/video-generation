import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from avatar_worker import manifest as manifest_module
from avatar_worker.manifest import main

COMMIT = "0123456789abcdef0123456789abcdef01234567"
WEIGHTS = {
    "/weights/a.safetensors": b"pesos sinteticos A" * 1000,
    "/weights/sub/b.json": b'{"sintetico": true}',
    "/wheels/w.whl": b"wheel que nao deve ser baixada",
}


class LocalServer:
    """Servidor HTTP local em thread que conta cada requisição recebida."""

    def __init__(self, files):
        self.files = dict(files)
        self.requests = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                server.requests.append(self.path)
                body = server.files.get(self.path)
                if body is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )

    def downloads(self):
        return [path for path in self.requests if path.startswith("/weights/")]


@pytest.fixture
def server(monkeypatch):
    local = LocalServer(WEIGHTS)
    local.thread.start()
    # A política exige https; só as URLs deste servidor de teste passam sem TLS.
    check_https = manifest_module._check_https
    monkeypatch.setattr(
        manifest_module,
        "_check_https",
        lambda label, url: [] if str(url).startswith(local.url) else check_https(label, url),
    )
    yield local
    local.httpd.shutdown()
    local.httpd.server_close()


def _file(server, path, body=None):
    body = WEIGHTS[path] if body is None else body
    return {
        "path": path.removeprefix("/weights/"),
        "url": f"{server.url}{path}",
        "sha256": hashlib.sha256(body).hexdigest(),
        "size": len(body),
    }


def _manifest(server, files=None):
    if files is None:
        files = [_file(server, "/weights/a.safetensors"), _file(server, "/weights/sub/b.json")]
    wheel = WEIGHTS["/wheels/w.whl"]
    return {
        "schema_version": 1,
        "components": [
            {
                "id": "synthetic-weights",
                "kind": "model",
                "url": "https://huggingface.co/example/synthetic",
                "revision": COMMIT,
                "code_license": "Apache-2.0",
                "weights_license": "Apache-2.0",
                "commercial_use": True,
                "files": files,
            },
            {
                "id": "synthetic-wheel",
                "kind": "wheel",
                "url": "https://github.com/example/synthetic",
                "revision": "1.0.0",
                "code_license": "MIT",
                "weights_license": None,
                "commercial_use": True,
                "files": [
                    {
                        "path": "w.whl",
                        "url": f"{server.url}/wheels/w.whl",
                        "sha256": hashlib.sha256(wheel).hexdigest(),
                        "size": len(wheel),
                    }
                ],
            },
        ],
    }


def _pull(tmp_path, manifest):
    policy = tmp_path / "MODEL_MANIFEST.json"
    policy.write_text(json.dumps(manifest), encoding="utf-8")
    dest = tmp_path / "models"
    dest.mkdir(exist_ok=True)
    return main(["pull", "--policy", str(policy), "--dest", str(dest)]), dest


def _leftovers(dest):
    return sorted(str(path.relative_to(dest)) for path in dest.rglob("*.part"))


def test_pull_downloads_model_files_with_verified_hash(tmp_path, server, capsys):
    code, dest = _pull(tmp_path, _manifest(server))

    assert code == 0
    component = dest / "synthetic-weights"
    assert (component / "a.safetensors").read_bytes() == WEIGHTS["/weights/a.safetensors"]
    assert (component / "sub" / "b.json").read_bytes() == WEIGHTS["/weights/sub/b.json"]
    assert _leftovers(dest) == []
    assert server.requests == ["/weights/a.safetensors", "/weights/sub/b.json"]
    assert not (dest / "synthetic-wheel").exists()
    assert "2 baixado(s), 0 já presente(s)" in capsys.readouterr().out


def test_second_run_downloads_nothing(tmp_path, server, capsys):
    manifest = _manifest(server)
    assert _pull(tmp_path, manifest)[0] == 0
    assert len(server.downloads()) == 2
    capsys.readouterr()

    code, _ = _pull(tmp_path, manifest)

    assert code == 0
    assert len(server.downloads()) == 2
    out = capsys.readouterr().out
    assert "já conferido: synthetic-weights/a.safetensors" in out
    assert "0 baixado(s), 2 já presente(s)" in out


def test_wrong_hash_exits_1_without_file_or_part(tmp_path, server, capsys):
    bad = _file(server, "/weights/a.safetensors")
    bad["sha256"] = hashlib.sha256(b"outro conteudo").hexdigest()

    code, dest = _pull(tmp_path, _manifest(server, [bad]))

    assert code == 1
    assert server.downloads() == ["/weights/a.safetensors"]
    assert not (dest / "synthetic-weights" / "a.safetensors").exists()
    assert _leftovers(dest) == []
    err = capsys.readouterr().err
    assert "synthetic-weights/a.safetensors: sha256" in err
    assert "diferente do manifesto" in err


@pytest.mark.parametrize("delta", [-1, 1])
def test_wrong_size_exits_1_without_file_or_part(tmp_path, server, capsys, delta):
    entry = _file(server, "/weights/a.safetensors")
    entry["size"] += delta

    code, dest = _pull(tmp_path, _manifest(server, [entry]))

    assert code == 1
    assert not (dest / "synthetic-weights" / "a.safetensors").exists()
    assert _leftovers(dest) == []
    assert "synthetic-weights/a.safetensors" in capsys.readouterr().err


def test_http_error_exits_1_without_part(tmp_path, server, capsys):
    missing = _file(server, "/weights/a.safetensors")
    missing["url"] = f"{server.url}/weights/ausente.bin"

    code, dest = _pull(tmp_path, _manifest(server, [missing]))

    assert code == 1
    assert _leftovers(dest) == []
    err = capsys.readouterr().err
    assert "synthetic-weights/a.safetensors: falha no download" in err
    assert "404" in err


def test_corrupted_existing_file_is_downloaded_again(tmp_path, server):
    target = tmp_path / "models" / "synthetic-weights" / "a.safetensors"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x" * len(WEIGHTS["/weights/a.safetensors"]))

    code, dest = _pull(tmp_path, _manifest(server))

    assert code == 0
    assert target.read_bytes() == WEIGHTS["/weights/a.safetensors"]
    assert "/weights/a.safetensors" in server.downloads()


def test_policy_violation_stops_before_any_download(tmp_path, server, capsys):
    manifest = _manifest(server)
    manifest["components"][0]["weights_license"] = "CC-BY-NC-4.0"

    code, dest = _pull(tmp_path, manifest)

    assert code == 1
    assert server.requests == []
    assert list(dest.iterdir()) == []
    assert "weights_license 'CC-BY-NC-4.0' não é permitida" in capsys.readouterr().err


@pytest.mark.parametrize("path", ["../fora.bin", "/etc/fora.bin", "sub/../../fora.bin"])
def test_path_outside_component_is_refused(tmp_path, server, capsys, path):
    entry = _file(server, "/weights/a.safetensors")
    entry["path"] = path

    code, dest = _pull(tmp_path, _manifest(server, [entry]))

    assert code == 1
    assert server.requests == []
    assert not (tmp_path / "fora.bin").exists()
    assert "caminho fora de synthetic-weights/" in capsys.readouterr().err


@pytest.mark.parametrize("component_id", ["../x", "/x", "../../tmp/escape", "a/../../x"])
def test_component_id_outside_dest_is_refused(tmp_path, server, component_id):
    manifest = _manifest(server)
    manifest["components"][0]["id"] = component_id
    dest = tmp_path / "models"
    dest.mkdir()

    with pytest.raises(manifest_module.PullError, match="id fora do formato"):
        manifest_module.pull(manifest, dest)

    assert server.requests == []
    assert not (tmp_path / "x").exists()
    assert not (tmp_path / "escape").exists()


def test_target_through_symlink_outside_dest_is_refused(tmp_path, server):
    dest = tmp_path / "models"
    dest.mkdir()
    outside = tmp_path / "fora"
    outside.mkdir()
    (dest / "synthetic-weights").symlink_to(outside, target_is_directory=True)

    with pytest.raises(manifest_module.PullError, match="caminho fora de"):
        manifest_module.pull(_manifest(server), dest)

    assert server.requests == []
    assert list(outside.iterdir()) == []
