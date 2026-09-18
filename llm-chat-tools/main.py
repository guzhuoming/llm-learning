import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


from schemas import (
    ChatRequest, ChatResponse, Usage,
    PaymentClassifyResult, SentimentResult, SummarizeResult,
)
from llm_client import call_llm_structured, chat_with_tools

app = FastAPI(title="LLM Chat API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 场景 → Pydantic 模型映射
SCENE_MODELS = {
    "payment_classify": PaymentClassifyResult,
    "sentiment": SentimentResult,
    "summarize": SummarizeResult,
}

async def health():
    return {"status": "ok"}

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    统一对话接口，支持多场景结构化输出。
    """
    model_cls = SCENE_MODELS.get(req.scene)
    if not model_cls:
        raise HTTPException(status_code=400, detail=f"不支持的场景: {req.scene}")

    try:
        result, usage = await call_llm_structured(
            message=req.message,
            scene=req.scene,
            result_model=model_cls,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return ChatResponse(
        scene=req.scene,
        result=result,
        usage=Usage(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        ),
    )

# 本次新增
class ToolChatRequest(BaseModel):
    message: str

class ToolChatResponse(BaseModel):
    answer: str
    tool_calls: list
    usage: dict
    rounds: int

@app.post("/chat/tools", response_model=ToolChatResponse)
async def chat_tools(req: ToolChatRequest):
    """带工具调用的对话接口"""
    try:
        result = await chat_with_tools(req.message)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))