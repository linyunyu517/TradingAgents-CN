"""
用户活动记录查看组件
为管理员提供查看和分析用户操作行为的Web界面
"""

import json
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# 导入用户活动记录器
try:
    from ..utils.auth_manager import auth_manager
    from ..utils.user_activity_logger import user_activity_logger
except ImportError:
    user_activity_logger = None
    auth_manager = None


def render_user_activity_dashboard():
    """渲染用户活动仪表板"""

    # 检查权限
    if not auth_manager or not auth_manager.check_permission("admin"):
        st.error("❌ 您没有权限访问用户活动记录")
        return

    if not user_activity_logger:
        st.error("❌ 用户活动记录器未初始化")
        return

    st.title("📊 用户活动记录仪表板")

    # 侧边栏过滤选项
    with st.sidebar:
        st.header("🔍 过滤选项")

        # 日期范围选择
        date_range = st.selectbox("📅 时间范围", ["最近1天", "最近3天", "最近7天", "最近30天", "自定义"], index=2)

        if date_range == "自定义":
            start_date = st.date_input("开始日期", datetime.now() - timedelta(days=7))
            end_date = st.date_input("结束日期", datetime.now())
        else:
            days_map = {"最近1天": 1, "最近3天": 3, "最近7天": 7, "最近30天": 30}
            days = days_map[date_range]
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

        # 用户过滤
        username_filter = st.text_input("👤 用户名过滤", placeholder="留空显示所有用户")

        # 活动类型过滤
        action_type_filter = st.selectbox(
            "🔧 活动类型",
            ["全部", "auth", "analysis", "config", "navigation", "data_export", "user_management", "system"],
        )

        if action_type_filter == "全部":
            action_type_filter = None

    # 获取活动数据
    activities = user_activity_logger.get_user_activities(
        username=username_filter or None,
        start_date=start_date,
        end_date=end_date,
        action_type=action_type_filter,
        limit=1000,
    )

    if not activities:
        st.warning("📭 未找到符合条件的活动记录")
        return

    # 显示统计概览
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("📊 总活动数", len(activities))

    with col2:
        unique_users = len(set(a["username"] for a in activities))
        st.metric("👥 活跃用户", unique_users)

    with col3:
        successful_activities = sum(1 for a in activities if a.get("success", True))
        success_rate = (successful_activities / len(activities) * 100) if activities else 0
        st.metric("✅ 成功率", f"{success_rate:.1f}%")

    with col4:
        durations = [a.get("duration_ms", 0) for a in activities if a.get("duration_ms")]
        avg_duration = sum(durations) / len(durations) if durations else 0
        st.metric("⏱️ 平均耗时", f"{avg_duration:.0f}ms")

    # 标签页
    tab1, tab2, tab3, tab4 = st.tabs(["📈 统计图表", "📋 活动列表", "👥 用户分析", "📤 导出数据"])

    with tab1:
        render_activity_charts(activities)

    with tab2:
        render_activity_list(activities)

    with tab3:
        render_user_analysis(activities)

    with tab4:
        render_export_options(activities)


def render_activity_charts(activities: list[dict[str, Any]]):
    """渲染活动统计图表"""

    # 按活动类型统计
    st.subheader("📊 按活动类型统计")
    activity_types = {}
    for activity in activities:
        action_type = activity.get("action_type", "unknown")
        activity_types[action_type] = activity_types.get(action_type, 0) + 1

    if activity_types:
        fig_pie = px.pie(values=list(activity_types.values()), names=list(activity_types.keys()), title="活动类型分布")
        st.plotly_chart(fig_pie, use_container_width=True)

    # 按时间统计
    st.subheader("📅 按时间统计")
    daily_activities = {}
    for activity in activities:
        date_str = datetime.fromtimestamp(activity["timestamp"]).strftime("%Y-%m-%d")
        daily_activities[date_str] = daily_activities.get(date_str, 0) + 1

    if daily_activities:
        dates = sorted(daily_activities.keys())
        counts = [daily_activities[date] for date in dates]

        fig_line = go.Figure()
        fig_line.add_trace(
            go.Scatter(
                x=dates,
                y=counts,
                mode="lines+markers",
                name="每日活动数",
                line=dict(color="#1f77b4", width=2),
                marker=dict(size=6),
            ),
        )
        fig_line.update_layout(title="每日活动趋势", xaxis_title="日期", yaxis_title="活动数量")
        st.plotly_chart(fig_line, use_container_width=True)

    # 按用户统计
    st.subheader("👥 按用户统计")
    user_activities = {}
    for activity in activities:
        username = activity.get("username", "unknown")
        user_activities[username] = user_activities.get(username, 0) + 1

    if user_activities:
        # 只显示前10个最活跃的用户
        top_users = sorted(user_activities.items(), key=lambda x: x[1], reverse=True)[:10]
        usernames = [item[0] for item in top_users]
        counts = [item[1] for item in top_users]

        fig_bar = px.bar(
            x=counts,
            y=usernames,
            orientation="h",
            title="用户活动排行榜 (前10名)",
            labels={"x": "活动数量", "y": "用户名"},
        )
        st.plotly_chart(fig_bar, use_container_width=True)


