import json
import re
import aiohttp

# ===== ВПИШИ СВОЙ КЛЮЧ CEREBRAS =====
# Получи на https://cloud.cerebras.ai/platform
OPENAI_API_KEY = "csk-8kpd9nmcr8h9986p3rw999h4cftvehxwwt9pkvrkkv5rvj5k"  # ← ЗАМЕНИ ЭТО!
AI_API_URL = "https://api.cerebras.ai/v1/chat/completions"
AI_MODEL = "llama3.1-70b"

TIMEOUT = aiohttp.ClientTimeout(total=30)


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```json\s*|^```\s*|```$", "", text, flags=re.MULTILINE).strip()
    return text


def _fallback_analysis(title: str, description: str, link: str) -> dict:
    text = (title + " " + (description or "") + " " + link).lower()
    score = 0
    flags = []
    if "connect wallet" in text and ("private key" in text or "seed phrase" in text):
        score += 60
        flags.append("Запрос приватного ключа")
    if "guaranteed" in text or "100%" in text or "instant withdraw" in text:
        score += 40
        flags.append("Гарантированная прибыль")
    if "send eth" in text or "send bnb" in text:
        score += 30
        flags.append("Требуется отправка крипты")
    if score > 80:
        diff = 1
        profit = "0 (скам)"
    elif score > 40:
        diff = 2
        profit = "10-30"
    else:
        diff = 3
        profit = "30-200"
    return {
        "scam_probability": min(score, 100),
        "difficulty": diff,
        "expected_profit_usd": profit,
        "time_required_minutes": 30,
        "summary": "Базовая эвристика" if flags else "Стандартный аирдроп",
        "red_flags": flags if flags else ["Нет флагов"]
    }


async def analyze_airdrop(title: str, description: str, link: str) -> dict:
    print(f"[AI] KEY length: {len(OPENAI_API_KEY)}, starts with: {OPENAI_API_KEY[:8]}...")
    
    if not OPENAI_API_KEY or "ВАШ" in OPENAI_API_KEY or len(OPENAI_API_KEY) < 20:
        print("[AI] KEY invalid, using fallback")
        return _fallback_analysis(title, description, link)

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""Analyze crypto airdrop, return ONLY JSON:
{{"scam_probability":0-100,"difficulty":1-5,"expected_profit_usd":"10-50","time_required_minutes":30,"summary":"brief Russian conclusion","red_flags":["list or empty"]}}
Title:{title} Desc:{description or 'none'} Link:{link}"""

    try:
        print(f"[AI] Sending to {AI_URL}")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                AI_API_URL,
                headers=headers,
                json={"model": AI_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 400},
                timeout=TIMEOUT
            ) as resp:
                print(f"[AI] Response: HTTP {resp.status}")
                if resp.status != 200:
                    print(f"[AI] Error: {await resp.text()[:100]}")
                    return _fallback_analysis(title, description, link)
                
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                print(f"[AI] Content: {content[:80]}...")
                clean = _extract_json(content)
                result = json.loads(clean)
                result["scam_probability"] = max(0, min(100, int(result.get("scam_probability", 50))))
                result["difficulty"] = max(1, min(5, int(result.get("difficulty", 3))))
                print(f"[AI] Success: risk={result['scam_probability']}%")
                return result
                
    except Exception as e:
        print(f"[AI] Exception: {e}")
        return _fallback_analysis(title, description, link)
