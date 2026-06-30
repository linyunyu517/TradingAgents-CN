#!/usr/bin/env python3
"""
测试执行诊断脚本
逐步检查测试脚本闪退的原因
"""

import contextlib
import os
import sys
import traceback


def step1_basic_check():
    """步骤1: 基本环境检查"""
    print("🔍 步骤1: 基本环境检查")
    print("-" * 40)

    try:
        print(f"✅ Python版本: {sys.version}")
        print(f"✅ Python路径: {sys.executable}")
        print(f"✅ 工作目录: {os.getcwd()}")
        print(f"✅ 虚拟环境: {os.environ.get('VIRTUAL_ENV', '未激活')}")
        return True
    except Exception as e:
        print(f"❌ 基本检查失败: {e}")
        return False


def step2_path_check():
    """步骤2: 路径检查"""
    print("\n🔍 步骤2: 路径检查")
    print("-" * 40)

    try:
        # 检查项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        print(f"✅ 项目根目录: {project_root}")

        # 检查关键目录
        key_dirs = ["tradingagents", "tests", "cli"]
        for dir_name in key_dirs:
            dir_path = os.path.join(project_root, dir_name)
            if os.path.exists(dir_path):
                print(f"✅ {dir_name}目录: 存在")
            else:
                print(f"❌ {dir_name}目录: 不存在")

        # 添加到Python路径
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
            print("✅ 已添加项目根目录到Python路径")

        return True
    except Exception as e:
        print(f"❌ 路径检查失败: {e}")
        traceback.print_exc()
        return False


def step3_import_check():
    """步骤3: 导入检查"""
    print("\n🔍 步骤3: 导入检查")
    print("-" * 40)

    imports = [
        ("langchain_core.messages", "HumanMessage"),
        ("langchain_core.tools", "tool"),
        ("tradingagents.llm_adapters", "ChatDashScopeOpenAI"),
        ("tradingagents.config.config_manager", "token_tracker"),
    ]

    success_count = 0
    for module, item in imports:
        try:
            exec(f"from {module} import {item}")
            print(f"✅ {module}.{item}: 导入成功")
            success_count += 1
        except ImportError as e:
            print(f"❌ {module}.{item}: 导入失败 - {e}")
        except Exception as e:
            print(f"⚠️ {module}.{item}: 导入异常 - {e}")

    print(f"\n📊 导入结果: {success_count}/{len(imports)} 成功")
    return success_count == len(imports)


def step4_env_check():
    """步骤4: 环境变量检查"""
    print("\n🔍 步骤4: 环境变量检查")
    print("-" * 40)

    try:
        # 检查关键环境变量
        env_vars = ["DASHSCOPE_API_KEY", "TUSHARE_TOKEN", "OPENAI_API_KEY"]

        for var in env_vars:
            value = os.getenv(var)
            if value:
                print(f"✅ {var}: 已设置 ({value[:10]}...)")
            else:
                print(f"⚠️ {var}: 未设置")

        return True
    except Exception as e:
        print(f"❌ 环境变量检查失败: {e}")
        return False


def step5_simple_llm_test():
    """步骤5: 简单LLM测试"""
    print("\n🔍 步骤5: 简单LLM测试")
    print("-" * 40)

    try:
        # 检查API密钥
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            print("⚠️ DASHSCOPE_API_KEY未设置，跳过LLM测试")
            return True

        print("🔄 导入LLM适配器...")
        from tradingagents.llm_adapters import ChatDashScopeOpenAI

        print("✅ LLM适配器导入成功")

        print("🔄 创建LLM实例...")
        ChatDashScopeOpenAI(model="qwen-turbo", temperature=0.1, max_tokens=50)
        print("✅ LLM实例创建成功")

        return True

    except Exception as e:
        print(f"❌ 简单LLM测试失败: {e}")
        traceback.print_exc()
        return False


