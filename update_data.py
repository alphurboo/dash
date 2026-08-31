import os
import json
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re
import html
from datetime import datetime, timedelta

# ----------------------------------------------------
# 1. 油價爬蟲 (精確卡片日期字典解析，無明日卡片絕不顯示數字)
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

    cur_price = "182.9"
    pred_price = "--"
    trend = "⏳ 明日預測待公佈"
    trend_class = "gas-neutral"

    try:
        url = "https://gaswizard.ca/gas-prices/toronto/"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            full_text = soup.get_text(separator=" ", strip=True)

            date_regex = re.compile(
                r'\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2}),?\s*(20\d{2})\b',
                re.IGNORECASE
            )

            matches = list(date_regex.finditer(full_text))
            date_price_map = {}

            for i, match in enumerate(matches):
                month_str, day_str, year_str = match.groups()
                try:
                    m_str = month_str[:3].capitalize()
                    dt = datetime.strptime(f"{m_str} {day_str} {year_str}", "%b %d %Y").date()
                except Exception:
                    continue

                start_pos = match.end()
                end_pos = matches[i + 1].start() if i + 1 < len(matches) else start_pos + 300
                section_text = full_text[start_pos:end_pos]

                price_match = re.search(r'\b(1[2-9]\d\.[0-9]|2[0-1]\d\.[0-9])\b', section_text)
                if price_match:
                    price_val = float(price_match.group(1))
                    if dt not in date_price_map:
                        date_price_map[dt] = price_val

            # 決定今日油價
            if today_dt in date_price_map:
                cur_price = f"{date_price_map[today_dt]:.1f}"
            else:
                past_dates = [d for d in date_price_map.keys() if d <= today_dt]
                if past_dates:
                    latest_past = max(past_dates)
                    cur_price = f"{date_price_map[latest_past]:.1f}"

            # 決定明日油價
            if tom_dt in date_price_map:
                tomorrow_val = date_price_map[tom_dt]
                pred_price = f"{tomorrow_val:.1f}"
                diff = round(tomorrow_val - float(cur_price), 1)
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
# 2. 即時新聞爬蟲 (排除中國官方及中資背景傳媒)
# ----------------------------------------------------
CHINESE_MEDIA_BLACKLIST = [
    # 內地官媒與主要門戶
    "中國共產黨新聞網", "共产党", "人民網", "人民日报", "新華社", "新华社", "新華網", "新华网",
    "央視", "央视", "CCTV", "CGTN", "環球網", "环球网", "環球時報", "环球时报", "中新社", "中新網",
    "觀察者網", "观察者", "今日頭條", "今日头条", "網易", "网易", "新浪", "搜狐", "騰訊", "腾讯",
    "百度", "澎湃新聞", "澎湃", "界面新聞", "財聯社", "财联社", "參考消息", "参考消息",
    # 中資/香港建制背景傳媒
    "香港文匯報", "文匯報", "文汇报", "大公報", "大公报", "香港商報", "香港商报", "點新聞", "点新闻",
    "橙新聞", "橙新闻", "巴士的報", "巴士的报", "港人講地", "港人讲地", "鳳凰網", "凤凰网",
    "鳳凰衛視", "凤凰卫视", "中通社", "香港中通社", "紫荊", "紫荆", "堅料網", "思考HK", "SL886"
]

def fetch_rss_news(query_url, limit=7, exclude_keywords=None):
    if exclude_keywords is None:
        exclude_keywords = []

    # 合併關鍵字黑名單與傳媒機構黑名單
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

                # 確保 Google News Link 有效
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

                # 嚴格黑名單過濾：檢查標題與來源名稱
                check_target = f"{title} {source}".lower()
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

    # 2. 抓取國際焦點 Top 7 (鎖定歐美、中東及全球重大地緣事件)
    world_rss = "https://news.google.com/rss/search?q=(國際+OR+全球+OR+歐盟+OR+美國+OR+中東+OR+俄烏+OR+地緣政治+OR+白宮)+when:24h&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
    latest_world = fetch_rss_news(
        world_rss, 
        limit=7, 
        exclude_keywords=["香港", "港府", "特區", "大灣區", "內地", "港幣"]
    )
    if latest_world:
        data["news_world"] = latest_world

    # 3. 抓取美股要聞 6 條 (鎖定美股與全球宏觀，排除港股/A股)
    stock_rss = "https://news.google.com/rss/search?q=(美股+OR+納斯達克+OR+標普+OR+聯儲局+OR+華爾街+OR+科技股+OR+降息+OR+美債)+when:8h&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
    latest_stock = fetch_rss_news(
        stock_rss, 
        limit=6, 
        exclude_keywords=["港股", "恒指", "恒生", "A股", "內房", "滬深", "北向資金", "港交所"]
    )
    if latest_stock:
        data["news_stock"] = latest_stock

    # 4. 更新日程倒數
    if "events" in data:
        data["events"] = update_events_countdown(data["events"])

    # 5. 寫入 data.json
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("✅ data.json 更新完成：已成功過濾中資與官方背景傳媒！")

if __name__ == "__main__":
    main()
