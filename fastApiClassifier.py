import json
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal

# ================= 配置区 =================
API_KEY = "sk-166bd5f18f324b78ae5490b9ddd046ac"
URL = "https://api.deepseek.com/v1/chat/completions"

SYSTEM_PROMPT = """你是一个支付问题分类器。请对用户输入的支付问题进行分类。

分类标准：
- category（必须从以下枚举中选一个）：
  - 退款问题：退款申请、退款进度、退款失败
  - 到账问题：收款未到账、到账延迟、金额不符
  - 费率问题：手续费、费率计算、扣费异常
  - 账户问题：登录、实名、绑定、账户冻结
  - 风控问题：交易被拦截、限额、风险提示
  - 其他：以上都不属于

- priority（必须从以下枚举中选一个）：
  - 高：涉及资金损失、账户安全、无法交易
  - 中：影响使用但可绕过、有明确诉求
  - 低：咨询类、无紧急诉求

- need_human（布尔值）：
  - true：涉及资金纠纷、账户安全、投诉、复杂问题
  - false：标准问题、可自动解答

只输出 JSON，不要任何解释、不要 markdown 代码块。
格式：
{"category": "...", "priority": "...", "need_human": true/false}
"""

# ================= Pydantic 模型 =================
Category = Literal["退款问题", "到账问题", "费率问题", "账户问题", "风控问题", "其他"]
Priority = Literal["高", "中", "低"]

class ClassifyRequest(BaseModel):
    question: str

class ClassifyResponse(BaseModel):
    category: Category
    priority: Priority
    need_human: bool

# ================= 核心逻辑 =================
async def classify(question: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(URL, headers=headers, json=data)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)

async def classify_with_retry(question: str, max_retry: int = 3) -> dict:
    for i in range(max_retry):
        try:
            raw = await classify(question)
            # 用 Pydantic 自动校验（替代手写 if）
            validated = ClassifyResponse(**raw)
            return validated.model_dump()
        except Exception as e:
            print(f"第 {i+1} 次尝试失败: {e}")
            if i == max_retry - 1:
                print("连续重试失败，自动转人工处理。")
                return {"category": "其他", "priority": "高", "need_human": True}
    return {"category": "其他", "priority": "高", "need_human": True}

# ================= FastAPI 应用 =================
app = FastAPI(
    title="支付问题智能分类器 API",
    description="输入支付问题，返回分类、优先级、是否需要人工",
    version="1.0.0",
)

# CORS，允许前端跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    """健康检查接口"""
    return {"status": "ok"}

@app.post("/classify", response_model=ClassifyResponse)
async def classify_api(req: ClassifyRequest):
    """分类接口"""
    try:
        result = await classify_with_retry(req.question)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ================= 本地调试 =================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
