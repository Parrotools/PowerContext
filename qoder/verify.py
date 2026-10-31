"""
知序 (ZhiXu) — 自动验证脚本
评审运行此脚本可一键验证所有核心功能。

用法:
    python verify.py
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE = "http://localhost:8000"
PC_BASE = "http://localhost:8010"
PASS = "PASS"
FAIL = "FAIL"
results = []
skipped = []


def api(method, path, body=None, base=None):
    """Make an HTTP request and return (status, data)."""
    url = f"{base or BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode()) if e.readable() else {}
    except Exception as e:
        return 0, {"error": str(e)}


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, condition))
    mark = "[PASS]" if condition else "[FAIL]"
    print(f"  {mark} {name}")
    if detail and condition:
        print(f"         {detail}")
    return condition


def skip(name, detail=""):
    skipped.append(name)
    print(f"  [SKIP] {name}")
    if detail:
        print(f"         {detail}")


def wait_for_health(timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, _ = api("GET", "/api/health")
        if status == 200:
            return True
        time.sleep(2)
    return False


def restart_backend(command):
    """Run the restart command from the qoder/ directory and wait for health."""
    print(f"  [....] Restarting backend: {command}")
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return False, "restart command timed out"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")[:300]
        return False, f"exit {proc.returncode}: {detail}"
    return True, "restart command completed"


def main():
    parser = argparse.ArgumentParser(description="ZhiXu verification script")
    parser.add_argument(
        "--restart-cmd",
        default=os.environ.get("ZHIXU_RESTART_CMD", ""),
        help="command that restarts the backend; defaults to 'docker compose restart backend' when Docker is available",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  ZhiXu Verification Script")
    print("=" * 60)
    print()

    # 1. Health check
    print("[1/6] Health Check")
    status, data = api("GET", "/api/health")
    check("Backend reachable", status == 200, f"status={status}")
    check("SeekDB connected", "sqlite-vec" in data.get("seekdb", ""), data.get("seekdb", ""))
    check("PowerContext configured", "powercontext" in data, data.get("powercontext", ""))
    print()

    # 2. Knowledge base - list documents
    print("[2/6] Knowledge Base - Document List")
    status, docs = api("GET", "/api/knowledge/documents")
    check("List documents API", status == 200 and isinstance(docs, list))
    check("Sample data seeded", len(docs) >= 6, f"found {len(docs)} documents")
    if docs:
        titles = [d["title"] for d in docs[:3]]
        check("Document titles valid", all(t for t in titles), f"titles: {titles}")
    print()

    # 3. Knowledge base - hybrid search
    print("[3/6] Knowledge Base - Hybrid Search")
    status, search = api("GET", "/api/knowledge/search?q=binary+tree+traversal&limit=5")
    check("Search API", status == 200)
    check("Search returns results", len(search.get("results", [])) > 0, f"found {search.get('total', 0)} results")
    if search.get("results"):
        top = search["results"][0]
        check("Result has score", "score" in top and top["score"] > 0, f"top score: {top.get('score', 0)}")
        check("Result has snippet", len(top.get("snippet", "")) > 0, f"snippet length: {len(top.get('snippet', ''))}")
    print()

    # 4. Review coach - mark mastery
    print("[4/6] Review Coach - Memory Write (PowerContext)")
    topics = [
        ("verify-tree", "learning", "auto verification test"),
        ("verify-graph", "mastered", "auto verification test"),
        ("verify-dp", "needs_review", "auto verification test"),
    ]
    all_marked = True
    for topic, mastery, note in topics:
        status, resp = api("POST", "/api/review/mastery", {
            "user_id": "verify-test",
            "topic": topic,
            "mastery": mastery,
            "note": note,
        })
        if status != 200 or not resp.get("ok"):
            all_marked = False
    check("Mark 3 topics", all_marked, "wrote 3 learning state memories to PowerContext")

    # Read back
    time.sleep(1)
    status, review = api("GET", "/api/review/status/verify-test")
    check("Get review status", status == 200)
    tracked = len(review.get("topics", []))
    check("Topics tracked", tracked >= 3, f"tracking {tracked} topics")
    recs = len(review.get("recommendations", []))
    check("Recommendations generated", recs > 0, f"generated {recs} recommendations")
    print()

    # 5. Chat - search + memory fusion + restart persistence
    print("[5/6] Chat - SeekDB Retrieval + PowerContext Memory")
    nonce = f"verify-{int(time.time())}"
    question = f"{nonce}: What are the traversal methods for binary trees?"
    status, chat = api("POST", "/api/chat/message", {
        "message": question,
        "user_id": "verify-test",
    })
    check("Chat API", status == 200)
    check("Chat returns sources", len(chat.get("sources", [])) > 0, f"retrieved {len(chat.get('sources', []))} sources from SeekDB")
    if chat.get("sources"):
        src = chat["sources"][0]
        check("Source has relevance score", src.get("score", 0) > 0, f"score: {src.get('score', 0)}")

    # Ask the same question again: the first interaction must be recalled from PowerContext.
    status, chat2 = api("POST", "/api/chat/message", {
        "message": question,
        "user_id": "verify-test",
    })
    memory = chat2.get("memory_context") or ""
    check("Memory written and recalled", status == 200 and nonce in memory, f"recalled {len(memory)} bytes of prepared context")
    check("Recalled memory matches question", "traversal" in memory.lower(), f"marker {nonce} found in memory context")

    # Restart the backend process, then ask again. Memory must still be recalled.
    restart_cmd = args.restart_cmd
    if not restart_cmd and shutil.which("docker"):
        restart_cmd = "docker compose restart backend"
    if restart_cmd:
        restarted, detail = restart_backend(restart_cmd)
        check("Backend restarted", restarted, detail)
        check("Backend healthy after restart", wait_for_health(), "GET /api/health -> 200")
        status, chat3 = api("POST", "/api/chat/message", {
            "message": question,
            "user_id": "verify-test",
        })
        memory_after = chat3.get("memory_context") or ""
        check(
            "Memory survived restart",
            status == 200 and nonce in memory_after,
            f"recalled {len(memory_after)} bytes after restart",
        )
    else:
        skip(
            "Memory survived restart",
            "no restart command found; pass --restart-cmd or set ZHIXU_RESTART_CMD, or install Docker",
        )
    print()

    # 6. PowerContext direct verification
    print("[6/6] PowerContext - Direct Memory Verification")
    status, pc_health = api("GET", "/health/ready", base=PC_BASE)
    check("PowerContext reachable", status == 200, f"health status: {status}")

    # Use backend API to verify memory was written
    status, review = api("GET", "/api/review/status/verify-test")
    check("Memory entries listable", status == 200)
    entry_count = len(review.get("topics", []))
    check("Memory entries exist", entry_count > 0, f"found {entry_count} memory entries via backend API")
    print()

    # Summary
    print("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    failed = total - passed
    print(f"  Results: {passed}/{total} passed, {failed} failed, {len(skipped)} skipped")
    if failed == 0:
        print("  ALL CHECKS PASSED")
    else:
        print("  FAILED CHECKS:")
        for name, ok in results:
            if not ok:
                print(f"    - {name}")
    if skipped:
        print("  SKIPPED CHECKS:")
        for name in skipped:
            print(f"    - {name}")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
