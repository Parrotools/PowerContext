"""Replay the Dify HTTP bodies against a live PowerContext server.

Two separate HTTP conversations share one scope. The first writes a grudge
that contains quotes and a backslash. The second is a new conversation: it
only calls prepare, and the returned context must contain that grudge.

The request bytes are produced with json.dumps, the same calls as the
「编码读取请求」 and 「编码写入请求」 nodes in innkeeper-grudge.yml.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = os.environ.get("POWERCONTEXT_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("POWERCONTEXT_TOKEN")
TURN_ONE = '我把你的招牌酒换成了醋，还说"这瓶\\更好"'
TURN_TWO = "老板，我又来了"


def prepare_body(scope_id: str, query: str) -> str:
    payload = {
        "scope_id": scope_id,
        "query": "客栈记仇 " + (query or ""),
        "max_bytes": 2000,
    }
    return json.dumps(payload, ensure_ascii=False)


def remember_body(scope_id: str, query: str) -> str:
    payload = {
        "scope_id": scope_id,
        "kind": "decision",
        "text": "客栈记仇：客人刚刚做了这件事：" + (query or ""),
        "reason": "innkeeper demo turn",
    }
    return json.dumps(payload, ensure_ascii=False)


def assert_roundtrip(scope_id: str) -> None:
    for raw in (prepare_body(scope_id, TURN_ONE), remember_body(scope_id, TURN_ONE)):
        parsed = json.loads(raw)
        found = parsed.get("query") or parsed.get("text") or ""
        if TURN_ONE not in found:
            raise SystemExit("encoded body dropped the original user text")
        if '\\"' not in raw or "\\\\" not in raw:
            raise SystemExit("encoded body did not escape the sample quotes and backslash")


def post(path: str, body: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return {"status": response.status, "body": json.loads(raw)}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"POST {path} failed: HTTP {error.code}: {detail}") from error


def create_scope() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = json.dumps(
        {
            "title": "记仇的客栈老板",
            "summary": "cross-session evidence",
            "idempotency_key": f"dify-innkeeper-evidence-{stamp}",
        },
        ensure_ascii=False,
    )
    created = post("/v1/scopes", payload)
    return created["body"]["scope_id"]


def main() -> None:
    scope_id = "pending"
    assert_roundtrip("scope-check")
    scope_id = create_scope()
    assert_roundtrip(scope_id)

    first_prepare = post("/v1/context/prepare", prepare_body(scope_id, TURN_ONE))
    first_content = str((first_prepare["body"] or {}).get("content") or "")
    if TURN_ONE in first_content:
        raise SystemExit("first conversation already contained this grudge")
    first_remember = post("/v1/memory/remember", remember_body(scope_id, TURN_ONE))

    second_prepare = post("/v1/context/prepare", prepare_body(scope_id, TURN_TWO))
    second_content = str((second_prepare["body"] or {}).get("content") or "")
    if "招牌酒" not in second_content and "醋" not in second_content:
        raise SystemExit(
            "second conversation did not read the first grudge back: "
            + json.dumps(second_prepare["body"], ensure_ascii=False)
        )

    evidence = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "powercontext_url": BASE_URL,
        "scope_id": scope_id,
        "note": (
            "Two separate HTTP conversations. The second call does not reuse "
            "a Dify conversation id; it only shares the PowerContext scope."
        ),
        "turn_one": {
            "user": TURN_ONE,
            "prepare": {
                "request": json.loads(prepare_body(scope_id, TURN_ONE)),
                "response": first_prepare,
            },
            "remember": {
                "request": json.loads(remember_body(scope_id, TURN_ONE)),
                "response": first_remember,
            },
        },
        "turn_two_new_conversation": {
            "user": TURN_TWO,
            "prepare": {
                "request": json.loads(prepare_body(scope_id, TURN_TWO)),
                "response": second_prepare,
            },
        },
    }
    out = Path(__file__).resolve().parent / "evidence" / "rounds.json"
    out.parent.mkdir(parents=True)
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"scope_id={scope_id}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
