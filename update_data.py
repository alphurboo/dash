import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime, timedelta

def fetch_date_aware_gas_prices():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    now = datetime.now()
    today_dt = now.date()
    tom_dt = (now + timedelta(days=1)).date()

    # 日期字串格式 (例如: "Aug 31", "August 31", "Aug 30", "Sep 1")
    today_patterns = [today_dt.strftime("%b %d"), today_dt.strftime("%B %d"), f"{today_dt.month}/{today_dt.day}"]
    tom_patterns = [tom_dt.strftime("%b %d"), tom_dt.strftime("%B %d"), f"{tom_dt.month}/{tom_dt.day}"]

    p_today = None
    p_tomorrow = None
    source = "GASWIZARD"

    try:
        url = "https://gaswizard.ca/gas-prices/toronto/"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            
            # 抓取表格行或區塊 (包含日期與價格)
            entries = []
            for row in soup.find_all(['tr', 'div', 'li']):
                text = row.get_text(separator=' ', strip=True)
                # 尋找日期格式 (如 "August 30, 2026") 與 價格 (如 "182.9")
                price_match = re.search(r'\b(1[2-9][0-9]\.[0-9]|2[0-1][0-9]\.[0-9])\b', text)
                if price_match:
                    price_val = float(price_match.group(1))
                    entries.append((text, price_val))

            # 精確比對今日與明日
            for text, price in entries:
                # 判斷是否屬於明日
                if any(p.lower() in text.lower() for p in tom_patterns) or "tomorrow" in text.lower():
                    if not p_tomorrow:
                        p_tomorrow = price
                # 判斷是否屬於今日
                elif any(p.lower() in text.lower() for p in today_patterns) or "today" in text.lower():
                    if not p_today:
                        p_today = price

            # 若沒明確抓到今日，但有最新一筆合理價格，設為今日
            if not p_today and len(entries) > 0:
                p_today = entries[0][1]

    except Exception as e:
        print(f"GasWizard 解析失敗: {e}")

    # 保底數值
    if not p_today:
        p_today = 182.9

    return p_today, p_tomorrow, source

def fetch_weather_markham():
    url = "https://api.open-meteo.com/v1/forecast?latitude=43.8561&longitude=-79.3370&current=temperature_2m,apparent_temperature,precipitation_probability,weather_code,uv_index&hourly=temperature_2m,precipitation_probability&timezone=America%2FToronto"
    try:
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            data = r.json()
            curr = data.get("current", {})
            hourly = data.get("hourly", {})
            
            forecast_hours = []
            now_hour = datetime.now().hour
            for i in range(1, 10, 2):
                idx = now_hour + i
                if idx < len(hourly.get("temperature_2m", [])):
                    h_time = (datetime.now() + timedelta(hours=i)).strftime("%-I %p")
                    h_temp = round(hourly["temperature_2m"][idx])
                    h_pop = hourly["precipitation_probability"][idx]
                    forecast_hours.append({
                        "time": h_time,
                        "temp": f"{h_temp}°",
                        "pop": f"{h_pop}%"
                    })

            weather_code = curr.get("weather_code", 0)
            desc = "晴朗"
            if weather_code in [1, 2, 3]: desc = "多雲"
            elif weather_code in [51, 53, 55, 61, 63, 65, 80, 81, 82]: desc = "有雨"
            elif weather_code in [71, 73, 75, 85, 86]: desc = "有雪"
            elif weather_code >= 95: desc = "雷雨"

            return {
                "temp": f"{round(curr.get('temperature_2m', 20))}°C",
                "feel": f"{round(curr.get('apparent_temperature', 20))}°C",
                "pop": f"{curr.get('precipitation_probability', 0)}%",
                "uv": f"{curr.get('uv_index', 2.0):.1f}",
                "condition": desc,
                "high_low": "23° / 18°",
                "hourly": forecast_hours
            }
    except Exception as e:
        print(f"Weather fetch failed: {e}")

    return {
        "temp": "19°C", "feel": "21°C", "pop": "10%", "uv": "2.0",
        "condition": "多雲", "high_low": "23° / 18°", "hourly": []
    }

def main():
    p_today, p_tomorrow, source_name = fetch_date_aware_gas_prices()
    
    now = datetime.now()
    today_str = f"{now.month}月{now.day}日 (現行油價)"
    tom = now + timedelta(days=1)
    tom_str = f"{tom.month}月{tom.day}日 (明日預測)"

    # 處理明日油價公佈狀態
    if p_tomorrow is not None and p_tomorrow != p_today:
        diff = round(p_tomorrow - p_today, 1)
        if diff > 0:
            status = f"↑ 明日預測升 {diff} ¢"
        elif diff < 0:
            status = f"↓ 明日預測跌 {abs(diff)} ¢"
        else:
            status = "→ 油價平穩"
        tomorrow_display = p_tomorrow
    else:
        # 明日尚未公佈
        status = "⏳ 明日預測待公佈 (約下午更新)"
        tomorrow_display = "--"

    gas_data = {
        "today_price": p_today,
        "tomorrow_price": tomorrow_display,
        "today_date": today_str,
        "tomorrow_date": tom_str,
        "status": status,
        "source": source_name
    }

    weather_data = fetch_weather_markham()

    final_output = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "weather": weather_data,
        "gas": gas_data
    }

    with open("dashboard_data.json", "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)

    print("Dashboard 數據已成功更新：")
    print(json.dumps(final_output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
