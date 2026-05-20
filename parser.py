import asyncio
import json
import aiohttp
from bs4 import BeautifulSoup
from database import add_airdrop, save_airdrop_analysis
from ai_filter import analyze_airdrop

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

TIMEOUT = aiohttp.ClientTimeout(total=15)


async def parse_airdrops_io(session: aiohttp.ClientSession):
    url = "https://airdrops.io/latest/"
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
            soup = BeautifulSoup(html, "lxml")
            items = soup.select(".airdrop-item, .post-item, article, .card")
            results = []
            for item in items[:5]:
                title_tag = item.select_one("h2, .title, .entry-title, a")
                link_tag = item.select_one("a")
                desc_tag = item.select_one(".description, p, .summary")
                if title_tag and link_tag:
                    title = title_tag.get_text(strip=True)
                    link = link_tag.get("href", "")
                    if link.startswith("/"):
                        link = "https://airdrops.io" + link
                    desc = desc_tag.get_text(strip=True)[:300] if desc_tag else ""
                    results.append({"title": title, "link": link, "description": desc, "category": "Other"})
            return results
    except Exception as e:
        print(f"[airdrops.io] Ошибка: {e}")
        return []


async def parse_dropsEarn(session: aiohttp.ClientSession):
    url = "https://dropsearn.com/airdrops/"
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
            soup = BeautifulSoup(html, "lxml")
            items = soup.select(".airdrop-card, .post, article, .item")
            results = []
            for item in items[:5]:
                title_tag = item.select_one("h2, .entry-title, a")
                link_tag = item.select_one("a")
                desc_tag = item.select_one(".entry-summary, p, .excerpt")
                if title_tag and link_tag:
                    title = title_tag.get_text(strip=True)
                    link = link_tag.get("href", "")
                    if link.startswith("/"):
                        link = "https://dropsearn.com" + link
                    desc = desc_tag.get_text(strip=True)[:300] if desc_tag else ""
                    results.append({"title": title, "link": link, "description": desc, "category": "Other"})
            return results
    except Exception as e:
        print(f"[dropsearn.com] Ошибка: {e}")
        return []


async def parse_coinmarketcap(session: aiohttp.ClientSession):
    url = "https://coinmarketcap.com/airdrops/"
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
            soup = BeautifulSoup(html, "lxml")
            items = soup.select("tr")
            results = []
            for item in items[1:6]:
                cols = item.select("td")
                if len(cols) >= 3:
                    title = cols[0].get_text(strip=True)
                    link_tag = cols[0].select_one("a")
                    link = link_tag.get("href", "") if link_tag else ""
                    if link.startswith("/"):
                        link = "https://coinmarketcap.com" + link
                    desc = cols[2].get_text(strip=True)[:300] if len(cols) > 2 else ""
                    results.append({"title": title, "link": link, "description": desc, "category": "Other"})
            return results
    except Exception as e:
        print(f"[coinmarketcap] Ошибка: {e}")
        return []


async def fetch_and_save_airdrops():
    async with aiohttp.ClientSession() as session:
        all_results = []
        all_results.extend(await parse_airdrops_io(session))
        await asyncio.sleep(2)
        all_results.extend(await parse_dropsEarn(session))
        await asyncio.sleep(2)
        all_results.extend(await parse_coinmarketcap(session))

        added = 0
        for airdrop in all_results:
            try:
                airdrop_id = await add_airdrop(
                    title=airdrop["title"],
                    description=airdrop["description"],
                    link=airdrop["link"],
                    category=airdrop["category"]
                )
                # Google AI анализ
                analysis = await analyze_airdrop(airdrop["title"], airdrop["description"], airdrop["link"])
                await save_airdrop_analysis(
                    airdrop_id=airdrop_id,
                    scam=analysis["scam_probability"],
                    difficulty=analysis["difficulty"],
                    profit=analysis["expected_profit_usd"],
                    time_req=analysis["time_required_minutes"],
                    summary=analysis["summary"],
                    red_flags=json.dumps(analysis["red_flags"], ensure_ascii=False)
                )
                added += 1
            except Exception as e:
                print(f"[Parser] Не удалось сохранить аирдроп: {e}")

        print(f"[Parser] Добавлено {added} новых аирдропов (с Google AI анализом)")
        return added
