import os
import json
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime, timedelta
import requests
import pandas as pd
import numpy as np

# ==========================================
# 配置读取 (优先从环境变量读取)
# ==========================================
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.126.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 465))
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
# Server酱 Key
SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY")
# Gist 订阅者列表配置
GIST_SUBSCRIBERS_URL = os.environ.get("GIST_SUBSCRIBERS_URL")
GIST_TOKEN = os.environ.get("GIST_TOKEN")

# ==========================================
# 最优策略参数配置 (来自回测优化结果)
# RSI(15) EMA 32/77 - 联结基金模式（理论最优）
# 总收益268.02%, 年化20.90%
# 注：联结基金可小数份额申购，ETF需100份整手交易
# ==========================================
ETF_CODE = "512890"  # 红利低波ETF
ETF_NAME = "红利低波ETF"
RSI_PERIOD = 15  # RSI周期（使用EMA平滑）
RSI_BUY_THRESHOLD = int(os.environ.get("RSI_BUY_THRESHOLD", 32))  # 买入阈值
RSI_SELL_THRESHOLD = int(os.environ.get("RSI_SELL_THRESHOLD", 77))  # 卖出阈值

def fetch_subscriber_emails():
    """
    从私有 Gist 获取订阅者邮箱列表
    如果 Gist 配置不存在，则回退到环境变量 SUBSCRIBER_EMAILS
    """
    # 优先从 Gist 读取
    if GIST_SUBSCRIBERS_URL and GIST_TOKEN:
        try:
            headers = {
                'Authorization': f'token {GIST_TOKEN}',
                'Accept': 'application/vnd.github.v3.raw'
            }
            response = requests.get(GIST_SUBSCRIBERS_URL, headers=headers, timeout=10)
            if response.status_code == 200:
                # 支持每行一个邮箱或逗号分隔
                content = response.text.strip()
                emails = []
                for line in content.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#'):  # 忽略空行和注释
                        # 支持逗号分隔的多个邮箱
                        emails.extend([e.strip() for e in line.split(',') if e.strip()])
                print(f"从 Gist 获取到 {len(emails)} 个订阅者邮箱")
                return emails
            else:
                print(f"从 Gist 获取邮箱失败: HTTP {response.status_code}")
        except Exception as e:
            print(f"从 Gist 获取邮箱出错: {e}")
    
    # 回退到环境变量
    fallback_emails = os.environ.get("SUBSCRIBER_EMAILS", "")
    if fallback_emails:
        emails = [e.strip() for e in fallback_emails.split(",") if e.strip()]
        print(f"使用环境变量 SUBSCRIBER_EMAILS，共 {len(emails)} 个订阅者")
        return emails
    
    return []

def calculate_rsi_ema(prices, period):
    """
    计算RSI指标（使用EMA平滑，更敏感）
    与回测代码保持一致
    """
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    
    # 使用EMA而非SMA（更敏感）
    alpha = 1 / period  # EMA平滑因子
    avg_gain = gain.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def fetch_etf_data(code, days=60):
    """
    使用 akshare 获取ETF历史数据
    返回最近N天的数据用于计算RSI
    """
    import akshare as ak
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始获取 {code} 数据...")
    
    try:
        # 获取ETF日线数据（前复权）
        df = ak.fund_etf_hist_em(symbol=code, period="daily", adjust="qfq")
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.rename(columns={
            '日期': 'date',
            '收盘': 'close'
        })
        df = df.sort_values('date').reset_index(drop=True)
        
        # 只取最近N天
        df = df.tail(days).reset_index(drop=True)
        
        print(f"获取到 {len(df)} 条数据，从 {df['date'].min()} 到 {df['date'].max()}")
        return df
        
    except Exception as e:
        print(f"获取ETF数据失败: {e}")
        return None


