import gc
import importlib.util
import sys
import types
import weakref
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "tts_stage_lifetime", ROOT / "apps/worker/runtimes/tts/tts_stage.py"
)
tts_stage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tts_stage)


@pytest.mark.parametrize("completed", [True, False], ids=["completed", "rejected"])
def test_model_releases_without_waiting_for_cyclic_gc(monkeypatch, tmp_path, completed):
    references = []

    class Wave:
        def unchanged(self, *args, **kwargs):
            return self

        squeeze = clamp = to = cpu = __mul__ = unchanged

        def numpy(self):
            return np.zeros(24, dtype=np.int16)

    class T3:
        hp = types.SimpleNamespace(stop_speech_token=23)

        def inference(self, **kwargs):
            return np.asarray([[7, 23 if completed else 7]], dtype=np.int64)

    class Model:
        sr = tts_stage.SAMPLE_RATE

        def __init__(self):
            self.t3 = T3()
            references.append(weakref.ref(self.t3))

        def generate(self, *args, **kwargs):
            self.t3.inference(max_new_tokens=1000)
            return Wave()

    monkeypatch.setattr(tts_stage, "load_model", lambda *args: Model())
    monkeypatch.setitem(
        sys.modules,
        "torch",
        types.SimpleNamespace(
            cuda=types.SimpleNamespace(is_available=lambda: False), int16=np.int16
        ),
    )
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        if completed:
            tts_stage.chatterbox_synthesize("Olá.", "pt", None, tmp_path)
        else:
            with pytest.raises(tts_stage.StageError):
                tts_stage.chatterbox_synthesize("Olá.", "pt", None, tmp_path)
        assert references[0]() is None
    finally:
        if was_enabled:
            gc.enable()
        gc.collect()
