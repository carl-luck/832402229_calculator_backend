# Backend coding style

- 使用 Python 3.10+，采用 4 个空格缩进和 `snake_case` 命名。
- HTTP 层只负责请求校验、状态码和 JSON 响应；表达式解析集中在 `calculator.py`。
- 数据库访问使用参数化 SQL，禁止把用户输入拼接进 SQL。
- 表达式解析禁止 `eval`、`exec` 和动态导入；新增运算符时应先补充词法规则和边界校验。
- 错误以明确的 `4xx` 状态码和 `{ "success": false, "error": { "message": "..." } }` 返回。
- 修改后至少运行 `python -m py_compile calculator.py server.py`，并手动检查健康、计算、历史和删除接口。

