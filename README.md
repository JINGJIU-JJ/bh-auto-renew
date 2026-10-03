# bot-hosting.net 免费档自动续约（GitHub Actions）

免费档每 4 天要手动点一次 "Renew"，且续约按钮带 Cloudflare 人机验证，
纯 requests/curl 会被 403 拦截。本项目用 SeleniumBase 的 undetected 模式
驱动真实浏览器，在 GitHub Actions 上每天自动检查一次并续约。

## 关于登录方式（先读这段）

你提到平时用 Discord 授权登录。这里特别说明：本脚本**不使用 Discord token**。
从浏览器里抠出 Discord 账号 token 去伪造登录，违反 Discord 服务条款、有封号风险，
不建议也没有必要。

正确且更简单的做法：借一次 Discord 授权登录，拿到 bot-hosting 发给你的
`session_token` cookie，脚本复用它保持登录态即可。每次成功续约后 cookie 也会被
重新使用一次（相当于续命），通常可以稳定用几周；等它彻底失效，重新拿一次即可。

## 部署步骤

### 1. 拿到 session_token

1. 浏览器正常登录 <https://bot-hosting.net>（点 Login with Discord 完成授权）。
2. 按 `F12` 打开开发者工具 → `Application`（应用）→ 左侧 `Cookies` →
   选中 `https://bot-hosting.net`。
3. 找到名为 `session_token` 的行，双击 `Value` 并完整复制其值。

### 2. 建仓库并上传本目录

1. 在 GitHub 新建一个仓库（建议 **Private 私有**）。
2. 把本目录所有文件（含 `.github/workflows/renew.yml`）提交推送到该仓库主分支。

### 3. 配置 Secrets

仓库 `Settings` → `Secrets and variables` → `Actions` → `New repository secret`：

| Secret 名称 | 必填 | 说明 |
|---|---|---|
| `SESSION_TOKEN` | ✅ | 第 1 步复制的 cookie 值 |
| `TG_BOT_TOKEN` | ❌ | Telegram bot token，填了才推送续约结果 |
| `TG_CHAT_ID` | ❌ | Telegram chat id，需与上面同时填写 |
| `PROXY_SERVER` | ❌ | 形如 `http://user:pass@host:port` 的代理，见下方排错 |

### 4. 启用工作流并试运行

1. 仓库 `Actions` 页 → 若有 "This workflow has... workflows" 提示，点 **Allow
   workflows**。
2. 点 `bot-hosting auto renew` → **Run workflow** 手动跑一次，观察日志：
   - 输出 `✅ 续约成功` → 部署完成。
   - 输出 `⏳ 未到续约时间` → 也正常，说明当前还没到 4 天节点。
   - 报错 → 看下面排错。

之后每天早上 5:00 UTC（北京时间 13:00）自动运行，无需干预。

## 排错

**Cloudflare 验证一直不过 / 页面 403 / `Just a moment` 卡住**
GitHub Actions 的机房 IP 属于数据中心段，Cloudflare 有时会反复拦截。这是本方案
最大的不确定点，不是脚本 bug。处理办法：

1. 直接用你的个人电脑/家庭宽带重跑（本目录代码不依赖 Actions，本地装好
   Python 3.12 + `pip install -r requirements.txt`，把环境变量填上后
   `python renew.py` 即可，本地 IP 通常能过验证）。
2. 或者配一个**住宅 IP** 代理，把地址填进 `PROXY_SERVER` secret。

**`登录态失效，被重定向到 /login`**
`SESSION_TOKEN` 过期或被撤销，回到第 1 步重新复制一次。

**`未找到续约按钮`**
bot-hosting 改版了。打开 Actions 运行日志里的 `renew-debug.png` 截图，看账单页
现在的按钮文案，把 `renew.py` 里第 4 步与第 6 步的选择器对应改掉即可。

## 本地调试

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
set SESSION_TOKEN=你的值      # PowerShell 用 $env:SESSION_TOKEN="你的值"
set HEADLESS=false            # 有头模式，肉眼盯着验证过程
python renew.py
```

## 说明与风险

- 自动续约是让免费实例不被回收，属于服务提供的正常续期操作；但仍请自行确认符合
  bot-hosting 的服务条款，不要多账号批量刷取免费资源。
- Cookie 等于登录凭证，务必放在 GitHub 私有仓库的 Secrets 里，不要提交进代码。
- 本脚本按当前页面结构编写，站点改版可能需要更新选择器。
