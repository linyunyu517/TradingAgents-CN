"""
用户认证管理器
处理用户登录、权限验证等功能
支持前端缓存登录状态，10分钟无操作自动失效

安全加固：
- [Bug B02] 移除硬编码默认密码 admin123/user123
- [Bug B21] 添加密码强度检查基础框架
- [Bug B21] 添加登录失败速率限制基础设施
"""

import hashlib
import json
import os
import time
from pathlib import Path

import streamlit as st

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("auth")

# 导入用户活动记录器
try:
    from .user_activity_logger import user_activity_logger
except ImportError:
    user_activity_logger = None
    logger.warning("⚠️ 用户活动记录器导入失败")


# ============================================================
# 🔒 [Bug B21] 密码强度检查
# ============================================================
def check_password_strength(password: str) -> tuple[bool, str]:
    """
    检查密码强度

    Args:
        password: 待检查的密码

    Returns:
        (是否通过, 提示信息)
    """
    if len(password) < 8:
        return False, "密码长度至少8位"
    if not any(c.isupper() for c in password):
        return False, "密码需包含至少一个大写字母"
    if not any(c.islower() for c in password):
        return False, "密码需包含至少一个小写字母"
    if not any(c.isdigit() for c in password):
        return False, "密码需包含至少一个数字"
    if not any(c in "!@#$%^&*()-_=+[]{}|;:',.<>?/`~" for c in password):
        return False, "密码需包含至少一个特殊字符"
    return True, ""


# ============================================================
# 🔒 [Bug B21] 登录失败记录器（速率限制基础设施）
# ============================================================
class LoginAttemptTracker:
    """登录失败跟踪器 - 用于速率限制"""

    def __init__(self, max_attempts: int = 5, lockout_minutes: int = 15):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_minutes * 60
        self._attempts: dict[str, list] = {}  # username -> [timestamp, ...]

    def record_failure(self, username: str):
        """记录一次登录失败"""
        now = time.time()
        if username not in self._attempts:
            self._attempts[username] = []
        # 清理过期记录
        self._attempts[username] = [t for t in self._attempts[username] if now - t < self.lockout_seconds]
        self._attempts[username].append(now)

    def is_locked(self, username: str) -> bool:
        """检查用户是否被锁定"""
        if username not in self._attempts:
            return False
        now = time.time()
        recent = [t for t in self._attempts[username] if now - t < self.lockout_seconds]
        return len(recent) >= self.max_attempts

    def get_remaining_attempts(self, username: str) -> int:
        """获取剩余尝试次数"""
        if username not in self._attempts:
            return self.max_attempts
        now = time.time()
        recent = [t for t in self._attempts[username] if now - t < self.lockout_seconds]
        return max(0, self.max_attempts - len(recent))

    def reset(self, username: str):
        """重置用户的失败记录（登录成功后调用）"""
        self._attempts.pop(username, None)


# 全局登录失败跟踪器
login_tracker = LoginAttemptTracker()


# ============================================================
# 🔒 [Bug B02] 从环境变量读取管理员默认密码
# ============================================================
def _get_admin_default_password() -> str | None:
    """
    从环境变量 ADMIN_DEFAULT_PASSWORD 读取管理员默认密码

    Returns:
        密码字符串，如果未设置则返回 None
    """
    return os.environ.get("ADMIN_DEFAULT_PASSWORD") or None


def _get_user_default_password() -> str | None:
    """
    从环境变量 USER_DEFAULT_PASSWORD 读取普通用户默认密码

    Returns:
        密码字符串，如果未设置则返回 None
    """
    return os.environ.get("USER_DEFAULT_PASSWORD") or None


