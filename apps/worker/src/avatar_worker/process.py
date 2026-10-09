"""Subprocessos locais: cancelamento por lease encerra a sessão inteira, sem shell."""

import os
import signal
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

POLL_SECONDS = 0.1
TERM_TIMEOUT_SECONDS = 2.0
DIAGNOSTIC_BYTES = 8192


class ProcessFailure(Exception):
    """Diagnóstico local limitado; nunca retornar este texto ao consumidor da API."""

    def __init__(self, returncode: int | None, diagnostic: str):
        super().__init__(diagnostic)
        self.returncode = returncode
        self.diagnostic = diagnostic


def _stop_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=TERM_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        pass
    finally:
        # O líder pode ter saído antes dos filhos ou sem esperar o renderer.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def run_process(
    argv: Sequence[str],
    check: Callable[[], None],
    log_path: Path,
    cwd: Path | None = None,
) -> None:
    """Verifica lease antes/durante/depois; stdout/stderr ficam em disco, não na RAM."""
    check()
    with log_path.open("wb") as output:
        try:
            process = subprocess.Popen(
                argv,
                shell=False,
                start_new_session=True,
                cwd=cwd,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        except OSError as exc:
            raise ProcessFailure(None, str(exc)) from exc
        try:
            while process.poll() is None:
                check()
                try:
                    process.wait(timeout=POLL_SECONDS)
                except subprocess.TimeoutExpired:
                    continue
            check()
        finally:
            _stop_group(process)
    if process.returncode != 0:
        with log_path.open("rb") as output:
            output.seek(max(0, output.seek(0, os.SEEK_END) - DIAGNOSTIC_BYTES))
            diagnostic = output.read(DIAGNOSTIC_BYTES).decode("utf-8", "replace")
        raise ProcessFailure(process.returncode, diagnostic)
