import os
import json
import httpx
import logging
from typing import Type, TypeVar, Any
from pydantic import BaseModel, ValidationError
from tools import TOOLS_SCHEMA, execute_tool

from prompts import SYSTEM_PROMPTS

API_KEY = os.getenv("DEEPSEEK_API_KEY")
URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"

T = TypeVar("T", bound=BaseModel)

async def call_llm_structured(
    message: str,
    scene: str,
    result_model: Type[T],
    max_retry: int = 3,
) -> tuple[T, dict]:
    """
    调 LLM 并返回结构化结果。
    返回 (校验后的模型, usage)
    """
    system_prompt = SYSTEM_PROMPTS.get(scene)
    if not system_prompt:
        raise ValueError(f"未知场景: {scene}")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    last_error = None
    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(max_retry):
            try:
                resp = await client.post(URL, headers=headers, json=data)
                resp.raise_for_status()
                body = resp.json()

                content = body["choices"][0]["message"]["content"]
                usage = body.get("usage", {})

                # ★ 用 Pydantic 校验
                parsed = result_model.model_validate_json(content)

                logging.info(f"scene={scene} tokens={usage.get('total_tokens')}")
                return parsed, usage

            except ValidationError as e:
                last_error = e
                logging.warning(f"第{i+1}次校验失败: {e}")
            except Exception as e:
                last_error = e
                logging.warning(f"第{i+1}次调用失败: {e}")

    raise RuntimeError(f"LLM 调用失败，重试 {max_retry} 次: {last_error}")


# 本次新增
async def chat_with_tools(
    user_message: str,
    max_tool_rounds: int = 5,
) -> dict:
    """
    带工具调用的对话。
    返回 {answer, tool_calls, usage}
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    
    messages = [{"role": "user", "content": user_message}]
    all_tool_calls = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    
    async with httpx.AsyncClient(timeout=60) as client:
        for round_idx in range(max_tool_rounds):
            data = {
                "model": MODEL,
                "messages": messages,
                "tools": TOOLS_SCHEMA,
                "tool_choice": "auto",
                "temperature": 0,
            }
            
            resp = await client.post(URL, headers=headers, json=data)
            resp.raise_for_status()
            body = resp.json()
            
            # 累计 usage
            usage = body.get("usage", {})
            for k in total_usage:
                total_usage[k] += usage.get(k, 0)
            
            msg = body["choices"][0]["message"]
            finish_reason = body["choices"][0].get("finish_reason")
            
            # 没有工具调用，直接返回
            if not msg.get("tool_calls"):
                return {
                    "answer": msg.get("content", ""),
                    "tool_calls": all_tool_calls,
                    "usage": total_usage,
                    "rounds": round_idx + 1,
                }
            
            # 有工具调用：把 assistant 消息加进历史
            messages.append(msg)
            
            # 逐个执行工具
            for tool_call in msg["tool_calls"]:
                func_name = tool_call["function"]["name"]
                arguments = tool_call["function"]["arguments"]
                
                logging.info(f"调用工具: {func_name}({arguments})")
                result = execute_tool(func_name, arguments)
                
                all_tool_calls.append({
                    "name": func_name,
                    "arguments": arguments,
                    "result": result,
                })
                
                # 把工具结果作为 tool 消息回传
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })
        
        # 超过最大轮次
        return {
            "answer": "工具调用轮次过多，已终止",
            "tool_calls": all_tool_calls,
            "usage": total_usage,
            "rounds": max_tool_rounds,
        }