def fetch_rsi_and_price():
    """
    获取 RSI 和 价格数据
    使用自己计算的 RSI(15) EMA，与回测策略保持一致
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始获取数据...")
    
    # 获取ETF历史数据
    df = fetch_etf_data(ETF_CODE, days=60)  # 获取60天数据，确保RSI计算准确
    
    if df is None or len(df) < RSI_PERIOD + 5:
        print("无法获取足够的历史数据")
        return None, None
    
    # 计算RSI(15) EMA
    df['rsi'] = calculate_rsi_ema(df['close'], RSI_PERIOD)
    
    # 获取最新的RSI和价格
    latest = df.iloc[-1]
    rsi_value = latest['rsi']
    latest_price = latest['close']
    latest_date = latest['date'].strftime('%Y-%m-%d')
    
    if pd.notna(rsi_value):
        print(f"获取到 RSI({RSI_PERIOD}) EMA: {rsi_value:.2f}")
        print(f"最新价格: {latest_price:.4f}")
        print(f"数据日期: {latest_date}")
    else:
        print("RSI计算失败，数据不足")
        return None, None
    
    return rsi_value, latest_price

def send_email(to_email, subject, content):
    """
    发送邮件函数
    """
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("未配置发件人邮箱或密码，跳过发送邮件。")
        return

    # 构建 HTML 邮件内容
    html_content = f"""
    <html>
    <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f4f6f9; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 10px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
            <h2 style="color: #2c3e50; margin-top: 0; border-bottom: 2px solid #3498db; padding-bottom: 10px;">{subject}</h2>
            
            <div style="font-size: 16px; line-height: 1.6; color: #34495e; margin: 20px 0;">
                {content.replace(chr(10), '<br>')}
            </div>
            
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ecf0f1; font-size: 12px; color: #95a5a6; text-align: center;">
                <p>此邮件由 GitHub Actions 自动发送，请勿直接回复。</p>
                <p>
                    如果您不想继续接收此类邮件，可以 
                    <a href="mailto:{SENDER_EMAIL}?subject=取消订阅 RSI 监控&body=请将我的邮箱从订阅列表中移除" style="color: #e74c3c; text-decoration: none; font-weight: bold;">点击此处取消订阅</a>
                </p>
            </div>
        </div>
    </body>
    </html>
    """

    message = MIMEText(html_content, 'html', 'utf-8')
    # RFC5322 要求 From 必须包含可解析的邮箱地址；使用“显示名 <邮箱>”格式
    message['From'] = Header(f"RSI 监控助手 <{SENDER_EMAIL}>", 'utf-8')
    message['To'] = Header(to_email, 'utf-8')
    message['Subject'] = Header(subject, 'utf-8')

    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, [to_email], message.as_string())
        server.quit()
        print(f"邮件已发送至 {to_email}")
    except Exception as e:
        print(f"邮件发送失败: {e}")

def send_wechat(title, content):
    """
    微信通知 (Server酱)
    """
    if not SERVERCHAN_KEY:
        print("未配置 SERVERCHAN_KEY，跳过微信通知。")
        return
    
    data = {'title': title,
            'desp': content,
            'channel': 9}
    msg_url = f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send"

    try:
        response = requests.post(msg_url, data=data)
        print(f"微信通知发送结果: {response.text}")
    except Exception as e:
        print(f"微信通知发送失败: {e}")

def main():
    rsi, price = fetch_rsi_and_price()
    
    if rsi is None:
        print("未能获取有效 RSI 数据，程序结束。")
        return

    print(f"当前状态: RSI={rsi}, 价格={price}")

    subject = ""
    content = ""

    if rsi < RSI_BUY_THRESHOLD:
        subject = f"【买入提醒】{ETF_NAME} RSI低于{RSI_BUY_THRESHOLD}"
        content = f"""当前{ETF_NAME} ({ETF_CODE}) 的 RSI({RSI_PERIOD}) EMA 为 {rsi:.2f}，已低于 {RSI_BUY_THRESHOLD}，建议关注买入机会。

📊 策略参数:
- RSI周期: {RSI_PERIOD}日 (EMA平滑)
- 买入阈值: RSI < {RSI_BUY_THRESHOLD}
- 卖出阈值: RSI > {RSI_SELL_THRESHOLD}

💰 回测表现:
- 总收益: 268.02%
- 年化收益: 20.90%

