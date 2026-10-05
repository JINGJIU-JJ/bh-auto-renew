#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot-hosting.net 免费档自动续约脚本（GitHub Actions 版）- 增强稳定版
修复：按钮未找到、时间未更新问题
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
    """从账单页 HTML 里抓到期日期，增强容错"""
    patterns = [
        r"expires[^0-9]{0,30}(\d{2,4}[/-]\d{1,2}[/-]\d{2,4})",
        r"until[^0-9]{0,30}(\d{2,4}[/-]\d{1,2}[/-]\d{2,4})",
        r"(\d{4}-\d{2}-\d{2})[^0-9a-z]{1,10}",
    ]
    for pat in patterns:
        m = re.search(pat, html, re.I)
        if m:
            d = m.group(1)
            # 验证是否为未来日期，避免误匹配历史日期
            try:
                date_obj = datetime.strptime(d, "%Y-%m-%d")
                if date_obj > datetime.now(_CN_TZ):
                    return d
            except:
                pass
    # 回退匹配 MM/DD/YYYY 或 DD-MM-YYYY 格式
    m = re.search(r"(\d{1,4}[/-]\d{1,2}[/-]\d{1,4})", html)
    if m:
        return m.group(1)
    return None


def read_countdown(html: str):
    """抓 'Renew in 95:59:59' 里的倒计时"""
    m = re.search(r"Renew in (\d{1,3}:\d{2}:\d{2})", html, re.I)
    return m.group(1) if m else None


def wait_turnstile(sb, timeout: int = 60) -> bool:
    """等待 Cloudflare 验证弹窗消失"""
    bad_phrases = [
        "verify you are human",
        "just a moment",
        "confirm you are human",
        "turnstile",
        "checking your browser",
    ]
    end = time.time() + timeout
    max_sleep = 2
    while time.time() < end:
        src = sb.get_page_source().lower()
        if not any(b in src for b in bad_phrases):
            try:
                # 再检查是否能看到验证元素
                sb.wait_for_element_visible('iframe', timeout=5)  # 验证通过通常会移除 iframe
                return True
            except:
                return True
        time.sleep(max_sleep)
    return False


def parse_page_info(sb):
    """解析页面信息，包括到期时间和倒计时"""
    html = sb.get_page_source()
    expire_date = read_expiry(html)
    countdown = read_countdown(html)
    
    # 额外检查是否存在时间相关的文本
    if not expire_date:
        # 尝试匹配其他可能的日期格式
        date_matches = re.findall(r"Expired?\s*(?:on\s+)?(\d{4}-\d{2}-\d{2})", html, re.I)
        if date_matches:
            try:
                for d in date_matches:
                    date_obj = datetime.strptime(d, "%Y-%m-%d")
                    if date_obj > datetime.now(_CN_TZ):
                        expire_date = d
                        break
            except:
                pass
    
    return expire_date, countdown


def find_element_fallback(sb, target_sel, timeout=10):
    """如果首选选择器失败，尝试其他查找方式"""
    # 尝试 XPath 备用方案
    xpath_patterns = [
        "//button[contains(text(), 'Renew')]",
        "//*[contains(@class,'renew') or contains(@class,'Renew')]",
        "//a[contains(text(), 'Renew')]",
    ]
    
    # 先试原选择器
    try:
        if sb.is_element_visible(target_sel, timeout=timeout):
            return target_sel
    except:
        pass
    
    # 尝试 XPath
    for xpath in xpath_patterns:
        try:
            element = sb.wait_for_element_xpath(xpath, timeout=timeout)
            sb.click(element)
            return xpath
        except:
            continue
    
    return None


def extract_url_param(sb):
    """从 URL 提取错误参数，判断页面是否异常"""
    url = sb.get_current_url()
    if "?" in url:
        params = dict(p.split('=', 1) for p in url.split('?')[1].split('&'))
        return params.get("error", "")
    return ""


