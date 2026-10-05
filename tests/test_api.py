"""后端接口冒烟测试（只依赖标准库，直接用 pytest 或 python 运行）。

运行：
    pytest -q                 # 需要已安装 pytest
    python tests/test_api.py  # 无需 pytest 也能跑
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ["CALCULATOR_DB"] = str(Path(tempfile.mkdtemp(prefix="calclab-test-")) / "test.db")

import server  # noqa: E402


class ApiTestCase(unittest.TestCase):
    """启动一个真实的 HTTP 服务，用真请求验证四个必做功能。"""

    @classmethod
    def setUpClass(cls):
        server.initialize_database()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.CalculatorHandler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    # ------------------------------------------------------------------ 工具
    def call(self, method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode())

    def clear(self):
        self.call("DELETE", "/api/history")

    # ------------------------------------------------- 功能 1：基本四则运算
    def test_basic_operations(self):
        self.clear()
        for expression, expected in [("12+8", 20), ("12-8", 4), ("12*8", 96), ("12/8", 1.5)]:
            status, body = self.call("POST", "/api/calculate", {"expression": expression})
            self.assertEqual(status, 200, body)
            self.assertTrue(body["success"])
            self.assertEqual(body["data"]["result"], expected)

    # ------------------------------------------------- 功能 2：复合表达式
    def test_compound_expressions(self):
        self.clear()
        cases = {
            "1+2*3": 7,        # 优先级
            "(1+2)*3": 9,      # 括号
            "10/2+7": 12,
            "8-3*2": 2,
            "-5+8": 3,         # 一元正负号
            "3*-2": -6,
            "1.5+2.25": 3.75,  # 小数
        }
        for expression, expected in cases.items():
            status, body = self.call("POST", "/api/calculate", {"expression": expression})
            self.assertEqual(status, 200, f"{expression} -> {body}")
            self.assertAlmostEqual(body["data"]["result"], expected, places=9, msg=expression)

    def test_result_has_no_floating_point_noise(self):
        """0.1 + 0.2 必须返回 0.3，而不是 0.30000000000000004。"""
        status, body = self.call("POST", "/api/calculate", {"expression": "0.1+0.2"})
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["result"], 0.3)

    def test_invalid_expressions_and_division_by_zero(self):
        for expression in ["1/0", "1+", "(1+2", "1++2*", "sqrt(", ""]:
            status, body = self.call("POST", "/api/calculate", {"expression": expression})
            self.assertEqual(status, 400, f"{expression!r} 应该被拒绝，实际 {status} {body}")
            self.assertFalse(body["success"])

    def test_failed_calculation_not_stored(self):
        self.clear()
        self.call("POST", "/api/calculate", {"expression": "1/0"})
        _, body = self.call("GET", "/api/history")
        self.assertEqual(body["data"], [])

    # ------------------------------------------------- 功能 3：历史持久化
    def test_history_persisted_and_ordered(self):
        self.clear()
        for expression in ["1+2", "5*8", "(2+3)*4"]:
            self.call("POST", "/api/calculate", {"expression": expression})
        status, body = self.call("GET", "/api/history")
        self.assertEqual(status, 200)
        records = body["data"]
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["expression"], "(2+3)*4")  # 最新在最前
        for record in records:
            self.assertIn("expression", record)
            self.assertIn("result", record)
            self.assertIn("created_at", record)

    # ------------------------------------------------- 功能 4：删除历史
    def test_delete_one_and_all(self):
        self.clear()
        _, created = self.call("POST", "/api/calculate", {"expression": "8*8"})
        record_id = created["data"]["id"]

        status, body = self.call("DELETE", f"/api/history/{record_id}")
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["deleted"], record_id)

        _, history = self.call("GET", "/api/history")
        self.assertEqual(history["data"], [])

        # 再删一次应该是 404
        status, _ = self.call("DELETE", f"/api/history/{record_id}")
        self.assertEqual(status, 404)

        self.call("POST", "/api/calculate", {"expression": "1+1"})
        status, body = self.call("DELETE", "/api/history")
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["deleted"], 1)

    # ------------------------------------------------- 其它
    def test_health(self):
        status, body = self.call("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["status"], "ok")
        self.assertEqual(body["data"]["database"], "up")

    def test_unknown_endpoint_returns_404(self):
        status, body = self.call("GET", "/api/nope")
        self.assertEqual(status, 404)
        self.assertFalse(body["success"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
