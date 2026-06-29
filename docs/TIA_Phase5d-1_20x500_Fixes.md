# TIA — 技术影响评估报告

> **项目**: TradingAgents-CN v1.0.1  
> **阶段**: Phase 5d-1 — 修复 20 个 HTTP 500 内部服务器错误  
> **日期**: 2026-06-16  
> **状态**: ✅ 全部修复并验证通过  

---

## 概述

本次修复针对 API 全量回归测试中发现的 **20 个 HTTP 500 错误**，分为两组：

| 分组 | 数量 | 路由范围 | 根因类别 |
|------|------|----------|----------|
| **Group A** | 16 | `/api/scheduler/*` (全部路由) | 全局单例未初始化 |
| **Group B** | 4 | `migrate-legacy`, `backups DELETE`, `logs/export/csv`, `tags DELETE` | 导入路径、数据验证、参数约束 |

**修复原则**: 仅改动有问题的文件，不修改无关代码；替换裸 `except:` 为具体异常类型；新增 ObjectId 格式验证将错误转化为 400 而非 500。

---

## Fix #1 — Scheduler 全局单例初始化 (Group A, 16 routes)

### 根因

[`app/main.py`](app/main.py:244) 的 `lifespan()` 异步上下文管理器在应用启动时**没有创建并设置 `AsyncIOScheduler` 实例**。所有 16 个 scheduler 路由均通过 `Depends(get_scheduler_service)` 依赖注入调用 [`scheduler_service.py`](app/services/scheduler_service.py:1046) 中的 `get_scheduler_service()`，该函数在检测到全局 `_scheduler_instance is None` 时抛出 `RuntimeError("调度器未初始化")`，FastAPI 全局异常处理器将其转为 500 响应。

### 修复内容

在 [`app/main.py`](app/main.py:294) 的 `lifespan()` 中，在 `yield` 之前插入：

```python
scheduler = AsyncIOScheduler()
try:
    set_scheduler_instance(scheduler)
    scheduler.start()
    logger.info("✅ 调度器实例已创建并启动")
except Exception as e:
    logger.warning(f"⚠️ 调度器初始化失败: {e}")
```

在 `yield` 之后插入：

```python
try:
    scheduler.shutdown(wait=False)
    logger.info("✅ 调度器已关闭")
except Exception as e:
    logger.warning(f"⚠️ 关闭调度器时出错: {e}")
```

### 影响范围

- **直接影响**: 16 个 scheduler 路由全部恢复可用
- **间接影响**: 无 — 不改变路由逻辑、不修改数据库结构
- **回滚风险**: 极低 — 仅增加启动/关闭流程，不影响现有数据

### 验证结果

| 端点 | 方法 | 状态码 | 说明 |
|------|------|--------|------|
| `/api/scheduler/jobs` | GET | ✅ 200 | 返回空任务列表 |
| `/api/scheduler/stats` | GET | ✅ 200 | 调度器统计 |
| `/api/scheduler/health` | GET | ✅ 200 | 健康检查 |
| `/api/scheduler/history` | GET | ✅ 200 | 历史记录 |
| `/api/scheduler/executions` | GET | ✅ 200 | 执行记录 |
| `/api/scheduler/jobs/{id}/detail` | GET | ✅ 404 | 不存在的任务返回 404 |
| `/api/scheduler/jobs/{id}/history` | GET | ✅ 200 |  |
| `/api/scheduler/jobs/{id}/executions` | GET | ✅ 200 |  |
| `/api/scheduler/jobs/{id}/execution-stats` | GET | ✅ 200 |  |
| `/api/scheduler/jobs/{id}/pause` | POST | ✅ 400 | 无请求体时返回 400 (Pydantic 校验) |
| `/api/scheduler/jobs/{id}/resume` | POST | ✅ 400 | 同上 |
| `/api/scheduler/jobs/{id}/trigger` | POST | ✅ 400 | 同上 |
| `/api/scheduler/jobs/{id}/metadata` | POST | ✅ 400 | 同上 |

