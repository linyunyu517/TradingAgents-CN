"""
测试 preferred_sources 参数是否生效
"""

import asyncio

from app.core.database import init_db
from app.services.data_sources.manager import DataSourceManager


async def test_default_order():
    """测试默认优先级顺序"""
    print("=" * 80)
    print("测试1: 默认优先级顺序")
    print("=" * 80)

    manager = DataSourceManager()
    available_adapters = manager.get_available_adapters()

    print(f"\n可用的数据源: {len(available_adapters)} 个")
    for adapter in available_adapters:
        print(f"  - {adapter.name} (优先级: {adapter.priority})")

    print("\n尝试获取股票列表（默认顺序）...")
    df, source = manager.get_stock_list_with_fallback()

    if df is not None and not df.empty:
        print(f"✅ 成功从 {source} 获取 {len(df)} 只股票")
    else:
        print("❌ 获取失败")

    print()


async def test_preferred_sources_akshare():
    """测试指定 akshare 为优先数据源"""
    print("=" * 80)
    print("测试2: 指定 akshare 为优先数据源")
    print("=" * 80)

    manager = DataSourceManager()
    preferred = ["akshare"]

    print(f"\n指定优先数据源: {preferred}")
    print("\n尝试获取股票列表...")
    df, source = manager.get_stock_list_with_fallback(preferred_sources=preferred)

    if df is not None and not df.empty:
        print(f"✅ 成功从 {source} 获取 {len(df)} 只股票")
        if source == "akshare":
            print("✅ 验证通过：使用了指定的优先数据源")
        else:
            print(f"⚠️  警告：期望使用 akshare，但实际使用了 {source}")
    else:
        print("❌ 获取失败")

    print()


async def test_preferred_sources_baostock():
    """测试指定 baostock 为优先数据源"""
    print("=" * 80)
    print("测试3: 指定 baostock 为优先数据源")
    print("=" * 80)

    manager = DataSourceManager()
    preferred = ["baostock"]

    print(f"\n指定优先数据源: {preferred}")
    print("\n尝试获取股票列表...")
    df, source = manager.get_stock_list_with_fallback(preferred_sources=preferred)

    if df is not None and not df.empty:
        print(f"✅ 成功从 {source} 获取 {len(df)} 只股票")
        if source == "baostock":
            print("✅ 验证通过：使用了指定的优先数据源")
        else:
            print(f"⚠️  警告：期望使用 baostock，但实际使用了 {source}")
    else:
        print("❌ 获取失败")

    print()


async def test_preferred_sources_multiple():
    """测试指定多个优先数据源"""
    print("=" * 80)
    print("测试4: 指定多个优先数据源 (baostock, akshare)")
    print("=" * 80)

    manager = DataSourceManager()
    preferred = ["baostock", "akshare"]

    print(f"\n指定优先数据源: {preferred}")
    print("期望顺序: baostock → akshare → tushare")
    print("\n尝试获取股票列表...")
    df, source = manager.get_stock_list_with_fallback(preferred_sources=preferred)

    if df is not None and not df.empty:
        print(f"✅ 成功从 {source} 获取 {len(df)} 只股票")
        if source in preferred:
            print(f"✅ 验证通过：使用了指定的优先数据源之一 ({source})")
        else:
            print(f"⚠️  警告：期望使用 {preferred}，但实际使用了 {source}")
    else:
        print("❌ 获取失败")

    print()


async def test_preferred_sources_invalid():
    """测试指定不存在的数据源"""
    print("=" * 80)
    print("测试5: 指定不存在的数据源 (invalid_source)")
    print("=" * 80)

    manager = DataSourceManager()
    preferred = ["invalid_source", "akshare"]

    print(f"\n指定优先数据源: {preferred}")
    print("期望行为: 忽略不存在的数据源，使用 akshare")
    print("\n尝试获取股票列表...")
    df, source = manager.get_stock_list_with_fallback(preferred_sources=preferred)

    if df is not None and not df.empty:
        print(f"✅ 成功从 {source} 获取 {len(df)} 只股票")
        if source == "akshare":
            print("✅ 验证通过：正确忽略了不存在的数据源")
        else:
            print(f"⚠️  警告：期望使用 akshare，但实际使用了 {source}")
    else:
        print("❌ 获取失败")

    print()


async def test_api_integration():
    """测试完整的API集成"""
    print("=" * 80)
    print("测试6: API集成测试")
    print("=" * 80)

    from app.services.multi_source_basics_sync_service import get_multi_source_sync_service

    service = get_multi_source_sync_service()

    print("\n测试场景: 使用 preferred_sources=['akshare', 'baostock']")
    print("注意: 这是一个完整的同步测试，可能需要较长时间...")

    user_input = input("\n是否继续？(y/N): ").strip().lower()
    if user_input not in ["y", "yes"]:
        print("⏭️  跳过API集成测试")
        return

    print("\n开始同步...")
    try:
        result = await service.run_full_sync(force=False, preferred_sources=["akshare", "baostock"])

        print("\n同步结果:")
        print(f"  状态: {result.get('status')}")
        print(f"  总数: {result.get('total', 0)}")
        print(f"  插入: {result.get('inserted', 0)}")
        print(f"  更新: {result.get('updated', 0)}")
        print(f"  错误: {result.get('errors', 0)}")

        if result.get("data_sources_used"):
            print(f"  使用的数据源: {result['data_sources_used']}")

            # 验证是否使用了指定的优先数据源
            sources_str = str(result["data_sources_used"])
            if "akshare" in sources_str or "baostock" in sources_str:
                print("✅ 验证通过：使用了指定的优先数据源")
            else:
                print("⚠️  警告：没有使用指定的优先数据源")

    except Exception as e:
        print(f"❌ 同步失败: {e}")
        import traceback

        traceback.print_exc()

    print()


async def main():
    """主测试函数"""
    print("\n" + "🔬" * 40)
    print("preferred_sources 参数测试")
    print("🔬" * 40)
    print()

    # 初始化数据库
    try:
        await init_db()
        print("✅ 数据库初始化成功\n")
    except Exception as e:
        print(f"❌ 数据库初始化失败: {e}\n")
        return

    # 运行测试
    await test_default_order()
    await test_preferred_sources_akshare()
    await test_preferred_sources_baostock()
    await test_preferred_sources_multiple()
    await test_preferred_sources_invalid()
    await test_api_integration()

    print("=" * 80)
    print("✅ 所有测试完成")
    print("=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试出错: {e}")
        import traceback

        traceback.print_exc()
