#!/usr/bin/env python3
"""
直接访问东方财富网新闻 API - 绕过 AKShare
测试在 Docker 环境中是否能正常获取新闻数据
"""

import json
import time

import requests


def get_stock_news_direct(symbol: str, page_size: int = 10):
    """
    直接访问东方财富网新闻 API

    Args:
        symbol: 股票代码（如 600089）
        page_size: 每页数量

    Returns:
        新闻列表
    """
    # 构建完整的浏览器请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.eastmoney.com/",
        "Origin": "https://www.eastmoney.com",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

    # 方法1：尝试使用搜索 API
    url = "https://search-api-web.eastmoney.com/search/jsonp"

    # 构建请求参数
    param = {
        "uid": "",
        "keyword": symbol,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": page_size,
                "preTag": "<em>",
                "postTag": "</em>",
            },
        },
    }

    params = {"cb": f"jQuery{int(time.time() * 1000)}", "param": json.dumps(param), "_": str(int(time.time() * 1000))}

    print("【方法1】搜索 API")
    print(f"URL: {url}")
    print(f"股票代码: {symbol}")
    print("-" * 80)

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"状态码: {response.status_code}")
        print(f"响应长度: {len(response.text)} 字符")

        if response.status_code == 200:
            # 解析 JSONP
            text = response.text
            if text.startswith("jQuery"):
                text = text[text.find("(") + 1 : text.rfind(")")]

            data = json.loads(text)
            print(f"返回的键: {list(data.keys())}")

            if "result" in data:
                print(f"result 的键: {list(data['result'].keys())}")

                if "cmsArticleWebOld" in data["result"]:
                    articles = data["result"]["cmsArticleWebOld"]
                    print(f"✅ 成功获取 {len(articles)} 条新闻")
                    return articles
                print("❌ 未找到 cmsArticleWebOld 字段")
                print(f"可用字段: {list(data['result'].keys())}")
    except Exception as e:
        print(f"❌ 方法1失败: {e}")

    # 方法2：尝试使用资讯中心 API
    print("\n【方法2】资讯中心 API")
    url2 = "https://np-anotice-stock.eastmoney.com/api/content/ann"

    params2 = {
        "client_source": "web",
        "page_index": 1,
        "page_size": page_size,
        "stock_list": symbol,
        "f_node": "0",
        "s_node": "0",
    }

    print(f"URL: {url2}")
    print("-" * 80)

    try:
        response = requests.get(url2, params=params2, headers=headers, timeout=10)
        print(f"状态码: {response.status_code}")
        print(f"响应长度: {len(response.text)} 字符")

        if response.status_code == 200:
            data = response.json()
            print(f"返回的键: {list(data.keys())}")

            if "data" in data and "list" in data["data"]:
                articles = data["data"]["list"]
                print(f"✅ 成功获取 {len(articles)} 条公告")
                return articles
    except Exception as e:
        print(f"❌ 方法2失败: {e}")

    # 方法3：尝试使用股吧新闻 API
    print("\n【方法3】股吧新闻 API")
    url3 = "https://guba.eastmoney.com/interface/GetData.aspx"

    params3 = {"type": "1", "code": symbol, "ps": page_size, "p": 1, "sort": "1"}

    print(f"URL: {url3}")
    print("-" * 80)

    try:
        response = requests.get(url3, params=params3, headers=headers, timeout=10)
        print(f"状态码: {response.status_code}")
        print(f"响应长度: {len(response.text)} 字符")
        print("响应内容（前500字符）:")
        print(response.text[:500])

        if response.status_code == 200 and len(response.text) > 0:
            data = response.json()
            print("✅ 成功获取数据")
            return data
    except Exception as e:
        print(f"❌ 方法3失败: {e}")

    # 方法4：尝试使用新闻列表 API（不带搜索）
    print("\n【方法4】新闻列表 API")
    url4 = "https://newsapi.eastmoney.com/api/news/list"

    params4 = {"keyword": symbol, "pageSize": page_size, "pageIndex": 1, "type": "1"}

    print(f"URL: {url4}")
    print("-" * 80)

    try:
        response = requests.get(url4, params=params4, headers=headers, timeout=10)
        print(f"状态码: {response.status_code}")
        print(f"响应长度: {len(response.text)} 字符")

        if response.status_code == 200:
            data = response.json()
            print(f"返回的键: {list(data.keys())}")

            if "data" in data:
                articles = data["data"]
                print(f"✅ 成功获取 {len(articles)} 条新闻")
                return articles
    except Exception as e:
        print(f"❌ 方法4失败: {e}")

    return []


if __name__ == "__main__":
    print("=" * 80)
    print("🧪 测试直接访问东方财富网新闻 API（绕过 AKShare）")
    print("=" * 80)

    test_symbols = ["600089", "000001"]

    for symbol in test_symbols:
        print(f"\n{'=' * 80}")
        print(f"测试股票: {symbol}")
        print(f"{'=' * 80}")

        news_list = get_stock_news_direct(symbol, page_size=5)

        if news_list:
            print(f"\n✅ 成功获取 {len(news_list)} 条数据")
            print("\n第一条数据:")
            print(json.dumps(news_list[0], indent=2, ensure_ascii=False)[:500])
        else:
            print("\n❌ 未获取到数据")

        time.sleep(1)  # 避免请求过快