def step6_tool_binding_test():
    """步骤6: 工具绑定测试"""
    print("\n🔍 步骤6: 工具绑定测试")
    print("-" * 40)

    try:
        # 检查API密钥
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            print("⚠️ DASHSCOPE_API_KEY未设置，跳过工具绑定测试")
            return True

        from langchain_core.tools import tool

        from tradingagents.llm_adapters import ChatDashScopeOpenAI

        print("🔄 定义测试工具...")

        @tool
        def test_tool(text: str) -> str:
            """测试工具"""
            return f"工具返回: {text}"

        print("🔄 创建LLM并绑定工具...")
        llm = ChatDashScopeOpenAI(model="qwen-turbo", max_tokens=50)
        llm.bind_tools([test_tool])
        print("✅ 工具绑定成功")

        return True

    except Exception as e:
        print(f"❌ 工具绑定测试失败: {e}")
        traceback.print_exc()
        return False


def step7_actual_call_test():
    """步骤7: 实际调用测试"""
    print("\n🔍 步骤7: 实际调用测试")
    print("-" * 40)

    try:
        # 检查API密钥
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            print("⚠️ DASHSCOPE_API_KEY未设置，跳过实际调用测试")
            return True

        from langchain_core.messages import HumanMessage
        from langchain_core.tools import tool

        from tradingagents.llm_adapters import ChatDashScopeOpenAI

        @tool
        def test_tool(text: str) -> str:
            """测试工具"""
            return f"工具返回: {text}"

        print("🔄 创建LLM并绑定工具...")
        llm = ChatDashScopeOpenAI(model="qwen-turbo", max_tokens=100)
        llm_with_tools = llm.bind_tools([test_tool])

        print("🔄 发送测试请求...")
        response = llm_with_tools.invoke([HumanMessage(content="请回复：测试成功")])

        print("✅ 调用成功")
        print(f"   响应类型: {type(response)}")
        print(f"   响应长度: {len(response.content)}字符")
        print(f"   响应内容: {response.content[:100]}...")

        # 检查工具调用
        tool_calls = getattr(response, "tool_calls", [])
        print(f"   工具调用数量: {len(tool_calls)}")

        return True

    except Exception as e:
        print(f"❌ 实际调用测试失败: {e}")
        traceback.print_exc()
        return False


def main():
    """主诊断函数"""
    print("🔬 测试执行诊断")
    print("=" * 60)
    print("💡 目标: 找出测试脚本闪退的原因")
    print("=" * 60)

    # 运行所有诊断步骤
    steps = [
        ("基本环境检查", step1_basic_check),
        ("路径检查", step2_path_check),
        ("导入检查", step3_import_check),
        ("环境变量检查", step4_env_check),
        ("简单LLM测试", step5_simple_llm_test),
        ("工具绑定测试", step6_tool_binding_test),
        ("实际调用测试", step7_actual_call_test),
    ]

    results = []
    for step_name, step_func in steps:
        print(f"\n{'=' * 60}")
        try:
            result = step_func()
            results.append((step_name, result))

            if not result:
                print(f"\n❌ {step_name}失败，停止后续测试")
                break

        except Exception as e:
            print(f"\n❌ {step_name}异常: {e}")
            traceback.print_exc()
            results.append((step_name, False))
            break

    # 总结
    print(f"\n{'=' * 60}")
    print("📋 诊断总结")
    print("=" * 60)

    passed = 0
    for step_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{step_name}: {status}")
        if result:
            passed += 1

    total = len(results)
    print(f"\n📊 诊断结果: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有诊断通过！")
        print("测试脚本应该可以正常运行")
    else:
        print(f"\n⚠️ 在第{passed + 1}步失败")
        print("请根据错误信息修复问题")

    # 防止脚本闪退
    print("\n" + "=" * 60)
    print("诊断完成！按回车键退出...")
    with contextlib.suppress(BaseException):
        input()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n💥 主函数异常: {e}")
        traceback.print_exc()
        print("\n按回车键退出...")
        with contextlib.suppress(BaseException):
            input()