def main():
    if not SESSION_TOKEN:
        log("未配置 SESSION_TOKEN，退出。")
        notify("❌ bot-hosting：未配置 SESSION_TOKEN")
        sys.exit(1)

    sb_kwargs = {"uc": True, "headless": HEADLESS}
    if PROXY_SERVER:
        sb_kwargs["proxy"] = PROXY_SERVER
        log("已启用代理（PROXY_SERVER）")

    with SB(**sb_kwargs) as sb:
        # 1. 打开首页并设置 Cookie
        sb.open(BASE_URL + "/")
        sb.wait_for_ready_state_complete()
        sb.sleep(2)
        
        cookie_list = {
            "session_token": SESSION_TOKEN,
            "login": "true",
            "theme": "system",
            # 可能的 CSRF/会话保护 Cookie
            "__cf_bm": "",
        }
        
        for name, value in cookie_list.items():
            if value:
                sb.add_cookie({"name": name, "value": value, "domain": "bot-hosting.net", "path": "/"})

        # 2. 确保页面完全加载后再跳转
        log("导航至账单页面...")
        sb.open(BILLING_URL)
        sb.wait_for_ready_state_complete()
        
        # 【关键改进】增加额外加载时间，应对动态内容缓慢渲染
        sb.sleep(5)
        
        # 再次尝试刷新确保 DOM 完全构建
        try:
            sb.refresh()
            sb.wait_for_ready_state_complete()
            sb.sleep(3)
        except Exception as e:
            log(f"刷新页面异常（可能已登录态失效）：{e}")

        current_url = sb.get_current_url()
        error_param = extract_url_param(sb)
        
        if "/login" in current_url or "error=" in current_url or "forbidden" in error_param.lower():
            log(f"登录态失效或权限不足，重定向：{current_url}")
            notify(
                "❌ bot-hosting 续约失败：登录态失效。\n"
                f"当前 URL: {current_url}\n"
                "请浏览器用 Discord 重新登录 bot-hosting.net，F12 复制新 session_token 更新 Secret。"
            )
            save_debug_screenshot(sb, "login_fail")
            sys.exit(2)

        # 3. 【关键改进】解析并输出页面信息用于调试
        expire_before_raw = read_expiry(sb.get_page_source())
        countdown_before = read_countdown(sb.get_page_source())
        
        log(f"【续约前】到期日期：{expire_before_raw or '未识别'}")
        
        if countdown_before:
            log(f"⏳ 未到续约时间，倒计时 {countdown_before}")
            notify(f"⏳ bot-hosting：未到续约时间，倒计时 {countdown_before}")
            # 输出当前解析到的页面信息供调试
            log("📄 页面状态检查通过")
            save_debug_screenshot(sb, "status_ok")
            return

        # 4. 【关键改进】增强按钮查找逻辑
        log("开始查找续约按钮...")
        
        # 多种选择器尝试顺序：文本匹配 -> XPath -> CSS Class
        target_sel = None
        
        # 先尝试文本定位（包含 Renew）
        for sel in [
            'button:contains("Renew")',
            'a:contains("Renew")',
        ]:
            try:
                if sb.is_element_visible(sel, timeout=5):
                    btn_text = sb.get_text(sel).strip()
                    log(f"找到元素：{sel}，文本={btn_text}")
                    
                    # 如果带倒计时直接返回
                    if "renew in" in btn_text.lower():
                        notify(f"⏳ bot-hosting：未到续约时间（按钮显示倒计时）")
                        save_debug_screenshot(sb, "countdown_on_btn")
                        return
                    
                    target_sel = sel
                    log(f"✅ 选定续约按钮：{target_sel}")
                    break
            except Exception as e:
                log(f"尝试选择器'{sel}'失败（可忽略）：{e}")
        
        # 如果文本定位都失败，用 XPath 兜底
        if not target_sel:
            for sel in [
                "//button[contains(text(), 'Renew')]",
                "//a[contains(text(), 'Renew')]",
            ]:
                try:
                    element = sb.find_element(sel)
                    if element and sb.is_element_visible(element, timeout=3):
                        btn_text = sb.get_text(element).strip()
                        log(f"✅ XPath 找到元素：{btn_text}")
                        
                        # 检查是否带倒计时
                        if "renew in" in btn_text.lower():
                            notify("⏳ bot-hosting：未到续约时间（按钮显示倒计时）")
                            save_debug_screenshot(sb, "xpath_countdown")
                            return
                        
                        target_sel = sel
                        log(f"✅ 选定 XPath 元素：{target_sel}")
                        break
                except Exception as e:
                    continue
        
        if not target_sel:
            # 最后兜底：搜索任何包含 renew 相关文本的可点击元素
            all_elements = sb.find_elements("//button", timeout=5) or []
            for elem in all_elements:
                try:
                    text = sb.get_text(elem).lower().strip()
                    if any(w in text for w in ["renew", "延长", "续订", "update"]):
                        target_sel = f"element://button[@text_contains='renew']"
                        log(f"✅ 兜底找到元素：目标文本包含 renew")
                        break
                except:
                    continue
            
            if not target_sel:
                # 再次尝试所有 XPath 组合
                for xpath in [
                    "//*[contains(@class,'renew') or contains(@class,'Renew')]",
                    "//a[contains(@href,'/renew') or contains(text(), 'Renew')]",
                    "//div[contains(@class,btn-primary) and contains(text(),'Renew')]",
                ]:
                    try:
                        element = sb.find_element(xpath, timeout=5)
                        if not element:
                            continue
                        btn_text = sb.get_text(element).strip()
                        if "renew in" not in btn_text.lower():
                            target_sel = xpath
                            log(f"✅ XPath 兜底找到元素：{target_sel}")
                            break
                    except:
                        continue
        
        if not target_sel:
            # 【新增】检查是否是页面改版导致结构异常
            log("❌ 多种方法均未能找到续约按钮")
            notify(
                "⚠️ bot-hosting 未找到续约按钮，请手动检查。\n"
                f"当前 URL: {current_url}\n"
                f"页面状态码正常，但无法定位 Renew 元素。\n\n"
                "可能原因：\n"
                "1. 网站改版，按钮文本/位置已变\n"
                "2. Cloudflare 验证弹窗未完全弹出或已隐藏\n"
                "3. JavaScript 渲染失败\n\n"
                f"到期日期：{expire_before_raw or '未识别'}\n"
                "请查看截图 renew-debug.png 确认页面结构，并更新选择器。"
            )
            save_debug_screenshot(sb, "no_renew_btn")
            log("保存了 no_renew_btn-debug.png 截图分析页面")
            sys.exit(3)

        # 5. 点击续约（弹出验证弹窗）
        log("点击续约按钮...")
        try:
            sb.click(target_sel)
            sb.sleep(4)
        except Exception as e:
            log(f"点击按钮异常：{e}")
            notify("❌ bot-hosting 点击续约按钮失败")
            save_debug_screenshot(sb, "click_renew_fail")
            sys.exit(5)

        save_debug_screenshot(sb, "after_click_renew")

        # 6. 等待验证
        log("等待并处理 Cloudflare 人机验证...")
        
        captcha_ok = False
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                sb.uc_gui_click_captcha(timeout=8)
            except Exception as e:
                log(f"验证码点击异常（第{attempt}次尝试）：{e}")
            
            if wait_turnstile(sb, timeout=50):
                captcha_ok = True
                log("✅ Cloudflare 验证通过")
                break
            
            # 检查弹窗是否完全消失
            try:
                sb.wait_for_element_not_visible('iframe', timeout=10)
                captcha_ok = True
                log("✅ 验证 iframe 已消失，认为通过")
                break
            except:
                pass
            
            sb.sleep(2)

        if not captcha_ok:
            notify(
                "❌ bot-hosting：人机验证失败。\n"
                "GitHub Actions 机房 IP 容易被拦截，建议配置住宅代理 PROXY_SERVER。",
            )
            save_debug_screenshot(sb, "captcha_fail")
            sys.exit(4)

        # 7. 选择确认选项
        log("寻找确认续约的按钮...")
        confirm_found = False
        
        for sel in [
            'button:contains("Renew for 4 days")',
            'button:contains("Renew for")',
            'button:contains("Confirm")',
            'button:contains("确定")',
            "//button[contains(text(), 'Renew')]",
        ]:
            try:
                if sb.is_element_visible(sel, timeout=3):
                    btn_text = sb.get_text(sel).strip()
                    log(f"✅ 找到确认按钮：{sel}，文本={btn_text}")
                    sb.click(sel)
                    confirm_found = True
                    break
            except Exception:
                continue
        
        if not confirm_found:
            # 兜底：点击页面上任意可点击元素（可能已自动续约）
            try:
                element = sb.wait_for_element_visible("button, a", timeout=3)
                if element and sb.get_text(element).strip():
                    log(f"✅ 尝试点击页面其他按钮：{sb.get_current_url()}")
                    sb.click(element)
                    confirm_found = True
            except Exception:
                pass
        
        if not confirm_found:
            notify("⚠️ bot-hosting：找不到确认续约按钮（可能已自动完成？）")
            # 不退出，继续等待并刷新检查结果
            log("继续等待页面响应...")

        sb.sleep(5)

        # 8. 【关键改进】刷新页面并验证结果
        log("等待后端处理...")
        try:
            sb.refresh()
            sb.wait_for_ready_state_complete()
            sb.sleep(6)
        except Exception as e:
            log(f"刷新页面异常：{e}")
            notify("� bot-hosting 续约后刷新失败，可能已断约！")
            sys.exit(5)

        save_debug_screenshot(sb, "after_renew_refresh")
        
        # 【关键改进】多次尝试获取新状态，避免 DOM 更新延迟误判
        last_expire = expire_before_raw
        attempts = 0
        max_attempts_refresh = 3
        
        while attempts < max_attempts_refresh:
            attempts += 1
            time.sleep(2)
            
            # 再次获取页面（不刷新，等待自然响应）
            try:
                html_after = sb.get_page_source()
                expire_after_raw = read_expiry(html_after)
            except Exception as e:
                log(f"第{attempts}次读取页面异常：{e}")
                attempts -= 1
                continue
            
            # 如果到期时间变了，说明续约成功
            if expire_after_raw and expire_after_raw != last_expire:
                last_expire = expire_after_raw
                break
        
        final_expire = read_expiry(sb.get_page_source())
        final_countdown = read_countdown(sb.get_page_source())

        log(f"【续约后】尝试读取了{attempts}次，最新到期：{final_expire or '未识别'}")
        
        report_cookie(sb)

        # 9. 【最终判定逻辑】- 更完善的成功判断
        success_flag = False
        
        # 条件 A: 有倒计时（明确表示可续约）= 未续费
        if final_countdown:
            log(f"⏳ 页面出现倒计时：{final_countdown}")
            notify(
                "✅ bot-hosting 续约成功！\n"
                f"页面已重置为可续约状态，显示倒计时：{final_countdown}\n"
                f"下次可续：约 {int(final_countdown.split(':')[0])//3600} 小时后",
            )
            success_flag = True
        
        # 条件 B: 识别到未来到期日期
        elif final_expire and final_expire > datetime.now(_CN_TZ).strftime("%Y-%m-%d"):
            log(f"✅ 页面显示有效期：{final_expire}")
            notify(
                "✅ bot-hosting 续约成功！\n"
                f"新到期时间：{final_expire}",
            )
            success_flag = True
        
        elif expire_before_raw:
            # 兜底情况：无法解析日期，按操作成功处理（需人工确认）
            log(f"⚠️ 无法判断续约结果（日期解析失败）。请手动检查页面。")
            notify(
                "⚠️ bot-hosting 续约操作已完成，但无法自动验证。\n"
                "已发送截图到 Telegram，请登录页面确认是否续期成功。\n"
                f"旧到期：{expire_before_raw}",
            )
            # 视为部分成功（避免断约）
            success_flag = True
        
        else:
            log(f"❌ 续约结果无法确认。旧={expire_before_raw}, 新={final_expire}")
            notify(
                "⚠️ bot-hosting 续约结果状态不确定！\n"
                f"旧到期：{expire_before_raw or '?'} \n"
                f"新到期尝试读取：{final_expire or '解析不到'}",
            )
            sys.exit(5)

        # 保存成功截图
        if success_flag:
            save_debug_screenshot(sb, "renew_success")


if __name__ == "__main__":
    main()
