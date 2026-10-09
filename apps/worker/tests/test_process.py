import subprocess
import sys
import time

import pytest

from avatar_worker.process import ProcessFailure, run_process


class LostLease(Exception):
    pass


def test_lease_loss_terminates_renderer_child_and_releases_its_lock(tmp_path):
    child = tmp_path / "child.py"
    lock = tmp_path / "renderer.lock"
    ready = tmp_path / "ready"
    child.write_text(
        "import fcntl, pathlib, signal, sys\n"
        "with open(sys.argv[1], 'w') as handle:\n"
        "    fcntl.flock(handle, fcntl.LOCK_EX)\n"
        "    pathlib.Path(sys.argv[2]).write_text('ready')\n"
        "    signal.pause()\n"
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess, sys\n"
        "child = subprocess.Popen([sys.executable, *sys.argv[1:]])\n"
        "child.wait()\n"
    )
    deadline = time.monotonic() + 5

    def check():
        if ready.exists():
            raise LostLease
        if time.monotonic() >= deadline:
            pytest.fail("Renderer de teste não confirmou prontidão")

    with pytest.raises(LostLease):
        run_process(
            [sys.executable, str(parent), str(child), str(lock), str(ready)],
            check,
            tmp_path / "runtime.log",
        )
    assert ready.read_text() == "ready"
    # O lock pertence ao filho, não ao adaptador. Só sua morte permite adquirir este lock.
    subprocess.run(
        [sys.executable, "-c",
         "import fcntl, sys; f=open(sys.argv[1]); fcntl.flock(f, fcntl.LOCK_EX)", str(lock)],
        check=True,
        timeout=3,
    )


def test_expired_lease_does_not_launch_process(tmp_path):
    output = tmp_path / "should-not-exist"

    def check():
        raise LostLease

    with pytest.raises(LostLease):
        run_process(
            [sys.executable, "-c", "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()",
             str(output)],
            check,
            tmp_path / "runtime.log",
        )
    assert not output.exists()


def test_failed_runtime_preserves_local_diagnostic_and_does_not_return_success(tmp_path):
    with pytest.raises(ProcessFailure) as failure:
        run_process(
            [sys.executable, "-c", "import sys; print('CUDA out of memory'); sys.exit(7)"],
            lambda: None,
            tmp_path / "runtime.log",
        )
    assert failure.value.returncode == 7
    assert "out of memory" in failure.value.diagnostic
