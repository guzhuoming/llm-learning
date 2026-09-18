import requests
import json

API_KEY = "sk-166bd5f18f324b78ae5490b9ddd046ac"
URL = "https://api.deepseek.com/v1/chat/completions"

# ==== System Prompt：定义角色、枚举、输出格式 ====
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

def classify(question: str) -> dict:
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
        "temperature": 0,          # 分类任务要确定性
        "response_format": {"type": "json_object"},  # JSON Mode
    }
    resp = requests.post(URL, headers=headers, json=data, timeout=30)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)

# 1. 定义枚举常量，方便校验
VALID_CATEGORIES = {"退款问题", "到账问题", "费率问题", "账户问题", "风控问题", "其他"}
VALID_PRIORITIES = {"高", "中", "低"}

def classify_with_retry(question, max_retry=3):
    for i in range(max_retry):
        try:
            # 调用你刚才写好的 classify 函数
            result = classify(question)
            
            # 2. 强校验逻辑（这是支付场景必须的）
            if result.get("category") not in VALID_CATEGORIES:
                raise ValueError(f"非法 category: {result.get('category')}")
            if result.get("priority") not in VALID_PRIORITIES:
                raise ValueError(f"非法 priority: {result.get('priority')}")
            if not isinstance(result.get("need_human"), bool):
                raise ValueError(f"need_human 必须是 bool: {result.get('need_human')}")
            
            return result  # 校验通过，返回结果
            
        except Exception as e:
            print(f"⚠️ 第 {i+1} 次尝试失败: {e}")
            if i == max_retry - 1:
                # 3. 兜底策略：连续失败转人工
                print("❌ 连续重试失败，自动转人工处理。")
                return {"category": "其他", "priority": "高", "need_human": True}


# ==== 测试 ====
if __name__ == "__main__":
    tests = [
        "我昨天买的商品退款还没到账，都三天了",
        "你们的费率为什么这么高？",
        "我的账户被冻结了，怎么解冻？",
        "请问怎么修改绑定手机号？",
    ]
    for q in tests:
        result = classify(q)
        print(f"问题：{q}")
        print(f"结果：{result}\n")