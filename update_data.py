import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta

ALLOWED_STORES = [
    "no frills", "freshco", "food basics", "walmart", "costco",
    "metro", "loblaws", "superstore", "real canadian", "longo",
    "sobeys", "giant tiger", "farm boy", "shoppers drug mart", "rexall",
    "t&t", "t & t", "大統華", "winco", "華盛", "foody", "豐泰",
    "bestco", "鴻泰", "seasons", "四季", "tone tai", "鼎泰",
    "sunny", "陽光", "first choice", "冠業", "btrust", "信達",
    "field fresh", "國泰", "top food", "百好", "hong tai"
]

def shorten_store_name(name):
    n = name.strip()
    if "Shoppers" in n: return "Shoppers"
    if "Food Basics" in n: return "FoodBasics"
    if "No Frills" in n: return "NoFrills"
    if "Real Canadian Superstore" in n: return "Superstore"
    if "Winco" in n: return "Winco"
    if "Seasons" in n: return "Seasons"
    if "T&T" in n or "大統華" in n: return "T&T"
    if "Foody" in n or "豐泰" in n: return "豐泰"
    if "Costco" in n: return "Costco"
    if "Walmart" in n: return "Walmart"
    if "FreshCo" in n: return "FreshCo"
    if "Loblaws" in n: return "Loblaws"
    if "Metro" in n: return "Metro"
    if "Sobeys" in n: return "Sobeys"
    if "Longos" in n or "Longo's" in n: return "Longos"
    return n[:10]

def get_store_tag(merchant_name):
    m_low = merchant_name.lower()
    if "freshco" in m_low: return "tag-freshco"
    if "food basics" in m_low or "foodbasics" in m_low: return "tag-foodbasics"
    if "walmart" in m_low: return "tag-walmart"
    if "costco" in m_low: return "tag-costco"
    if any(c in m_low for c in ["t&t", "大統華", "winco", "華盛", "foody", "豐泰", "bestco", "seasons", "tone tai", "sunny", "first choice"]): 
        return "tag-tnt"
    return "tag-nofrills"

def get_gas_wizard_prices():
    today = date.today()
    tomorrow = today + timedelta(days=1)
    today_label = f"{today.month}月{today.day}日 (現行油價)"
    tomorrow_label = f"{tomorrow.month}月{tomorrow.day}日 (明日預測)"

    gas_data = {
        "current_label": today_label,
        "current_price": "174.9",
        "predict_label": tomorrow_label,
        "predict_price": "--",
        "trend": "⏳ 下午 2-3 PM 公佈",
        "trend_class": "gas-neutral"
    }

    url_citynews = "https://toronto.citynews.ca/toronto-gta-gas-prices/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(url_citynews, headers=headers, timeout=10)
        if res.status_code == 200:
            text = res.text
            m = re.search(r'expected to (fall|rise|drop|increase|remain unchanged)\s*(\d+)?\s*cent.*?at 12:01am on ([A-Za-z]+ \d+).*?to an average of (\d+\.?\d*)', text, re.IGNORECASE)
            if m:
                action = m.group(1).lower()
                cents = m.group(2) or "0"
                target_date_str = m.group(3)
                pred_price = m.group(4)
                gas_data["predict_price"] = pred_price
                gas_data["predict_label"] = f"{target_date_str} (預測油價)"

                if "fall" in action or "drop" in action:
                    gas_data["trend"] = f"↓ 跌 {cents} 仙 (建議聽日入)"
                    gas_data["trend_class"] = "gas-down"
                    try: gas_data["current_price"] = f"{(float(pred_price) + float(cents)):.1f}"
                    except: pass
                elif "rise" in action or "increase" in action:
                    gas_data["trend"] = f"↑ 升 {cents} 仙 (建議今日入)"
                    gas_data["trend_class"] = "gas-up"
                    try: gas_data["current_price"] = f"{(float(pred_price) - float(cents)):.1f}"
                    except: pass
                else:
                    gas_data["trend"] = "→ 油價平穩"
                    gas_data["trend_class"] = "gas-neutral"
                    gas_data["current_price"] = pred_price
                return gas_data
    except:
        pass

    url_gw = "https://gaswizard.ca/gas-prices/toronto/"
    try:
        res_gw = requests.get(url_gw, headers=headers, timeout=10)
        if res_gw.status_code == 200:
            prices = re.findall(r'(\d{3}\.\d)', res_gw.text)
            if len(prices) >= 2:
                gas_data["current_price"] = prices[0]
                gas_data["predict_price"] = prices[1]
                diff = round(float(prices[1]) - float(prices[0]), 1)
                if diff < 0:
                    gas_data["trend"] = f"↓ 跌 {abs(diff)} 仙 (建議聽日入)"
                    gas_data["trend_class"] = "gas-down"
                elif diff > 0:
                    gas_data["trend"] = f"↑ 升 {diff} 仙 (建議今日入)"
                    gas_data["trend_class"] = "gas-up"
                else:
                    gas_data["trend"] = "→ 油價平穩"
                    gas_data["trend_class"] = "gas-neutral"
    except:
        pass
    return gas_data

