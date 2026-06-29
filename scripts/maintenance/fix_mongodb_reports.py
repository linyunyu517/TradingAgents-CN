#!/usr/bin/env python3
"""
修复MongoDB中不一致的分析报告数据结构

这个脚本用于修复MongoDB中保存的分析报告数据结构不一致的问题。
主要解决以下问题：
1. 缺少reports字段的文档
2. reports字段为空或None的文档
3. 字段结构不标准的文档

使用方法：
python scripts/maintenance/fix_mongodb_reports.py
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    """主函数"""
    print("🔧 MongoDB分析报告数据修复工具")
    print("=" * 50)

    try:
        # 导入MongoDB管理器
        from web.utils.mongodb_report_manager import MongoDBReportManager

        # 创建MongoDB管理器实例
        mongodb_manager = MongoDBReportManager()

        if not mongodb_manager.connected:
            print("❌ MongoDB未连接，无法执行修复")
            return False

        print("✅ MongoDB连接成功")

        # 1. 检查当前数据状态
        print("\n📊 检查当前数据状态...")
        all_reports = mongodb_manager.get_all_reports(limit=1000)
        print(f"📈 总报告数量: {len(all_reports)}")

        # 统计不一致的报告
        inconsistent_count = 0
        missing_reports_count = 0
        empty_reports_count = 0

        for report in all_reports:
            if "reports" not in report:
                inconsistent_count += 1
                missing_reports_count += 1
            elif not report.get("reports") or report.get("reports") == {}:
                inconsistent_count += 1
                empty_reports_count += 1

        print(f"⚠️ 不一致报告数量: {inconsistent_count}")
        print(f"   - 缺少reports字段: {missing_reports_count}")
        print(f"   - reports字段为空: {empty_reports_count}")

        if inconsistent_count == 0:
            print("✅ 所有报告数据结构一致，无需修复")
            return True

        # 2. 询问用户是否继续修复
        print(f"\n🔧 准备修复 {inconsistent_count} 个不一致的报告")
        response = input("是否继续修复？(y/N): ").strip().lower()

        if response not in ["y", "yes"]:
            print("❌ 用户取消修复操作")
            return False

        # 3. 执行修复
        print("\n🔧 开始修复不一致的报告...")
        success = mongodb_manager.fix_inconsistent_reports()

        if success:
            print("✅ 修复完成")

            # 4. 验证修复结果
            print("\n📊 验证修复结果...")
            updated_reports = mongodb_manager.get_all_reports(limit=1000)

            # 重新统计
            final_inconsistent_count = 0
            for report in updated_reports:
                if "reports" not in report or not isinstance(report.get("reports"), dict):
                    final_inconsistent_count += 1

            print(f"📈 修复后不一致报告数量: {final_inconsistent_count}")

            if final_inconsistent_count == 0:
                print("🎉 所有报告数据结构已修复完成！")
                return True
            print(f"⚠️ 仍有 {final_inconsistent_count} 个报告需要手动处理")
            return False
        print("❌ 修复失败")
        return False

    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print("请确保MongoDB相关依赖已安装")
        return False
    except Exception as e:
        print(f"❌ 修复过程出错: {e}")
        logger.error(f"修复异常: {e}")
        return False


def show_report_details():
    """显示报告详细信息（调试用）"""
    try:
        from web.utils.mongodb_report_manager import MongoDBReportManager

        mongodb_manager = MongoDBReportManager()
        if not mongodb_manager.connected:
            print("❌ MongoDB未连接")
            return

        reports = mongodb_manager.get_all_reports(limit=10)

        print("\n📋 最近10个报告的详细信息:")
        print("=" * 80)

        for i, report in enumerate(reports, 1):
            print(f"\n{i}. 报告ID: {report.get('analysis_id', 'N/A')}")
            print(f"   股票代码: {report.get('stock_symbol', 'N/A')}")
            print(f"   时间戳: {report.get('timestamp', 'N/A')}")
            print(f"   分析师: {report.get('analysts', [])}")
            print(f"   研究深度: {report.get('research_depth', 'N/A')}")
            print(f"   状态: {report.get('status', 'N/A')}")
            print(f"   来源: {report.get('source', 'N/A')}")

            # 检查reports字段
            reports_field = report.get("reports")
            if reports_field is None:
                print("   Reports字段: ❌ 缺失")
            elif isinstance(reports_field, dict):
                if reports_field:
                    print(f"   Reports字段: ✅ 存在 ({len(reports_field)} 个报告)")
                    for report_type in reports_field:
                        print(f"     - {report_type}")
                else:
                    print("   Reports字段: ⚠️ 空字典")
            else:
                print(f"   Reports字段: ❌ 类型错误 ({type(reports_field)})")

            print("-" * 60)

    except Exception as e:
        print(f"❌ 显示报告详情失败: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="修复MongoDB分析报告数据结构")
    parser.add_argument("--details", action="store_true", help="显示报告详细信息")
    parser.add_argument("--fix", action="store_true", help="执行修复操作")

    args = parser.parse_args()

    if args.details:
        show_report_details()
    elif args.fix:
        success = main()
        sys.exit(0 if success else 1)
    else:
        # 默认执行修复
        success = main()
        sys.exit(0 if success else 1)
