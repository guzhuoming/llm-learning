import json
from typing import Any

# ============ 工具定义（给 LLM 看的 schema） ============
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "query_transaction",
            "description": "根据交易 ID 查询交易详情，包括金额、状态、时间",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {
                        "type": "string",
                        "description": "交易 ID，例如 12345"
                    }
                },
                "required": ["transaction_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_risk_rules",
            "description": "查询当前风控规则，返回规则列表",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]

# ============ 工具的真实执行函数 ============
def query_transaction(transaction_id: str) -> dict:
    """模拟查交易（真实场景应查数据库）"""
    # 这里用假数据演示
    fake_db = {
        "12345": {
            "transaction_id": "12345",
            "amount": 9800,
            "currency": "CNY",
            "status": "success",
            "time": "2026-09-17T03:00:00",
            "merchant": "某某商户",
            "location": "境外",
        },
        "67890": {
            "transaction_id": "67890",
            "amount": 100,
            "currency": "CNY",
            "status": "failed",
            "time": "2026-09-16T12:00:00",
            "merchant": "测试商户",
            "location": "境内",
        },
    }
    return fake_db.get(transaction_id, {"error": "交易不存在"})

def query_risk_rules() -> dict:
    """模拟查风控规则"""
    return {
        "rules": [
            "境外 + 凌晨 + 大额 = 高风险",
            "同一卡短时间多次交易 = 可疑",
            "金额超过 5000 且首次交易 = 人工审核",
        ]
    }

# ============ 工具路由表 ============
TOOL_FUNCTIONS = {
    "query_transaction": query_transaction,
    "query_risk_rules": query_risk_rules,
}

def execute_tool(name: str, arguments: str) -> Any:
    """
    根据工具名和参数执行工具。
    arguments 是 JSON 字符串，需要先解析。
    """
    if name not in TOOL_FUNCTIONS:
        return {"error": f"未知工具: {name}"}
    
    try:
        args = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        return {"error": f"参数不是合法 JSON: {arguments}"}
    
    try:
        return TOOL_FUNCTIONS[name](**args)
    except Exception as e:
        return {"error": f"工具执行失败: {str(e)}"}