def parse_rss_feed_robust(url, max_count=7):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    items = []
    seen = set()
    try:
        res = requests.get(url, headers=headers, timeout=12)
        if res.status_code == 200:
            raw_items = re.findall(r'<item>(.*?)</item>', res.text, re.DOTALL)
            for raw in raw_items:
                title_m = re.search(r'<title>(.*?)</title>', raw, re.DOTALL)
                link_m = re.search(r'<link>(.*?)</link>', raw, re.DOTALL)
                if not title_m: continue
                full_title = title_m.group(1).replace("<![CDATA[", "").replace("]]>", "").strip()
                link = link_m.group(1).replace("<![CDATA[", "").replace("]]>", "").strip() if link_m else "#"
                clean_full = BeautifulSoup(full_title, "html.parser").get_text().strip()
                if " - " in clean_full:
                    parts = clean_full.rsplit(" - ", 1)
                    title, source = parts[0].strip(), parts[1].strip()
                else:
                    title, source = clean_full, "焦點要聞"
                clean_title = re.sub(r'^\s*\d+[\.\、\)\s\-]+', '', title).strip()
                if not clean_title or clean_title in seen: continue
                seen.add(clean_title)
                items.append({"title": clean_title, "source": source, "link": link})
                if len(items) >= max_count: break
    except:
        pass
    return items

def get_world_news_24h():
    url = "https://news.google.com/rss/headlines/section/topic/WORLD?hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
    news = parse_rss_feed_robust(url, max_count=7)
    if not news:
        url_backup = "https://news.google.com/rss/search?q=國際焦點+when:24h&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
        news = parse_rss_feed_robust(url_backup, max_count=7)
    return news

def get_stock_news_8h():
    url = "https://news.google.com/rss/search?q=美股+OR+股市+OR+美聯儲+when:8h&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
    news = parse_rss_feed_robust(url, max_count=6)
    if not news:
        url_backup = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
        news = parse_rss_feed_robust(url_backup, max_count=6)
    return news

