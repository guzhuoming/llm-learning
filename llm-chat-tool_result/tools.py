import json
import time
import sqlite3
import logging
from typing import Any, Literal
from pydantic import BaseModel, Field

# ============================================================
# 1. 数据库初始化
# ============================================================

DB_PATH = "llm_tools.db"

def init_db():
    """初始化工具调用日志表"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            tool_name TEXT,
            arguments TEXT,
            result TEXT,
            latency_ms INTEGER,
            success INTEGER
        )
    """)
    conn.commit()
    conn.close()

def log_tool_call(tool_name: str, arguments: str, result: dict,
                  latency_ms: int, success: bool):
    """落库：每次工具调用记录一条"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """INSERT INTO tool_calls
               (timestamp, tool_name, arguments, result, latency_ms, success)
               VALUES (datetime('now'), ?, ?, ?, ?, ?)""",
            (tool_name, arguments, json.dumps(result, ensure_ascii=False),
             latency_ms, int(success))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"落库失败: {e}")

# 启动时初始化
init_db()

# ============================================================
# 2. 脱敏工具
# ============================================================

def mask_card(card_no: str) -> str:
    """卡号脱敏：6222****7890"""
    if not card_no or len(card_no) < 8:
        return "****"
    return card_no[:4] + "****" + card_no[-4:]

def mask_phone(phone: str) -> str:
    """手机号脱敏：138****8888"""
    if not phone or len(phone) < 11:
        return "****"
    return phone[:3] + "****" + phone[-4:]

def mask_dict(data: dict, fields: list) -> dict:
    """对 dict 中指定字段做脱敏"""
    masked = dict(data)
    for f in fields:
        if f in masked and masked[f]:
            if "card" in f:
                masked[f] = mask_card(str(masked[f]))
            elif "phone" in f or "mobile" in f:
                masked[f] = mask_phone(str(masked[f]))
            else:
                masked[f] = "****"
    return masked

# ============================================================
# 3. 截断工具
# ============================================================

def limit_items(items: list, max_items: int = 20) -> dict:
    """大结果截断"""
    if len(items) > max_items:
        return {
            "items": items[:max_items],
            "truncated": True,
            "total": len(items),
            "message": f"结果过多，只展示前 {max_items} 条",
        }
    return {"items": items, "total": len(items), "truncated": False}

# ============================================================
# 4. Pydantic 参数模型
# ============================================================

class QueryTransactionArgs(BaseModel):
    """查询交易详情"""
    transaction_id: str = Field(..., description="交易 ID，例如 12345")

class QueryRiskRulesArgs(BaseModel):
    """查询风控规则，无参数"""
    pass

class CreateRefundArgs(BaseModel):
    """发起退款（高风险）"""
    transaction_id: str = Field(..., description="要退款的交易 ID")
    amount: float = Field(..., gt=0, description="退款金额，单位元")
    reason: Literal["用户申请", "系统错误", "风控拦截"] = Field(
        ..., description="退款原因"
    )

# ============================================================
# 5. 真实执行函数
# ============================================================

def query_transaction(transaction_id: str) -> dict:
    """模拟查交易"""
    fake_db = {
        "12345": {
            "transaction_id": "12345",
            "amount": 9800,
            "currency": "CNY",
            "status": "success",
            "time": "2026-09-17T03:00:00",
            "merchant": "某某商户",
            "location": "境外",
            "card_no": "6222021234567890",   # 演示脱敏
            "phone": "13812345678",           # 演示脱敏
        },
        "67890": {
            "transaction_id": "67890",
            "amount": 100,
            "currency": "CNY",
            "status": "failed",
            "time": "2026-09-16T12:00:00",
            "merchant": "测试商户",
            "location": "境内",
            "card_no": "6222029876543210",
            "phone": "13987654321",
        },
    }
    raw = fake_db.get(transaction_id)
    if not raw:
        return {"error": "交易不存在", "code": "TRANSACTION_NOT_FOUND"}
    # ★ 脱敏后再返回给模型
    return mask_dict(raw, ["card_no", "phone"])

def query_risk_rules() -> dict:
    """模拟查风控规则"""
    return {
        "rules": [
            "境外 + 凌晨 + 大额 = 高风险",
            "同一卡短时间多次交易 = 可疑",
            "金额超过 5000 且首次交易 = 人工审核",
        ]
    }

def create_refund(transaction_id: str, amount: float, reason: str) -> dict:
    """模拟发起退款"""
    return {
        "success": True,
        "transaction_id": transaction_id,
        "amount": amount,
        "reason": reason,
        "message": "退款申请已提交",
    }

# ============================================================
# 6. 工具注册表
# ============================================================

TOOL_REGISTRY = {
    "query_transaction": {
        "description": "根据交易 ID 查询单笔交易的详情，包括金额、状态、时间、商户。当用户询问某笔交易的具体信息时使用。",
        "args_model": QueryTransactionArgs,
        "func": query_transaction,
    },
    "query_risk_rules": {
        "description": "查询当前风控规则列表。当用户询问风控规则、风险判断依据时使用。",
        "args_model": QueryRiskRulesArgs,
        "func": query_risk_rules,
    },
    "create_refund": {
        "description": "对指定交易发起退款。当用户明确要求退款时使用。高风险操作。",
        "args_model": CreateRefundArgs,
        "func": create_refund,
    },
}

# ============================================================
# 7. 自动生成 Tool Schema
# ============================================================

def build_tools_schema() -> list:
    tools = []
    for name, info in TOOL_REGISTRY.items():
        model = info["args_model"]
        params_schema = model.model_json_schema()
        params_schema.pop("title", None)
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": info["description"],
                "parameters": params_schema,
            }
        })
    return tools

TOOLS_SCHEMA = build_tools_schema()

# ============================================================
# 8. 执行工具（生产级：统一格式 + 永不抛异常 + 落库）
# ============================================================

def execute_tool(name: str, arguments: str) -> dict:
    """
    执行工具，返回统一格式的 Tool Result。
    永不抛异常，所有错误都以 {"success": False, "error": ...} 返回。
    """
    start = time.time()
    success = False
    result = None

    try:
        # 1. 工具存在性检查
        if name not in TOOL_REGISTRY:
            result = {"success": False, "error": f"未知工具: {name}"}
            return result

        # 2. 参数 JSON 解析
        try:
            args_dict = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            result = {"success": False, "error": f"参数不是合法 JSON: {arguments}"}
            return result

        # 3. Pydantic 参数校验
        args_model = TOOL_REGISTRY[name]["args_model"]
        try:
            validated = args_model(**args_dict)
        except Exception as e:
            result = {"success": False, "error": f"参数校验失败: {str(e)}"}
            return result

        # 4. 执行真实函数
        func = TOOL_REGISTRY[name]["func"]
        data = func(**validated.model_dump())

        success = True
        result = {"success": True, "data": data, "error": None}

    except Exception as e:
        result = {"success": False, "error": f"工具执行失败: {str(e)}"}

    finally:
        latency_ms = int((time.time() - start) * 1000)
        logging.info(f"tool={name} success={success} latency={latency_ms}ms")
        # ★ 落库
        log_tool_call(name, arguments, result, latency_ms, success)

    return result