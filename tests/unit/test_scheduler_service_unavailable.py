#!/usr/bin/env python
"""
测试当调度器服务不可用（get_scheduler_service 返回 None）时，
路由层应返回 503 Service Unavailable 而非 500 Internal Server Error。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import scheduler as scheduler_router
from app.routers.auth_db import get_current_user
from app.services.scheduler_service import get_scheduler_service

PREFIX = "/api/scheduler"


def create_test_app():
    """创建仅挂载 scheduler 路由的最小测试应用，避免触发 app.main lifespan"""
    app = FastAPI()
    app.include_router(scheduler_router.router)
    # 覆盖 auth 依赖，绕过 Bearer token 校验
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "test",
        "username": "test",
        "is_admin": True,
        "roles": ["admin"],
    }
    return app


@pytest.fixture
def client():
    app = create_test_app()
    with TestClient(app) as c:
        yield c


class TestSchedulerServiceUnavailable:
    """
    当 get_scheduler_service() 返回 None 时，所有路由均应返回 503。
    覆盖所有 16 个路由端点，确保无遗漏。
    """

    def _setup_none_service(self, app):
        """将 get_scheduler_service 覆盖为返回 None"""
        app.dependency_overrides[get_scheduler_service] = lambda: None

    # ── GET 端点 ──────────────────────────────────────────

    def test_list_jobs_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.get(f"{PREFIX}/jobs")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"
        assert "调度器服务不可用" in resp.text

    def test_get_job_detail_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.get(f"{PREFIX}/jobs/test_job")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"

    def test_get_job_history_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.get(f"{PREFIX}/jobs/test_job/history")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"

    def test_get_all_history_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.get(f"{PREFIX}/history")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"

    def test_get_scheduler_stats_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.get(f"{PREFIX}/stats")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"

    def test_scheduler_health_check_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.get(f"{PREFIX}/health")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"

    def test_get_job_executions_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.get(f"{PREFIX}/executions")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"

    def test_get_single_job_executions_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.get(f"{PREFIX}/jobs/test_job/executions")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"

    def test_get_job_execution_stats_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.get(f"{PREFIX}/jobs/test_job/execution-stats")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"

    # ── POST 端点 ─────────────────────────────────────────

    def test_pause_job_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.post(f"{PREFIX}/jobs/test_job/pause")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"

    def test_resume_job_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.post(f"{PREFIX}/jobs/test_job/resume")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"

    def test_trigger_job_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.post(f"{PREFIX}/jobs/test_job/trigger")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"

    def test_cancel_execution_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.post(f"{PREFIX}/executions/test_id/cancel")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"

    def test_mark_execution_failed_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.post(f"{PREFIX}/executions/test_id/mark-failed")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"

    # ── PUT 端点 ──────────────────────────────────────────

    def test_update_job_metadata_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.put(f"{PREFIX}/jobs/test_job/metadata", json={})
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"

    # ── DELETE 端点 ───────────────────────────────────────

    def test_delete_execution_returns_503_when_service_none(self, client):
        app = client.app
        self._setup_none_service(app)
        resp = client.delete(f"{PREFIX}/executions/test_id")
        assert resp.status_code == 503, f"期望 503，得到 {resp.status_code}"
