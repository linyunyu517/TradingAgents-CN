import sys
print(f'Python: {sys.executable}')
import requests
print(f'requests: {requests.__version__}')
import os
env_path = 'D:\\AI-Projects\\TradingAgents-CN_v1.0.1\\.env'
token = ''
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('TUSHARE_TOKEN='):
                token = line.split('=', 1)[1].strip().strip("\"'") or ''
                break
print(f'Token: {token[:8]}...' if token else 'NO TOKEN')
try:
    resp = requests.post('http://api.tushare.pro/dataapi/trade_cal',
        json={'api_name':'trade_cal','token':token,'params':{'exchange':'SSE','start_date':'20260101','end_date':'20260110'}},
        timeout=10)
    print(f'HTTP {resp.status_code}')
    data = resp.json()
    print(f'Code: {data.get("code")}')
    if data.get('data'):
        items = data['data'].get('items', [])
        print(f'Items: {len(items)} rows')
        import pandas as pd
        df = pd.DataFrame(items, columns=data['data']['fields'])
        print(df.to_string())
        print('SUCCESS')
    else:
        print(f'No data: {data}')
except Exception as e:
    import traceback
    print(f'ERROR: {type(e).__name__}: {e}')
    traceback.print_exc()
