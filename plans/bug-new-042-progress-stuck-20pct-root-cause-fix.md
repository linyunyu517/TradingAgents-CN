# BUG-NEW-042: Progress stuck at 20% (model_loading) — Root Cause & Fix

## Bug ID
BUG-NEW-042

## Severity
P0 — Production: progress never advances beyond 20%, users see "正在加载分析模型..." forever

## Root Cause (Confirmed by Log Evidence)

### Fault Chain
1. **`_send_progress_update()`** at [`trading_graph.py:1280`](../tradingagents/graph/trading_graph.py:1280) calls `progress_callback(progress_data)` where `progress_data` is a **dict**:
   ```python
   progress_data = {
       "status": "running",
       "elapsed_time": 12.5,
       "remaining_time": 25.0,
       "estimated_total_time": 2400,
       "progress_percentage": 33.3,
       "message": "🔮 AIF 预测",  # <-- node name is nested inside
   }
   progress_callback(progress_data)  # sends dict, not str!
   ```

2. **`graph_progress_callback(message: str)`** at [`simple_analysis_service.py:1336`](../app/services/simple_analysis_service.py:1336) declares `message: str` but receives **dict**.

3. **Line 1350** [`simple_analysis_service.py:1350`](../app/services/simple_analysis_service.py:1350): `if message in _seen_progress_messages:` → **`TypeError: unhashable type: 'dict'`**

   Log confirmation:
   ```
   2026-06-22 21:30:52 ERROR ❌ Graph进度回调失败: unhashable type: 'dict'
     File "simple_analysis_service.py", line 1350, in graph_progress_callback
       if message in _seen_progress_messages:
   TypeError: unhashable type: 'dict'
   ```

4. **Line 1389-1390** [`simple_analysis_service.py:1389`](../app/services/simple_analysis_service.py:1389): The outer `except Exception` catches the TypeError, logs it, and **silently discards** the progress update.

5. **Result**: Every single callback from the trading graph crashes at line 1350 → **progress stays at 20% forever**.

### Secondary Bug: Fallback Counter Cannot Escape 20%

Even if the TypeError were caught gracefully, the fallback counter at line 1365 has a **design flaw**:

```python
progress_pct = min(95, (_progress_callback_count * 100) // 15)
# count=1 → 6, count=2 → 13, count=3 → 20
new_pct = max(6, 20) = 20  # ← ALWAYS capped by initial 20%!
```

When `_PROGRESS_TOTAL_STEPS = 15`:
- callback #1: `min(95, 100//15) = 6` → `max(6, 20) = 20` ✗
- callback #2: `min(95, 200//15) = 13` → `max(13, 20) = 20` ✗
- callback #3: `min(95, 300//15) = 20` → `max(20, 20) = 20` ✗
- callback #4: `min(95, 400//15) = 26` → `max(26, 20) = 26` ✓ (finally escapes!)

So even with the bug fixed, the first **3 callbacks produce no progress advancement**, wasting ~3-5 seconds of user feedback.

### Related: `_seen_progress_messages` set stores dict

Even if we replaced `in` with a try-except, the set would store the dict object, causing memory reference issues and `TypeError` on subsequent lookups.

## Impact Scope

| Scope | Finding |
|-------|---------|
| `model_loading` step references | ONLY 1 occurrence in entire codebase ([`line 1264`](../app/services/simple_analysis_service.py:1264)) |
| `graph_progress_callback` definition | ONLY in [`simple_analysis_service.py:1336`](../app/services/simple_analysis_service.py:1336) |
| `_seen_progress_messages` usage | ONLY in `graph_progress_callback` |
| `node_progress_map` usage | [`simple_analysis_service.py`](../app/services/simple_analysis_service.py:1274) + [`test_progress_tracking.py`](../scripts/test_progress_tracking.py:108) |
| `_send_progress_update` | ONLY in [`trading_graph.py`](../tradingagents/graph/trading_graph.py:1136) |
| Other callback implementations (`analysis_service.py`, `worker.py`, `web/app.py`) | Different signatures — NOT affected |
| Frontend `model_loading` step reference | Only present as `current_step_name` in MongoDB task documents |

**Conclusion**: Bug is **isolated to** [`simple_analysis_service.py:graph_progress_callback`](../app/services/simple_analysis_service.py:1336) ↔ [`trading_graph.py:_send_progress_update`](../tradingagents/graph/trading_graph.py:1280). No other files are affected.

## Fix Applied

**File**: [`app/services/simple_analysis_service.py:1336`](../app/services/simple_analysis_service.py:1336)

### Three-Pronged Fix

#### ① Compat dict message (`_node_key` extraction)
```python
_node_key = message
if isinstance(message, dict):
    _node_key = message.get('message', '') or ''
```
Extracts `"🔮 AIF 预测"` from `{'status': 'running', 'message': '🔮 AIF 预测', ...}`, enabling correct `node_progress_map` lookup.

#### ② Fix `_seen_progress_messages` set (skip for dict)
```python
if not _is_dict_msg:
    if _node_key in _seen_progress_messages:
        ...
    else:
        _seen_progress_messages.add(_node_key)
```
Dict messages skip set operations entirely, avoiding `TypeError: unhashable type: 'dict'`.

#### ③ Fix fallback counter escape
```python
# Original: progress_pct starts at 6%, always capped by current 20%
# Fix: force +1% minimum advancement when counter is stuck
if new_pct == current_progress and _progress_callback_count > 1:
    new_pct = min(95, current_progress + 1)
```
Ensures fallback counter can always advance progress by at least 1% per callback, even when current progress is high.

## Verification

After fix, the expected behavior for task `fd0d2330` (stock 000425):
1. `graph_progress_callback` receives `dict` → extracts `"🔮 AIF 预测"` → `node_progress_map["🔮 AIF 预测"]` = 36
2. Progress updates correctly from 20% → 36% on first callback
3. No `TypeError` logged
4. All subsequent node callbacks map correctly (HSR-MC 28→34%, AIF 36→48%, analysts 57.5→75%, etc.)
5. Users see real-time progress instead of permanent "正在加载分析模型..."

## Timeline
- **21:30:46** — Task `fd0d2330` created
- **21:30:52** — First `TypeError: unhashable type: 'dict'` logged (first graph callback)
- **21:30:53** — 4 more TypeErrors logged (4 more callbacks silently dropped)
- **21:31:37** — Status query: `progress: 20, message: "正在加载分析模型..."` 
- **21:47:39** — Status query: STILL `progress: 20` (1012 seconds stuck!)
- **21:47:39** — Watchdog warning: "任务疑似卡死 (超过5分钟未更新)"
