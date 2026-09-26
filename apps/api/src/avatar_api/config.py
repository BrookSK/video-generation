import os
from dataclasses import dataclass
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    return default if value is None or value == "" else int(value)


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_dir: Path
    worker_token: str
    app_env: str = "production"
    lease_seconds: int = 120
    heartbeat_interval_seconds: int = 20
    sweep_interval_seconds: int = 30
    session_ttl_hours: int = 12
    max_upload_bytes: int = 2 * 1024 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", ""),
            data_dir=Path(os.environ.get("DATA_DIR", "data")),
            worker_token=os.environ.get("WORKER_TOKEN", ""),
            app_env=os.environ.get("APP_ENV", "production"),
            lease_seconds=_int_env("LEASE_SECONDS", 120),
            heartbeat_interval_seconds=_int_env("HEARTBEAT_INTERVAL_SECONDS", 20),
            sweep_interval_seconds=_int_env("SWEEP_INTERVAL_SECONDS", 30),
            session_ttl_hours=_int_env("SESSION_TTL_HOURS", 12),
            max_upload_bytes=_int_env("MAX_UPLOAD_BYTES", 2 * 1024 * 1024 * 1024),
        )
