#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot-hosting.net 免费档自动续约脚本（GitHub Actions 版）

背景
----
免费档（$0）每 4 天需要手动点一次 "Renew" 来延长，续约按钮带 Cloudflare
Turnstile 人机验证。纯 HTTP 请求（官方 API / requests）会被 Cloudflare 拦截
（对非机房 IP 直接 403），所以自动续约必须驱动一个真实浏览器。

登录方式（重要）
----------------
本脚本 **不使用** Discord 账号 token（提取 token 会违反 Discord 服务条款，
有封号风险）。正确做法：你在浏览器里正常用 "Login with Discord" 登录一次，
F12 打开开发者工具 -> Application -> Cookies，复制 bot-hosting.net 的
`session_token` cookie 值，填到 GitHub 仓库的 Secret 里。脚本每次成功续约后
会把这个 cookie 重新使用一次，相当于把它续命，可长期复用。当 cookie 彻底过期
（通常几周）时，重新登录拿一次新的即可。

环境变量（GitHub: Settings -> Secrets and variables -> Actions -> New secret）
--------------------------------------------------------------------------
  SESSION_TOKEN   必填   bot-hosting.net 的 session_token cookie 值
  TG_BOT_TOKEN    可选   Telegram bot token，配置后推送续约结果通知
  TG_CHAT_ID      可选   Telegram chat id，需与 TG_BOT_TOKEN 同时填写
  PROXY_SERVER    可选   形如 http://user:pass@host:port 的代理；GitHub 机房 IP
                         被 Cloudflare 反复拦截时，换一个住宅 IP 代理再填这里
  HEADLESS        可选   true/false，默认 true（Actions 无界面运行）
