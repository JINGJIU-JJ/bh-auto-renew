# -*- coding: utf-8 -*-
"""
Telegram 通知脚本
用于接收 GitHub Actions 的工作流状态并发送报告
使用 Telethon 或 aiohttp + Bot API 都可以
"""

import os
import asyncio
from pathlib import Path


# 如果使用 Bot API
from telegram import Bot
from telegram.utils.errors import NetworkError
