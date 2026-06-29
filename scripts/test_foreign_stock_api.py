#!/usr/bin/env python3
"""
测试港股和美股API接口
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.foreign_stock_service import ForeignStockService


async def test_hk_quote():
    """测试港股实时行情"""
    print("\n" + "=" * 60)
    print("测试港股实时行情")
    print("=" * 60)

    service = ForeignStockService()

    # 测试腾讯控股
    test_codes = ["0700", "00700", "0700.HK"]

    for code in test_codes:
        print(f"\n📊 测试代码: {code}")
        try:
            quote = await service.get_quote("HK", code)
            print("✅ 成功获取行情:")
            print(f"   代码: {quote.get('code')}")
            print(f"   名称: {quote.get('name')}")
            print(f"   价格: {quote.get('price')} {quote.get('currency')}")
            print(f"   涨跌幅: {quote.get('change_percent')}%")
            print(f"   数据源: {quote.get('source')}")
            print(f"   更新时间: {quote.get('updated_at')}")
        except Exception as e:
            print(f"❌ 获取失败: {e}")


async def test_us_quote():
    """测试美股实时行情"""
    print("\n" + "=" * 60)
    print("测试美股实时行情")
    print("=" * 60)

    service = ForeignStockService()

    # 测试苹果和特斯拉
    test_codes = ["AAPL", "TSLA"]

    for code in test_codes:
        print(f"\n📊 测试代码: {code}")
        try:
            quote = await service.get_quote("US", code)
            print("✅ 成功获取行情:")
            print(f"   代码: {quote.get('code')}")
            print(f"   名称: {quote.get('name')}")
            print(f"   价格: {quote.get('price')} {quote.get('currency')}")
            print(f"   涨跌幅: {quote.get('change_percent')}%")
            print(f"   数据源: {quote.get('source')}")
            print(f"   更新时间: {quote.get('updated_at')}")
        except Exception as e:
            print(f"❌ 获取失败: {e}")


async def test_cache():
    """测试缓存功能"""
    print("\n" + "=" * 60)
    print("测试缓存功能")
    print("=" * 60)

    service = ForeignStockService()

    code = "AAPL"

    # 第一次获取（从API）
    print(f"\n📊 第一次获取 {code}（应该从API获取）")
    import time

    start = time.time()
    try:
        quote1 = await service.get_quote("US", code, force_refresh=True)
        elapsed1 = time.time() - start
        print(f"✅ 成功，耗时: {elapsed1:.2f}秒")
        print(f"   数据源: {quote1.get('source')}")
    except Exception as e:
        print(f"❌ 失败: {e}")
        return

    # 第二次获取（从缓存）
    print(f"\n📊 第二次获取 {code}（应该从缓存获取）")
    start = time.time()
    try:
        quote2 = await service.get_quote("US", code, force_refresh=False)
        elapsed2 = time.time() - start
        print(f"✅ 成功，耗时: {elapsed2:.2f}秒")
        print(f"   数据源: {quote2.get('source')}")

        if elapsed2 < elapsed1 * 0.5:
            print(f"✅ 缓存生效！速度提升 {elapsed1 / elapsed2:.1f}x")
        else:
            print("⚠️ 缓存可能未生效")
    except Exception as e:
        print(f"❌ 失败: {e}")


async def test_market_detection():
    """测试市场类型检测"""
    print("\n" + "=" * 60)
    print("测试市场类型检测")
    print("=" * 60)

    from app.routers.stocks import _detect_market_and_code

    test_cases = [
        ("000001", "CN", "000001"),
        ("600519", "CN", "600519"),
        ("0700", "HK", "00700"),
        ("00700", "HK", "00700"),
        ("0700.HK", "HK", "00700"),
        ("AAPL", "US", "AAPL"),
        ("TSLA", "US", "TSLA"),
    ]

    for code, expected_market, expected_code in test_cases:
        market, normalized_code = _detect_market_and_code(code)
        status = "✅" if market == expected_market and normalized_code == expected_code else "❌"
        print(
            f"{status} {code:10s} → 市场: {market:2s}, 代码: {normalized_code:6s} (期望: {expected_market:2s}, {expected_code:6s})",
        )


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("港股和美股API接口测试")
    print("=" * 60)

    # 测试市场类型检测
    await test_market_detection()

    # 测试港股行情
    await test_hk_quote()

    # 测试美股行情
    await test_us_quote()

    # 测试缓存
    await test_cache()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
