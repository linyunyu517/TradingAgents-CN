#!/usr/bin/env python3
"""
Phase 6: 结构化代码审查脚本
对 efinance.py, base_provider.py, data_source_manager.py 进行代码审查
"""

import ast
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def check_docstrings(filepath: str, module_name: str) -> dict[str, Any]:
    """检查文件的 docstring 覆盖率"""

    with open(filepath, encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    total = len(classes) + len(functions)
    documented = 0

    results = []
    for cls in classes:
        has_doc = ast.get_docstring(cls) is not None
        if has_doc:
            documented += 1
        results.append(
            {
                "type": "class",
                "name": cls.name,
                "line": cls.lineno,
                "has_docstring": has_doc,
            },
        )

    for func in functions:
        has_doc = ast.get_docstring(func) is not None
        if has_doc:
            documented += 1
        results.append(
            {
                "type": "function",
                "name": func.name,
                "line": func.lineno,
                "has_docstring": has_doc,
            },
        )

    coverage = (documented / total * 100) if total > 0 else 0

    return {
        "module": module_name,
        "file": filepath,
        "total_definitions": total,
        "documented": documented,
        "undocumented": total - documented,
        "docstring_coverage": round(coverage, 1),
        "details": results,
    }


def check_type_annotations(filepath: str, module_name: str) -> dict[str, Any]:
    """检查类型注解覆盖率"""

    with open(filepath, encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    total = len(functions)
    annotated_return = 0
    annotated_args = 0
    total_args = 0

    details = []
    for func in functions:
        has_return_annotation = func.returns is not None
        if has_return_annotation:
            annotated_return += 1

        # Count annotated args
        func_total_args = len(func.args.args)
        func_annotated_args = sum(1 for a in func.args.args if a.annotation is not None)
        total_args += func_total_args
        annotated_args += func_annotated_args

        details.append(
            {
                "name": func.name,
                "line": func.lineno,
                "return_annotated": has_return_annotation,
                "args_total": func_total_args,
                "args_annotated": func_annotated_args,
            },
        )

    return_coverage = (annotated_return / total * 100) if total > 0 else 0
    args_coverage = (annotated_args / total_args * 100) if total_args > 0 else 0

    return {
        "module": module_name,
        "file": filepath,
        "total_functions": total,
        "return_annotated": annotated_return,
        "args_annotated": annotated_args,
        "total_args": total_args,
        "return_annotation_coverage": round(return_coverage, 1),
        "args_annotation_coverage": round(args_coverage, 1),
        "details": details,
    }


def check_exception_handling(filepath: str, module_name: str) -> dict[str, Any]:
    """检查异常处理"""

    with open(filepath, encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)

    # Find all try/except blocks
    try_blocks = [n for n in ast.walk(tree) if isinstance(n, ast.Try)]

    total_bare_excepts = 0
    total_general_excepts = 0
    total_specific_excepts = 0

    for try_block in try_blocks:
        for handler in try_block.handlers:
            if handler.type is None:
                total_bare_excepts += 1
            elif isinstance(handler.type, ast.Name) and handler.type.id == "Exception":
                total_general_excepts += 1
            else:
                total_specific_excepts += 1

    total = total_bare_excepts + total_general_excepts + total_specific_excepts

    return {
        "module": module_name,
        "file": filepath,
        "total_try_blocks": len(try_blocks),
        "bare_excepts": total_bare_excepts,
        "general_excepts": total_general_excepts,
        "specific_excepts": total_specific_excepts,
        "specific_ratio": round(total_specific_excepts / total * 100, 1) if total > 0 else 0,
    }


def review_efinance():
    """审查 efinance.py"""
    filepath = os.path.join(
        os.path.dirname(__file__), "..", "tradingagents", "dataflows", "providers", "china", "efinance.py",
    )

    print("=" * 60)
    print("📋 efinance.py 代码审查")
    print("=" * 60)

    doc_result = check_docstrings(filepath, "efinance")
    print(f"\n📝 Docstring 覆盖率: {doc_result['docstring_coverage']}%")
    print(f"   总定义数: {doc_result['total_definitions']}")
    print(f"   已文档化: {doc_result['documented']}")
    print(f"   未文档化: {doc_result['undocumented']}")
    for d in doc_result["details"]:
        status = "✅" if d["has_docstring"] else "❌"
        print(f"   {status} {d['type']} {d['name']} (line {d['line']})")

    type_result = check_type_annotations(filepath, "efinance")
    print("\n📝 类型注解覆盖率:")
    print(f"   返回类型注解: {type_result['return_annotation_coverage']}%")
    print(f"   参数类型注解: {type_result['args_annotation_coverage']}%")
    for d in type_result["details"]:
        rt = "✅" if d["return_annotated"] else "❌"
        args_pct = round(d["args_annotated"] / d["args_total"] * 100, 1) if d["args_total"] > 0 else 100
        print(
            f"   {rt} {d['name']} (line {d['line']}): 参数 {args_pct}% 注解, 返回{'有' if d['return_annotated'] else '无'}注解",
        )

    exc_result = check_exception_handling(filepath, "efinance")
    print("\n📝 异常处理:")
    print(f"   try 块数: {exc_result['total_try_blocks']}")
    print(f"   bare except: {exc_result['bare_excepts']}")
    print(f"   except Exception: {exc_result['general_excepts']}")
    print(f"   具体异常: {exc_result['specific_excepts']}")
    print(f"   具体异常比例: {exc_result['specific_ratio']}%")

    return {
        "efinance": {
            "docstring": doc_result,
            "type_annotations": type_result,
            "exception_handling": exc_result,
        },
    }


def review_base_provider():
    """审查 base_provider.py"""
    filepath = os.path.join(
        os.path.dirname(__file__), "..", "tradingagents", "dataflows", "providers", "base_provider.py",
    )

    print("=" * 60)
    print("📋 base_provider.py 代码审查")
    print("=" * 60)

    doc_result = check_docstrings(filepath, "base_provider")
    print(f"\n📝 Docstring 覆盖率: {doc_result['docstring_coverage']}%")
    print(f"   总定义数: {doc_result['total_definitions']}")
    print(f"   已文档化: {doc_result['documented']}")
    print(f"   未文档化: {doc_result['undocumented']}")
    for d in doc_result["details"]:
        status = "✅" if d["has_docstring"] else "❌"
        print(f"   {status} {d['type']} {d['name']} (line {d['line']})")

    type_result = check_type_annotations(filepath, "base_provider")
    print("\n📝 类型注解覆盖率:")
    print(f"   返回类型注解: {type_result['return_annotation_coverage']}%")
    print(f"   参数类型注解: {type_result['args_annotation_coverage']}%")

    # Check abstract methods
    with open(filepath, encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)

    # Find abstract methods
    abstract_methods = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "abstractmethod":
                    abstract_methods.append(node.name)

    print("\n📝 抽象方法:")
    for m in abstract_methods:
        print(f"   🔷 {m}")

    return {
        "base_provider": {
            "docstring": doc_result,
            "type_annotations": type_result,
            "abstract_methods": abstract_methods,
        },
    }


def review_data_source_manager():
    """审查 data_source_manager.py"""
    filepath = os.path.join(os.path.dirname(__file__), "..", "tradingagents", "dataflows", "data_source_manager.py")

    print("=" * 60)
    print("📋 data_source_manager.py 代码审查")
    print("=" * 60)

    # Count lines
    with open(filepath, encoding="utf-8") as f:
        lines = f.readlines()

    print(f"\n   📏 总行数: {len(lines)}")

    doc_result = check_docstrings(filepath, "data_source_manager")
    print(f"\n📝 Docstring 覆盖率: {doc_result['docstring_coverage']}%")
    print(f"   总定义数: {doc_result['total_definitions']}")
    print(f"   已文档化: {doc_result['documented']}")
    print(f"   未文档化: {doc_result['undocumented']}")

    # Check routing logic (search for key method patterns)
    routing_methods = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if any(kw in stripped for kw in ["def get_stock", "def get_data_source", "def _route", "def _select"]):
            routing_methods.append((i, stripped))

    print("\n📝 路由相关方法:")
    for line_no, method in routing_methods:
        print(f"   🔷 Line {line_no}: {method}")

    return {
        "data_source_manager": {
            "docstring": doc_result,
            "total_lines": len(lines),
        },
    }


if __name__ == "__main__":
    print("=" * 60)
    print("🔍 结构化代码审查报告")
    print("=" * 60)

    results = {}
    results.update(review_efinance())
    print()
    results.update(review_base_provider())
    print()
    results.update(review_data_source_manager())

    print("\n" + "=" * 60)
    print("📊 汇总")
    print("=" * 60)

    for module, data in results.items():
        doc = data.get("docstring", {})
        print(f"\n{module}:")
        print(f"   Docstring 覆盖率: {doc.get('docstring_coverage', 'N/A')}%")
        print(f"   未文档化: {doc.get('undocumented', 'N/A')} 处")