> **说明**: pause/resume/trigger/metadata 在无请求体时返回 400 是预期的 Pydantic 校验行为，不是 500 错误。

---

## Fix #2 — `scripts/` 包缺失 (Group B, migrate-legacy)

### 根因

[`config_service.py`](app/services/config_service.py:865) 中 `migrate_legacy_config()` 执行 `from scripts.migrate_config_to_webapi import ConfigMigrator`。但 `scripts/` 目录缺少 `__init__.py` 文件，Python 无法将其识别为 package，导致 `ModuleNotFoundError`，转为 500 响应。

### 修复内容

创建 [`scripts/__init__.py`](scripts/__init__.py)，内容：

```python
# scripts package — utility and migration scripts
```

### 影响范围

- **直接影响**: 修复 `POST /api/config/migrate-legacy`
- **间接影响**: 使 `scripts/` 下所有模块可被导入
- **回滚风险**: 无

---

## Fix #3 — `webapi → app` 残留导入路径 (Group B, migrate-legacy)

### 根因

[`scripts/migrate_config_to_webapi.py`](scripts/migrate_config_to_webapi.py:20) 中仍使用 `from webapi.core.database import DatabaseManager` 等旧路径。项目已从 `webapi` 重命名为 `app`，这些导入全部失败。

### 修复内容

替换三处导入：

| 原导入 (webapi) | 新导入 (app) |
|----------------|-------------|
| `from webapi.core.database import DatabaseManager` | `from app.core.database import DatabaseManager` |
| `from webapi.models.config import (...)` | `from app.models.config import (...)` |
| `from webapi.services.config_service import ConfigService` | `from app.services.config_service import ConfigService` |

### 影响范围

- **直接影响**: 修复 `POST /api/config/migrate-legacy` — 全部 3 处导入路径修正
- **间接影响**: 无
- **回滚风险**: 低 — 仅修改导入路径

---

## Fix #4 — ObjectId 验证缺失 (Group B, backups DELETE)

### 根因

[`app/services/database/backups.py`](app/services/database/backups.py:219) 中 [`delete_backup(backup_id)`](app/services/database/backups.py:220) 直接调用 `ObjectId(backup_id)` 而不做格式验证。当传入非法 ID 字符串（如 `"1"`）时，`bson.errors.InvalidId` 异常被抛出，不被任何 except 捕获，最终由全局异常处理器转为 500。

### 修复内容

在 `delete_backup()` 中添加显式 ObjectId 格式验证：

```python
from bson.errors import InvalidId
try:
    oid = ObjectId(backup_id)
except (InvalidId, Exception) as e:
    logger.error(f"⚠️ 无效的备份 ID 格式: {backup_id} — {e}")
    raise ValueError(f"无效的备份 ID 格式: {backup_id}")
```

在 [`app/routers/database.py`](app/routers/database.py:238) 的 `delete_backup` 路由中添加了 `except ValueError` 分支，返回 400 而非 500：

```python
except ValueError as e:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(e)
    )
```

### 影响范围

- **直接影响**: 修复 `DELETE /api/system/database/backups/{backup_id}` 的非法 ID 场景
- **间接影响**: 无 — 合法 ID 路径不变
- **回滚风险**: 低 — 新增 `except ValueError` 在旧的 `except Exception` 之前，不会改变合法请求行为

---

## Fix #5 — 错误导入残留 (Group B, backups DELETE — 二次修复)

### 根因

Fix #4 的实现过程中，在 [`backups.py`](app/services/database/backups.py) 的 except 块中意外插入了 `from app.core.database import get_collection_names`。该函数在 `app.core.database` 中不存在，运行时触发 `ImportError` 转为 500。

### 修复内容

移除 `backups.py` 中 except 块内的 `from app.core.database import get_collection_names` 行。

