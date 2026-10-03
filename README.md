ot-hosting.net 免费档自动续约脚本（GitHub Actions 版）

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
