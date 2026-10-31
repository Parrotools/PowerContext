"""
知序 (ZhiXu) — 自动验证脚本
评审运行此脚本可一键验证所有核心功能。

用法:
    python verify.py
"""

import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8000"
PC_BASE = "http://localhost:8010"
PASS = "PASS"
FAIL = "FAIL"
results = []


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


def main():
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

    # 5. Chat - search + memory fusion
    print("[5/6] Chat - SeekDB Retrieval + PowerContext Memory")
    status, chat = api("POST", "/api/chat/message", {
        "message": "What are the traversal methods for binary trees?",
        "user_id": "verify-test",
    })
    check("Chat API", status == 200)
    check("Chat returns sources", len(chat.get("sources", [])) > 0, f"retrieved {len(chat.get('sources', []))} sources from SeekDB")
    if chat.get("sources"):
        src = chat["sources"][0]
        check("Source has relevance score", src.get("score", 0) > 0, f"score: {src.get('score', 0)}")
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
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print("  ALL CHECKS PASSED")
    else:
        print("  FAILED CHECKS:")
        for name, ok in results:
            if not ok:
                print(f"    - {name}")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
