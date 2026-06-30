#!/usr/bin/env python3
"""
测试Pydantic v2修复
"""

try:
    from bson import ObjectId
    from webapi.models.user import User

    print("✅ 导入成功")

    # 测试PyObjectId
    test_id = ObjectId()
    print(f"✅ ObjectId创建成功: {test_id}")

    # 测试User模型
    user_data = {
        "username": "test_user",
        "email": "test@example.com",
        "is_active": True,
        "is_verified": False,
        "is_admin": False,
    }

    user = User(**user_data)
    print(f"✅ User模型创建成功: {user.username}")

    print("🎉 Pydantic v2修复验证成功！")

except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback

    traceback.print_exc()
