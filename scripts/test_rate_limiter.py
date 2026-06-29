"""
测试速率限制器
验证Tushare速率限制器是否正常工作
"""

import asyncio
import time

from app.core.rate_limiter import TushareRateLimiter, get_tushare_rate_limiter


async def test_basic_rate_limiter():
    """测试基本速率限制功能"""

    print("=" * 80)
    print("测试1: 基本速率限制功能")
    print("=" * 80)

    # 创建一个限制为10次/秒的限制器
    limiter = TushareRateLimiter(tier="free", safety_margin=1.0)  # 100次/分钟

    print(f"\n配置: {limiter.max_calls}次/{limiter.time_window}秒")
    print("开始测试...")

    start_time = time.time()

    # 快速调用150次
    for i in range(150):
        await limiter.acquire()
        if (i + 1) % 10 == 0:
            elapsed = time.time() - start_time
            stats = limiter.get_stats()
            print(
                f"  已调用 {i + 1}次, 耗时 {elapsed:.2f}秒, "
                f"等待次数: {stats['total_waits']}, "
                f"总等待时间: {stats['total_wait_time']:.2f}秒",
            )

    total_time = time.time() - start_time
    stats = limiter.get_stats()

    print("\n✅ 测试完成:")
    print(f"  总调用次数: {stats['total_calls']}")
    print(f"  总耗时: {total_time:.2f}秒")
    print(f"  等待次数: {stats['total_waits']}")
    print(f"  总等待时间: {stats['total_wait_time']:.2f}秒")
    print(f"  平均等待时间: {stats['avg_wait_time']:.2f}秒")
    print(f"  实际速率: {stats['total_calls'] / total_time:.1f}次/秒")
    print(f"  理论速率: {limiter.max_calls / limiter.time_window:.1f}次/秒")


async def test_different_tiers():
    """测试不同积分等级的速率限制"""

    print("\n" + "=" * 80)
    print("测试2: 不同积分等级的速率限制")
    print("=" * 80)

    tiers = ["free", "basic", "standard", "premium", "vip"]
    test_calls = 50  # 每个等级测试50次调用

    for tier in tiers:
        print(f"\n📊 测试 {tier.upper()} 等级:")

        limiter = TushareRateLimiter(tier=tier, safety_margin=0.8)
        print(f"  配置: {limiter.max_calls}次/{limiter.time_window}秒 (安全边际: 80%)")

        start_time = time.time()

        for _i in range(test_calls):
            await limiter.acquire()

        total_time = time.time() - start_time
        stats = limiter.get_stats()

        print(f"  ✅ {test_calls}次调用耗时: {total_time:.2f}秒")
        print(f"  等待次数: {stats['total_waits']}")
        if total_time > 0:
            print(f"  实际速率: {test_calls / total_time:.1f}次/秒")
        else:
            print("  实际速率: 瞬间完成（无限制）")


async def test_concurrent_calls():
    """测试并发调用"""

    print("\n" + "=" * 80)
    print("测试3: 并发调用测试")
    print("=" * 80)

    limiter = TushareRateLimiter(tier="standard", safety_margin=0.8)
    print(f"\n配置: {limiter.max_calls}次/{limiter.time_window}秒")

    async def worker(worker_id: int, num_calls: int):
        """模拟工作线程"""
        for _i in range(num_calls):
            await limiter.acquire()
            # 模拟API调用
            await asyncio.sleep(0.01)
        print(f"  Worker {worker_id} 完成 {num_calls} 次调用")

    print("\n启动3个并发工作线程，每个调用30次...")
    start_time = time.time()

    # 启动3个并发工作线程
    await asyncio.gather(worker(1, 30), worker(2, 30), worker(3, 30))

    total_time = time.time() - start_time
    stats = limiter.get_stats()

    print("\n✅ 并发测试完成:")
    print(f"  总调用次数: {stats['total_calls']}")
    print(f"  总耗时: {total_time:.2f}秒")
    print(f"  等待次数: {stats['total_waits']}")
    print(f"  实际速率: {stats['total_calls'] / total_time:.1f}次/秒")


async def test_safety_margin():
    """测试安全边际的效果"""

    print("\n" + "=" * 80)
    print("测试4: 安全边际效果测试")
    print("=" * 80)

    safety_margins = [1.0, 0.8, 0.6]
    test_calls = 100

    for margin in safety_margins:
        print(f"\n📊 测试安全边际: {margin * 100:.0f}%")

        limiter = TushareRateLimiter(tier="standard", safety_margin=margin)
        print(f"  配置: {limiter.max_calls}次/{limiter.time_window}秒")

        start_time = time.time()

        for _i in range(test_calls):
            await limiter.acquire()

        total_time = time.time() - start_time
        stats = limiter.get_stats()

        print(f"  ✅ {test_calls}次调用耗时: {total_time:.2f}秒")
        print(f"  等待次数: {stats['total_waits']}")
        if total_time > 0:
            print(f"  实际速率: {test_calls / total_time:.1f}次/秒")
        else:
            print("  实际速率: 瞬间完成（无限制）")


async def test_global_limiter():
    """测试全局单例限制器"""

    print("\n" + "=" * 80)
    print("测试5: 全局单例限制器测试")
    print("=" * 80)

    # 获取两次全局限制器，应该是同一个实例
    limiter1 = get_tushare_rate_limiter(tier="standard", safety_margin=0.8)
    limiter2 = get_tushare_rate_limiter(tier="premium", safety_margin=0.9)  # 参数会被忽略

    print("\n检查单例模式:")
    print(f"  limiter1 == limiter2: {limiter1 is limiter2}")
    print(f"  limiter1配置: {limiter1.max_calls}次/{limiter1.time_window}秒")
    print(f"  limiter2配置: {limiter2.max_calls}次/{limiter2.time_window}秒")

    if limiter1 is limiter2:
        print("  ✅ 单例模式正常工作")
    else:
        print("  ❌ 单例模式失败")


async def main():
    """主函数"""

    print("\n🚀 Tushare速率限制器测试")
    print()

    # 测试1: 基本功能
    await test_basic_rate_limiter()

    # 测试2: 不同等级
    await test_different_tiers()

    # 测试3: 并发调用
    await test_concurrent_calls()

    # 测试4: 安全边际
    await test_safety_margin()

    # 测试5: 全局单例
    await test_global_limiter()

    print("\n" + "=" * 80)
    print("✅ 所有测试完成！")
    print("=" * 80)

    print("\n💡 使用建议:")
    print("  1. 根据您的Tushare积分等级设置 TUSHARE_TIER 环境变量")
    print("  2. 建议设置安全边际为 0.8，避免突发流量超限")
    print("  3. 在 .env 文件中配置:")
    print("     TUSHARE_TIER=standard")
    print("     TUSHARE_RATE_LIMIT_SAFETY_MARGIN=0.8")
    print()


if __name__ == "__main__":
    asyncio.run(main())