def get_macro_and_earnings_events():
    today = date.today()
    macro_schedule = [
        {"title": "非農就業數據 (NFP)", "date": "2026-09-04", "tag": "💼 就業", "desc": "美聯儲降息路徑核心指標"},
        {"title": "消費者物價指數 (CPI)", "date": "2026-09-11", "tag": "📊 通脹", "desc": "8月通脹年率與核心CPI公布"},
        {"title": "FOMC 議息 (附點陣圖/SEP)", "date": "2026-09-16", "tag": "🏛️ 議息", "desc": "聯儲局公佈利率決議與最新經濟預測點陣圖"},
        {"title": "美股「四巫日」(Quad Witching)", "date": "2026-09-18", "tag": "🧙‍♂️ 四巫日", "desc": "季結指數/股票期權期貨集中結算轉倉"},
        {"title": "非農就業數據 (NFP)", "date": "2026-10-02", "tag": "💼 就業", "desc": "9月就業市場數據"},
        {"title": "消費者物價指數 (CPI)", "date": "2026-10-14", "tag": "📊 通脹", "desc": "9月通脹數據"},
        {"title": "美國國會中期選舉 (大選日)", "date": "2026-11-03", "tag": "🗳️ 大選", "desc": "參眾兩院改選，影響財政及監管政策"},
        {"title": "FOMC 議息會議", "date": "2026-11-05", "tag": "🏛️ 議息", "desc": "11月利率政策決議"},
        {"title": "非農就業數據 (NFP)", "date": "2026-11-06", "tag": "💼 就業", "desc": "10月就業市場數據"},
        {"title": "消費者物價指數 (CPI)", "date": "2026-11-12", "tag": "📊 通脹", "desc": "10月通脹數據"},
        {"title": "感恩節及黑色星期五", "date": "2026-11-27", "tag": "🛍️ 消費", "desc": "北美年尾零售購物季開鑼"},
        {"title": "非農就業數據 (NFP)", "date": "2026-12-04", "tag": "💼 就業", "desc": "11月就業市場數據"},
        {"title": "消費者物價指數 (CPI)", "date": "2026-12-10", "tag": "📊 通脹", "desc": "11月通脹數據"},
        {"title": "FOMC 議息 (附點陣圖/SEP)", "date": "2026-12-16", "tag": "🏛️ 議息", "desc": "年終議息與 2027 年利率展望點陣圖"},
        {"title": "美股「四巫日」(年結轉倉)", "date": "2026-12-18", "tag": "🧙‍♂️ 四巫日", "desc": "Q4 期權大結算"}
    ]

    stock_schedule = [
        # NVDA
        {"ticker": "NVDA", "name": "Nvidia", "type": "財報 Q2", "date": "2026-08-26", "desc": "今季 AI 晶片出貨與業績指引"},
        {"ticker": "NVDA", "name": "Nvidia", "type": "9月除淨", "date": "2026-09-10", "desc": "季度股息除淨日 (Ex-Dividend)"},
        {"ticker": "NVDA", "name": "Nvidia", "type": "財報 Q3", "date": "2026-11-18", "desc": "Blackwell 晶片出貨與數據中心營收"},
        {"ticker": "NVDA", "name": "Nvidia", "type": "12月除淨", "date": "2026-12-04", "desc": "季度股息除淨日"},

        # GOOG
        {"ticker": "GOOG", "name": "Alphabet", "type": "9月除淨", "date": "2026-09-04", "desc": "季度股息除淨日 (Ex-Dividend)"},
        {"ticker": "GOOG", "name": "Alphabet", "type": "財報 Q3", "date": "2026-10-22", "desc": "雲計算及 AI 資本支出回報"},
        {"ticker": "GOOG", "name": "Alphabet", "type": "12月除淨", "date": "2026-12-04", "desc": "季度股息除淨日"},

        # TSM
        {"ticker": "TSM", "name": "台積電", "type": "月度營收", "date": "2026-09-10", "desc": "8月份合併營收月報公布"},
        {"ticker": "TSM", "name": "台積電", "type": "9月除淨", "date": "2026-09-16", "desc": "季度高息除淨日 (Ex-Dividend)"},
        {"ticker": "TSM", "name": "台積電", "type": "月度營收", "date": "2026-10-09", "desc": "9月份合併營收月報公布"},
        {"ticker": "TSM", "name": "台積電", "type": "財報 Q3", "date": "2026-10-15", "desc": "Q3 業績與 2nm 製程展望"},
        {"ticker": "TSM", "name": "台積電", "type": "月度營收", "date": "2026-11-10", "desc": "10月份合併營收月報公布"},
        {"ticker": "TSM", "name": "台積電", "type": "月度營收", "date": "2026-12-10", "desc": "11月份合併營收月報公布"},
        {"ticker": "TSM", "name": "台積電", "type": "12月除淨", "date": "2026-12-16", "desc": "季度高息除淨日"},

        # EXE.TO (精確拆分：月末除淨日 vs 月中派息入帳日)
        {"ticker": "EXE.TO", "name": "Extendicare", "type": "8月除淨", "date": "2026-08-31", "desc": "8月份股息買入資格截止 (Ex-Div)"},
        {"ticker": "EXE.TO", "name": "Extendicare", "type": "9月派息", "date": "2026-09-15", "desc": "8月份月度股息現金入帳日 (Payable Date)"},
        {"ticker": "EXE.TO", "name": "Extendicare", "type": "9月除淨", "date": "2026-09-30", "desc": "9月份股息買入資格截止 (Ex-Div)"},
        {"ticker": "EXE.TO", "name": "Extendicare", "type": "10月派息", "date": "2026-10-15", "desc": "9月份月度股息現金入帳日 (Payable Date)"},
        {"ticker": "EXE.TO", "name": "Extendicare", "type": "10月除淨", "date": "2026-10-30", "desc": "10月份股息買入資格截止 (Ex-Div)"},
        {"ticker": "EXE.TO", "name": "Extendicare", "type": "財報 Q3", "date": "2026-11-05", "desc": "長者護理業務利潤與現金流報告"},
        {"ticker": "EXE.TO", "name": "Extendicare", "type": "11月派息", "date": "2026-11-16", "desc": "10月份月度股息現金入帳日 (Payable Date)"},
        {"ticker": "EXE.TO", "name": "Extendicare", "type": "11月除淨", "date": "2026-11-30", "desc": "11月份股息買入資格截止 (Ex-Div)"},
        {"ticker": "EXE.TO", "name": "Extendicare", "type": "12月派息", "date": "2026-12-15", "desc": "11月份月度股息現金入帳日 (Payable Date)"},

        # XIU.TO
        {"ticker": "XIU.TO", "name": "TSX 60 ETF", "type": "Q3除淨", "date": "2026-09-29", "desc": "加拿大 60 指數 Q3 收益分配除淨 (Ex-Div)"},
        {"ticker": "XIU.TO", "name": "TSX 60 ETF", "type": "Q4除淨", "date": "2026-12-30", "desc": "加拿大 60 指數 Q4 收益分配除淨 (Ex-Div)"},

        # ENB.TO
        {"ticker": "ENB.TO", "name": "Enbridge", "type": "財報 Q3", "date": "2026-11-06", "desc": "天然氣及管線業務季度業績"},
        {"ticker": "ENB.TO", "name": "Enbridge", "type": "Q4除淨", "date": "2026-11-13", "desc": "高股息除淨日 (Quarterly Ex-Div)"},

        # L.TO
        {"ticker": "L.TO", "name": "Loblaw", "type": "財報/除淨", "date": "2026-11-12", "desc": "零售利潤與季度股息除淨 (Ex-Div)"}
    ]

    upcoming_macro = []
    for m in macro_schedule:
        m_date = datetime.strptime(m["date"], "%Y-%m-%d").date()
        diff = (m_date - today).days
        if 0 <= diff <= 30:
            upcoming_macro.append({"title": m["title"], "date": m["date"], "days_left": diff, "status_badge": "今日" if diff == 0 else f"{diff} 日後", "tag": m["tag"], "desc": m["desc"]})
    upcoming_macro.sort(key=lambda x: x["days_left"])

    upcoming_stocks = []
    for s in stock_schedule:
        s_date = datetime.strptime(s["date"], "%Y-%m-%d").date()
        diff = (s_date - today).days
        if 0 <= diff <= 30:
            upcoming_stocks.append({"ticker": s["ticker"], "name": s["name"], "type": s["type"], "date": s["date"], "days_left": diff, "status_badge": "今日" if diff == 0 else f"{diff} 日後", "desc": s["desc"]})
    upcoming_stocks.sort(key=lambda x: x["days_left"])
    return {"macro": upcoming_macro, "stocks": upcoming_stocks}

