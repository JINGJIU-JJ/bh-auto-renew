# bot-hosting.net 免费档自动续约脚本 [GitHub Actions]
## 功能说明
- 每天北京时间 13:00 自动检查并续约到期服务（最多延长 4 天）
- 增强容错：多重选择器查找按钮、多次刷新读取时间
- Telegram 通知：失败/成功时发送通知

## 快速部署
### 1. 创建仓库后上传以下文件
```bash
├── renew.py              # 主脚本
├── renew.yml             # GitHub Actions 工作流
├── requirements.txt      # Python 依赖（见下方）
├── screenshots/          # 调试截图目录（会自动创建）
└── README.md
