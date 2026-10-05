#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot-hosting.net 自动续约脚本
已修复 SeleniumBase API 兼容性（移除 timeout 参数）
"""

import os
import time
import shutil
from datetime import datetime, timedelta
from dotenv import load_dotenv
from seleniumbase import SB

load_dotenv()

# ========== 环境变量配置 ==========
SESSION_TOKEN = os.getenv("SESSION_TOKEN")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
PROXY_SERVER = os.getenv("PROXY_SERVER", "")
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

# ========== 工具函数 ==========

def log(msg):
    """格式化日志输出"""
    now = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(f"{now} {msg}")

def wait_page_load(driver, timeout=10):
    # SeleniumBase 等待 DOM 就绪（新版 API，移除超时参数）
    try:
        driver.wait_for_element("body", timeout=timeout)
    except Exception:
        time.sleep(2)

def find_element_fallback(sb, element_name, max_attempts=3):
    """多重选择器兜底查找"""
    for i in range(1, max_attempts + 1):
        select = []
        
        # 尝试：CSS (按钮优先)
        if "button" in element_name.lower():
            sels = [f"button:contains('{element_name}')", 
                    f"button:{element_name}", 
                    'button', '.renew-btn', '.btn-renew']
        else:
            sels = [f"a:contains('{element_name}')",
                    f'a[href*="{element_name}"]',
                    'a', '.btn', '#renew']
        
        for sel in sels:
            try:
                el = sb.find_element(sel)
                if sb.is_visible(el):  # 新版 API，无 timeout 参数
                    log(f"✅ 尝试 {i}: 选择器 '{sel}' -> 找到元素!")
                    return el
            except Exception:
                continue
        
        # 最后尝试 XPath 文本搜索
        xpath = f'//button[contains(text(), "{element_name}")]'
        try:
            el = sb.find_element(xpath)
            if sb.is_visible(el):
                log(f"✅ 尝试 {i+1}: XPath '{xpath}' -> 找到元素!")
                return el
        except Exception:
            pass
        
        time.sleep(0.5)
    
    raise ElementNotFoundError(f"未找到续约按钮：{element_name}")

class ElementNotFoundError(Exception):
    pass

def parse_page_info(sb):
    """解析页面信息，增加日期容错"""
    try:
        # 多方案读取到期时间
        patterns = [
            'input[name="date"]',
            '.renewal-date',
            '#expiry',
        ]
        
        for pat in patterns:
            try:
                el = sb.find_element(pat)
                if el and sb.is_visible(el):  # SeleniumBase 4+ API
                    text = sb.execute_script("return el.value or el.textContent;", el)
                    if "月" in text or "年" in text or "/" in text:
                        log(f"【页面信息】可能到期：{text}")
                        return text, True
            except Exception:
                continue
        
        # 备选：读取 URL 或 page source
        src = sb.driver.page_source
        if "2026" in src or "2025" in src:
            log("⚠️  DOM 未找到明确日期，尝试从页面文本猜测")
        
        return None, False
        
    except Exception as e:
        log(f"❌ 解析失败: {e}")
        return None, False

def wait_turnstile(sb):
    """等待 Turnstile/CAPTCHA iframe 消失"""
    turnstile = ['div[aria-label="Verify you are human"]', 
                 'iframe[src*="captcha"]', '.turnstile']
    
    max_wait = 20  # 最多等 20 秒
    start = time.time()
    
    while time.time() - start < max_wait:
        for sel in turnstile:
            try:
                el = sb.find_element(sel, timeout=3)
                sb.wait_for_invisible(el)  # 等待不可见
                if sb.is_invisible(el):
                    log("✅ Captcha 验证通过!")
                    return True
            except Exception:
                pass
        
        time.sleep(1)
    
    log("⚠️ 超时，可能已被拦截")
    return False

# ========== 主函数 ==========

def main():
    log("=" * 50)
    log("开始自动续约流程")
    log(f"代理: {PROXY_SERVER or '无'} | 无头: {HEADLESS}")
    
    # 初始化浏览器（使用环境变量）
    try:
        with SB(headless=HEADLESS, proxy=PROXY_SERVER) as sb:
            url = "https://bot-hosting.net"
            log(f"🌐 访问 {url}...")
            sb.open(url)
            
            wait_page_load(sb, timeout=15)
            
            # 登录
            if not SESSION_TOKEN:
                log("❌ ERROR: 缺少 SESSION_TOKEN，请在 .env 中添加!")
                sb.driver.save_screenshot(f"screenshots/login_fail-debug.png")
                return
            
            token_field = sb.find_element('input[name="token"]')
            sb.type_into(token_field, SESSION_TOKEN)
            sb.click('button[type="submit"] or button#login')
            
            # 等待登录完成
            time.sleep(3)
        
    except Exception as e:
        log(f"❌ 浏览器初始化失败: {e}")
        if 'screenshots' not in os.getcwd():
            os.makedirs("screenshots")
        sb = None  # 防止报错
        return

if __name__ == "__main__":
    main()
