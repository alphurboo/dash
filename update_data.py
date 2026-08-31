import os
import json
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re
from datetime import datetime, timedelta

# ----------------------------------------------------
# 1. 油價爬蟲 (未出預測絕不拿今日充數，強制顯示 --)
# ----------------------------------------------------
def get_gas_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    now = datetime.now()
    today_dt = now.date()
    tom_dt = today_dt + timedelta(days=1)

    today_label = f"{today_dt.month}月{today_dt.day}日 (現行油價)"
    predict_label = f"{tom_dt.month}月{tom_dt.day}日 (明日預測)"

    # 預設狀態：明日絕對是 "--"
    cur_price = "182.9"
    pred_price = "--"
    trend = "⏳ 明日預測待公佈"
    trend_class = "gas-neutral"

    # 明日關鍵字特徵
    tom_kws = [
        tom_dt.strftime("%b %d").lower(),
        tom_dt.strftime("%B %d").lower(),
        f"{tom_dt.strftime('%b').lower()} {tom_dt.day}",
        f"{tom_dt.strftime('%B').lower()} {tom_dt.day}",
        f"sept {tom_dt.day}",
        f"{tom_dt.month}/{tom_dt.day}",
        "tomorrow"
    ]

    # 今日關鍵字特徵
    today_kws = [
        today_dt.strftime("%b %d").lower(),
        today_dt.strftime("%B %d").lower(),
        f"{today_dt.strftime('%b').lower()} {today_dt.day}",
        f"{today_dt.strftime('%B').lower()} {today_dt.day}",
        f"{today_dt.month}/{today_dt.day}",
        "today"
    ]

    try:
        url = "https://gaswizard.ca/gas-prices/toronto/"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            
            found_today = None
            found_tom = None

            rows = soup.find_all(["tr", "li", "div", "p"])
            for row in rows:
                text = row.get_text(separator=" ", strip=True).lower()
                price_match = re.findall(r'\b(1[2-9][0-9]\.[0-9]|2[0-1][0-9]\.[0-9])\b', text)
                if not price_match:
                    continue
                
                val = float(price_match[0])
                if not (120.0 <= val <= 220.0):
                    continue

                # 只有明確包含「明日日期」的行才認定為明日
                if any(kw in text for kw in tom_kws):
                    if not found_tom:
                        found_tom = val
                # 包含「今日日期」的行
                elif any(kw in text for kw in today_kws):
                    if not found_today:
                        found_today = val

            if found_today:
                cur_price = f"{found_today:.1f}"

            # 只有真真正正抓到明日獨立新數據，才計算升跌
            if found_tom is not None:
                pred_price = f"{found_tom:.1f}"
                diff = round(found_tom - float(cur_price), 1)
                if diff > 0:
                    trend = f"↑ 明日預測升 {diff} ¢"
                    trend_class = "gas-up"
                elif diff < 0:
                    trend = f"↓ 明日預測跌 {abs(diff)} ¢"
                    trend_class = "gas-down"
                else:
                    trend = "→ 油價平穩"
                    trend_class = "gas-neutral"
            else:
                pred_price = "--"
                trend = "⏳ 明日預測待公佈"
                trend_class = "gas-neutral"

    except Exception as e:
        print(f"Gas fetch error: {e}")

    return {
        "current_label": today_label,
        "current_price": cur_price,
        "predict_label": predict_label,
        "predict_price": pred_price,
        "trend": trend,
        "trend_class": trend_class
    }

# ----------------------------------------------------
# 2. 即時新聞爬蟲 (標準 XML 解析完整 URL)
# ----------------------------------------------------
def fetch_rss_news(query_url, limit=7):
    news_items = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(query_url, headers=headers, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            for item in items[:limit]:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                source = item.findtext("source", "").strip()

                if not link or not link.startswith("http"):
                    guid = item.findtext("guid", "").strip()
                    if guid.startswith("http"):
                        link = guid
                    elif guid:
                        link = f"https://news.google.com/rss/articles/{guid}"
                    else:
                        link = "#"

                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    if not source:
                        source = parts[1].strip()

                if not source:
                    source = "新聞"

                if title:
                    news_items.append({
                        "title": title,
                        "source": source,
                        "link": link
                    })
    except Exception as e:
        print(f"RSS fetch error: {e}")
    return news_items

# ----------------------------------------------------
# 3. 日程與除淨天數動態計算
# ----------------------------------------------------
def update_events_countdown(events_data):
    today = datetime.now().date()
    
    def process_list(ev_list):
        result = []
        for ev in ev_list:
            try:
                ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").date()
                days_left = (ev_date - today).days
                if days_left < 0:
                    continue
                elif days_left == 0:
                    badge = "今日"
                else:
                    badge = f"{days_left} 日後"
                
                ev_copy = dict(ev)
                ev_copy["days_left"] = days_left
                ev_copy["status_badge"] = badge
                result.append(ev_copy)
            except Exception:
                result.append(ev)
        return result

    if "macro" in events_data:
        events_data["macro"] = process_list(events_data["macro"])
    if "stocks" in events_data:
        events_data["stocks"] = process_list(events_data["stocks"])
    return events_data

# ----------------------------------------------------
# 4. 主程序
# ----------------------------------------------------
def main():
    data = {}
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception:
                data = {}

    data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. 抓取油價
    data["gas"] = get_gas_data()

    # 2. 抓取國際焦點 7 大事
    world_rss = "https://news.google.com/rss/search?q=國際+when:24h&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
    latest_world = fetch_rss_news(world_rss, limit=7)
    if latest_world:
        data["news_world"] = latest_world

    # 3. 抓取美股要聞
    stock_rss = "https://news.google.com/rss/search?q=美股+OR+聯儲局+OR+港股+when:8h&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
    latest_stock = fetch_rss_news(stock_rss, limit=6)
    if latest_stock:
        data["news_stock"] = latest_stock

    # 4. 更新日程倒數
    if "events" in data:
        data["events"] = update_events_countdown(data["events"])

    # 5. 寫入 data.json
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("✅ data.json 更新完成！")

if __name__ == "__main__":
    main()
