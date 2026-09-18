# LLM Chat Tools

基于 FastAPI + DeepSeek 的 LLM 应用示例，演示 **Function Calling（工具调用）** 的完整实现。

## 项目简介

这是一个生产级骨架的 LLM 应用，支持：

- 通过 HTTP API 调用大模型
- 模型自主决定调用哪些工具（Function Calling）
- 工具参数用 Pydantic 校验
- 工具结果统一格式、脱敏、截断
- 每次工具调用落库（SQLite）用于审计
- FastAPI 自动生成 Swagger 文档

## 架构

```
┌─────────────────────────────────────────────┐
│ 客户端（curl / Swagger） │
└──────────────────────┬──────────────────────┘
│ POST /chat/tools
▼
┌─────────────────────────────────────────────┐
│ FastAPI（main.py） │
│ - 路由 /chat/tools │
│ - Pydantic 请求/响应校验 │
└──────────────────────┬──────────────────────┘
│
▼
┌─────────────────────────────────────────────┐
│ LLM Client（llm_client.py） │
│ - 组装 messages + tools │
│ - 调 DeepSeek API │
│ - 循环处理 tool_calls │
└──────────────────────┬──────────────────────┘
│
┌──────────────┴──────────────┐
▼ ▼
┌──────────────────┐ ┌──────────────────┐
│ DeepSeek API │ │ Tools（tools.py）│
│ （LLM 推理） │ │ - 参数校验 │
│ │ │ - 工具执行 │
│ │ │ - 脱敏 │
│ │ │ - 落库 │
└──────────────────┘ └────────┬─────────┘
▼
┌──────────────────┐
│ SQLite │
│ llm_tools.db │
└──────────────────┘
```




## 项目结构

```
llm-chat-tools/
├── main.py # FastAPI 应用，/chat/tools 接口
├── llm_client.py # LLM 调用 + 工具循环
├── tools.py # 工具定义 + 执行 + 脱敏 + 落库
├── schemas.py # Pydantic 模型
├── prompts.py # System Prompt
├── requirements.txt # 依赖
├── .gitignore # Git 忽略规则
└── README.md # 本文档
```



## 快速开始

### 1. 安装依赖

```bash
python3 -m venv myenv
source myenv/bin/activate
pip install -r requirements.txt
```

### 2. 设置 API Key

```
export DEEPSEEK_API_KEY="sk-你的key"
```

**注意**：`export` 只在当前终端会话有效，关掉就失效。生产环境用密钥管理服务。

### 3. 启动服务

```
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. 访问 Swagger 文档

```
http://localhost:8000/docs
```

## 使用示例

### 查交易

```bash
curl -X POST http://localhost:8000/chat/tools \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我查一下交易 12345"}'
```



返回：

```json
{
  "answer": "交易 12345 金额 9800 元，状态成功，卡号 6222****7890，手机 138****5678。",
  "tool_calls": [
    {
      "name": "query_transaction",
      "arguments": "{\"transaction_id\": \"12345\"}",
      "result": {"success": true, "data": {...}}
    }
  ],
  "usage": {"total_tokens": 250},
  "rounds": 2
}
```



### 查风控规则

```bash
curl -X POST http://localhost:8000/chat/tools \
  -H "Content-Type: application/json" \
  -d '{"message": "当前风控规则有哪些？"}'
```



## 技术亮点

### 1. Function Calling 完整闭环

- 模型输出 `tool_calls`（要调什么、传什么参数）
- 程序执行真实函数
- 结果作为 `role: "tool"` 消息回传
- 模型基于结果生成最终回答
- **模型只"提议"，程序"执行"**

### 2. Tool Schema 用 Pydantic 自动生成

```py
class QueryTransactionArgs(BaseModel):
    transaction_id: str = Field(..., description="交易 ID")

# 自动生成 JSON Schema
schema = QueryTransactionArgs.model_json_schema()
```



**一份定义两处用**：给 LLM 当说明书，给程序做参数校验。

### 3. 参数校验

Pydantic 自动校验模型填的参数：

- 类型不对 → 拦截
- 枚举值非法 → 拦截
- 数值范围越界 → 拦截

**模型乱填也进不来。**

### 4. Tool Result 统一格式

```json
{"success": true, "data": {...}, "error": null}
{"success": false, "error": "..."}
```

- **永不抛异常**，所有错误都转成结构化结果
- 不中断 Agent 循环
- 模型能根据错误决策

### 5. 脱敏

卡号、手机号返回给模型前自动打码：

```
6222021234567890 → 6222****7890
13812345678      → 138****5678
```



### 6. 落库审计

每次工具调用记录到 SQLite：

| 字段       | 说明     |
| :--------- | :------- |
| timestamp  | 时间     |
| tool_name  | 工具名   |
| arguments  | 参数     |
| result     | 结果     |
| latency_ms | 耗时     |
| success    | 是否成功 |

支撑**审计、统计、监控**。

### 7. 防死循环

工具调用循环有**轮次上限**，防止模型反复调同一工具。

## 数据库查询

用 Python 查询落库记录：

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('llm_tools.db')
print('表:', conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall())
print('记录数:', conn.execute('SELECT COUNT(*) FROM tool_calls').fetchone()[0])
for row in conn.execute('SELECT * FROM tool_calls ORDER BY id DESC LIMIT 5'):
    print(row)
"
```



统计各工具调用次数：

```sql
SELECT tool_name, COUNT(*) FROM tool_calls GROUP BY tool_name;
```



## 安全设计

- **模型不执行函数**：执行权在程序手里
- **参数强校验**：Pydantic 拦截非法输入
- **脱敏**：敏感字段不暴露给模型
- **落库审计**：可追溯
- **只读优先**：当前示例工具都是查询，高风险操作（退款）需二次确认

## 生产级扩展方向

| 方向               | 说明                |
| :----------------- | :------------------ |
| API Key 认证       | 保护接口，防滥用    |
| 限流               | 每用户每分钟限制    |
| LLM 调用落库       | 记录 token、耗时    |
| 高风险工具二次确认 | 资金操作人工审批    |
| RAG                | 检索知识库增强回答  |
| Streaming          | 打字流式输出        |
| 多厂商路由         | 按场景选不同模型    |
| 单元测试           | pytest 覆盖核心逻辑 |

## 技术栈

| 组件     | 用途                  |
| :------- | :-------------------- |
| FastAPI  | Web 框架              |
| Uvicorn  | ASGI 服务器           |
| httpx    | 异步 HTTP 客户端      |
| Pydantic | 数据校验、Schema 生成 |
| SQLite   | 落库审计              |
| DeepSeek | LLM 服务              |

## 参考资料

- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [Pydantic 官方文档](https://docs.pydantic.dev/)
- [DeepSeek API 文档](https://platform.deepseek.com/api-docs/)
- [OpenAI Function Calling 文档](https://platform.openai.com/docs/guides/function-calling)

## License