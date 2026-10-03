#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot-hosting.net 免费档自动续约脚本（GitHub Actions 版）
修复：到达续约窗口执行完流程后提示【续约结果未知】实际并未续约问题
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
    except Exception as e:
        log(f"Telegram 通知发送失败：{e}")


def save_debug_screenshot(sb, name: str):
    """保存调试截图，方便排错"""
    try:
        filename = f"{name}-debug.png"
        sb.save_screenshot(filename)
        log(f"已保存调试截图：{filename}")
    except Exception:
        pass


def read_expiry(html: str):
    """【优化正则】从账单页 HTML 里抓到期日期，增强容错"""
    # 匹配 expires / valid until 后面日期
    patterns = [
        r"expires[^0-9]{0,30}(\d{2,4}[/-]\d{1,2}[/-]\d{2,4})",
        r"until[^0-9]{0,30}(\d{2,4}[/-]\d{1,2}[/-]\d{2,4})",
        r"(\d{2,4}[/-]\d{1,2}[/-]\d{2,4})[^0-9a-z]{1,10}renew",
    ]
    for pat in patterns:
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1)
    return None


def read_countdown(html: str):
    """抓 'Renew in 95:59:59' 里的倒计时；有倒计时说明还没到续约时间。"""
    m = re.search(r"Renew in (\d{1,3}:\d{2}:\d{2})", html, re.I)
    return m.group(1) if m else None


def wait_turnstile(sb, timeout: int = 45) -> bool:
    """【增大超时】等待 Cloudflare 验证弹窗消失"""
    bad_phrases = ["verify you are human", "just a moment", "confirm you are human", "turnstile"]
    end = time.time() + timeout
    while time.time() < end:
        src = sb.get_page_source().lower()
        if not any(b in src for b in bad_phrases):
            return True
        time.sleep(1.2)
    return False


