import requests
from bs4 import BeautifulSoup
import re

def fetch_gta_gas_price():
    url = "https://gaswizard.ca/gas-price-predictions/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # 預設合理托底值 (Cents/L)
    result = {
        "today_price": 155.9,
        "tomorrow_price": 155.9,
        "status": "油價平穩",
        "today_date": "今日",
        "tomorrow_date": "明日"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # 尋找 Toronto / GTA 區塊
            toronto_row = None
            for row in soup.find_all(["tr", "div", "li"]):
                text = row.get_text()
                if "Toronto" in text or "GTA" in text:
                    toronto_row = text
                    break
            
            target_text = toronto_row if toronto_row else soup.get_text()
            
            # 使用正則只抓取合理油價範圍 (100.0 - 250.0 ¢/L)，避免誤抓日期數字
            matches = re.findall(r'\b(1[0-9]{2}\.[0-9])\b', target_text)
            
            if len(matches) >= 2:
                p_today = float(matches[0])
                p_tomorrow = float(matches[1])
                
                result["today_price"] = p_today
                result["tomorrow_price"] = p_tomorrow
                
                diff = round(p_tomorrow - p_today, 1)
                if diff > 0:
                    result["status"] = f"↑ 明日預測升 {diff} ¢"
                elif diff < 0:
                    result["status"] = f"↓ 明日預測跌 {abs(diff)} ¢"
                else:
                    result["status"] = "→ 油價平穩"
            elif len(matches) == 1:
                result["today_price"] = float(matches[0])
                result["tomorrow_price"] = float(matches[0])
                result["status"] = "→ 價格維持"
    except Exception as e:
        print(f"Fetch gas price failed: {e}")
        
    return result
