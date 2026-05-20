import json
import re
import aiohttp

# ===== ХАРДКОД КЛЮЧА CEREBRAS =====
# Впиши свой ключ сюда (начинается с csk-):
OPENAI_API_KEY = "csk-8kpd9nmcr8h9986p3rw999h4cftvehxwwt9pkvrkkv5rvj5k"
AI_API_URL = "https://api.cerebras.ai/v1/chat/completions"
AI_MODEL = "llama3.1-70b"

TIMEOUT = aiohttp.ClientTimeout(total=30)


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```json\s*|^```\s*|```$", "", text, flags=re.MULTILINE).strip()
    return text


def _fallback_analysis(title: str, description: str, link: str) -> dict:
    """Если Cerebras недоступен — простая эвристика."""
    text = (title + " " + (description or "") + " " + link).lower()
    score = 0
    flags = []
    if "connect wallet" in text and ("private key" in text or "seed phrase" in text or "secret phrase" in text):
        score += 60
        flags.append("Запрос приватного ключа/сид-фразы")
    if "guaranteed" in text or "100%" in text or "instant withdraw" in text:
        score += 40
        flags.append("Гарантированная/мгновенная прибыль")
    if "send eth" in text or "send bnb" in text or "deposit first" in text:
        score += 30
        flags.append("Требуется отправка крипты")
    if "referral" in text or "invite" in text:
        score += 10
    if score > 80:
        diff = 1
        profit = "0 (вероятный скам)"
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
        "summary": "Базовая эвристика: проверьте проект вручную." if flags else "Выглядит стандартно.",
        "red_flags": flags if flags else ["Нет явных флагов"]
    }


async def analyze_airdrop(title: str, description: str, link: str) -> dict:
    # ОТЛАДКА: показываем статус ключа в логах
    print(f"[DEBUG] API_KEY начинается с: {OPENAI_API_KEY[:10] if OPENAI_API_KEY else 'EMPTY'}...")
    print(f"[DEBUG] API_KEY длина: {len(OPENAI_API_KEY) if OPENAI_API_KEY else 0}")

    if not OPENAI_API_KEY or OPENAI_API_KEY == "csk-ВАШ_РЕАЛЬНЫЙ_КЛЮЧ_ЗДЕСЬ" or len(OPENAI_API_KEY) < 20:
        print("[DEBUG] Ключ не валиден, используем fallback")
        return _fallback_analysis(title, description, link)

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""Проанализируй крипто-аирдроп и верни ТОЛЬКО JSON без markdown, без текста вне JSON:
{{
  "scam_probability": число от 0 до 100,
  "difficulty": число от 1 до 5,
  "expected_profit_usd": "диапазон в долларах, например 10-50",
  "time_required_minutes": число,
  "summary": "краткий вывод на русском, 1-2 предложения",
  "red_flags": ["список подозрительных моментов или пустой список"]
}}

Название: {title}
Описание: {description or "нет"}
Ссылка: {link}"""

    try:
        print(f"[DEBUG] Отправляем запрос к {AI_API_URL}")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                AI_API_URL,
                headers=headers,
                json={
                    "model": AI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 600
                },
                timeout=TIMEOUT
            ) as resp:
                print(f"[DEBUG] Ответ Cerebras: HTTP {resp.status}")
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"[Cerebras] HTTP {resp.status}: {error_text[:200]}")
                    return _fallback_analysis(title, description, link)

                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                print(f"[DEBUG] Ответ ИИ: {content[:100]}...")
                clean = _extract_json(content)
                result = json.loads(clean)
                result["scam_probability"] = max(0, min(100, int(result.get("scam_probability", 50))))
                result["difficulty"] = max(1, min(5, int(result.get("difficulty", 3))))
                print(f"[DEBUG] ИИ-анализ успешен: риск {result['scam_probability']}%")
                return result

    except Exception as e:
        print(f"[Cerebras] Ошибка: {e}")
        return _fallback_analysis(title, description, link)
