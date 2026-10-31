"""dev 全链路模拟测试:本地 OpenAI 兼容桩服务器扮演 MiniMax,验证

导入 → 上下文 → dev(请求/解析/应用补丁) → after 验证全绿 的完整机制。

说明:该测试不调用真实 MiniMax,仅证明 dev→apply→verify 链路正确;
真实 MiniMax 调用记录在拿到 API Key 后由 `sddctx dev` 生成。
"""

import asyncio
import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from sddctx.agent import run_dev
from sddctx.config import Settings
from sddctx.importer import run_import
from sddctx.runner import run_verify

_HOME = Path(__file__).resolve().parents[1]
TASK = (
    "为订单查询增加最小金额筛选条件:customer_orders 支持 min_total 参数,"
    "含边界,不影响既有调用"
)

# 桩服务器返回的“模型输出”:正确实现 SPEC-003 的 min_total 过滤
CANNED_IMPLEMENTATION = """分析:repository.for_customer 需要按 SPEC-003-2 实现含边界过滤。

=== FILE: sample-project/src/checkout/repository.py ===
```python
\"\"\"订单仓储。内存实现,提供订单查询接口(订单查询/查询接口/customer_orders 的底层实现)。\"\"\"

from __future__ import annotations

from decimal import Decimal

from checkout.models import Order


class OrderRepository:
    \"\"\"按客户查询订单、保存订单的内存仓储。\"\"\"

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}

    def add(self, order: Order) -> None:
        self._orders[order.order_id] = order

    def get(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def for_customer(
        self,
        customer_id: str,
        min_total: Decimal | None = None,
    ) -> list[Order]:
        \"\"\"按客户查询订单,结果按创建时间升序排列(同一时间按 order_id 升序)。

        SPEC-003:提供 min_total 时,只返回订单总额 >= min_total 的订单
        (含边界);未提供时返回全部订单。
        \"\"\"
        orders = [order for order in self._orders.values() if order.customer_id == customer_id]
        orders.sort(key=lambda order: (order.created_at, order.order_id))
        if min_total is not None:
            orders = [order for order in orders if order.total() >= min_total]
        return orders
```

已完成 SPEC-003 的最小金额过滤,保持排序与兼容性不变。
"""

# 初始(未实现)版 repository.py:测试自备确定初始态,不依赖真实工程当前进度
INITIAL_REPOSITORY = '''"""订单仓储。内存实现,提供订单查询接口(订单查询/查询接口/customer_orders 的底层实现)。"""

from __future__ import annotations

from decimal import Decimal

from checkout.models import Order


class OrderRepository:
    """按客户查询订单、保存订单的内存仓储。"""

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}

    def add(self, order: Order) -> None:
        self._orders[order.order_id] = order

    def get(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def for_customer(
        self,
        customer_id: str,
        min_total: Decimal | None = None,
    ) -> list[Order]:
        """按客户查询订单,结果按创建时间升序排列(同一时间按 order_id 升序)。

        SPEC-003 要求:提供 min_total 时,只返回订单总额 >= min_total 的订单
        (含边界,min_total 与某订单总额相等时该订单必须返回)。

        TODO(SPEC-003): min_total 过滤行为尚未实现,当前直接返回全部订单。
        """
        orders = [order for order in self._orders.values() if order.customer_id == customer_id]
        orders.sort(key=lambda order: (order.created_at, order.order_id))
        if min_total is not None:
            # SPEC-003 未实现:此处应过滤订单总额 >= min_total 的订单。
            pass
        return orders
'''


class _StubMiniMaxHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", 0))
        request_body = json.loads(self.rfile.read(length) or b"{}")
        self.server.last_request = request_body  # 供断言检查请求结构
        payload = {
            "model": request_body.get("model", "stub-model"),
            "choices": [
                {
                    "message": {"role": "assistant", "content": CANNED_IMPLEMENTATION, "reasoning_content": ""},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:  # 静默
        pass


def _make_settings(tmp_path: Path) -> tuple[Settings, HTTPServer]:
    """在临时 home 中复制规格与业务工程;配置指向临时目录与本机桩服务器。"""
    shutil.copytree(_HOME / "sample-project", tmp_path / "sample-project")
    shutil.copytree(_HOME / "specs", tmp_path / "specs")
    # 固定为“未实现”初始态,使测试与真实工程的修改进度无关
    (tmp_path / "sample-project" / "src" / "checkout" / "repository.py").write_text(
        INITIAL_REPOSITORY, encoding="utf-8"
    )
    httpd = HTTPServer(("127.0.0.1", 0), _StubMiniMaxHandler)
    port = httpd.server_address[1]
    settings = Settings.load()
    for name, value in {
        "home": tmp_path,
        "seekdb_path": tmp_path / ".sddctx-data" / "seekdb",
        "db_query_log": tmp_path / "records" / "db-query-log.md",
        "powercontext_log": tmp_path / "records" / "powercontext-log.md",
        "powercontext_url": "http://127.0.0.1:1",  # 不可达:验证降级路径
        "minimax_api_key": "stub-key-for-pipeline-test",
        "minimax_base_url": f"http://127.0.0.1:{port}/v1",
        "minimax_model": "MiniMax-M3.1-Flash",
    }.items():
        object.__setattr__(settings, name, value)
    return settings, httpd


def test_dev_pipeline_end_to_end(tmp_path: Path):
    settings, httpd = _make_settings(tmp_path)
    run_import(settings)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        result = run_dev(settings, TASK, "task-001")
        # 请求结构正确(OpenAI 兼容)
        request_body = httpd.last_request
        assert request_body["model"] == "MiniMax-M3.1-Flash"
        assert any(message["role"] == "system" for message in request_body["messages"])
        user_messages = [m for m in request_body["messages"] if m["role"] == "user"]
        assert "SPEC-003-1" in user_messages[0]["content"]  # 上下文进入了提示词
        # 补丁已应用
        assert [Path(item.path).name for item in result.applied] == ["repository.py"]
        repository = tmp_path / "sample-project" / "src" / "checkout" / "repository.py"
        assert "order.total() >= min_total" in repository.read_text(encoding="utf-8")
        # 修改前快照与开发留档
        assert "TODO(SPEC-003)" in (result.run_dir / "before" / "src" / "checkout" / "repository.py").read_text(encoding="utf-8")
        devlog = (result.run_dir / "devlog.md").read_text(encoding="utf-8")
        assert "MiniMax 开发记录" in devlog and "修改 `sample-project/src/checkout/repository.py`" in devlog
        assert (result.run_dir / "context.md").exists()
        assert (result.run_dir / "code.diff.md").exists()
        diff_text = (result.run_dir / "code.diff.md").read_text(encoding="utf-8")
        assert "+            orders = [order for order in orders if order.total() >= min_total]" in diff_text
        assert "TODO(SPEC-003)" in diff_text  # 旧行被移除(以 - 开头出现)
    finally:
        httpd.shutdown()

    # after 验证:目标 7 例 + 回归全量全部转绿
    outcome = run_verify(settings, "task-001", ["tests/test_order_query_filter.py"], "after")
    assert outcome.accepted, outcome.summary
    assert outcome.target.passed and outcome.regression is not None and outcome.regression.passed