### 影响范围

- **直接影响**: 修复 `DELETE /api/system/database/backups/{backup_id}` 在 except 路径上的崩溃
- **间接影响**: 无
- **回滚风险**: 无 — 仅删除一行不存在的导入

---

## Fix #6 — `page_size` Pydantic 约束过紧 (Group B, logs/export/csv)

### 根因

[`app/models/operation_log.py`](app/models/operation_log.py:52) 中 `OperationLogQuery.page_size` 的 Pydantic 定义为 `Field(20, ge=1, le=100, ...)`，而 [`app/routers/operation_logs.py`](app/routers/operation_logs.py:220) 的 `export_logs_csv()` 路由调用时传入了 `page_size=10000`（绕过模型验证直接传参）。实际数据库条目数为约 822 条，但 `10000 > 100` 触发 Pydantic 的 `le=100` 约束验证失败，返回 500。

### 修复内容

| 文件 | 改动 |
|------|------|
| [`app/models/operation_log.py`](app/models/operation_log.py:52) | `le=100` → `le=100000` |
| [`app/routers/operation_logs.py`](app/routers/operation_logs.py:220) | `page_size=10000` → `page_size=100000` |

### 影响范围

- **直接影响**: 修复 `GET /api/system/logs/export/csv`
- **间接影响**: 不影响分页列表查询（默认 20 条），仅提高导出 CSV 时的上限
- **回滚风险**: 低

---

## Fix #7 — ObjectId 验证缺失 (Group B, tags DELETE)

### 根因

[`app/routers/tags.py`](app/routers/tags.py:79) 中 [`delete_tag`](app/routers/tags.py:80) 路由直接将 `tag_id` 参数传入 service 层，service 层在 MongoDB 查询时调用 `ObjectId(tag_id)`。非法格式的 `tag_id` 抛出 `InvalidId` 异常，未被路由层捕获，转为 500。

### 修复内容

在 [`app/routers/tags.py`](app/routers/tags.py:84) 的 `delete_tag` 路由中添加 ObjectId 格式前置验证：

```python
from bson.errors import InvalidId
try:
    ObjectId(tag_id)
except (InvalidId, Exception):
    return JSONResponse(
        status_code=400,
        content={"success": False, "message": f"无效的标签 ID 格式: {tag_id}"}
    )
```

### 影响范围

- **直接影响**: 修复 `DELETE /api/tags/{tag_id}` 的非法 ID 场景
- **间接影响**: 无 — 合法 ID 路径不变
- **回滚风险**: 低

---

## 综合验证结果

### 测试环境

| 项目 | 值 |
|------|-----|
| 后端地址 | `http://localhost:8000` |
| Python 环境 | `.venv\Scripts\python.exe` (项目虚拟环境) |
| 认证方式 | JWT Bearer Token (admin/admin123) |
| 测试方法 | 带 Auth 头的 `Invoke-WebRequest` |

### 全部 20 个路由验证结果

