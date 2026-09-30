import os
import json
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re
import html
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# 固定使用多倫多當地時區 (EDT/EST)
TORONTO_TZ = ZoneInfo("America/Toronto")

# ----------------------------------------------------
# 1. 油價爬蟲 (CityNews Toronto / 鎖定多倫多時區)
# ----------------------------------------------------
def get_gas_data(existing_data):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    # 強制獲取多倫多當地日期，避免 GitHub Actions 伺服器 UTC 提早跳日
    now = datetime.now(TORONTO_TZ)
    today_dt = now.date()
    tom_dt = today_dt + timedelta(days=1)

    today_label = f"{today_dt.month}月{today_dt.day}日 (現行油價)"
    predict_label = f"{tom_dt.month}月{tom_dt.day}日 (明日預測)"

    old_gas = existing_data.get("gas", {}) if isinstance(existing_data, dict) else {}
    old_pred = old_gas.get("predict_price", "--")
    old_cur = old_gas.get("current_price", "--")

    # 若昨日已存有預測價，今日自動滾動為現行價
    cur_price = old_pred if (old_pred and old_pred != "--") else (old_cur if old_cur else "--")
    pred_price = "--"
    trend = "⏳ 明日預測待公佈"
    trend_class = "gas-neutral"

    try:
        url = "https://toronto.citynews.ca/toronto-gta-gas-prices/"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(separator=" ", strip=True)

            # 解析生效日期與目標價格 (例: on September 30, 2026 to an average of 180.9 cent)
            pattern = re.compile(
                r'on\s+([A-Za-z]+)\s+(\d{1,2}),?\s*(20\d{2})'
                r'.*?average of\s+(\d+(?:\.\d+)?)\s*cent',
                re.IGNORECASE
            )

            m = pattern.search(text)
            if m:
                month_str = m.group(1)[:3].capitalize()
                day_str = m.group(2)
                year_str = m.group(3)
                target_price = float(m.group(4))
                target_date = datetime.strptime(f"{month_str} {day_str} {year_str}", "%b %d %Y").date()

                # 當公佈的價格在明天生效
                if target_date == tom_dt:
                    pred_price = f"{target_price:.1f}"

            # 備用補底：若首次運行或資料清空，從 Historical Values 取得今日價格
            if cur_price == "--":
                hist_pattern = re.compile(
                    rf'(?:{today_dt.strftime("%B")}|{today_dt.strftime("%b")})\s+{today_dt.day},?\s*{today_dt.year}.*?(\d+(?:\.\d+)?)\s*cent',
                    re.IGNORECASE
                )
                hist_match = hist_pattern.search(text)
                if hist_match:
                    cur_price = f"{float(hist_match.group(1)):.1f}"

            # 計算升跌趨勢
            if pred_price != "--":
                if cur_price != "--":
                    diff = round(float(pred_price) - float(cur_price), 1)
                    if diff > 0:
                        trend = f"↑ 明日預測升 {diff:.1f} ¢"
                        trend_class = "gas-up"
                    elif diff < 0:
                        trend = f"↓ 明日預測跌 {abs(diff):.1f} ¢"
                        trend_class = "gas-down"
                    else:
                        trend = "→ 油價平穩"
                        trend_class = "gas-neutral"
                else:
                    trend = "→ 預測已更新"
                    trend_class = "gas-neutral"

    except Exception as e:
        print(f"CityNews gas fetch error: {e}")

    return {
        "current_label": today_label,
        "current_price": cur_price,
        "predict_label": predict_label,
        "predict_price": pred_price,
        "trend": trend,
        "trend_class": trend_class
    }

# ----------------------------------------------------
# 2. 即時新聞爬蟲 (嚴格屏蔽大公、文匯及中資官媒與其網域)
# ----------------------------------------------------
CHINESE_MEDIA_BLACKLIST = [
    # 網域名稱封殺
    "wenweipo", "takungpao", "tkww", "dotdotnews", "orangenews", "bastillepost",
    "xinhuanet", "people.com", "cctv", "cgtn", "globaltimes", "chinanews",
    "guancha", "sina", "sohu", "163.com", "qq.com", "thepaper",
    # 中文名稱封殺
    "文匯報", "文汇报", "大公報", "大公报", "大公文匯", "點新聞", "点新闻", "橙新聞",
    "橙新闻", "巴士的報", "巴士的报", "港人講地", "港人讲地", "中國新聞社", "中新網",
    "新華社", "新华社", "人民日報", "人民網", "央視", "央视", "環球時報", "环球网",
    "觀察者", "觀察者網", "澎湃新聞", "界面新聞", "鳳凰網", "鳳凰衛視", "中通社"
]

