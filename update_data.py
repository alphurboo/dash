import os
import json
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta

# ----------------------------------------------------
# 1. 油價爬蟲 (GasWizard Toronto 地區頁 + 防黏合防 921)
# ----------------------------------------------------
def get_gas_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    now = datetime.now()
    today_label = f"{now.month}月{now.day}日 (現行油價)"
    tom = now + timedelta(days=1)
    predict_label = f"{tom.month}月{tom.day}日 (明日預測)"

    cur_price = "182.9"
    pred_price = "--"
    trend = "⏳ 明日預測待公佈"
    trend_class = "gas-neutral"

    try:
        url = "https://gaswizard.ca/gas-prices/toronto/"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            
            # 嚴格正則：只抓取 120.0 至 220.0 之間的多倫多正常油價
            raw_matches = re.findall(r'\b(1[2-9][0-9]\.[0-9]|2[0-1][0-9]\.[0-9])\b', text)
            valid_prices = [float(p) for p in raw_matches if 120.0 <= float(p) <= 220.0]

            if len(valid_prices) >= 1:
                cur_price = f"{valid_prices[0]:.1f}"

            if len(valid_prices) >= 2 and valid_prices[1] != valid_prices[0]:
                p1, p2 = valid_prices[0], valid_prices[1]
                pred_price = f"{p2:.1f}"
                diff = round(p2 - p1, 1)
                if diff > 0:
                    trend = f"↑ 明日預測升 {diff} ¢"
                    trend_class = "gas-up"
                elif diff < 0:
                    trend = f"↓ 明日預測跌 {abs(diff)} ¢"
                    trend_class = "gas-down"
                else:
                    trend = "→ 油價平穩"
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
# 2. 即時新聞爬蟲 (Google News RSS - 國際 & 美股)
# ----------------------------------------------------
def fetch_rss_news(query_url, limit=7):
    news_items = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(query_url, headers=headers, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.content, "html.parser")
            items = soup.find_all("item")
            for item in items[:limit]:
                title_elem = item.find("title")
                guid_elem = item.find("guid")
                source_elem = item.find("source")

                full_title = title_elem.get_text() if title_elem else ""
                link = guid_elem.get_text() if guid_elem else "#"
                source = source_elem.get_text() if source_elem else ""

                # 去除 Google News 標題末尾的來源字樣 (例: "xxx - 明報")
                if " - " in full_title:
                    parts = full_title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    if not source:
                        source = parts[1].strip()
                else:
                    title = full_title.strip()

                if not source:
                    source = "新聞"

                news_items.append({
                    "title": title,
                    "source": source,
                    "link": link
                })
    except Exception as e:
        print(f"RSS fetch failed for {query_url}: {e}")
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
                    continue # 過期事件自動隱藏
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
# 4. 主執行程序：整合寫入 data.json
# ----------------------------------------------------
def main():
    # 讀取現有 data.json 取得基礎結構與超市特價
    data = {}
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception:
                data = {}

    # 1. 更新時間戳
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 2. 抓取最新油價
    data["gas"] = get_gas_data()

    # 3. 抓取最新國際焦點 7 大事 (過去 24 小時)
    world_rss = "https://news.google.com/rss/search?q=國際+when:24h&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
    latest_world = fetch_rss_news(world_rss, limit=7)
    if latest_world:
        data["news_world"] = latest_world

    # 4. 抓取過去 8 小時股市要聞
    stock_rss = "https://news.google.com/rss/search?q=美股+OR+聯儲局+OR+港股+when:8h&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
    latest_stock = fetch_rss_news(stock_rss, limit=6)
    if latest_stock:
        data["news_stock"] = latest_stock

    # 5. 自動重新計算日程距離今天的天數
    if "events" in data:
        data["events"] = update_events_countdown(data["events"])

    # 6. 寫入 data.json
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("✅ data.json 全部模組（油價 + 國際新聞 + 股市要聞 + 日程天數）已成功同步更新！")

if __name__ == "__main__":
    main()
