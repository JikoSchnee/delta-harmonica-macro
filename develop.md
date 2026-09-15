# Harmonica Deck 开发与维护指南

本文件面向开发者、部署维护者和曲库审核者。普通用户请阅读 [README.md](README.md)。

## 项目结构

- `index.html`、`styles.css`、`app.js`：静态前端。
- `tools/local_library_server.py`：本地维护、公共曲库、邮箱认证与匿名分析服务。
- `data/community-scores/`：已审核的社区曲谱源文件。
- `data/community-songs.js`：由曲谱源文件生成的浏览器曲库数据，不应手工编辑。
- `tools/import_community_scores.py`：社区曲谱审核与曲库生成工具。
- `preview.sh`：本地预览入口；`deploy.sh`：正式服务部署脚本。

## 本地预览

不要直接双击 `index.html`。在项目根目录运行：

```bash
./preview.sh
```

脚本会输出本地网址。访问量会在 Header 显示；打开 `http://127.0.0.1:8765/admin/analytics.html`，并输入 `local-preview-analytics`，可预览分析后台。可通过 `DELTA_PREVIEW_PORT` 与 `DELTA_LOCAL_ANALYTICS_TOKEN` 修改端口和本地令牌。

## 静态 GitHub Pages

`.github/workflows/deploy-pages.yml` 会在推送到 `main` 后发布 `pages-redirect` 到 GitHub Pages。首次启用时，在仓库 **Settings → Pages → Build and deployment** 将 Source 设置为 **GitHub Actions**。

GitHub Pages 只能承载静态页面，无法发送验证码、保存会话或接收用户写入；页面会隐藏登录和直传入口。需要公共投稿时请部署内置服务。

### 前端缓存策略

`tools/local_library_server.py` 会对 HTML 和静态资源返回重新验证缓存头，对所有 `/api/` 响应使用 `no-store`，因此正式站点普通刷新即可获取新版本。GitHub Pages 无法由本项目控制响应头；修改 `index.html`、`app.js`、`styles.css` 或曲库数据后，请同步递增 `index.html` 底部脚本和样式链接中的 `?v=YYYYMMDD` 版本号。管理员账号按邮箱识别，当前管理员为 `274492469@qq.com`；管理员登录后可在曲库中维护「推荐」曲库。

发布新网页版本时，请同步更新 `app.js`、`index.html`、`README.md` 和 `version.json` 中的版本号；`version.json` 还应填写更新标题、摘要和变更列表，供在线页面自动提示用户刷新。

## 公共服务配置

最小部署命令：

```bash
DELTA_AUTH_SECRET='请使用随机长密钥' \
DELTA_SMTP_HOST='smtp.example.com' \
DELTA_SMTP_PORT='587' \
DELTA_SMTP_USERNAME='smtp-user' \
DELTA_SMTP_PASSWORD='smtp-password' \
DELTA_SMTP_FROM='三角洲口琴演奏家 <noreply@example.com>' \
python3 tools/local_library_server.py --public --trust-proxy --port 8765
```

也可以在同一套账户体系中启用 QQ 与微信网站扫码登录。密钥只配置在服务端，不要写入 `index.html` 或 `app.js`：

```bash
export DELTA_AUTH_SECRET='请使用随机长密钥'
export DELTA_QQ_APP_ID='QQ互联 App ID'
export DELTA_QQ_APP_KEY='QQ互联 App Key'
export DELTA_QQ_REDIRECT_URI='https://jiko-official.top/delta/api/auth/oauth/qq/callback'
export DELTA_WECHAT_APP_ID='微信开放平台网站应用 AppID'
export DELTA_WECHAT_APP_SECRET='微信开放平台网站应用 AppSecret'
export DELTA_WECHAT_REDIRECT_URI='https://jiko-official.top/delta/api/auth/oauth/wechat/callback'
python3 tools/local_library_server.py --public --trust-proxy --port 8765
```

QQ 需要在 QQ 互联应用中登记 QQ 回调地址；微信需要在微信开放平台「网站应用」中登记授权回调域名。两者的回调地址必须使用 HTTPS，并分别以 `/api/auth/oauth/qq/callback` 与 `/api/auth/oauth/wechat/callback` 结尾。网页中的「QQ 快捷登录」和「微信扫码登录」会跳转到对应官方授权页，首次登录会自动创建用户 ID（例如 `qq_name` 或 `wx_xxxxx`），并复用现有投稿权限与会话 Cookie。未配置的平台不会显示按钮。

将 HTTPS 反向代理指向该端口，并让服务用户拥有 `data/` 的写权限。生产环境必须使用 HTTPS：认证 Cookie 默认带 `Secure` 标记。`data/auth.sqlite3` 保存邮箱、账户、会话和投稿归属，`data/hot-rankings.sqlite3` 保存每日热门榜结果；两者都应使用持久化数据卷且不得提交到 Git。