当前价格: {price}"""
    elif rsi > RSI_SELL_THRESHOLD:
        subject = f"【卖出提醒】{ETF_NAME} RSI高于{RSI_SELL_THRESHOLD}"
        content = f"""当前{ETF_NAME} ({ETF_CODE}) 的 RSI({RSI_PERIOD}) EMA 为 {rsi:.2f}，已高于 {RSI_SELL_THRESHOLD}，建议关注卖出风险。

📊 策略参数:
- RSI周期: {RSI_PERIOD}日 (EMA平滑)
- 买入阈值: RSI < {RSI_BUY_THRESHOLD}
- 卖出阈值: RSI > {RSI_SELL_THRESHOLD}

💰 回测表现:
- 总收益: 268.02%
- 年化收益: 20.90%

当前价格: {price}"""
    else:
        print(f"RSI 在正常范围内 ({RSI_BUY_THRESHOLD}-{RSI_SELL_THRESHOLD})，无需发送提醒。")

    if subject:
        print(f"触发条件，准备发送邮件: {subject}")
        subscribers = fetch_subscriber_emails()
        if not subscribers:
            print("没有配置订阅者邮箱，无法发送。")
        
        for email in subscribers:
            send_email(email, subject, content)
            
        # 发送微信通知
        send_wechat(subject, content)

    # ==========================================
    # 生成静态数据文件 (供 GitHub Pages 使用)
    # ==========================================
    docs_dir = "docs"
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir)
    
    # GitHub Actions 运行在 UTC 时区，需要转换为北京时间 (UTC+8)
    beijing_time = datetime.utcnow() + timedelta(hours=8)
    
    # 计算买卖信号状态
    if rsi < RSI_BUY_THRESHOLD:
        signal = "买入"
        signal_color = "#22c55e"  # 绿色
    elif rsi > RSI_SELL_THRESHOLD:
        signal = "卖出"
        signal_color = "#ef4444"  # 红色
    else:
        signal = "持有"
        signal_color = "#3b82f6"  # 蓝色
    
    data = {
        "etf_code": ETF_CODE,
        "etf_name": ETF_NAME,
        "rsi": round(rsi, 2),
        "rsi_period": RSI_PERIOD,
        "price": round(price, 4) if price else None,
        "buy_threshold": RSI_BUY_THRESHOLD,
        "sell_threshold": RSI_SELL_THRESHOLD,
        "signal": signal,
        "signal_color": signal_color,
        "strategy": f"RSI({RSI_PERIOD}) EMA {RSI_BUY_THRESHOLD}/{RSI_SELL_THRESHOLD}",
        "backtest_return": "268.02%",
        "backtest_annual": "20.90%",
        "timestamp": beijing_time.strftime("%Y-%m-%d %H:%M:%S") + " (北京时间)"
    }
    
    with open(os.path.join(docs_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"静态数据已保存至 {docs_dir}/data.json")

    # ==========================================
    # 动态注入订阅服务地址 (从环境变量)
    # ==========================================
    subscribe_worker_url = os.environ.get("SUBSCRIBE_WORKER_URL")
    formspree_id = os.environ.get("FORMSPREE_ID")
    
    index_path = os.path.join(docs_dir, "index.html")
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            updated = False
            
            # 注入 Worker URL
            if subscribe_worker_url and "__SUBSCRIBE_WORKER_URL__" in content:
                content = content.replace("__SUBSCRIBE_WORKER_URL__", subscribe_worker_url)
                print(f"已注入 Worker URL: {subscribe_worker_url}")
                updated = True
            
            # 注入 Formspree ID (备用方案)
            if formspree_id and "__FORMSPREE_ID__" in content:
                content = content.replace("__FORMSPREE_ID__", formspree_id)
                print(f"已注入 Formspree ID: {formspree_id}")
                updated = True
            
            if updated:
                with open(index_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print("index.html 更新完成")
            else:
                print("index.html 中未找到需要替换的占位符，跳过。")
        except Exception as e:
            print(f"更新 index.html 失败: {e}")

if __name__ == "__main__":
    main()
