import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta

def parse_gas_numbers(text):
    """
    嚴格過濾安省 GTA 合理油價 (120.0¢ ~ 220.0¢)
    杜絕誤抓 9月1日 (9 + 21.9 -> 921.9)
    """
    # 僅匹配 120.0 至 219.9 之間的小數
    raw_matches = re.findall(r'\b(1[2-9][0-9]\.[0-9]|2[0-1][0-9]\.[0-9])\b', text)
    valid_prices = []
    for m in raw_matches:
        val = float(m)
        if 120.0 <= val <= 220.0:
            valid_prices.append(val)
    return valid_prices

def fetch_from_citynews():
    """來源 1: CityNews Toronto (toronto.citynews.ca/toronto-gta-gas-prices/)"""
    url = "https://toronto.citynews.ca/toronto-gta-gas-prices/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # 優先搜尋 Toronto / GTA 專屬卡片區塊
            text_blocks = []
            for tag in soup.find_all(['div', 'p', 'table', 'section']):
                t = tag.get_text(separator=' ', strip=True)
                if any(k in t for k in ["Toronto", "GTA", "Gas Prices", "Today", "Tomorrow"]):
                    text_blocks.append(t)
            
            full_text = " ".join(text_blocks)
            prices = parse_gas_numbers(full_text)
            if len(prices) >= 2:
                return prices[0], prices[1], "CITYNEWS"
            elif len(prices) == 1:
                return prices[0], prices[0], "CITYNEWS"
    except Exception as e:
        print(f"CityNews fetch failed: {e}")
    return None

def fetch_from_gaswizard():
    """來源 2: GasWizard Canada (gaswizard.ca/gas-price-predictions/)"""
    url = "https://gaswizard.ca/gas-price-predictions/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # 鎖定 Toronto 列
            toronto_text = ""
            for row in soup.find_all(['tr', 'div', 'li']):
                t = row.get_text(separator=' ', strip=True)
                if "Toronto" in t or "GTA" in t:
                    toronto_text += " " + t
            
            target_text = toronto_text if toronto_text else soup.get_text(separator=' ', strip=True)
            prices = parse_gas_numbers(target_text)
            if len(prices) >= 2:
                return prices[0], prices[1], "GASWIZARD"
            elif len(prices) == 1:
                return prices[0], prices[0], "GASWIZARD"
    except Exception as e:
        print(f"GasWizard fetch failed: {e}")
    return None

def get_gta_gas_price_data():
    """
    雙源比對與容錯主調用函數
    """
    # 1. 優先嘗試 CityNews
    result = fetch_from_citynews()
    
    # 2. 若失敗則備用 GasWizard
    if not result:
        result = fetch_from_gaswizard()
        
    # 3. 若兩者皆異常時的托底基準值
    if result:
        p_today, p_tomorrow, source_name = result
    else:
        p_today, p_tomorrow, source_name = 155.9, 155.9, "DEFAULT"

    # 日期生成
    now = datetime.now()
    today_str = f"{now.month}月{now.day}日 (現行油價)"
    tom = now + timedelta(days=1)
    tom_str = f"{tom.month}月{tom.day}日 (明日預測)"

    diff = round(p_tomorrow - p_today, 1)
    if diff > 0:
        status = f"↑ 明日預測升 {diff} ¢"
    elif diff < 0:
        status = f"↓ 明日預測跌 {abs(diff)} ¢"
    else:
        status = "→ 油價平穩"

    return {
        "today_price": p_today,
        "tomorrow_price": p_tomorrow,
        "today_date": today_str,
        "tomorrow_date": tom_str,
        "status": status,
        "source": source_name
    }