`--public` 监听所有网卡并启用公共直传；只有端口不直接暴露、且 `X-Forwarded-For` 由自有反向代理覆盖时，才可使用 `--trust-proxy`。

验证码为 6 位、有效期 10 分钟、最多尝试 5 次，并按邮箱与 IP 限流。首次注册要求唯一用户 ID（3–24 位字母、数字或下划线）；改名会同步已直传曲谱的署名，旧 ID 永久保留。465 端口设 `DELTA_SMTP_SSL=true`；默认 587 使用 STARTTLS。

本地开发可加 `--auth-code-log-only --insecure-auth-cookies`，验证码仅写入终端。此模式禁止用于公网。

## Docker 部署

首次挂载空命名卷时，Docker 会使用镜像中的初始 `data/` 初始化卷；之后用户投稿会保留在卷内：

```bash
docker build -t delta-harmonica-macro .
docker run -d --name delta-harmonica-macro --restart unless-stopped \
  -p 127.0.0.1:8765:8765 \
  -v delta-harmonica-data:/app/data \
  -e DELTA_AUTH_SECRET='随机长密钥' \
  -e DELTA_SMTP_HOST='smtp.example.com' \
  -e DELTA_SMTP_PORT=587 \
  -e DELTA_SMTP_USERNAME='smtp-user' \
  -e DELTA_SMTP_PASSWORD='smtp-password' \
  -e DELTA_SMTP_FROM='三角洲口琴演奏家 <noreply@example.com>' \
  delta-harmonica-macro --public --trust-proxy --port 8765
```

## 一键部署到正式站点

`deploy.sh` 的目标为 `jiko-official.top`。脚本会打包项目、上传服务器、重建镜像并替换容器，再请求 `https://jiko-official.top/delta/api/public-library/status` 验证服务。

```bash
./deploy.sh
```

它会保留现有容器的 `DELTA_*` 环境变量，避免认证、邮件和分析配置在更新时丢失。部署会替换生产容器；执行前请确认当前工作区不包含不应发布的文件。

## 匿名数据分析

内置分析默认关闭。设置管理令牌后启用：

```bash
DELTA_ANALYTICS_ADMIN_TOKEN='请使用随机长令牌' \
python3 tools/local_library_server.py --public --trust-proxy --port 8765
```

Docker 方式增加 `-e DELTA_ANALYTICS_ADMIN_TOKEN='请使用随机长令牌'`。后台地址为 `/admin/analytics.html`，可查看最近 7、30 或 90 天数据。令牌只由浏览器提交给本站接口，不会写入前端代码或 Git。

分析仅记录临时匿名会话 ID、匿名谱子标识、来源类别、入口选择、曲库来源类别、输入模式、试听、编辑打开/保存、导出格式和投稿成功等事件；不记录 IP、曲名、谱子内容、搜索词、MIDI 文件名、上传文件或剪贴板内容。后台会按匿名谱子标识聚合载入、编辑和导出操作量；热门曲库每天按服务器本地时间凌晨 0 点计算一次，结果保存在 `data/hot-rankings.sqlite3`，页面不会实时重排。分析数据按天存于 `data/analytics/`，默认保留 90 天，可用 `--analytics-retention-days 1..365` 调整。请在站点隐私说明中告知访客。

## 社区曲谱维护

### 审核与生成

投稿源文件放在 `data/community-scores/`。不要直接编辑 `data/community-songs.js`，部署时会从已审核源文件重新生成它。

先生成审核报告：

```bash
python3 tools/import_community_scores.py submissions \
  --report community-review.json
```

确认后生成公开曲库数据：

```bash
python3 tools/import_community_scores.py approved \
  --report community-review.json \
  --output data/community-songs.js
```

工具会校验版本、必填元数据、调号、拍号、BPM、可选 HTTPS 展示链接和简谱符号；歌名、作者与共享人均相同的重复项会被拒绝。GitHub Pages 会在提交 `data/community-songs.js` 后自动更新。

### 本地维护者入库

```bash
python3 tools/local_library_server.py
```

访问 `http://127.0.0.1:8765/` 后，曲库标题旁会显示仅本地可见的「收录当前曲目」。该操作写入 `data/community-scores/` 并重建 `data/community-songs.js`；歌名、作者、共享人相同的曲目会覆盖原版本，不同共享人会共存。

该操作不会创建 Git 提交或推送。审核后自行执行 `git status`、`git add`、`git commit` 与 `git push`。

### 同步生产投稿

生产环境的公开投稿位于 Docker 卷，不会自动进入 Git。可在服务器上使用 `tools/sync_community_to_github.sh` 同步 `data/community-scores/` 与 `data/community-songs.js`。该脚本只在内容变化时创建 `chore: sync community songs` 提交并推送到 `track` 分支。

先为仓库配置具有写权限的 Deploy Key，并将私钥保存到 `/root/.ssh/delta_harmonica_github`。维护者审核后手动将 `track` 合并回目标分支。