def fetch_flipp(queries, must_all=None, must_any=None, exclude=None, min_p=0, max_p=999, postal_code="L6G0G5"):
    url = "https://backflipp.wishabi.com/flipp/items/search"
    headers = {"User-Agent": "Mozilla/5.0"}
    if isinstance(queries, str): queries = [queries]
    all_items = []
    for q in queries:
        try:
            res = requests.get(url, params={"locale": "en-ca", "postal_code": postal_code, "q": q}, headers=headers, timeout=8)
            if res.status_code == 200: all_items.extend(res.json().get("items", []))
        except: continue

    parsed = []
    seen = set()
    for it in all_items:
        merchant = it.get("merchant_name") or ""
        name = it.get("name") or ""
        price = it.get("current_price")
        orig_price = it.get("original_price")
        m_low, n_low = merchant.lower(), name.lower()

        if not any(kw in m_low for kw in ALLOWED_STORES): continue
        if must_all and not all(k in n_low for k in must_all): continue
        if must_any and not any(k in n_low for k in must_any): continue
        if exclude and any(k in n_low for k in exclude): continue
        if price is None: continue
        try: price_num = float(str(price).replace("$", "").strip())
        except: continue
        if not (min_p <= price_num <= max_p): continue

        short_name = shorten_store_name(merchant)
        unique_key = f"{short_name}_{price_num}"
        if unique_key in seen: continue
        seen.add(unique_key)

        deal = "👍抵買"
        deal_class = "deal-good"
        if orig_price:
            try:
                orig_num = float(str(orig_price).replace("$", "").strip())
                if (orig_num - price_num) / orig_num >= 0.2:
                    deal = "🔥大減價"
                    deal_class = "deal-hot"
            except: pass

        parsed.append({"store": short_name, "tag": get_store_tag(merchant), "name": name, "price": f"${price_num:.2f}", "price_num": price_num, "deal": deal, "class": deal_class})
    parsed.sort(key=lambda x: x["price_num"])
    return parsed[:5]

