"""测试环境自检用的最小 HTTP 桩服务（只用标准库）。

定位：证明「JSON 用例 → HTTP 请求 → 字段断言 → Allure 附件」这条管线可用。
它不是被测服务的业务实现，也不产出任何业务结论；业务结论只能来自真实服务。
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator

TRIGGERS = {"DAILY_BATCH", "APP_OPENED", "TASK_CHANGED", "PREFERENCE_CHANGED"}
SNOOZE_PATH = re.compile(r"^/internal/v1/reminders/(?P<decision_id>[^/]+)/snooze$")
EVALUATE_PATH = "/internal/v1/reminders/evaluate"
DISPATCH_PATH = "/internal/v1/reminders/dispatch-due"

COMPLETED_USER = "stub-user-completed"


class StubState:
    """桩服务的进程内状态：只用于自检幂等与排程行为。"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.decisions: dict[str, str] = {}

    def decision_for(self, request_id: str) -> str | None:
        with self.lock:
            return self.decisions.get(request_id)

    def remember(self, request_id: str) -> str:
        with self.lock:
            decision_id = self.decisions.get(request_id)
            if decision_id is None:
                decision_id = f"decision-{uuid.uuid4().hex}"
                self.decisions[request_id] = decision_id
            return decision_id


class _Handler(BaseHTTPRequestHandler):
    server_version = "ReminderTestStub/1.0"
    protocol_version = "HTTP/1.1"
    state: StubState

    def log_message(self, *args: Any) -> None:  # 静音 stdlib 访问日志
        return

    def _request_id(self) -> str:
        return self.headers.get("X-Request-ID") or uuid.uuid4().hex

    def _send(self, status: int, payload: Any, request_id: str) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-ID", request_id)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str, request_id: str, retryable: bool = False) -> None:
        self._send(
            status,
            {"code": code, "message": message, "request_id": request_id, "retryable": retryable},
            request_id,
        )

    def _read_body(self, request_id: str) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._error(400, "INVALID_REQUEST", "请求体不是合法 JSON", request_id)
            return None
        if not isinstance(parsed, dict):
            self._error(400, "INVALID_REQUEST", "请求体必须是 JSON 对象", request_id)
            return None
        return parsed

    def do_GET(self) -> None:  # noqa: N802 - stdlib 命名
        request_id = self._request_id()
        if self.path == "/healthz":
            self._send(200, {"status": "ok"}, request_id)
            return
        self._error(404, "NOT_FOUND", f"未知路径 {self.path}", request_id)

    def do_POST(self) -> None:  # noqa: N802 - stdlib 命名
        request_id = self._request_id()
        body = self._read_body(request_id)
        if body is None:
            return
        if self.path == EVALUATE_PATH:
            self._evaluate(body, request_id)
            return
        if self.path == DISPATCH_PATH:
            self._dispatch(body, request_id)
            return
        matched = SNOOZE_PATH.match(self.path)
        if matched:
            self._snooze(body, request_id, matched.group("decision_id"))
            return
        self._error(404, "NOT_FOUND", f"未知路径 {self.path}", request_id)

    def _evaluate(self, body: dict[str, Any], request_id: str) -> None:
        missing = [key for key in ("request_id", "user_id", "task_date", "trigger") if not body.get(key)]
        if missing:
            self._error(400, "INVALID_REQUEST", f"缺少必填字段：{', '.join(missing)}", request_id)
            return
        trigger = body["trigger"]
        if trigger not in TRIGGERS:
            self._error(400, "INVALID_REQUEST", f"未知 trigger 取值：{trigger}", request_id)
            return
        if trigger != "APP_OPENED" and "last_open_at" in body:
            self._error(400, "INVALID_REQUEST", "last_open_at 仅允许在 trigger=APP_OPENED 时传入", request_id)
            return

        decision_id = self.state.decision_for(body["request_id"])
        reused = decision_id is not None
        if decision_id is None:
            decision_id = self.state.remember(body["request_id"])

        if body["user_id"] == COMPLETED_USER:
            payload = {
                "decision_id": decision_id,
                "status": "REUSED" if reused else "CREATED",
                "reason_code": "TASK_COMPLETED",
                "should_remind": False,
                "strategy_version": "v1",
            }
        else:
            payload = {
                "decision_id": decision_id,
                "status": "REUSED" if reused else "CREATED",
                "reason_code": "ELIGIBLE",
                "should_remind": True,
                "scheduled_at": "2026-09-20T19:30:00Z",
                "channel": "push",
                "user_segment": "PASSIVE",
                "strategy_version": "v1",
            }
        self._send(200, payload, request_id)

    def _dispatch(self, body: dict[str, Any], request_id: str) -> None:
        batch_size = body.get("batch_size", 50)
        if not isinstance(batch_size, int) or not 1 <= batch_size <= 50:
            self._error(400, "INVALID_REQUEST", "batch_size 必须是 1..50 的整数", request_id)
            return
        self._send(
            200,
            {"scanned": 0, "claimed": 0, "sent": 0, "cancelled": 0, "failed": 0, "unknown": 0, "retried": 0, "finished": True},
            request_id,
        )

    def _snooze(self, body: dict[str, Any], request_id: str, decision_id: str) -> None:
        if not body.get("request_id") or not body.get("user_id"):
            self._error(400, "INVALID_REQUEST", "缺少必填字段：request_id, user_id", request_id)
            return
        if decision_id != "decision-allowed":
            self._error(400, "INVALID_REQUEST", f"未知 decision_id：{decision_id}", request_id)
            return
        self._send(
            200,
            {
                "schedule_id": f"schedule-{uuid.uuid4().hex}",
                "status": "SCHEDULED",
                "reason_code": "ELIGIBLE",
                "snooze_until": "2026-09-20T20:30:00Z",
                "channel": "push",
                "schedule_type": "SNOOZE",
            },
            request_id,
        )


class StubService:
    def __init__(self, server: ThreadingHTTPServer) -> None:
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, name="reminder-test-stub", daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> "StubService":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@contextmanager
def start_stub() -> Iterator[StubService]:
    handler = type("_BoundHandler", (_Handler,), {"state": StubState()})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    service = StubService(server).start()
    try:
        yield service
    finally:
        service.stop()