def fetch_rss_news(query_url, limit=7, exclude_keywords=None):
    if exclude_keywords is None:
        exclude_keywords = []

    full_blacklist = [kw.lower() for kw in (exclude_keywords + CHINESE_MEDIA_BLACKLIST)]
    news_items = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(query_url, headers=headers, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            
            for item in items:
                raw_title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                source = item.findtext("source", "").strip()

                title = html.unescape(raw_title)

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

                # 檢查 title、source 及 url link 是否包含黑名單
                check_target = f"{title} {source} {link}".lower()
                if any(bad_word in check_target for bad_word in full_blacklist):
                    continue

                if title:
                    news_items.append({
                        "title": title,
                        "source": source,
                        "link": link
                    })

                if len(news_items) >= limit:
                    break
    except Exception as e:
        print(f"RSS fetch error: {e}")
        
    return news_items

# ----------------------------------------------------
# 3. 日程與除淨天數動態計算 (內置美股與個股清單)
# ----------------------------------------------------
DEFAULT_MACRO_EVENTS = [
    {"tag": "CPI", "title": "美國 9 月 CPI 通脹數據", "date": "2026-10-14", "desc": "美聯儲關注通脹指標"},
    {"tag": "FOMC", "title": "美聯儲 11 月議息會議", "date": "2026-11-05", "desc": "公佈最新利率決議與路徑"}
]

DEFAULT_STOCK_EVENTS = [
    {"ticker": "EXE.TO", "name": "Extendicare", "type": "9月除淨", "date": "2026-09-30", "desc": "9月份股息買入資格截止 (Ex-Div)"},
    {"ticker": "TSM", "name": "台積電", "type": "Q3 財報", "date": "2026-10-15", "desc": "2026 Q3 業績公佈與法說會"},
    {"ticker": "GOOG", "name": "Alphabet", "type": "Q3 財報", "date": "2026-10-28", "desc": "美股盤後公佈 Q3 財報"},
    {"ticker": "NVDA", "name": "NVIDIA", "type": "Q3 財報", "date": "2026-11-18", "desc": "美股盤後公佈 Q3 財報"}
]

def update_events_countdown(events_data):
    today = datetime.now(TORONTO_TZ).date()

    # 確保內置基礎標的不會因為空白被洗掉
    macro_list = events_data.get("macro") if (events_data and events_data.get("macro")) else DEFAULT_MACRO_EVENTS
    stock_list = events_data.get("stocks") if (events_data and events_data.get("stocks")) else DEFAULT_STOCK_EVENTS

    # 補充缺漏的重點個股
    existing_stock_tickers = [s.get("ticker") for s in stock_list]
    for def_stock in DEFAULT_STOCK_EVENTS:
        if def_stock["ticker"] not in existing_stock_tickers:
            stock_list.append(def_stock)

    def process_list(ev_list):
        result = []
        for ev in ev_list:
            try:
                ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").date()
                days_left = (ev_date - today).days
                if days_left < 0:
                    continue  # 過期自動剔除
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
        # 依剩餘天數升冪排列
        result.sort(key=lambda x: x.get("days_left", 999))
        return result

    return {
        "macro": process_list(macro_list),
        "stocks": process_list(stock_list)
    }

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

    # 多倫多當地時間記錄
    data["updated_at"] = datetime.now(TORONTO_TZ).strftime("%Y-%m-%d %H:%M:%S")

    # 1. 抓取油價
    data["gas"] = get_gas_data(data)

    # 2. 抓取國際焦點 Top 7 (過濾中資與官媒)
    world_rss = "https://news.google.com/rss/search?q=(國際+OR+全球+OR+歐盟+OR+美國+OR+中東+OR+俄烏+OR+地緣政治+OR+白宮)+when:24h&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
    latest_world = fetch_rss_news(
        world_rss, 
        limit=7, 
        exclude_keywords=["香港", "港府", "特區", "大灣區", "內地", "港幣"]
    )
    if latest_world:
        data["news_world"] = latest_world

    # 3. 抓取美股要聞 6 條
    stock_rss = "https://news.google.com/rss/search?q=(美股+OR+納斯達克+OR+標普+OR+聯儲局+OR+華爾街+OR+科技股+OR+降息+OR+美債)+when:8h&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
    latest_stock = fetch_rss_news(
        stock_rss, 
        limit=6, 
        exclude_keywords=["港股", "恒指", "恒生", "A股", "內房", "滬深", "北向資金", "港交所"]
    )
    if latest_stock:
        data["news_stock"] = latest_stock

    # 4. 更新日程倒數 (含 TSM、GOOG、NVDA 財報)
    data["events"] = update_events_countdown(data.get("events", {}))

    # 5. 寫入 data.json
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("✅ data.json 更新完成：多倫多時區對齊、中資官媒全面屏蔽、個股財報已回填！")

if __name__ == "__main__":
    main()
