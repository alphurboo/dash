import os
import json
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta

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
            # 強制加入空格分隔，杜絕 9月 與 21.9 黏合
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

def main():
    # 讀取現有 data.json (保留新聞、日程與超市資料)
    data = {}
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception:
                data = {}

    # 更新油價與時間戳
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["gas"] = get_gas_data()

    # 寫入回 data.json
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("已成功將最新油價寫入 data.json！")
    print(json.dumps(data["gas"], ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