"""

import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from seleniumbase import SB

BASE_URL = "https://bot-hosting.net"
BILLING_URL = f"{BASE_URL}/a/billings"

SESSION_TOKEN = os.environ.get("SESSION_TOKEN", "").strip()
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
PROXY_SERVER = os.environ.get("PROXY_SERVER", "").strip()
HEADLESS = os.environ.get("HEADLESS", "true").strip().lower() != "false"

_CN_TZ = timezone(timedelta(hours=8))


def log(msg: str) -> None:
    now = datetime.now(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


def notify(text: str) -> None:
    """配置了 TG 才发通知，否则只打日志。"""
    if not (TG_BOT_TOKEN and TG_CHAT_ID):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": text},
            timeout=10,
        )
    except Exception as e:  # noqa: BLE001
        log(f"Telegram 通知发送失败：{e}")


def read_expiry(html: str):
    """从账单页 HTML 里抓到期日期，兼容 2026/10/05 与 10/05/2026 两种写法。"""
    m = re.search(r"expires[^0-9]{0,20}(\d{2,4}[/-]\d{2}[/-]\d{2,4})", html, re.I)
    if m:
        return m.group(1)
    m = re.search(r"(\d{2,4}[/-]\d{2}[/-]\d{2,4})[^0-9a-z]{1,6}renew", html, re.I)
    return m.group(1) if m else None


def read_countdown(html: str):
    """抓 'Renew in 95:59:59' 里的倒计时；有倒计时说明还没到续约时间。"""
    m = re.search(r"Renew in (\d{1,3}:\d{2}:\d{2})", html, re.I)
    return m.group(1) if m else None


def wait_turnstile(sb, timeout: int = 30) -> bool:
    """等 Cloudflare 验证通过：页面不再出现 'verify you are human / just a moment'。"""
    bad = ["verify you are human", "just a moment", "确认您是真人", "troubleshoot this"]
    end = time.time() + timeout
    while time.time() < end:
        src = sb.get_page_source().lower()
        if not any(b in src for b in bad):
            return True
        time.sleep(1)
    return False


def report_cookie(sb) -> None:
    """把当前 session_token 打码打印，便于确认 cookie 仍在有效期内（日志不暴露完整值）。"""
    try:
        for c in sb.get_cookies():
            if c.get("name") == "session_token":
                v = c["value"]
                log(f"当前 session_token（已打码）：{v[:4]}...{v[-4:]}")
                return
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    if not SESSION_TOKEN:
        log("未配置 SESSION_TOKEN，退出。")
        notify("❌ bot-hosting 续约失败：未配置 SESSION_TOKEN")
        sys.exit(1)

    sb_kwargs = {"uc": True, "headless": HEADLESS}
    if PROXY_SERVER:
        sb_kwargs["proxy"] = PROXY_SERVER
        log("已启用代理（PROXY_SERVER）")

    with SB(**sb_kwargs) as sb:
        # 1) 先开首页建立 cookie 作用域，再注入登录 cookie
        sb.open(BASE_URL + "/")
        sb.wait_for_ready_state_complete()
        sb.sleep(2)
        for name, value in {
            "session_token": SESSION_TOKEN,
            "login": "true",
            "theme": "system",
        }.items():
            if value:
                sb.add_cookie({"name": name, "value": value, "domain": "bot-hosting.net"})

        # 2) 进入账单页
        sb.open(BILLING_URL)
        sb.wait_for_ready_state_complete()
        sb.sleep(3)
        url = sb.get_current_url()
        if "/login" in url or "error=" in url:
            log(f"登录态失效，被重定向到：{url}")
            notify(
                "❌ bot-hosting 续约失败：session_token 已失效。\n"
                "请在浏览器用 Discord 重新登录 bot-hosting.net，"
                "F12 -> Application -> Cookies 复制新的 session_token 更新到 Secret。"
            )
            sys.exit(2)

        html = sb.get_page_source()
        current_expiry = read_expiry(html)
        log(f"当前到期日期：{current_expiry or '未识别'}")

        # 3) 还没到续约时间就直接退出（每天跑一次，靠这里判断"今天该不该续"）
        countdown = read_countdown(html)
        if countdown:
            log(f"未到续约时间，倒计时 {countdown}")
            notify(f"⏳ bot-hosting 未到续约时间，倒计时 {countdown}（到期 {current_expiry or '?'}）")
            report_cookie(sb)
            return

        # 4) 找可点击的续约按钮
        outer = None
        for sel in [
            'button:contains("Renew")',
            'a:contains("Renew")',
            '[class*="renew"]',
            '[class*="Renew"]',
        ]:
            try:
                if sb.is_element_visible(sel):
                    txt = sb.get_text(sel)
                    if "Renew in" in txt:
                        countdown = txt.strip()
                        break
                    if "renew" in txt.lower():
                        outer = sel
                        log(f"发现续约按钮：{txt!r}")
                        break
            except Exception:  # noqa: BLE001
                pass

        if not outer:
            if countdown:
                log("未到续约时间（按钮显示倒计时）")
                notify(f"⏳ bot-hosting 未到续约时间（到期 {current_expiry or '?'}）")
            else:
                log("未找到续约按钮，状态未知。")
                notify(f"⚠️ bot-hosting 未找到续约按钮，请手动检查（到期 {current_expiry or '?'}）")
            report_cookie(sb)
            return

        # 5) 点续约 -> 弹窗里的 Turnstile
        sb.sleep(2)
        sb.click(outer)
        sb.sleep(8)

        passed = False
        for attempt in range(1, 4):
            try:
                sb.uc_gui_click_captcha()
                time.sleep(10)
            except Exception as e:  # noqa: BLE001
                log(f"第 {attempt} 次点击 Turnstile 出错：{e}")
            if wait_turnstile(sb, timeout=25):
                passed = True
                break
            log(f"第 {attempt} 次验证未通过，重试…")

        if not passed:
            log("Cloudflare Turnstile 验证未通过。")
            notify(
                "❌ bot-hosting 续约失败：Cloudflare 人机验证未通过。\n"
                "GitHub 机房 IP 可能被拦，建议配置 PROXY_SERVER 换住宅 IP 后重跑。"
            )
            report_cookie(sb)
            sys.exit(3)

        # 6) 点确认续约
        sb.sleep(3)
        for sel in [
            'button:contains("Renew for 4 days")',
            'button:contains("Confirm")',
            'button:contains("Renew")',
        ]:
            try:
                if sb.is_element_visible(sel):
                    sb.click(sel, timeout=8)
                    log(f"点击确认：{sel}")
                    break
            except Exception:  # noqa: BLE001
                pass
        sb.sleep(6)

        # 7) 校验续约结果
        new_html = sb.get_page_source()
        new_expiry = read_expiry(new_html)
        new_cd = read_countdown(new_html)
        if new_cd or (new_expiry and new_expiry != current_expiry):
            log(f"✅ 续约成功。新到期：{new_expiry or '（见页面）'}，下次倒计时：{new_cd or '（见页面）'}")
            notify(
                "✅ bot-hosting 续约成功\n"
                f"到期：{new_expiry or '（见页面）'}\n"
                f"下次可续：{new_cd or '约 4 天后'}"
            )
        else:
            log("⚠️ 续约结果未确认，请登录后台检查。")
            notify(f"⚠️ bot-hosting 续约结果未知，请手动检查（到期 {new_expiry or current_expiry or '?'}）")
        report_cookie(sb)


if __name__ == "__main__":
    main()
