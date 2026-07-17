"""
成本统计可视化面板（Gradio）
"""
import os
import gradio as gr
import matplotlib
matplotlib.use('Agg')  # 非交互式后端，避免线程问题
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from datetime import datetime, timedelta
from db import get_db
from io import BytesIO
import base64
from token_tracker import get_user_summary, get_purpose_summary, get_daily_usage_cost, get_token_budget_info
from token_tracker import PRICING

# ==================== 字体配置 ====================
def setup_chinese_font():
    """配置中文字体，优先使用系统可用字体"""
    font_candidates = [
        '/System/Library/Fonts/PingFang.ttc',
        '/System/Library/Fonts/STHeiti Light.ttc',
        '/System/Library/Fonts/Hiragino Sans GB.ttc',
        'SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei'
    ]
    for font_path in font_candidates:
        try:
            fm.font_manager.fontManager.addfont(font_path)
            prop = fm.FontProperties(fname=font_path)
            plt.rcParams['font.family'] = prop.get_name()
            return
        except Exception:
            continue
    plt.rcParams['font.family'] = 'sans-serif'

setup_chinese_font()

# ==================== 数据库查询辅助 ====================
def query_db(sql, params=None):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
    except Exception as e:
        print(f"查询失败: {e}")
        return []

# ==================== 图表生成 ====================
def create_purpose_pie_chart(user_name: str) -> str:
    """生成按用途分布的花费饼图，返回 base64 图片"""
    rows = query_db(
        """SELECT purpose, SUM(total_cost) as cost
           FROM cost_records 
           WHERE user_name = %s AND created_at >= CURRENT_DATE
           GROUP BY purpose ORDER BY cost DESC""",
        (user_name,)
    )
    if not rows:
        return None

    labels = [r[0] for r in rows]
    sizes = [r[1] for r in rows]
    colors = ['#ff6b6b', '#ffd93d', '#6bcb77', '#4d96ff', '#9b59b6', '#ff9f43']
    
    fig, ax = plt.subplots(figsize=(6, 5))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors[:len(labels)],
        autopct='%1.1f%%', startangle=90,
        textprops={'fontsize': 10}
    )
    ax.set_title('今日花费用途分布', fontsize=14, fontweight='bold')
    
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', transparent=True)
    plt.close()
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')

def create_daily_trend_chart(user_name: str, days: int = 7) -> str:
    """生成每日花费趋势折线图，返回 base64 图片"""
    rows = query_db(
        """SELECT DATE(created_at) as date, SUM(total_cost) as cost, COUNT(*) as calls
           FROM cost_records 
           WHERE user_name = %s AND created_at >= CURRENT_DATE - %s
           GROUP BY DATE(created_at) ORDER BY date""",
        (user_name, days)
    )
    if not rows:
        return None

    dates = [r[0] for r in rows]
    costs = [r[1] for r in rows]
    calls = [r[2] for r in rows]

    fig, ax1 = plt.subplots(figsize=(8, 4))
    color1, color2 = '#4d96ff', '#ff6b6b'
    ax1.set_xlabel('日期', fontsize=10)
    ax1.set_ylabel('花费 (元)', fontsize=10, color=color1)
    ax1.plot(dates, costs, 'o-', color=color1, linewidth=2, markersize=6, label='花费')
    ax1.tick_params(axis='y', labelcolor=color1)
    for i, (d, c) in enumerate(zip(dates, costs)):
        ax1.annotate(f'{c:.4f}', (d, c), textcoords="offset points", xytext=(0,10), ha='center', fontsize=8, color=color1)

    ax2 = ax1.twinx()
    ax2.set_ylabel('调用次数', fontsize=10, color=color2)
    ax2.bar(dates, calls, alpha=0.3, color=color2, label='调用次数')
    ax2.tick_params(axis='y', labelcolor=color2)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=8)

    ax1.set_title(f'近{days}日花费趋势', fontsize=14, fontweight='bold')
    fig.autofmt_xdate()
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', transparent=True)
    plt.close()
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')

# ==================== 数据查询 ====================
def get_dashboard_summary(user_name: str):
    info = get_token_budget_info(user_name)
    today_cost = get_daily_usage_cost(user_name)
    purpose = get_purpose_summary()
    total_calls = sum(p.get("calls", 0) for p in purpose.values())
    return (
        f"💰 今日花费: ¥{today_cost:.4f}",
        f"📊 总调用次数: {total_calls}",
        f"💳 预算: {info['daily_budget']} | 剩余: {info['remaining']}",
        f"📈 今日 Token: {info['used_today']}"
    )

def get_model_pricing_table():
    rows = [["模型", "输入价格 (元/1K tokens)", "输出价格 (元/1K tokens)"]]
    for model, price in PRICING.items():
        rows.append([model, str(price["prompt"]), str(price["completion"])])
    return rows

