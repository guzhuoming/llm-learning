from pydantic import BaseModel, Field
from typing import Literal, Union

# ============ 请求 ============
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    scene: Literal["payment_classify", "sentiment", "summarize"] = "payment_classify"

# ============ 场景 1：支付分类 ============
class PaymentClassifyResult(BaseModel):
    category: Literal["退款问题", "到账问题", "费率问题", "账户问题", "风控问题", "其他"]
    priority: Literal["高", "中", "低"]
    need_human: bool

# ============ 场景 2：情感分析 ============
class SentimentResult(BaseModel):
    sentiment: Literal["正面", "负面", "中性"]
    confidence: float = Field(..., ge=0.0, le=1.0)

# ============ 场景 3：摘要 ============
class SummarizeResult(BaseModel):
    summary: str = Field(..., max_length=200)
    keywords: list[str]

# ============ 统一响应 ============
class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatResponse(BaseModel):
    scene: str
    result: Union[PaymentClassifyResult, SentimentResult, SummarizeResult]
    usage: Usage