def render_activity_list(activities: list[dict[str, Any]]):
    """渲染活动列表"""

    st.subheader("📋 活动记录列表")

    # 分页设置
    page_size = st.selectbox("每页显示", [10, 25, 50, 100], index=1)
    total_pages = (len(activities) + page_size - 1) // page_size

    page = st.number_input("页码", min_value=1, max_value=total_pages, value=1) - 1 if total_pages > 1 else 0

    # 获取当前页数据
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(activities))
    page_activities = activities[start_idx:end_idx]

    # 转换为DataFrame显示
    df_data = []
    for activity in page_activities:
        timestamp = datetime.fromtimestamp(activity["timestamp"])
        df_data.append(
            {
                "时间": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "用户": activity.get("username", "unknown"),
                "角色": activity.get("user_role", "unknown"),
                "活动类型": activity.get("action_type", "unknown"),
                "活动名称": activity.get("action_name", "unknown"),
                "成功": "✅" if activity.get("success", True) else "❌",
                "耗时(ms)": activity.get("duration_ms", ""),
                "详情": json.dumps(activity.get("details", {}), ensure_ascii=False)[:100] + "..."
                if activity.get("details")
                else "",
            },
        )

    if df_data:
        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True)

        # 显示分页信息
        if total_pages > 1:
            st.info(
                f"📄 第 {page + 1} 页，共 {total_pages} 页 | 显示 {start_idx + 1}-{end_idx} 条，共 {len(activities)} 条记录",
            )
    else:
        st.info("📭 当前页没有数据")


def render_user_analysis(activities: list[dict[str, Any]]):
    """渲染用户分析"""

    st.subheader("👥 用户行为分析")

    # 用户选择
    usernames = sorted(set(a["username"] for a in activities))
    selected_user = st.selectbox("选择用户", usernames)

    if selected_user:
        user_activities = [a for a in activities if a["username"] == selected_user]

        col1, col2 = st.columns(2)

        with col1:
            st.metric("📊 总活动数", len(user_activities))

            # 成功率
            successful = sum(1 for a in user_activities if a.get("success", True))
            success_rate = (successful / len(user_activities) * 100) if user_activities else 0
            st.metric("✅ 成功率", f"{success_rate:.1f}%")

        with col2:
            # 最常用功能
            action_counts = {}
            for activity in user_activities:
                action = activity.get("action_name", "unknown")
                action_counts[action] = action_counts.get(action, 0) + 1

            if action_counts:
                most_used = max(action_counts.items(), key=lambda x: x[1])
                st.metric("🔥 最常用功能", most_used[0])
                st.metric("📈 使用次数", most_used[1])

        # 用户活动时间线
        st.subheader(f"📅 {selected_user} 的活动时间线")

        timeline_data = []
        for activity in user_activities[-20:]:  # 显示最近20条
            timestamp = datetime.fromtimestamp(activity["timestamp"])
            timeline_data.append(
                {
                    "时间": timestamp.strftime("%m-%d %H:%M"),
                    "活动": f"{activity.get('action_type', 'unknown')} - {activity.get('action_name', 'unknown')}",
                    "状态": "✅" if activity.get("success", True) else "❌",
                },
            )

        if timeline_data:
            df_timeline = pd.DataFrame(timeline_data)
            st.dataframe(df_timeline, use_container_width=True)


