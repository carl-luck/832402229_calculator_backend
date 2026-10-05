"""HTTP API for the calculator assignment（纯后端，只提供 /api/* 接口）。

本仓库是作业要求中的**后端仓库**：只负责
    1. 接收表达式；2. 安全解析与计算；3. 校验与异常处理；4. 用 SQLite 持久化计算历史。

前端在同名的 `calclab-frontend` 仓库中，通过 HTTP + JSON 调用本服务的接口，
因此本项目是标准的前后端分离结构：后端不渲染页面，前端不算结果。

本地运行
--------
    python server.py                # 默认监听 0.0.0.0:8000
    CALCULATOR_PORT=5000 python server.py

云端运行（Render 等）
--------------------
平台会通过环境变量 `PORT` 指定端口，因此启动命令用：
    python server.py
`server.py` 会优先读取 `CALCULATOR_PORT`，其次读取平台注入的 `PORT`。

环境变量
--------
| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `8000` | 监听端口（Render 等平台会自动注入） |
| `CALCULATOR_PORT` | 空 | 显式指定端口，优先级高于 `PORT` |
| `CALCULATOR_HOST` | `0.0.0.0` | 监听地址 |
| `CALCULATOR_DB` | `backend/calculator.db` | SQLite 数据库文件路径 |
| `CORS_ORIGIN` | `*` | 允许跨域访问的前端来源，可填具体域名 |

接口一览
--------
| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| POST | `/api/calculate` | 计算表达式并写入历史，body: `{"expression": "1+2*3"}` |
| GET | `/api/history?limit=100` | 查询历史（按 id 倒序） |
| DELETE | `/api/history/{id}` | 删除指定历史记录 |
| DELETE | `/api/history` | 清空全部历史 |
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

try:
    from .calculator import CalculationError, evaluate
except ImportError:
    from calculator import CalculationError, evaluate


BACKEND_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.environ.get("CALCULATOR_DB", BACKEND_DIR / "calculator.db"))
HOST = os.environ.get("CALCULATOR_HOST", "0.0.0.0")
# Render 和大多数 PaaS 会注入 PORT；本地默认 8000。
PORT = int(os.environ.get("CALCULATOR_PORT", os.environ.get("PORT", "8000")))
# 允许的前端来源，默认 * 便于助教用任意地址测试；正式环境建议填具体域名。
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    with closing(get_connection()) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expression TEXT NOT NULL,
                result REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def normalize_result(value: float) -> float:
    """把结果规整到 10 位小数，消除浮点误差（0.1 + 0.2 应该是 0.3）。"""
    rounded = round(float(value), 10)
    return 0.0 if rounded == 0 else rounded


def save_calculation(expression: str, result: float) -> dict:
    result = normalize_result(result)
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            "INSERT INTO history (expression, result, created_at) VALUES (?, ?, ?)",
            (expression, result, created_at),
        )
        connection.commit()
        return {
            "id": cursor.lastrowid,
            "expression": expression,
            "result": result,
            "created_at": created_at,
        }


def list_history(limit: int = 100) -> list[dict]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT id, expression, result, created_at FROM history "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_history_item(record_id: int) -> bool:
    with closing(get_connection()) as connection:
        cursor = connection.execute("DELETE FROM history WHERE id = ?", (record_id,))
        connection.commit()
        return cursor.rowcount > 0


def delete_all_history() -> int:
    with closing(get_connection()) as connection:
        cursor = connection.execute("DELETE FROM history")
        connection.commit()
        return cursor.rowcount


def count_history() -> int:
    with closing(get_connection()) as connection:
        row = connection.execute("SELECT COUNT(*) FROM history").fetchone()
    return int(row[0])


class CalculatorHandler(BaseHTTPRequestHandler):
    server_version = "CalculatorAPI/1.0"

    def log_message(self, format: str, *args) -> None:
        # Keep the default access log while avoiding sensitive request bodies.
        super().log_message(format, *args)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        path, query = self._request_parts()
        if path == "/":
            # 后端不提供页面，只在根路径返回接口说明，便于助教确认服务已启动。
            self._send_json(
                HTTPStatus.OK,
                {
                    "success": True,
                    "service": "calclab-backend",
                    "message": "前后端分离计算器 · 后端 API（前端见 calclab-frontend 仓库）",
                    "endpoints": [
                        "GET    /api/health",
                        "POST   /api/calculate   {\"expression\": \"1+2*3\"}",
                        "GET    /api/history?limit=100",
                        "DELETE /api/history/{id}",
                        "DELETE /api/history",
                    ],
                },
            )
            return
        if path == "/api/health":
            try:
                total = count_history()
                database = "up"
            except sqlite3.Error as error:  # pragma: no cover - 仅在数据库异常时触发
                total, database = -1, f"down: {error}"
            self._send_json(
                HTTPStatus.OK,
                {
                    "success": True,
                    "data": {
                        "status": "ok",
                        "database": database,
                        "history_count": total,
                        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    },
                },
            )
            return
        if path == "/api/history":
            values = parse_qs(query)
            try:
                limit = int(values.get("limit", ["100"])[0])
            except ValueError:
                self._send_error(HTTPStatus.BAD_REQUEST, "limit must be an integer")
                return
            if not 1 <= limit <= 500:
                self._send_error(HTTPStatus.BAD_REQUEST, "limit must be between 1 and 500")
                return
            self._send_json(HTTPStatus.OK, {"success": True, "data": list_history(limit)})
            return
        self._send_error(HTTPStatus.NOT_FOUND, "endpoint not found")

    def do_POST(self) -> None:
        path, _ = self._request_parts()
        if path != "/api/calculate":
            self._send_error(HTTPStatus.NOT_FOUND, "endpoint not found")
            return
        try:
            payload = self._read_json()
            expression = payload.get("expression")
            if expression is None:
                expression = payload.get("formula")
            if not isinstance(expression, str):
                raise CalculationError("expression must be a string")
            result = evaluate(expression)
            record = save_calculation(expression.strip(), result)
        except CalculationError as error:
            self._send_error(HTTPStatus.BAD_REQUEST, str(error))
            return
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            self._send_error(HTTPStatus.BAD_REQUEST, f"invalid JSON: {error}")
            return
        except sqlite3.Error:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "database error")
            return
        self._send_json(HTTPStatus.OK, {"success": True, "data": record})

    def do_DELETE(self) -> None:
        path, _ = self._request_parts()
        if path == "/api/history":
            deleted = delete_all_history()
            self._send_json(HTTPStatus.OK, {"success": True, "data": {"deleted": deleted}})
            return
        prefix = "/api/history/"
        if path.startswith(prefix):
            raw_id = path[len(prefix):]
            try:
                record_id = int(raw_id)
                if record_id < 1:
                    raise ValueError
            except ValueError:
                self._send_error(HTTPStatus.BAD_REQUEST, "history id must be a positive integer")
                return
            if delete_history_item(record_id):
                self._send_json(HTTPStatus.OK, {"success": True, "data": {"deleted": record_id}})
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "history record not found")
            return
        self._send_error(HTTPStatus.NOT_FOUND, "endpoint not found")

    def _request_parts(self) -> tuple[str, str]:
        parsed = urlsplit(self.path)
        return unquote(parsed.path).rstrip("/") or "/", parsed.query

    def _read_json(self) -> dict:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise json.JSONDecodeError("missing request body", "", 0)
        try:
            length = int(raw_length)
        except ValueError as error:
            raise json.JSONDecodeError("invalid content length", raw_length, 0) from error
        if length < 0 or length > 64 * 1024:
            raise json.JSONDecodeError("request body is too large", "", 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise json.JSONDecodeError("JSON body must be an object", "", 0)
        return payload

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(encoded)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"success": False, "error": {"message": message}})

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def run() -> None:
    initialize_database()
    server = ThreadingHTTPServer((HOST, PORT), CalculatorHandler)
    print(f"CalcLab backend API listening on http://{HOST}:{PORT}")
    print(f"Database file: {DATABASE_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
