# CalcLab · 后端（前后端分离计算器系统）

软件工程第一次作业的**后端仓库**。只做四件事：接收表达式、安全解析计算、校验与异常处理、
把每次成功计算持久化到 SQLite 数据库。页面与交互在配套的前端仓库 `832402229_calculator_frontend` 中。

> **在线接口地址（部署后填这里）**：`https://832402229_calculator_backend-xxxx.onrender.com`
> **健康检查**：`GET /api/health` → `{"success": true, "data": {"status": "ok"}}`

---

## 1. 项目简介

| 项目 | 说明 |
| --- | --- |
| 名称 | 前后端分离计算器系统 · 后端 API |
| 技术栈 | Python 3.10+（实测 3.13）/ 仅标准库 `http.server` + `sqlite3`，**零第三方依赖** |
| 核心文件 | `calculator.py` 表达式解析与计算、`server.py` HTTP 接口与数据库、`tests/` 自动化测试 |
| 支持运算 | `+ - * /`、括号、一元正负号、小数、`^` 乘方、`%` 百分号 |
| 主要接口 | `POST /api/calculate`、`GET /api/history`、`DELETE /api/history/{id}`、`DELETE /api/history`、`GET /api/health` |

## 2. 环境要求

- Python 3.10 及以上（无需 pip 安装任何库，`requirements.txt` 为空说明）
- 无需安装数据库：使用 Python 内置 SQLite

## 3. 安装与启动

```bash
git clone https://github.com/832402229/832402229_calculator_backend.git
cd 832402229_calculator_backend

# 启动服务（首次运行会自动建库建表）
python server.py
# 看到 CalcLab backend API listening on http://0.0.0.0:8000 即为成功

# 想换端口：
CALCULATOR_PORT=5000 python server.py      # Linux / macOS
$env:CALCULATOR_PORT=5000; python server.py  # Windows PowerShell
```

启动后先用浏览器确认：

- 接口说明：<http://127.0.0.1:8000/>
- 健康检查：<http://127.0.0.1:8000/api/health>

## 4. 配置说明（全部通过环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `8000` | 监听端口（Render 等平台会自动注入该变量） |
| `CALCULATOR_PORT` | 空 | 显式指定端口，优先级高于 `PORT` |
| `CALCULATOR_HOST` | `0.0.0.0` | 监听地址 |
| `CALCULATOR_DB` | `backend/calculator.db` | SQLite 数据库文件路径 |
| `CORS_ORIGIN` | `*` | 允许跨域的前端来源；正式环境建议填具体域名 |

## 5. 数据库初始化

- 首次启动 `python server.py` 会自动执行 `CREATE TABLE IF NOT EXISTS`，**无需手工执行 SQL**。
- 表结构：

```sql
CREATE TABLE IF NOT EXISTS history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,  -- 主键，自增
    expression  TEXT NOT NULL,                      -- 计算表达式
    result      REAL NOT NULL,                      -- 计算结果
    created_at  TEXT NOT NULL                       -- 计算时间（UTC，ISO 8601）
);
```

- 重置数据库：删除数据库文件后重启即可。
- 查看数据：`sqlite3 calculator.db "select * from history order by id desc limit 5;"`

## 6. API 文档

### 6.1 计算

```http
POST /api/calculate
Content-Type: application/json

{ "expression": "(1+2)*3" }
```

成功（200）：

```json
{
  "success": true,
  "data": {
    "id": 12,
    "expression": "(1+2)*3",
    "result": 9,
    "created_at": "2026-10-05T06:20:38+00:00"
  }
}
```

失败（400，表达式非法 / 除零 / 括号不匹配等）：

```json
{ "success": false, "error": { "message": "division by zero" } }
```

### 6.2 历史

```http
GET /api/history?limit=100      → {"success": true, "data": [ {记录}, ... ]}   # 按 id 倒序
DELETE /api/history/12          → {"success": true, "data": {"deleted": 12}}
DELETE /api/history             → {"success": true, "data": {"deleted": 3}}   # 清空
GET /api/health                 → {"success": true, "data": {"status": "ok", "database": "up"}}
```

状态码约定：`200` 成功；`400` 参数或表达式错误；`404` 记录/接口不存在；`500` 数据库异常。

## 7. 计算模块说明（为什么不用 eval）

`calculator.py` 自己实现了一个完整的词法分析 + 语法分析（递归下降解析器）：

```
输入 "3*-2+(1+2)*4"
   │ ① 分词：识别数字、运算符、括号，并校验非法字符
   ▼
② 语法分析：按优先级递归下降（表达式 → 项 → 因子），一元正负号在"因子"层处理
   ▼
③ 求值：直接从语法树算出结果
```

- **全程不使用 `eval` / `exec`**，用户输入永远只是数据，不会被当作代码执行；
- 一元正负号在因子层解析，所以 `-5`、`3*-2`、`-(-3)` 都正确；
- 除零、括号不匹配、非法字符、超长表达式都会抛出带说明的 `CalculationError`；
- 结果统一规整到 10 位小数（`0.1 + 0.2` 返回 `0.3`，而不是 `0.30000000000000004`）。

## 8. 测试

```bash
python tests/test_calculator.py   # 计算核心单元测试（4 个）
python tests/test_api.py          # 接口集成测试：真起 HTTP 服务，9 个用例
# 或在装好 pytest 的环境下：
pytest -q
```

覆盖：四则运算、优先级、括号、一元正负号、小数精度、除零、非法表达式、
历史落库与顺序、删除单条与清空、健康检查、404。

## 9. 部署到 Render

1. 把本仓库推到 GitHub；
2. Render 控制台 → **New +** → **Web Service**（或 **Blueprint**，仓库已含 `render.yaml`）；
3. 配置：

   | 配置项 | 值 |
   | --- | --- |
   | Runtime | `Python 3` |
   | Build Command | 留空（无第三方依赖） |
   | Start Command | `python server.py` |
   | Health Check Path | `/api/health` |
   | Instance Type | `Free` |

4. 环境变量：`PYTHON_VERSION=3.12.6`、`CORS_ORIGIN=*`；
5. 部署完成后访问 `https://<服务名>.onrender.com/api/health` 验证。

> 免费实例长时间无访问会休眠，首次打开需等待约 30~50 秒；
> 实例磁盘在"重新部署"时重置（正常现象），如需长期保留可把 `CALCULATOR_DB`
> 指向持久磁盘目录，或改用托管 PostgreSQL。

## 10. 目录结构

```
832402229_calculator_backend/
├── server.py            # HTTP 接口、参数校验、SQLite 持久化、CORS
├── calculator.py        # 表达式分词 + 递归下降解析 + 求值（无 eval）
├── __init__.py          # 使 backend 可作为包导入
├── requirements.txt     # 无第三方依赖（仅说明）
├── render.yaml          # Render 一键部署配置
├── tests/
│   ├── test_calculator.py   # 计算核心单元测试
│   └── test_api.py          # 接口集成测试
├── codestyle.md         # 代码规范（PEP 8 + Google Python Style Guide）
└── README.md
```