# ==================== Gradio 界面 ====================

def refresh(user_name, days):
    pie = create_purpose_pie_chart(user_name)
    trend = create_daily_trend_chart(user_name, int(days))
    s1, s2, s3, s4 = get_dashboard_summary(user_name)
    pricing_table = get_model_pricing_table()
    return (
        s1, s2, s3, s4,
        gr.Image(value=None) if pie is None else f"data:image/png;base64,{pie}",
        gr.Image(value=None) if trend is None else f"data:image/png;base64,{trend}",
        pricing_table
    )

# 增加导出函数 CSV
import csv
import tempfile
import os

def export_cost_csv(user_name: str, days: int = 30) -> str:
    """
    导出用户最近 N 天的花费明细为 CSV 文件。
    返回 CSV 文件路径。
    """
    rows = query_db(
        """SELECT id, user_name, thread_id, model, purpose, 
                  prompt_tokens, completion_tokens, total_tokens,
                  total_cost, tool_name, created_at
           FROM cost_records 
           WHERE user_name = %s 
             AND created_at >= CURRENT_DATE - %s
           ORDER BY created_at DESC""",
        (user_name, days)
    )
    
    if not rows:
        return None
    
    # 生成 CSV 文件
    filename = f"cost_report_{user_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = os.path.join(tempfile.gettempdir(), filename)
    
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([
            "ID", "用户", "线程ID", "模型", "用途",
            "输入Token", "输出Token", "总Token", "花费(元)",
            "工具名", "时间"
        ])
        for row in rows:
            writer.writerow(row)
    
    return filepath


def refresh_with_export(user_name, days):
    """刷新面板数据并返回导出文件路径"""
    # 原有的面板刷新逻辑
    pie = create_purpose_pie_chart(user_name)
    trend = create_daily_trend_chart(user_name, int(days))
    s1, s2, s3, s4 = get_dashboard_summary(user_name)
    pricing_table = get_model_pricing_table()
    
    # 新增：导出 CSV
    csv_path = export_cost_csv(user_name, int(days))
    
    return (
        s1, s2, s3, s4,
        gr.Image(value=None) if pie is None else f"data:image/png;base64,{pie}",
        gr.Image(value=None) if trend is None else f"data:image/png;base64,{trend}",
        pricing_table,
        gr.File(value=csv_path, visible=True) if csv_path else gr.File(visible=False),
        gr.Markdown("✅ CSV 已生成，点击上方下载按钮保存文件", visible=True) if csv_path else gr.Markdown("⚠️ 暂无数据可导出", visible=True)
    )
def create_dashboard():
    with gr.Blocks(title="💰 成本统计面板", theme=gr.themes.Soft()) as dashboard:
        gr.Markdown("# 💰 AI 成本统计面板")
        
        with gr.Row():
            user_input = gr.Textbox(label="用户名", value="admin", scale=1)
            days_input = gr.Dropdown(label="趋势图天数", choices=[3, 7, 14, 30], value=7, scale=1)
            refresh_btn = gr.Button("🔄 刷新数据", variant="primary", scale=1)
            export_btn = gr.Button("📥 导出CSV", variant="secondary", scale=1)

        with gr.Row():
            stat1 = gr.Textbox(label="今日花费", interactive=False)
            stat2 = gr.Textbox(label="调用统计", interactive=False)
            stat3 = gr.Textbox(label="预算状态", interactive=False)
            stat4 = gr.Textbox(label="Token 统计", interactive=False)
        
        with gr.Row():
            pie_chart = gr.Image(label="用途分布", type="pil", scale=1)
            trend_chart = gr.Image(label="花费趋势", type="pil", scale=1)
        
        # 新增：CSV 下载区域
        with gr.Row():
            csv_file = gr.File(label="📄 花费明细下载", interactive=False, visible=True)
            export_status = gr.Markdown("", visible=True)

        with gr.Accordion("📋 模型定价表", open=False):
            pricing_table = gr.DataFrame(
                headers=["模型", "输入价格 (元/1K tokens)", "输出价格 (元/1K tokens)"],
                label="当前定价"
            )
        
        # 刷新按钮事件
        refresh_btn.click(
            fn=refresh,
            inputs=[user_input, days_input],
            outputs=[stat1, stat2, stat3, stat4, pie_chart, trend_chart, pricing_table]
        )
        
        # 导出按钮事件
        export_btn.click(
            fn=refresh_with_export,
            inputs=[user_input, days_input],
            outputs=[stat1, stat2, stat3, stat4, pie_chart, trend_chart, pricing_table, csv_file, export_status]
        )
        
        # 页面加载事件
        dashboard.load(
            fn=refresh,
            inputs=[user_input, days_input],
            outputs=[stat1, stat2, stat3, stat4, pie_chart, trend_chart, pricing_table]
        )

    return dashboard