def report_cookie(sb) -> None:
    """打码输出cookie，日志不泄露完整密钥"""
    try:
        for c in sb.get_cookies():
            if c.get("name") == "session_token":
                v = c["value"]
                log(f"当前 session_token（已打码）：{v[:4]}...{v[-4:]}")
                return
    except Exception:
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
        # 1 注入登录cookie
        sb.open(BASE_URL + "/")
        sb.wait_for_ready_state_complete()
        sb.sleep(2)
        cookie_list = {
            "session_token": SESSION_TOKEN,
            "login": "true",
            "theme": "system",
        }
        for name, value in cookie_list.items():
            if value:
                sb.add_cookie({"name": name, "value": value, "domain": "bot-hosting.net"})

        # 2 打开账单页面
        sb.open(BILLING_URL)
        sb.wait_for_ready_state_complete()
        sb.sleep(3)
        current_url = sb.get_current_url()
        if "/login" in current_url or "error=" in current_url:
            log(f"登录态失效，重定向：{current_url}")
            notify(
                "❌ bot-hosting 续约失败：session_token 已失效。\n"
                "浏览器Discord重新登录bot-hosting.net，F12复制新session_token更新Secret。"
            )
            save_debug_screenshot(sb, "login_fail")
            sys.exit(2)

        html_before = sb.get_page_source()
        expire_before = read_expiry(html_before)
        log(f"【续约前】到期日期：{expire_before or '未识别'}")

        countdown_before = read_countdown(html_before)
        if countdown_before:
            log(f"⏳未到续约时间，倒计时 {countdown_before}")
            notify(f"⏳ bot-hosting 未到续约时间，倒计时 {countdown_before}（到期 {expire_before or '?'}）")
            report_cookie(sb)
            return

        # 3 定位 Renew 按钮
        renew_sels = [
            'button:contains("Renew")',
            'a:contains("Renew")',
            '[class*="renew"]',
            '[class*="Renew"]',
        ]
        renew_selector = None
        for sel in renew_sels:
            try:
                if sb.is_element_visible(sel, timeout=3):
                    btn_text = sb.get_text(sel).strip()
                    if "renew in" in btn_text.lower():
                        log("按钮还显示倒计时，暂不可续约")
                        notify(f"⏳ bot-hosting 未到续约时间（到期 {expire_before or '?'}）")
                        report_cookie(sb)
                        return
                    renew_selector = sel
                    log(f"✅ 找到续约按钮，文本：{btn_text}")
                    break
            except Exception:
                continue

        if not renew_selector:
            log("❌ 找不到续约按钮")
            notify(f"⚠️ bot-hosting 未找到续约按钮，请手动检查（到期 {expire_before or '?'}）")
            save_debug_screenshot(sb, "no_renew_btn")
            report_cookie(sb)
            return

        # 4 点击续约，弹出人机验证弹窗
        sb.sleep(2)
        sb.click(renew_selector)
        sb.sleep(5)
        save_debug_screenshot(sb, "after_click_renew")

        # 多次尝试过Turnstile验证
        captcha_ok = False
        for attempt in range(1, 4):
            log(f"尝试通过人机验证 {attempt}/3")
            try:
                sb.uc_gui_click_captcha(timeout=12)
            except Exception as e:
                log(f"验证码点击异常：{str(e)}")
            if wait_turnstile(sb, timeout=40):
                captcha_ok = True
                log("✅ Cloudflare 人机验证已通过")
                break
            sb.sleep(2)

        if not captcha_ok:
            log("❌ Cloudflare Turnstile验证失败")
            notify(
                "❌ bot-hosting 续约失败：Cloudflare人机验证未通过。\n"
                "GitHub机房IP容易被拦截，配置住宅代理PROXY_SERVER或者本地运行脚本。"
            )
            save_debug_screenshot(sb, "captcha_fail")
            report_cookie(sb)
            sys.exit(3)

        sb.sleep(3)
        save_debug_screenshot(sb, "captcha_passed")

        # 5 点击确认续约按钮【调整选择器顺序，优先 "Renew for 4 days"】
        confirm_sels = [
            'button:contains("Renew for 4 days")',
            'button:contains("Renew")',
            'button:contains("Confirm")',
        ]
        confirm_clicked = False
        for sel in confirm_sels:
            try:
                if sb.is_element_visible(sel, timeout=5):
                    sb.click(sel)
                    log(f"✅ 点击确认续约按钮 {sel}")
                    confirm_clicked = True
                    break
            except Exception:
                continue

        if not confirm_clicked:
            log("⚠️ 没有找到确认续约按钮！")
            notify("❌ bot-hosting：找不到确认续约按钮，续约中断，请检查页面。")
            save_debug_screenshot(sb, "no_confirm_btn")
            report_cookie(sb)
            sys.exit(4)

        # ==========【关键修复】续约提交后刷新页面+拉长等待时间，等待后端生效 ==========
        log("等待续约请求提交生效，等待12秒...")
        sb.sleep(12)
        sb.refresh()  # 强制刷新账单页面拿最新状态，非常关键！
        sb.wait_for_ready_state_complete()
        sb.sleep(4)

        save_debug_screenshot(sb, "after_renew_refresh")
        html_after = sb.get_page_source()
        expire_after = read_expiry(html_after)
        cd_after = read_countdown(html_after)

        log(f"【续约后】到期日期：{expire_after or '未识别'}，倒计时：{cd_after or '无'}")
        report_cookie(sb)

        # 【优化结果判定逻辑】
        success_flag = False
        # 条件1：出现Renew in倒计时
        if cd_after:
            success_flag = True
        # 条件2：到期时间发生变化
        elif expire_before and expire_after and (expire_after != expire_before):
            success_flag = True
        # 兜底：如果识别不到倒计时，但到期时间为空，给警告而不是直接判定未知
        if success_flag:
            log(f"✅ 续约成功。新到期：{expire_after or '（页面查看）'}，下次倒计时：{cd_after or '约4天后'}")
            notify(
                "✅ bot-hosting 续约成功\n"
                f"到期：{expire_after or '（后台页面查看）'}\n"
                f"下次可续：{cd_after or '约 4 天后'}"
            )
        else:
            # 区分两种情况：完全没变 / 解析失败
            log(f"⚠️ 续约状态不确定。旧到期={expire_before},新到期={expire_after},cd={cd_after}")
            notify(
                "⚠️ bot-hosting 续约状态不确定！\n"
                f"旧到期：{expire_before or '?'} \n"
                f"新到期：{expire_after or '解析不到'}\n"
                "请登录后台确认实例是否续期成功！截图已生成。"
            )
            sys.exit(5)


if __name__ == "__main__":
    main()
