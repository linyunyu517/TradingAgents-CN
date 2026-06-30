#!/usr/bin/env python3
"""
验证通知功能移除
检查前端代码中是否还有通知相关的代码
"""

import os
import re


def check_notification_code():
    """检查前端代码中的通知相关代码"""
    print("=" * 60)
    print("🔍 检查通知功能移除情况")
    print("=" * 60)

    frontend_dir = "frontend/src"
    notification_patterns = [
        r"showDesktopNotification",
        r"testNotification",
        r"测试通知",
        r"Notification\.permission",
        r"new Notification",
        r"requestPermission",
        r"🧪 测试通知",
    ]

    found_issues = []

    # 遍历前端文件
    for root, _dirs, files in os.walk(frontend_dir):
        for file in files:
            if file.endswith((".vue", ".ts", ".js")):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, encoding="utf-8") as f:
                        content = f.read()

                    # 检查每个模式
                    for pattern in notification_patterns:
                        matches = re.finditer(pattern, content, re.IGNORECASE)
                        for match in matches:
                            # 计算行号
                            line_num = content[: match.start()].count("\n") + 1
                            line_content = content.split("\n")[line_num - 1].strip()

                            found_issues.append(
                                {"file": file_path, "line": line_num, "pattern": pattern, "content": line_content},
                            )

                except Exception as e:
                    print(f"⚠️ 无法读取文件 {file_path}: {e}")

    # 报告结果
    if found_issues:
        print(f"❌ 发现 {len(found_issues)} 个通知相关代码残留:")
        print()

        for issue in found_issues:
            print(f"📁 文件: {issue['file']}")
            print(f"📍 行号: {issue['line']}")
            print(f"🔍 模式: {issue['pattern']}")
            print(f"📝 内容: {issue['content']}")
            print("-" * 40)

        return False
    print("✅ 未发现通知相关代码残留")
    return True


def check_sync_control_component():
    """专门检查 SyncControl 组件"""
    print("\n" + "=" * 60)
    print("🔍 检查 SyncControl 组件")
    print("=" * 60)

    sync_control_path = "frontend/src/components/Sync/SyncControl.vue"

    if not os.path.exists(sync_control_path):
        print(f"❌ 文件不存在: {sync_control_path}")
        return False

    try:
        with open(sync_control_path, encoding="utf-8") as f:
            content = f.read()

        # 检查应该移除的功能
        removed_features = [
            "🧪 测试通知",
            "testNotification",
            "showDesktopNotification",
            "Notification.permission",
            "new Notification",
        ]

        # 检查应该保留的功能
        kept_features = [
            "showSyncCompletionNotification",
            "ElMessage",
            "emit('syncCompleted'",
        ]

        print("📋 检查移除的功能:")
        all_removed = True
        for feature in removed_features:
            if feature in content:
                print(f"   ❌ 仍然存在: {feature}")
                all_removed = False
            else:
                print(f"   ✅ 已移除: {feature}")

        print("\n📋 检查保留的功能:")
        all_kept = True
        for feature in kept_features:
            if feature in content:
                print(f"   ✅ 已保留: {feature}")
            else:
                print(f"   ❌ 意外移除: {feature}")
                all_kept = False

        # 检查按钮数量
        button_count = content.count("<el-button")
        print(f"\n📊 按钮数量: {button_count}")

        # 应该有4个按钮：开始同步、刷新状态、清空缓存、强制重新同步
        expected_buttons = 4
        if button_count == expected_buttons:
            print(f"   ✅ 按钮数量正确 (期望: {expected_buttons})")
        else:
            print(f"   ⚠️ 按钮数量可能不正确 (期望: {expected_buttons}, 实际: {button_count})")

        return all_removed and all_kept

    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return False


def generate_test_instructions():
    """生成测试说明"""
    print("\n" + "=" * 60)
    print("📝 前端测试说明")
    print("=" * 60)

    print("现在你可以在前端验证以下功能:")
    print()
    print("✅ **应该正常工作的功能:**")
    print("   1. 🚀 开始同步按钮")
    print("   2. 🔄 刷新状态按钮")
    print("   3. 🗑️ 清空缓存按钮")
    print("   4. 💪 强制重新同步按钮")
    print("   5. 📊 同步状态显示")
    print("   6. 📈 同步统计信息")
    print("   7. 💬 页面消息提示 (ElMessage)")
    print("   8. 📚 同步历史记录")
    print()
    print("❌ **应该已经移除的功能:**")
    print("   1. 🧪 测试通知按钮")
    print("   2. 🔔 桌面通知")
    print("   3. 📱 通知权限请求")
    print()
    print("🧪 **测试步骤:**")
    print("   1. 打开多数据源同步页面")
    print("   2. 确认只有4个操作按钮")
    print("   3. 点击'强制重新同步'")
    print("   4. 观察是否只显示页面消息，没有桌面通知")
    print("   5. 检查同步历史是否正常更新")
    print()
    print("如果以上测试都通过，说明通知功能移除成功！")


if __name__ == "__main__":
    print("🧹 通知功能移除验证")

    # 检查代码残留
    code_clean = check_notification_code()

    # 检查组件
    component_clean = check_sync_control_component()

    # 生成测试说明
    generate_test_instructions()

    # 总结
    print("\n" + "=" * 60)
    print("📊 验证结果")
    print("=" * 60)

    if code_clean and component_clean:
        print("🎉 通知功能移除成功！")
        print("   ✅ 代码清理完成")
        print("   ✅ 组件功能正确")
        print("   📝 请按照上述说明进行前端测试")
    else:
        print("⚠️ 发现问题，需要进一步检查:")
        if not code_clean:
            print("   ❌ 代码中仍有通知相关残留")
        if not component_clean:
            print("   ❌ 组件功能不正确")
