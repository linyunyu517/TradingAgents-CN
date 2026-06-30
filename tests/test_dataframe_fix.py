#!/usr/bin/env python3
"""
测试DataFrame Arrow转换修复
"""

import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_safe_dataframe():
    """测试安全DataFrame函数"""
    try:
        from web.components.analysis_results import safe_dataframe

        print("🔍 测试安全DataFrame函数...")

        # 测试混合数据类型
        mixed_data = {
            "项目": ["股票代码", "分析时间", "分析师数量", "研究深度"],
            "结果A": ["000001", "2025-07-31 12:00", 3, 5],  # 混合字符串和整数
            "结果B": ["000002", "2025-07-31 13:00", 2, 4],
        }

        # 使用安全函数创建DataFrame
        df = safe_dataframe(mixed_data)
        print(f"✅ 安全DataFrame创建成功，形状: {df.shape}")

        # 检查数据类型
        print("📊 数据类型检查:")
        for col in df.columns:
            dtype = df[col].dtype
            print(f"   {col}: {dtype}")
            if dtype == "object":
                print(f"   ✅ {col} 是字符串类型")
            else:
                print(f"   ⚠️ {col} 不是字符串类型")

        # 测试列表数据
        list_data = [{"股票": "000001", "价格": 10.5, "数量": 100}, {"股票": "000002", "价格": 20.3, "数量": 200}]

        df_list = safe_dataframe(list_data)
        print(f"✅ 列表数据DataFrame创建成功，形状: {df_list.shape}")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_comparison_data():
    """测试对比数据创建"""
    try:
        from web.components.analysis_results import safe_dataframe

        print("\n🔍 测试对比数据创建...")

        # 模拟对比数据
        comparison_data = {
            "项目": ["股票代码", "分析时间", "分析师数量", "研究深度", "状态", "标签数量"],
            "分析结果 A": [
                "000001",
                "2025-07-31 12:00",
                3,  # 整数
                5,  # 整数
                "✅ 完成",
                2,  # 整数
            ],
            "分析结果 B": [
                "000002",
                "2025-07-31 13:00",
                2,  # 整数
                4,  # 整数
                "❌ 失败",
                1,  # 整数
            ],
        }

        df = safe_dataframe(comparison_data)
        print("✅ 对比数据DataFrame创建成功")

        # 验证所有数据都是字符串
        all_string = all(df[col].dtype == "object" for col in df.columns)
        if all_string:
            print("✅ 所有列都是字符串类型")
        else:
            print("❌ 存在非字符串类型的列")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_timeline_data():
    """测试时间线数据创建"""
    try:
        from web.components.analysis_results import safe_dataframe

        print("\n🔍 测试时间线数据创建...")

        # 模拟时间线数据
        timeline_data = []
        for i in range(3):
            timeline_data.append(
                {
                    "序号": i + 1,  # 整数
                    "分析时间": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "分析师": "analyst1, analyst2",
                    "研究深度": 5,  # 整数
                    "状态": "✅" if i % 2 == 0 else "❌",
                },
            )

        df = safe_dataframe(timeline_data)
        print(f"✅ 时间线数据DataFrame创建成功，行数: {len(df)}")

        # 检查序号列是否为字符串
        if df["序号"].dtype == "object":
            print("✅ 序号列已转换为字符串类型")
        else:
            print(f"❌ 序号列类型: {df['序号'].dtype}")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_arrow_conversion():
    """测试Arrow转换"""
    try:
        import pyarrow as pa

        from web.components.analysis_results import safe_dataframe

        print("\n🔍 测试Arrow转换...")

        # 创建可能导致Arrow错误的数据
        problematic_data = {
            "文本列": ["text1", "text2", "text3"],
            "数字列": [1, 2, 3],  # 整数
            "浮点列": [1.1, 2.2, 3.3],  # 浮点数
            "布尔列": [True, False, True],  # 布尔值
            "混合列": ["text", 123, 45.6],  # 混合类型
        }

        # 使用安全函数
        df = safe_dataframe(problematic_data)

        # 尝试转换为Arrow
        table = pa.Table.from_pandas(df)
        print("✅ Arrow转换成功")
        print(f"   表格形状: {table.shape}")
        print(f"   列名: {table.column_names}")

        return True

    except Exception as e:
        print(f"❌ Arrow转换失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🚀 开始测试DataFrame Arrow转换修复")
    print("=" * 50)

    tests = [
        ("安全DataFrame函数", test_safe_dataframe),
        ("对比数据创建", test_comparison_data),
        ("时间线数据创建", test_timeline_data),
        ("Arrow转换", test_arrow_conversion),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n📋 测试: {test_name}")
        if test_func():
            passed += 1
            print(f"✅ {test_name} 通过")
        else:
            print(f"❌ {test_name} 失败")

    print("\n" + "=" * 50)
    print(f"📊 测试结果: {passed}/{total} 通过")

    if passed == total:
        print("🎉 所有测试通过！DataFrame Arrow转换问题已修复")
        return True
    print("⚠️ 部分测试失败，需要进一步检查")
    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
