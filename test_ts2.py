import requests, time

# Test 1: Can we reach anything?
print("=== Test 1: General connectivity ===")
for url in ["http://httpbin.org/get", "https://www.baidu.com", "http://www.tushare.pro"]:
    try:
        t0 = time.time()
        r = requests.get(url, timeout=8)
        print(f"  {url}: HTTP {r.status_code} ({time.time()-t0:.2f}s)")
    except Exception as e:
        print(f"  {url}: FAIL ({time.time()-t0:.2f}s) {type(e).__name__}")

# Test 2: Try different Tushare endpoints
print("\n=== Test 2: Tushare API variations ===")
env_path = r"D:\AI-Projects\TradingAgents-CN_v1.0.1\.env"
token = ""
with open(env_path) as f:
    for line in f:
        if line.startswith("TUSHARE_TOKEN="):
            token = line.split("=",1)[1].strip().strip("\"'")
            break

payloads = [
    ("With /dataapi/", "http://api.tushare.pro/dataapi/trade_cal"),
    ("Without /dataapi/", "http://api.tushare.pro"),
    ("HTTPS", "https://api.tushare.pro/dataapi/trade_cal"),
]
for name, url in payloads:
    try:
        t0 = time.time()
        r = requests.post(url,
            json={"api_name":"trade_cal","token":token,"params":{"exchange":"SSE","start_date":"20260101","end_date":"20260110"}},
            timeout=15)
        t = time.time() - t0
        data = r.json() if r.text else {}
        print(f"  {name}: HTTP {r.status_code} ({t:.2f}s) code={data.get('code')}")
    except Exception as e:
        print(f"  {name}: FAIL ({time.time()-t0:.2f}s) {type(e).__name__}")

# Test 3: Try with wget/curl from cmd
import subprocess
print("\n=== Test 3: curl from cmd ===")
r = subprocess.run(["curl.exe", "-s", "-o", "NUL", "-w", "%{http_code} (%{time_total}s)",
    "-X", "POST", "-H", "Content-Type: application/json",
    "-d", '{"api_name":"trade_cal","token":"'+token+'","params":{"exchange":"SSE","start_date":"20260101","end_date":"20260110"}}',
    "http://api.tushare.pro/dataapi/trade_cal"],
    capture_output=True, text=True, timeout=15)
print(f"  curl: {r.stdout.strip()}")
