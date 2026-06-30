"""
TradingAgents-CN WebSocket 实时进度推送验证脚本
测试所有发现的 WebSocket 端点
"""

import asyncio
import json
import sys
import time

import requests
import websockets

# ============================================================
# 配置
# ============================================================
BASE_URL = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"

# 登录凭据
USERNAME = "admin"
PASSWORD = "admin123"


# ============================================================
# 辅助函数
# ============================================================
def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def log_sep(title: str):
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


# ============================================================
# Step 1: 获取 Token
# ============================================================
def get_token() -> str:
    log_sep("Step 1: 登录获取 Token")
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={"username": USERNAME, "password": PASSWORD}, timeout=10)
    data = resp.json()
    if not data.get("success"):
        log(f"❌ 登录失败: {data}")
        sys.exit(1)
    token = data["data"]["access_token"]
    log("✅ 登录成功")
    log(f"   Token: {token[:50]}...")
    log(f"   有效期: {data['data']['expires_in']}s")
    log(f"   用户:   {data['data']['user']['username']}")
    return token


# ============================================================
# Step 2: 提交分析任务
# ============================================================
def submit_analysis_task(token: str) -> str:
    log_sep("Step 2: 提交分析任务")
    resp = requests.post(
        f"{BASE_URL}/api/analysis/single",
        json={"symbol": "600000", "market": "SH"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    data = resp.json()
    if data.get("success") and data.get("data", {}).get("task_id"):
        task_id = data["data"]["task_id"]
        log(f"✅ 任务提交成功, task_id: {task_id}")
    else:
        log(f"ℹ️ 单股分析接口返回: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
        # 尝试另一个接口
        log("尝试提交队列任务...")
        resp2 = requests.post(
            f"{BASE_URL}/api/analysis/queue",
            json={"symbol": "600000", "market": "SH"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        data2 = resp2.json()
        log(f"队列任务返回: {json.dumps(data2, ensure_ascii=False, indent=2)[:300]}")
        # 如果拿不到 task_id，生成一个测试用的
        task_id = data.get("data", {}).get("task_id") or data2.get("data", {}).get("task_id") or "test_task_ws_validate"
        if task_id == "test_task_ws_validate":
            log("⚠️ 无法获取真实 task_id，将使用测试 task_id")
    return task_id


# ============================================================
# Step 3: 测试 WebSocket 端点
# ============================================================


async def test_endpoint_ws_notifications(token: str):
    """测试 /api/ws/notifications 端点"""
    log_sep("Test: /api/ws/notifications (通知推送)")
    url = f"{WS_BASE}/api/ws/notifications?token={token}"
    log(f"连接: {url}")
    try:
        async with websockets.connect(url, ping_interval=None, close_timeout=10) as ws:
            log("✅ 连接成功!")
            # 接收连接确认消息
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            log(f"📩 收到消息: {json.dumps(data, ensure_ascii=False, indent=2)}")
            if data.get("type") == "connected":
                log("✅ 连接确认消息格式正确")
            # 等待一次心跳
            log("等待心跳消息 (30s)...")
            try:
                msg2 = await asyncio.wait_for(ws.recv(), timeout=35)
                data2 = json.loads(msg2)
                log(f"📩 收到消息: {json.dumps(data2, ensure_ascii=False, indent=2)}")
                if data2.get("type") == "heartbeat":
                    log("✅ 心跳消息正常")
            except asyncio.TimeoutError:
                log("⚠️ 30s内未收到心跳")
            log("🔌 主动断开连接")
    except websockets.exceptions.WebSocketException as e:
        log(f"❌ 连接失败: {e}")


async def test_endpoint_ws_tasks(task_id: str, token: str):
    """测试 /api/ws/tasks/{task_id} 端点 (来自 websocket_notifications.py)"""
    log_sep("Test: /api/ws/tasks/{task_id} (任务进度 - 通知模块)")
    url = f"{WS_BASE}/api/ws/tasks/{task_id}?token={token}"
    log(f"连接: {url}")
    try:
        async with websockets.connect(url, ping_interval=None, close_timeout=10) as ws:
            log("✅ 连接成功!")
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            log(f"📩 收到消息: {json.dumps(data, ensure_ascii=False, indent=2)}")
            if data.get("type") == "connected":
                log("✅ 连接确认消息格式正确")
            # 等待消息
            log("等待推送消息 (15s)...")
            try:
                msg2 = await asyncio.wait_for(ws.recv(), timeout=15)
                data2 = json.loads(msg2)
                log(f"📩 收到消息: {json.dumps(data2, ensure_ascii=False, indent=2)}")
            except asyncio.TimeoutError:
                log("⚠️ 15s内未收到推送（可能任务已结束或无进度推送到此端点）")
            log("🔌 主动断开连接")
    except websockets.exceptions.WebSocketException as e:
        log(f"❌ 连接失败: {e}")


async def test_endpoint_analysis_ws_task(task_id: str):
    """测试 /api/analysis/ws/task/{task_id} 端点 (来自 analysis.py)

    注意: 该端点 **没有** token 验证
    """
    log_sep("Test: /api/analysis/ws/task/{task_id} (任务进度 - 分析模块)")
    url = f"{WS_BASE}/api/analysis/ws/task/{task_id}"
    log(f"连接: {url}")
    log("注意: 该端点无认证要求")
    try:
        async with websockets.connect(url, ping_interval=None, close_timeout=10) as ws:
            log("✅ 连接成功!")
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            log(f"📩 收到消息: {json.dumps(data, ensure_ascii=False, indent=2)}")
            if data.get("type") == "connection_established":
                log("✅ 连接确认消息格式正确")
            # 等待推送消息（如进度更新）
            log("等待进度推送消息 (30s) - 如果任务正在运行会收到进度更新...")
            for i in range(6):
                try:
                    msg2 = await asyncio.wait_for(ws.recv(), timeout=5)
                    data2 = json.loads(msg2)
                    log(f"📩 [{i + 1}] 收到消息: {json.dumps(data2, ensure_ascii=False, indent=2)}")
                except asyncio.TimeoutError:
                    log(f"📭 [{i + 1}] 5s内无消息")
            log("🔌 主动断开连接")
    except websockets.exceptions.WebSocketException as e:
        log(f"❌ 连接失败: {e}")


async def test_endpoint_no_auth():
    """测试无 token 连接 (验证是否被拒绝)"""
    log_sep("Test: 无认证连接测试")

    # 通知端点 - 无 token
    url1 = f"{WS_BASE}/api/ws/notifications"
    log(f"1. 通知端点(无token): {url1}")
    try:
        async with websockets.connect(url1, ping_interval=None, close_timeout=5) as ws:
            log("⚠️  连接成功! (预期应被拒绝)")
    except websockets.exceptions.WebSocketException as e:
        log(f"✅ 连接被拒绝 (符合预期): {type(e).__name__}")

    # 任务进度端点 - 无 token
    url2 = f"{WS_BASE}/api/ws/tasks/test_no_auth"
    log(f"2. 任务进度端点(无token): {url2}")
    try:
        async with websockets.connect(url2, ping_interval=None, close_timeout=5) as ws:
            log("⚠️  连接成功! (预期应被拒绝)")
    except websockets.exceptions.WebSocketException as e:
        log(f"✅ 连接被拒绝 (符合预期): {type(e).__name__}")

    # 分析模块端点 - 无 token (这个端点本来就没认证)
    url3 = f"{WS_BASE}/api/analysis/ws/task/test_no_auth"
    log(f"3. 分析模块端点(无token): {url3}")
    try:
        async with websockets.connect(url3, ping_interval=None, close_timeout=5) as ws:
            log("✅ 连接成功 (该端点无认证要求)")
            msg = await asyncio.wait_for(ws.recv(), timeout=3)
            log(f"📩 收到: {msg}")
    except websockets.exceptions.WebSocketException as e:
        log(f"❌ 连接失败: {e}")


async def test_invalid_token(token: str):
    """测试无效 token"""
    log_sep("Test: 无效 Token 测试")

    bad_token = token[:-5] + "xxxxx"  # 篡改 token

    # 通知端点
    url = f"{WS_BASE}/api/ws/notifications?token={bad_token}"
    log(f"通知端点(无效token): {url}")
    try:
        async with websockets.connect(url, ping_interval=None, close_timeout=5) as ws:
            log("⚠️  连接成功! 但预期应被拒绝 (close code 1008)")
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=3)
                log(f"📩 收到: {msg}")
            except asyncio.TimeoutError:
                pass
    except websockets.exceptions.WebSocketException as e:
        log(f"✅ 连接被拒绝 (符合预期): {type(e).__name__}")

    # 任务进度端点
    url2 = f"{WS_BASE}/api/ws/tasks/test_task?token={bad_token}"
    log(f"任务进度端点(无效token): {url2}")
    try:
        async with websockets.connect(url2, ping_interval=None, close_timeout=5) as ws:
            log("⚠️  连接成功! 但预期应被拒绝 (close code 1008)")
    except websockets.exceptions.WebSocketException as e:
        log(f"✅ 连接被拒绝 (符合预期): {type(e).__name__}")


async def test_heartbeat_mechanism(task_id: str):
    """测试心跳机制（仅测试分析模块端点，它有完整的心跳）"""
    log_sep("Test: 心跳机制测试 (分析模块端点)")
    url = f"{WS_BASE}/api/analysis/ws/task/{task_id}"
    log(f"连接: {url}")
    try:
        async with websockets.connect(url, ping_interval=None, close_timeout=10) as ws:
            log("✅ 连接成功!")
            # 接收连接确认
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            log(f"📩 初始消息: {json.loads(msg)}")

            # 测试接收 ping 并回复 pong
            log("等待服务器 ping (30s)...")
            try:
                msg2 = await asyncio.wait_for(ws.recv(), timeout=35)
                data2 = json.loads(msg2)
                log(f"📩 收到: {json.dumps(data2, ensure_ascii=False)}")
                if data2.get("type") == "ping":
                    log("✅ 收到服务端 ping")
                    # 回复 pong
                    await ws.send(json.dumps({"type": "pong"}))
                    log("✅ 已回复 pong")
            except asyncio.TimeoutError:
                log("⚠️ 服务器未在30s内发送 ping")

            log("🔌 主动断开")
    except websockets.exceptions.WebSocketException as e:
        log(f"❌ 连接失败: {e}")


async def test_reconnect_simulation(task_id: str):
    """测试断线重连 - 服务器端断开后的行为"""
    log_sep("Test: 断线重连模拟")
    url = f"{WS_BASE}/api/analysis/ws/task/{task_id}"
    log(f"连接: {url}")
    try:
        async with websockets.connect(url, ping_interval=None, close_timeout=5) as ws:
            log("✅ 连接成功!")
            # 接收初始消息
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            log(f"📩 初始消息: {json.loads(msg)}")

            # 模拟客户端断开（关闭连接）
            log("🔌 断开连接...")

        # 等待一小段时间
        await asyncio.sleep(1)
        log("✅ 连接已关闭，服务端应已清理连接")

    except websockets.exceptions.WebSocketException as e:
        log(f"❌ 连接失败: {e}")


async def test_websocket_stats(token: str):
    """测试 WebSocket 统计端点"""
    log_sep("Test: WebSocket 统计端点")
    resp = requests.get(f"{BASE_URL}/api/ws/stats", headers={"Authorization": f"Bearer {token}"}, timeout=5)
    data = resp.json()
    log(f"统计: {json.dumps(data, ensure_ascii=False, indent=2)}")


# ============================================================
# Main
# ============================================================
async def main():
    log_sep("TradingAgents-CN WebSocket 进度推送验证")
    log(f"后端地址: {BASE_URL}")
    log(f"WebSocket: {WS_BASE}")

    # Step 1: 获取 token
    token = get_token()

    # Step 2: 提交分析任务
    task_id = submit_analysis_task(token)
    log(f"使用 task_id: {task_id}")

    # Step 3: 测试各个端点
    await test_endpoint_no_auth()
    await test_invalid_token(token)
    await test_endpoint_ws_notifications(token)
    await test_endpoint_ws_tasks(task_id, token)
    await test_endpoint_analysis_ws_task(task_id)
    await test_heartbeat_mechanism(task_id)
    await test_reconnect_simulation(task_id)
    await test_websocket_stats(token)

    # ============================================================
    # 最终报告
    # ============================================================
    log_sep("验证报告")
    print("""
┌─────────────────────────────────────────────────────────────────────┐
│                    WebSocket 端点验证清单                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. /api/ws/notifications?token=<jwt>                              │
│     - 功能: 通知推送                                               │
│     - 认证: token (query param)                                    │
│     - 消息: connected → notification / heartbeat                   │
│                                                                     │
│  2. /api/ws/tasks/{task_id}?token=<jwt>                           │
│     - 功能: 任务进度推送 (通知模块)                                │
│     - 认证: token (query param)                                    │
│     - 消息: connected → progress / completed / error / heartbeat   │
│                                                                     │
│  3. /api/analysis/ws/task/{task_id}                               │
│     - 功能: 任务进度推送 (分析模块)                                │
│     - 认证: 无 🔴 (安全问题)                                       │
│     - 消息: connection_established → ping/pong                     │
│     - 心跳: 服务端每30s发送 ping                                   │
│                                                                     │
│  ⚠️ 注意: /ws/tasks/{task_id} 和 /analysis/ws/task/{task_id}      │
│    是两条独立的 WebSocket 路径，共享消息推送逻辑                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
""")


if __name__ == "__main__":
    asyncio.run(main())
