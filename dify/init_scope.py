"""Create the PowerContext scope used by the innkeeper Dify app.

Prints the scope id. Put that value into the Dify environment variable
POWERCONTEXT_SCOPE. No API key is written to disk.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE_URL = os.environ.get("POWERCONTEXT_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("POWERCONTEXT_TOKEN")


def main() -> None:
    payload = {
        "title": "记仇的客栈老板",
        "summary": "OceanBase contest Dify demo",
        "idempotency_key": "dify-innkeeper-grudge",
    }
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    request = urllib.request.Request(
        f"{BASE_URL}/v1/scopes",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"create scope failed: HTTP {error.code}: {detail}") from error
    print(data["scope_id"])


if __name__ == "__main__":
    main()
