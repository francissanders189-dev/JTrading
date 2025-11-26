# JTrading - 红利低波ETF (512890) RSI 自动监控

基于 GitHub Actions 的轻量级 ETF 监控工具。无需服务器，每天自动检查 RSI 指标，触发条件时通过邮件和微信推送提醒，并生成静态状态页面。

## ✨ 功能特性

- **自动监控**: 利用 GitHub Actions 定时运行 (每天 10:00 和 14:00)。
- **多渠道通知**:
    - **邮件**: 发送包含详细数据、颜色区分的 HTML 格式邮件。
    - **微信**: 通过 Server酱推送即时消息。
- **静态看板**: 自动部署 GitHub Pages，随时查看最新 RSI 和价格状态。
- **完全免费**: 依赖 GitHub 免费资源，零成本运行。

## 🚀 快速部署指南

### 1. Fork 项目
点击右上角 **Fork** 按钮，将仓库复制到您的 GitHub 账号下。

### 2. 配置敏感信息 (Secrets)
进入仓库的 **Settings** -> **Secrets and variables** -> **Actions** -> **Secrets** 标签页，点击 **New repository secret** 添加：

| Secret 名称 | 必填 | 说明 | 示例 |
| :--- | :--- | :--- | :--- |
| `SENDER_EMAIL` | ✅ | 发件人邮箱 (默认配置支持126邮箱) | `example@126.com` |
| `SENDER_PASSWORD` | ✅ | 邮箱 SMTP 授权码 (非登录密码) | `abcdefghijklmn` |
| `SUBSCRIBER_EMAILS` | ✅ | 接收通知的邮箱 (多个用逗号分隔) | `me@qq.com,you@126.com` |
| `SERVERCHAN_KEY` | ❌ | Server酱 SendKey (用于微信通知) | `SCTxxxxxxxx` |

*注：默认 SMTP 服务器为 `smtp.126.com`。如需使用 QQ 邮箱或其他，请在 Secrets 中额外添加 `SMTP_SERVER` (如 `smtp.qq.com`) 和 `SMTP_PORT`。*

### 3. 配置阈值参数 (Variables)
进入 **Settings** -> **Secrets and variables** -> **Actions** -> **Variables** 标签页，点击 **New repository variable** 添加（可选，不添加则使用默认值）：

| Variable 名称 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `RSI_BUY_THRESHOLD` | `40` | RSI **低于** 此值时触发买入提醒 |
| `RSI_SELL_THRESHOLD` | `70` | RSI **高于** 此值时触发卖出提醒 |

### 4. 启用 GitHub Pages (查看看板)
1. 进入 **Actions** 页面，手动触发一次 "Daily RSI Check" 工作流，确保其运行成功。
2. 运行成功后，进入 **Settings** -> **Pages**。
3. 在 **Build and deployment** 下：
    *   **Source**: 选择 `Deploy from a branch`
    *   **Branch**: 选择 `gh-pages` 分支，文件夹选择 `/(root)`
4. 点击 **Save**。
5. 稍等片刻，您就可以通过 `https://<您的用户名>.github.io/JTrading/` 访问监控看板了。

## 🛠️ 技术栈

- **Python 3**: 数据抓取与逻辑处理 (`requests`, `BeautifulSoup`)
- **GitHub Actions**: 自动化定时任务调度
- **GitHub Pages**: 静态前端页面托管
- **Server酱**: 微信消息推送通道

## ⚠️ 免责声明

本项目仅供编程学习和技术交流使用，不构成任何投资建议。市场有风险，投资需谨慎。