class AuthManager:
    """用户认证管理器"""

    def __init__(self):
        self.users_file = Path(__file__).parent.parent / "config" / "users.json"
        self.session_timeout = 600000
        self._ensure_users_file()

    def _ensure_users_file(self):
        """确保用户配置文件存在"""
        self.users_file.parent.mkdir(exist_ok=True)

        if not self.users_file.exists():
            # 🔒 [Bug B02/B21] 不再使用硬编码的弱密码
            # 必须从环境变量读取，如果未设置则拒绝创建默认用户
            admin_password = _get_admin_default_password()
            user_password = _get_user_default_password()

            if not admin_password:
                logger.error("=" * 60)
                logger.error("❌ [安全拒绝] 环境变量 ADMIN_DEFAULT_PASSWORD 未设置！")
                logger.error("   系统无法使用弱密码回退，请通过以下方式设置：")
                logger.error("   1. 运行: python scripts/generate_credentials.py")
                logger.error("   2. 或手动设置环境变量 ADMIN_DEFAULT_PASSWORD")
                logger.error("=" * 60)
                # 不创建默认用户文件，后续认证将失败
                return

            if not user_password:
                logger.error("=" * 60)
                logger.error("❌ [安全拒绝] 环境变量 USER_DEFAULT_PASSWORD 未设置！")
                logger.error("   系统无法使用弱密码回退，请通过以下方式设置：")
                logger.error("   1. 运行: python scripts/generate_credentials.py")
                logger.error("   2. 或手动设置环境变量 USER_DEFAULT_PASSWORD")
                logger.error("=" * 60)
                return

            # 检查密码强度
            is_strong_admin, admin_msg = check_password_strength(admin_password)
            if not is_strong_admin:
                logger.error(f"❌ [安全拒绝] ADMIN_DEFAULT_PASSWORD 不符合密码强度要求：{admin_msg}")
                logger.error("   请使用包含大小写字母、数字和特殊字符的8位以上密码")
                return

            is_strong_user, user_msg = check_password_strength(user_password)
            if not is_strong_user:
                logger.error(f"❌ [安全拒绝] USER_DEFAULT_PASSWORD 不符合密码强度要求：{user_msg}")
                logger.error("   请使用包含大小写字母、数字和特殊字符的8位以上密码")
                return

            # 创建默认用户配置（使用环境变量中的强密码）
            default_users = {
                "admin": {
                    "password_hash": self._hash_password(admin_password),
                    "role": "admin",
                    "permissions": ["analysis", "config", "admin"],
                    "created_at": time.time(),
                },
                "user": {
                    "password_hash": self._hash_password(user_password),
                    "role": "user",
                    "permissions": ["analysis"],
                    "created_at": time.time(),
                },
            }

            with open(self.users_file, "w", encoding="utf-8") as f:
                json.dump(default_users, f, indent=2, ensure_ascii=False)

            logger.info("✅ 用户认证系统初始化完成（使用环境变量中的安全密码）")
            logger.info(f"📁 用户配置文件: {self.users_file}")

    def _inject_auth_cache_js(self):
        """注入前端认证缓存JavaScript代码"""
        js_code = """
        <script>
        // 认证缓存管理
        window.AuthCache = {
            // 保存登录状态到localStorage
            saveAuth: function(userInfo) {
                const authData = {
                    userInfo: userInfo,
                    loginTime: Date.now(),
                    lastActivity: Date.now()
                };
                localStorage.setItem('tradingagents_auth', JSON.stringify(authData));
                console.log('✅ 登录状态已保存到前端缓存');
            },

            // 从localStorage获取登录状态
            getAuth: function() {
                try {
                    const authData = localStorage.getItem('tradingagents_auth');
                    if (!authData) return null;

                    const data = JSON.parse(authData);
                    const now = Date.now();
                    const timeout = 10 * 60 * 1000; // 10分钟

                    // 检查是否超时
                    if (now - data.lastActivity > timeout) {
                        this.clearAuth();
                        console.log('⏰ 登录状态已过期，自动清除');
                        return null;
                    }

                    // 更新最后活动时间
                    data.lastActivity = now;
                    localStorage.setItem('tradingagents_auth', JSON.stringify(data));

                    return data.userInfo;
                } catch (e) {
                    console.error('❌ 读取登录状态失败:', e);
                    this.clearAuth();
                    return null;
                }
            },

            // 清除登录状态
            clearAuth: function() {
                localStorage.removeItem('tradingagents_auth');
                console.log('🧹 登录状态已清除');
            },

            // 更新活动时间
            updateActivity: function() {
                const authData = localStorage.getItem('tradingagents_auth');
                if (authData) {
                    try {
                        const data = JSON.parse(authData);
                        data.lastActivity = Date.now();
                        localStorage.setItem('tradingagents_auth', JSON.stringify(data));
                    } catch (e) {
                        console.error('❌ 更新活动时间失败:', e);
                    }
                }
            }
        };

        // 监听用户活动，更新最后活动时间
        ['click', 'keypress', 'scroll', 'mousemove'].forEach(event => {
            document.addEventListener(event, function() {
                window.AuthCache.updateActivity();
            }, { passive: true });
        });

        // 页面加载时检查登录状态
        document.addEventListener('DOMContentLoaded', function() {
            const authInfo = window.AuthCache.getAuth();
            if (authInfo) {
                console.log('🔄 从前端缓存恢复登录状态:', authInfo.username);
                // 通知Streamlit恢复登录状态
                window.parent.postMessage({
                    type: 'restore_auth',
                    userInfo: authInfo
                }, '*');
            }
        });
        </script>
        """
        st.components.v1.html(js_code, height=0)

    def _hash_password(self, password: str) -> str:
        """密码哈希"""
        return hashlib.sha256(password.encode()).hexdigest()

    def _load_users(self) -> dict:
        """加载用户配置"""
        try:
            with open(self.users_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ 加载用户配置失败: {e}")
            return {}

    def authenticate(self, username: str, password: str) -> tuple[bool, dict | None]:
        """
        用户认证

        Args:
            username: 用户名
            password: 密码

        Returns:
            (认证成功, 用户信息)
        """
        # 🔒 [Bug B21] 检查登录速率限制
        if login_tracker.is_locked(username):
            login_tracker.get_remaining_attempts(username)
            logger.warning(f"⛔ 用户 {username} 已被临时锁定（过多失败尝试）")
            if user_activity_logger:
                user_activity_logger.log_login(username, False, "账户临时锁定（速率限制）")
            return False, None

        users = self._load_users()

        if not users:
            logger.error("❌ 用户配置为空，请检查 ADMIN_DEFAULT_PASSWORD / USER_DEFAULT_PASSWORD 环境变量是否配置")
            return False, None

        if username not in users:
            logger.warning(f"⚠️ 用户不存在: {username}")
            # 记录登录失败
            if user_activity_logger:
                user_activity_logger.log_login(username, False, "用户不存在")
            return False, None

        user_info = users[username]
        password_hash = self._hash_password(password)

        if password_hash == user_info["password_hash"]:
            logger.info(f"✅ 用户登录成功: {username}")
            # 记录登录成功
            if user_activity_logger:
                user_activity_logger.log_login(username, True)
            # 🔒 [Bug B21] 登录成功后重置失败计数
            login_tracker.reset(username)
            return True, {"username": username, "role": user_info["role"], "permissions": user_info["permissions"]}
        logger.warning(f"⚠️ 密码错误: {username}")
        # 🔒 [Bug B21] 记录登录失败
        login_tracker.record_failure(username)
        if user_activity_logger:
            user_activity_logger.log_login(username, False, "密码错误")
        return False, None

    def check_permission(self, permission: str) -> bool:
        """
        检查当前用户权限

        Args:
            permission: 权限名称

        Returns:
            是否有权限
        """
        if not self.is_authenticated():
            return False

        user_info = st.session_state.get("user_info", {})
        permissions = user_info.get("permissions", [])

        return permission in permissions

    def is_authenticated(self) -> bool:
        """检查用户是否已认证"""
        # 首先检查session_state中的认证状态
        authenticated = st.session_state.get("authenticated", False)
        login_time = st.session_state.get("login_time", 0)
        current_time = time.time()

        logger.debug(
            f"🔍 [认证检查] authenticated: {authenticated}, login_time: {login_time}, current_time: {current_time}",
        )

        if authenticated:
            # 检查会话超时
            time_elapsed = current_time - login_time
            logger.debug(f"🔍 [认证检查] 会话时长: {time_elapsed:.1f}秒, 超时限制: {self.session_timeout}秒")

            if time_elapsed > self.session_timeout:
                logger.info(f"⏰ 会话超时，自动登出 (已过时间: {time_elapsed:.1f}秒)")
                self.logout()
                return False

            logger.debug("✅ [认证检查] 用户已认证且未超时")
            return True

        logger.debug("❌ [认证检查] 用户未认证")
        return False

    def login(self, username: str, password: str) -> bool:
        """
        用户登录

        Args:
            username: 用户名
            password: 密码

        Returns:
            登录是否成功
        """
        success, user_info = self.authenticate(username, password)

        if success:
            st.session_state.authenticated = True
            st.session_state.user_info = user_info
            st.session_state.login_time = time.time()

            # 保存到前端缓存 - 使用与前端JavaScript兼容的格式
            current_time_ms = int(time.time() * 1000)  # 转换为毫秒
            auth_data = {
                "userInfo": user_info,  # 使用userInfo而不是user_info
                "loginTime": time.time(),
                "lastActivity": current_time_ms,  # 添加lastActivity字段
                "authenticated": True,
            }

            save_to_cache_js = f"""
            <script>
            console.log('🔐 保存认证数据到localStorage');
            try {{
                const authData = {json.dumps(auth_data)};
                localStorage.setItem('tradingagents_auth', JSON.stringify(authData));
                console.log('✅ 认证数据已保存到localStorage:', authData);
            }} catch (e) {{
                console.error('❌ 保存认证数据失败:', e);
            }}
            </script>
            """
            st.components.v1.html(save_to_cache_js, height=0)

            logger.info(f"✅ 用户 {username} 登录成功，已保存到前端缓存")
            return True
        st.session_state.authenticated = False
        st.session_state.user_info = None
        return False

    def logout(self):
        """用户登出"""
        username = st.session_state.get("user_info", {}).get("username", "unknown")
        st.session_state.authenticated = False
        st.session_state.user_info = None
        st.session_state.login_time = None

        # 清除前端缓存
        clear_cache_js = """
        <script>
        console.log('🚪 清除认证数据');
        try {
            localStorage.removeItem('tradingagents_auth');
            localStorage.removeItem('tradingagents_last_activity');
            console.log('✅ 认证数据已清除');
        } catch (e) {
            console.error('❌ 清除认证数据失败:', e);
        }
        </script>
        """
        st.components.v1.html(clear_cache_js, height=0)

        logger.info(f"✅ 用户 {username} 登出，已清除前端缓存")

        # 记录登出活动
        if user_activity_logger:
            user_activity_logger.log_logout(username)

    def restore_from_cache(self, user_info: dict, login_time: float | None = None) -> bool:
        """
        从前端缓存恢复登录状态

        Args:
            user_info: 用户信息
            login_time: 原始登录时间，如果为None则使用当前时间

        Returns:
            恢复是否成功
        """
        try:
            # 验证用户信息的有效性
            username = user_info.get("username")
            if not username:
                logger.warning("⚠️ 恢复失败: 用户信息中没有用户名")
                return False

            # 检查用户是否仍然存在
            users = self._load_users()
            if username not in users:
                logger.warning(f"⚠️ 尝试恢复不存在的用户: {username}")
                return False

            # 恢复登录状态，使用原始登录时间或当前时间
            restore_time = login_time if login_time is not None else time.time()

            st.session_state.authenticated = True
            st.session_state.user_info = user_info
            st.session_state.login_time = restore_time

            logger.info(f"✅ 从前端缓存恢复用户 {username} 的登录状态")
            logger.debug(f"🔍 [恢复状态] login_time: {restore_time}, current_time: {time.time()}")
            return True

        except Exception as e:
            logger.error(f"❌ 从前端缓存恢复登录状态失败: {e}")
            return False

    def get_current_user(self) -> dict | None:
        """获取当前用户信息"""
        if self.is_authenticated():
            return st.session_state.get("user_info")
        return None

    def require_permission(self, permission: str) -> bool:
        """
        要求特定权限，如果没有权限则显示错误信息

        Args:
            permission: 权限名称

        Returns:
            是否有权限
        """
        if not self.check_permission(permission):
            st.error(f"❌ 您没有 '{permission}' 权限，请联系管理员")
            return False
        return True


# 全局认证管理器实例
auth_manager = AuthManager()