| # | 路由 | 修复前 | 修复后 | 说明 |
|---|------|--------|--------|------|
| 1 | `GET /api/scheduler/jobs` | 500 | ✅ 200 | Fix #1 |
| 2 | `GET /api/scheduler/stats` | 500 | ✅ 200 | Fix #1 |
| 3 | `GET /api/scheduler/health` | 500 | ✅ 200 | Fix #1 |
| 4 | `GET /api/scheduler/history` | 500 | ✅ 200 | Fix #1 |
| 5 | `GET /api/scheduler/executions` | 500 | ✅ 200 | Fix #1 |
| 6 | `GET /api/scheduler/jobs/{id}` | 500 | ✅ 404 | Fix #1 |
| 7 | `POST /api/scheduler/jobs/{id}/pause` | 500 | ✅ 400 | Fix #1 |
| 8 | `POST /api/scheduler/jobs/{id}/resume` | 500 | ✅ 400 | Fix #1 |
| 9 | `POST /api/scheduler/jobs/{id}/trigger` | 500 | ✅ 400 | Fix #1 |
| 10 | `GET /api/scheduler/jobs/{id}/detail` | 500 | ✅ 404 | Fix #1 |
| 11 | `GET /api/scheduler/jobs/{id}/history` | 500 | ✅ 200 | Fix #1 |
| 12 | `GET /api/scheduler/jobs/{id}/executions` | 500 | ✅ 200 | Fix #1 |
| 13 | `GET /api/scheduler/jobs/{id}/execution-stats` | 500 | ✅ 200 | Fix #1 |
| 14 | `POST /api/scheduler/jobs/{id}/metadata` | 500 | ✅ 400 | Fix #1 |
| 15 | `DELETE /api/scheduler/executions/{id}` | 500 | ✅ 404 | Fix #1 |
| 16 | `POST /api/scheduler/executions/{id}/cancel` | 500 | ✅ 404 | Fix #1 |
| 17 | `POST /api/config/migrate-legacy` | 500 | ✅ 200 | Fix #2 + Fix #3 |
| 18 | `DELETE /api/system/database/backups/{id}` | 500 | ✅ 400 | Fix #4 + Fix #5 |
| 19 | `GET /api/system/logs/export/csv` | 500 | ✅ 200 | Fix #6 |
| 20 | `DELETE /api/tags/{id}` | 500 | ✅ 400 | Fix #7 |

**结果**: 20/20 路由不再返回 500 ✅

---

## 修改文件清单

| # | 文件路径 | 改动类型 | 关联 Fix |
|---|----------|----------|----------|
| 1 | [`app/main.py`](app/main.py) | 修改 | Fix #1 |
| 2 | [`scripts/__init__.py`](scripts/__init__.py) | 新建 | Fix #2 |
| 3 | [`scripts/migrate_config_to_webapi.py`](scripts/migrate_config_to_webapi.py) | 修改 | Fix #3 |
| 4 | [`app/services/database/backups.py`](app/services/database/backups.py) | 修改 | Fix #4, #5 |
| 5 | [`app/routers/database.py`](app/routers/database.py) | 修改 | Fix #4 |
| 6 | [`app/models/operation_log.py`](app/models/operation_log.py) | 修改 | Fix #6 |
| 7 | [`app/routers/operation_logs.py`](app/routers/operation_logs.py) | 修改 | Fix #6 |
| 8 | [`app/routers/tags.py`](app/routers/tags.py) | 修改 | Fix #7 |

**总计**: 8 个文件 (1 新建, 7 修改)

---

## 经验教训

1. **全局单例模式的风险**: `set_scheduler_instance()` 必须在应用启动时被调用，依赖此单例的所有路由在初始化前全部不可用。建议使用 FastAPI 的 `app.state` 或依赖注入容器来管理此类资源生命周期。

2. **Pydantic Field 约束与业务需求的冲突**: `le=100` 的约束在分页场景下合理，但在 CSV 全量导出时成为瓶颈。建议对导出场景使用独立参数模型。

3. **`webapi → app` 重命名残留**: 项目重命名后，`scripts/` 目录下的迁移脚本未被检查。建议在重构后对 `import webapi` 做全库正则扫描。

4. **ObjectId 输入验证**: MongoDB 的 `ObjectId()` 构造函数在不合法输入时抛出异常，所有接收 ID 参数的端点都应添加前置格式验证并返回 400。

---

## 后续建议

- [ ] 考虑将 `AsyncIOScheduler` 生命周期纳入 FastAPI `app.state` 管理，而非全局变量
- [ ] 对全项目所有接收 `ObjectId` 字符串参数的端点进行统一审计，确保均有格式验证
- [ ] 在 CI 流程中加入 API 回归测试，确保类似问题不再漏出

---

*报告完毕 — 所有 20 个 HTTP 500 错误已修复并验证通过。*
