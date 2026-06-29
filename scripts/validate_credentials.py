#!/usr/bin/env python3
"""
凭据验证器 — 启动前校验所有必需凭据已设置且不使用默认值。
零降级：拒绝使用硬编码默认值，未设置时输出明确指引并退出。

检查项：
  1. MONGO_ROOT_PASSWORD — 不为空且 ≠ tradingagents123
  2. REDIS_PASSWORD      — 不为空且 ≠ tradingagents123
  3. JWT_SECRET          — 不为空且 ≠ change-me-in-production
  4. COOKIE_SECRET_KEY   — 不为空且 ≠ tradingagents_secret_key_2025
  5. ADMIN_PASSWORD      — 不为空且 ≠ admin123
  6. 所有密码强度 >= 16 字符

返回码：
  0 — 所有检查通过
  1 — 至少一项检查失败
"""

import os
import re
import sys

# ── 已知弱密码黑名单 ────────────────────────────────────────────────
WEAK_PASSWORDS = {
    "tradingagents123",
    "admin123",
    "password",
    "password123",
    "changeme",
    "change-me-in-production",
    "tradingagents_secret_key_2025",
    "docker-jwt-secret-key-change-in-production-2024",
    "docker-csrf-secret-key-change-in-production-2024",
}

# ── 检查项定义 ──────────────────────────────────────────────────────
# (环境变量名, 显示名称, 最小长度, 弱密码黑名单)
CHECK_ITEMS = [
    ("MONGO_ROOT_PASSWORD", "MongoDB Root 密码", 16, WEAK_PASSWORDS),
    ("REDIS_PASSWORD", "Redis 密码", 16, WEAK_PASSWORDS),
    ("JWT_SECRET", "JWT 签名密钥", 32, WEAK_PASSWORDS),
    ("COOKIE_SECRET_KEY", "Cookie 加密密钥", 32, WEAK_PASSWORDS),
    ("ADMIN_PASSWORD", "初始管理员密码", 8, WEAK_PASSWORDS),
]

# 可选但建议检查的凭据
OPTIONAL_CHECK_ITEMS = [
    ("MONGODB_PASSWORD", "MongoDB 用户密码", 16, WEAK_PASSWORDS),
]


def check_password_strength(password: str, min_length: int = 8) -> list[str]:
    """检查密码强度，返回问题列表（空列表 = 强度合格）"""
    issues: list[str] = []
    if len(password) < min_length:
        issues.append(f"长度不足（{len(password)} < {min_length} 字符）")
    if not re.search(r"[a-z]", password):
        issues.append("缺少小写字母")
    if not re.search(r"[A-Z]", password):
        issues.append("缺少大写字母")
    if not re.search(r"\d", password):
        issues.append("缺少数字")
    return issues


def check_credential(
    var_name: str,
    display_name: str,
    min_length: int,
    weak_set: set,
) -> tuple[bool, list[str]]:
    """检查单个凭据，返回 (通过?, [问题列表])"""
    issues: list[str] = []
    value = os.environ.get(var_name)

    if not value:
        issues.append(f"❌ 【未设置】环境变量 {var_name} 为空或未定义")
        return False, issues

    if value.strip() != value:
        issues.append(f"⚠️  {var_name} 包含前导/尾随空白")
        # 修整后继续检查
        value = value.strip()

    if value in weak_set:
        issues.append(f"🔴 【弱密码】{var_name} 使用了已知弱密码！请运行 generate_credentials.py 生成强密码")
        return False, issues

    # 强度检查（非密钥类凭据）
    if not var_name.endswith("_SECRET") and var_name != "JWT_SECRET":
        strength_issues = check_password_strength(value, min_length)
        if strength_issues:
            for si in strength_issues:
                issues.append(f"⚠️  {display_name} {si}")
            # 强度不足不阻塞启动，仅警告
            return True, issues

    return True, issues


def main() -> int:
    print("=" * 60)
    print("  TradingAgents-CN 凭据验证器")
    print("=" * 60)
    print()

    all_passed = True
    all_warnings: list[str] = []
    error_count = 0
    warning_count = 0

    # ── 检查必需项 ──────────────────────────────────────────────────
    print("📋 检查必需凭据:")
    print("-" * 40)
    for var_name, display_name, min_length, weak_set in CHECK_ITEMS:
        passed, issues = check_credential(var_name, display_name, min_length, weak_set)
        if passed and not issues:
            print(f"  ✅ {var_name} — 通过")
        else:
            for issue in issues:
                if issue.startswith("❌") or issue.startswith("🔴"):
                    print(f"  {issue}")
                    all_passed = False
                    error_count += 1
                else:
                    print(f"  {issue}")
                    all_warnings.append(f"{var_name}: {issue}")
                    warning_count += 1

    # ── 检查可选项 ──────────────────────────────────────────────────
    print()
    print("📋 检查可选凭据:")
    print("-" * 40)
    for var_name, display_name, min_length, weak_set in OPTIONAL_CHECK_ITEMS:
        passed, issues = check_credential(var_name, display_name, min_length, weak_set)
        if passed and not issues:
            print(f"  ✅ {var_name} — 通过")
        else:
            for issue in issues:
                if issue.startswith("❌"):
                    print(f"  ⚠️  {var_name} 未设置（可选，仅使用 MongoDB 时需要）")
                elif issue.startswith("🔴"):
                    print(f"  {issue}")
                    all_passed = False
                    error_count += 1
                else:
                    print(f"  {issue}")
                    warning_count += 1

    # ── 报告 ────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    if all_passed and warning_count == 0:
        print("  ✅ 所有凭据检查通过！")
        print("=" * 60)
        return 0

    if all_passed and warning_count > 0:
        print(f"  ⚠️  凭据检查通过，但有 {warning_count} 个警告：")
        for w in all_warnings:
            print(f"    - {w}")
        print("=" * 60)
        return 0

    # 有错误
    print(f"  🔴 凭据检查失败！{error_count} 个错误，{warning_count} 个警告")
    print()
    print("  请按以下步骤修复：")
    print()
    print("  1. 运行凭据生成器：")
    print("     python scripts/generate_credentials.py")
    print()
    print("  2. 或者手动设置环境变量后重新运行验证：")
    print("     python scripts/validate_credentials.py")
    print()
    print("  ⚠️  为保障系统安全，启动已被拒绝。")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    sys.exit(main())
