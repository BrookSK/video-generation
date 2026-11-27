"""Small JSON client for the Verda project used by the GPU controller."""

import json
import time
import urllib.error
import urllib.request
from uuid import UUID

API = "https://api.verda.com/v1"


class VerdaError(Exception):
    def __init__(self, status: int | None):
        self.status = status
        super().__init__(f"Verda HTTP {status}" if status else "Verda unavailable")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Verda:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.opener = urllib.request.build_opener(NoRedirect)
        self.token = ""
        self.expires_at = 0.0

    def _request(self, method, path, body=None, token=None):
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            API + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise VerdaError(None)
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raise VerdaError(exc.code) from None
        except (OSError, ValueError):
            raise VerdaError(None) from None

    def authorize(self):
        if time.monotonic() >= self.expires_at:
            data = self._request(
                "POST",
                "/oauth2/token",
                {
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            self.token = data["access_token"]
            self.expires_at = time.monotonic() + max(1, int(data["expires_in"]) - 30)

    def call(self, method, path, body=None):
        self.authorize()
        try:
            return self._request(method, path, body, self.token)
        except VerdaError as exc:
            if exc.status == 401:
                self.expires_at = 0
            raise

    def create(self, hostname: str, instance_type, location, volume_id, ssh_key_id, spot):
        return self.call(
            "POST",
            "/instances",
            {
                "hostname": hostname,
                "instance_type": instance_type,
                "location_code": location,
                "image": str(volume_id),
                "ssh_key_ids": [str(ssh_key_id)],
                "contract": "SPOT" if spot else "PAY_AS_YOU_GO",
                "is_spot": spot,
            },
        )

    def instances(self):
        rows = self.call("GET", "/instances")
        if not isinstance(rows, list):
            raise VerdaError(None)
        return rows

    def volume_in_use(self, volume_id: UUID) -> bool:
        return any(row.get("os_volume_id") == str(volume_id) for row in self.instances())

    def find(self, hostname):
        matches = [row for row in self.instances() if row.get("hostname") == hostname]
        if len(matches) > 1:
            raise VerdaError(None)
        return matches[0] if matches else None

    def get(self, instance_id: UUID):
        try:
            return self.call("GET", f"/instances/{instance_id}")
        except VerdaError as exc:
            if exc.status == 404:
                return None
            raise

    def delete(self, instance_id: UUID):
        result = self.call(
            "PUT", "/instances", {"id": [str(instance_id)], "action": "delete", "volume_ids": []}
        )
        if result is not None:
            if (
                not isinstance(result, list)
                or len(result) != 1
                or result[0].get("instanceId") != str(instance_id)
                or result[0].get("status") != "success"
            ):
                raise VerdaError(None)