def main():
    milk = fetch_flipp(queries=["3.25% milk", "homo milk", "sealtest 3.25", "neilson 3.25", "beatrice 3.25", "natrel 3.25", "milk 2L"], must_any=["3.25", "homo", "whole", "milk", "sealtest", "neilson", "beatrice", "natrel", "lactantia"], exclude=["almond", "oat", "soy", "silk", "cashew", "coconut", "chocolate", "lactose", "cream", "fairlife", "condensed", "evaporated", "coffee", "dog", "cat"], min_p=3.50, max_p=7.50)
    rice = fetch_flipp(queries=["botan brown rice", "tsuru mai brown", "brown rice", "calrose brown", "糙米", "玄米"], must_all=["rice"], must_any=["brown", "botan", "tsuru", "calrose", "糙米", "玄米", "rooster"], exclude=["dog", "cat", "pet", "tums", "antacid", "neutrogena", "aveeno", "tampon", "pad", "detergent", "gain", "tide", "shampoo", "cracker", "cake", "noodle", "salmon", "blue buffalo", "purina", "formula", "protection"], min_p=11.99, max_p=32.00)
    toilet_paper = fetch_flipp(queries=["charmin", "charmin 30", "cashmere 24", "purex 30", "royale 30", "cottonelle 24", "bathroom tissue 24", "toilet paper 30", "toilet paper", "bathroom tissue"], must_any=["cashmere", "purex", "royale", "cottonelle", "charmin", "toilet", "bathroom"], exclude=["sponge", "towel", "spongetowels", "facial", "napkin", "wipe"], min_p=11.49, max_p=35.00)
    eggs = fetch_flipp(queries=["large eggs", "eggs 12", "eggs 18", "white eggs", "brown eggs", "eggs"], must_any=["egg", "eggs", "蛋"], exclude=["duck", "quail", "tart", "salted", "preserved", "century", "roll", "easter", "chocolate", "candy", "plant", "liquid", "salad", "sandwich", "noodle", "snack", "powder", "tofu", "custard", "鵪鶉", "鴨蛋", "皮蛋", "鹹蛋", "蛋撻", "撻"], min_p=2.88, max_p=8.99)
    facial_tissue = fetch_flipp(queries=["scotties", "royale facial", "kleenex", "facial tissue", "facial tissues"], must_any=["facial", "kleenex", "scotties", "royale"], exclude=["bath", "bathroom", "toilet", "sponge", "towel", "spongetowels", "napkin", "wipe", "tampon", "pad", "diaper"], min_p=3.88, max_p=14.99)

    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "gas": get_gas_wizard_prices(),
        "news_world": get_world_news_24h(),
        "news_stock": get_stock_news_8h(),
        "events": get_macro_and_earnings_events(),
        "groceries": {"milk": milk, "rice": rice, "toilet_paper": toilet_paper, "eggs": eggs, "facial_tissue": facial_tissue}
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("成功更新 data.json（已精確修正 EXE 除淨與派息入帳日）！")

if __name__ == "__main__":
    main()
