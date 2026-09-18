import json
from typing import Any
from pydantic import BaseModel, Field
from typing import Literal

# ============================================================
# 1. 用 Pydantic 定义每个工具的参数
# ============================================================

class QueryTransactionArgs(BaseModel):
    """查询交易详情"""
    transaction_id: str = Field(..., description="交易 ID，例如 12345")

class QueryRiskRulesArgs(BaseModel):
    """查询风控规则，无参数"""
    pass

class CreateRefundArgs(BaseModel):
    """发起退款（高风险，仅示例）"""
    transaction_id: str = Field(..., description="要退款的交易 ID")
    amount: float = Field(..., gt=0, description="退款金额，单位元")
    reason: Literal["用户申请", "系统错误", "风控拦截"] = Field(
        ..., description="退款原因"
    )

# ============================================================
# 2. 工具注册表：name -> (描述, 参数模型, 真实函数)
# ============================================================

def query_transaction(transaction_id: str) -> dict:
    """真实执行：模拟查交易"""
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
    """真实执行：模拟查风控规则"""
    return {
        "rules": [
            "境外 + 凌晨 + 大额 = 高风险",
            "同一卡短时间多次交易 = 可疑",
            "金额超过 5000 且首次交易 = 人工审核",
        ]
    }

def create_refund(transaction_id: str, amount: float, reason: str) -> dict:
    """真实执行：模拟发起退款"""
    return {
        "success": True,
        "transaction_id": transaction_id,
        "amount": amount,
        "reason": reason,
        "message": "退款申请已提交",
    }

# ============================================================
# 3. 工具注册表
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
        "description": "对指定交易发起退款。当用户明确要求退款时使用。这是一个高风险操作。",
        "args_model": CreateRefundArgs,
        "func": create_refund,
    },
}

# ============================================================
# 4. 自动生成 Tool Schema（给 LLM 用）
# ============================================================

def build_tools_schema() -> list:
    """从注册表自动生成 OpenAI 风格的 tools schema"""
    tools = []
    for name, info in TOOL_REGISTRY.items():
        model = info["args_model"]
        # Pydantic 自动生成 JSON Schema
        params_schema = model.model_json_schema()
        # 去掉 Pydantic 加的 title/description，只保留结构
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
# 5. 执行工具（带 Pydantic 校验）
# ============================================================

def execute_tool(name: str, arguments: str) -> Any:
    """
    根据工具名和参数执行工具。
    arguments 是 JSON 字符串，先用 Pydantic 校验再执行。
    """
    if name not in TOOL_REGISTRY:
        return {"error": f"未知工具: {name}"}

    # 解析 JSON
    try:
        args_dict = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        return {"error": f"参数不是合法 JSON: {arguments}"}

    # ★ 用 Pydantic 校验参数
    args_model = TOOL_REGISTRY[name]["args_model"]
    try:
        validated = args_model(**args_dict)
    except Exception as e:
        return {"error": f"参数校验失败: {str(e)}"}

    # 执行真实函数
    func = TOOL_REGISTRY[name]["func"]
    try:
        return func(**validated.model_dump())
    except Exception as e:
        return {"error": f"工具执行失败: {str(e)}"}