def render_export_options(activities: list[dict[str, Any]]):
    """渲染导出选项"""

    st.subheader("📤 导出数据")

    col1, col2 = st.columns(2)

    with col1:
        export_format = st.selectbox("导出格式", ["CSV", "JSON", "Excel"])

    with col2:
        include_details = st.checkbox("包含详细信息", value=True)

    if st.button("📥 导出数据", type="primary"):
        try:
            # 准备导出数据
            export_data = []
            for activity in activities:
                timestamp = datetime.fromtimestamp(activity["timestamp"])
                row = {
                    "时间戳": activity["timestamp"],
                    "日期时间": timestamp.isoformat(),
                    "用户名": activity.get("username", ""),
                    "用户角色": activity.get("user_role", ""),
                    "活动类型": activity.get("action_type", ""),
                    "活动名称": activity.get("action_name", ""),
                    "会话ID": activity.get("session_id", ""),
                    "IP地址": activity.get("ip_address", ""),
                    "页面URL": activity.get("page_url", ""),
                    "耗时(ms)": activity.get("duration_ms", ""),
                    "成功": activity.get("success", True),
                    "错误信息": activity.get("error_message", ""),
                }

                if include_details:
                    row["详细信息"] = json.dumps(activity.get("details", {}), ensure_ascii=False)

                export_data.append(row)

            # 生成文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            if export_format == "CSV":
                df = pd.DataFrame(export_data)
                csv_data = df.to_csv(index=False, encoding="utf-8-sig")
                st.download_button(
                    label="📥 下载 CSV 文件",
                    data=csv_data,
                    file_name=f"user_activities_{timestamp}.csv",
                    mime="text/csv",
                )

            elif export_format == "JSON":
                json_data = json.dumps(export_data, ensure_ascii=False, indent=2)
                st.download_button(
                    label="📥 下载 JSON 文件",
                    data=json_data,
                    file_name=f"user_activities_{timestamp}.json",
                    mime="application/json",
                )

            elif export_format == "Excel":
                df = pd.DataFrame(export_data)
                # 注意：这里需要安装 openpyxl 库
                excel_buffer = df.to_excel(index=False, engine="openpyxl")
                st.download_button(
                    label="📥 下载 Excel 文件",
                    data=excel_buffer,
                    file_name=f"user_activities_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

            st.success(f"✅ 成功准备 {len(activities)} 条记录的导出文件")

        except Exception as e:
            st.error(f"❌ 导出失败: {e}")


def render_activity_summary_widget():
    """渲染活动摘要小部件（用于主页面）"""

    if not user_activity_logger or not auth_manager:
        return

    # 只有管理员才能看到
    if not auth_manager.check_permission("admin"):
        return

    st.subheader("📊 用户活动概览")

    # 获取最近24小时的活动
    end_date = datetime.now()
    start_date = end_date - timedelta(hours=24)

    activities = user_activity_logger.get_user_activities(start_date=start_date, end_date=end_date, limit=500)

    if activities:
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("📊 24小时活动", len(activities))

        with col2:
            unique_users = len(set(a["username"] for a in activities))
            st.metric("👥 活跃用户", unique_users)

        with col3:
            successful = sum(1 for a in activities if a.get("success", True))
            success_rate = (successful / len(activities) * 100) if activities else 0
            st.metric("✅ 成功率", f"{success_rate:.1f}%")

        # 显示最近的几条活动
        st.write("🕐 最近活动:")
        recent_activities = activities[:5]
        for activity in recent_activities:
            timestamp = datetime.fromtimestamp(activity["timestamp"])
            success_icon = "✅" if activity.get("success", True) else "❌"
            st.write(
                f"{success_icon} {timestamp.strftime('%H:%M')} - {activity.get('username', 'unknown')}: {activity.get('action_name', 'unknown')}",
            )
    else:
        st.info("📭 最近24小时无活动记录")
