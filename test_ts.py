import sys, os, time
env_path = r"D:\AI-Projects\TradingAgents-CN_v1.0.1\.env"
token = ""
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("TUSHARE_TOKEN="):
                token = line.split("=", 1)[1].strip().strip("\"'")
                break
import requests
print("=== Windows Python Tushare ===")
session = requests.Session()
session.headers.update({"Connection": "keep-alive"})
success = 0
fail = 0
for i in range(5):
    try:
        t0 = time.time()
        resp = session.post("http://api.tushare.pro/dataapi/trade_cal",
            json={"api_name":"trade_cal","token":token,"params":{"exchange":"SSE","start_date":"20260101","end_date":"20260110"}},
            timeout=15)
        data = resp.json()
        items = data["data"]["items"] if data.get("data") and data["data"].get("items") else []
        t = time.time() - t0
        print(f"  [{i+1}/5] SUCCESS ({t:.2f}s) items={len(items)}")
        success += 1
    except Exception as e:
        t = time.time() - t0
        print(f"  [{i+1}/5] FAIL ({t:.2f}s): {type(e).__name__}")
        fail += 1
    time.sleep(0.5)
session.close()
print(f"\nResult: {success}/5 success, {fail}/5 fail")
