#!/usr/bin/env python3
"""
凭据生成器 — 使用 secrets 模块生成强随机密码和密钥。
零降级：不覆盖已有凭据，仅补充缺失项。

生成以下凭据（若 .env 中尚未设置）：
  - MONGO_ROOT_PASSWORD    MongoDB root 密码
  - REDIS_PASSWORD          Redis 密码
  - COOKIE_SECRET_KEY       Cookie 加密密钥（64 字节 Hex）
  - JWT_SECRET              JWT 签名密钥（32 字节 Hex）
  - ADMIN_PASSWORD          初始管理员密码（24 字符可打印）

输出方式：
  1. 直接写入 .env 文件（若已存在则仅补充缺失项）
  2. 同时输出到 config/credentials.env 作为集中凭据管理文件
  3. 输出到控制台（便于手动设置）
"""

import secrets
import string
from pathlib import Path


# ── 项目根目录探测 ──────────────────────────────────────────────────
def _find_project_root() -> Path:
    """从当前文件向上搜索，找到包含 .env.example 或 pyproject.toml 的目录"""
    cwd = Path.cwd()
    for candidate in [cwd, *list(cwd.parents)]:
        if (candidate / ".env.example").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    # fallback: 当前目录
    return cwd


PROJECT_ROOT = _find_project_root()
DOT_ENV_PATH = PROJECT_ROOT / ".env"
CREDENTIALS_ENV_PATH = PROJECT_ROOT / "config" / "credentials.env"


# ── 密码生成函数 ────────────────────────────────────────────────────
def generate_password(length: int = 32) -> str:
    """生成 length 字符的十六进制随机字符串（适合 MongoDB / Redis 密码）"""
    return secrets.token_hex(length // 2 + 1)[:length]


def generate_printable_password(length: int = 24) -> str:
    """生成 length 字符的可打印 ASCII 密码（适合管理员密码）"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        # 确保至少包含一个小写、一个大写、一个数字和一个特殊字符
        if (
            any(c.islower() for c in pwd)
            and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "!@#$%^&*" for c in pwd)
        ):
            return pwd


def generate_cookie_secret() -> str:
    """生成 64 字节的 Cookie 加密密钥（128 字符 Hex）"""
    return secrets.token_hex(64)


def generate_jwt_secret() -> str:
    """生成 32 字节的 JWT 签名密钥（64 字符 Hex）"""
    return secrets.token_hex(32)


# ── 凭据定义 ────────────────────────────────────────────────────────
# 格式: (环境变量名, 生成函数, 描述)
CREDENTIAL_DEFINITIONS = [
    ("MONGO_ROOT_PASSWORD", generate_password, "MongoDB root 密码（32 字符 Hex）"),
    ("REDIS_PASSWORD", generate_password, "Redis 密码（32 字符 Hex）"),
    ("COOKIE_SECRET_KEY", generate_cookie_secret, "Cookie 加密密钥（128 字符 Hex）"),
    ("JWT_SECRET", generate_jwt_secret, "JWT 签名密钥（64 字符 Hex）"),
    ("ADMIN_PASSWORD", generate_printable_password, "初始管理员密码（24 字符可打印）"),
]


# ── 读取 / 写入 .env ────────────────────────────────────────────────
def parse_env_file(path: Path) -> dict[str, str]:
    """解析 .env 文件，返回 {KEY: VALUE} 字典（保留注释和空行按原样）"""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    with open(path, encoding="utf-8") as f:
        for line in f:
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("#"):
                continue
            if "=" in line_stripped:
                key, _, value = line_stripped.partition("=")
                key = key.strip()
                value = value.strip().strip("\"'")
                result[key] = value
    return result


def write_env_file(path: Path, env: dict[str, str]) -> None:
    """将 {KEY: VALUE} 字典写回 .env 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for key, value in env.items():
            if value:
                f.write(f"{key}={value}\n")
            else:
                f.write(f"{key}=\n")


def merge_env(existing: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    """合并两个 env 字典，新值不覆盖已有的（零降级）"""
    merged = dict(existing)
    for key, value in new.items():
        if key not in existing or not existing[key]:
            merged[key] = value
    return merged


# ── 主流程 ──────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  TradingAgents-CN 凭据生成器")
    print("=" * 60)
    print()

    # 1. 读取现有 .env（如果存在）
    existing_env = parse_env_file(DOT_ENV_PATH)
    if existing_env:
        print(f"📄 检测到现有 .env 文件: {DOT_ENV_PATH}")
        print(f"   已有 {len(existing_env)} 个变量，将仅补充缺失项")
    else:
        print("📄 .env 文件不存在，将创建新文件")

    # 2. 生成凭据
    new_credentials: dict[str, str] = {}
    print()

    for var_name, gen_func, description in CREDENTIAL_DEFINITIONS:
        if existing_env.get(var_name):
            print(f"  ✅ {var_name} 已存在，跳过")
            continue

        value = gen_func()
        new_credentials[var_name] = value
        print(f"  🔑 {var_name} = {value}")
        print(f"     ({description})")

    if not new_credentials:
        print("\n所有凭据已存在，无需生成。")
        # 但仍输出到 credentials.env（同步）
        _sync_credentials_file(existing_env)
        return

    # 3. 合并到 .env
    merged = merge_env(existing_env, new_credentials)
    write_env_file(DOT_ENV_PATH, merged)
    print(f"\n✅ 已更新 .env 文件: {DOT_ENV_PATH}")

    # 4. 同步到 config/credentials.env
    _sync_credentials_file(merged)

    # 5. 输出摘要
    print()
    print("─" * 60)
    print("  生成的凭据摘要")
    print("─" * 60)
    for var_name, gen_func, description in CREDENTIAL_DEFINITIONS:
        val = merged.get(var_name, "")
        if val:
            masked = val[:8] + "..." if len(val) > 12 else val
            print(f"  {var_name:<25} = {masked}")
        else:
            print(f"  ⚠️  {var_name:<25} = (未设置)")
    print()
    print("  ⚠️  请妥善保管以上凭据！")
    print("  运行 validate_credentials.py 验证凭据配置。")
    print("=" * 60)


def _sync_credentials_file(env: dict[str, str]) -> None:
    """同步凭据到 config/credentials.env"""
    credential_keys = {defn[0] for defn in CREDENTIAL_DEFINITIONS}
    cred_env = {k: v for k, v in env.items() if k in credential_keys}
    if cred_env:
        write_env_file(CREDENTIALS_ENV_PATH, cred_env)
        print(f"✅ 已同步到凭据文件: {CREDENTIALS_ENV_PATH}")


if __name__ == "__main__":
    main()
