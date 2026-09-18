# Harmonica Deck 开发与维护指南

本文件面向开发者、部署维护者和曲库审核者。普通用户请阅读 [README.md](README.md)。

## 项目结构

- `index.html`、`styles.css`、`app.js`：静态前端。
- `tools/local_library_server.py`：本地维护、公共曲库、邮箱认证与匿名分析服务。
- `data/community-scores/`：已审核的社区曲谱源文件。
- `data/community-songs.js`：由曲谱源文件生成的浏览器曲库数据，不应手工编辑。
- `tools/import_community_scores.py`：社区曲谱审核与曲库生成工具。
- `preview.sh`：本地预览入口；`deploy.sh`：正式服务部署脚本。

## 一键部署到正式站点

`deploy.sh` 的目标为 `jiko-official.top`。脚本只打包并上传代码，不包含 `data/` 下的用户、曲库和统计数据；生产数据由 Docker 持久化卷独立保存。脚本会先构建新镜像，构建期间旧容器继续提供服务。切换容器前会启用维护标记，新容器就绪后自动清除标记，访客在切换窗口看到“正在更新”页面而不是 502。脚本最后请求 `https://jiko-official.top/delta/api/public-library/status` 验证服务。

```bash
./deploy.sh
```

它会保留现有容器的 `DELTA_*` 环境变量，避免认证、邮件和分析配置在更新时丢失。部署会替换生产容器，但不会同步或重建数据卷；执行前请确认当前工作区不包含不应发布的代码或配置文件。

## 发布录制助手

`release-helper.sh` 发布的是 Windows `win-x64` 自包含录制助手，网页版本与助手版本独立维护。完整发布命令如下：

```bash
./release-helper.sh 2.0.0
```

脚本按以下顺序执行：

1. 使用 .NET 8 构建 `HarmonicaRecorder.exe`。
2. 将 EXE 与 `Install.cmd`、`README.txt`、`Uninstall.cmd` 打包为 `2.0.0-HarmonicaRecorder-win-x64.zip`。
3. 更新 `recording-helper/version.json`，写入 GitHub 下载地址、服务器备用下载地址和 SHA-256。
4. 创建或更新 GitHub Release `helper-v2.0.0` 并上传 ZIP。
5. 上传到服务器宿主机 `/opt/delta-harmonica-macro/downloads/`，再同步到正在运行的 Docker 容器 `/app/downloads/`。
6. 校验本地两份 ZIP、GitHub 下载地址和服务器下载地址的 SHA-256。

GitHub Release 已存在时，可以跳过重新上传 GitHub 资产，只重新同步服务器并校验：

```bash
./release-helper.sh 2.0.0 --skip-github
```

其他选项：

```bash
./release-helper.sh 2.0.0 --skip-server   # 只发布 GitHub，不上传服务器
./release-helper.sh 2.0.0 --skip-verify   # 跳过远程 HTTP 校验，仅用于排查网络问题
```

可用环境变量：

```bash
HELPER_GITHUB_REPOSITORY=JikoSchnee/delta-harmonica-macro
HELPER_SERVER_SSH_TARGET=root@47.102.211.4
HELPER_SERVER_PROJECT_DIR=/opt/delta-harmonica-macro
HELPER_SERVER_CONTAINER_NAME=delta-harmonica-macro
HELPER_SERVER_PUBLIC_BASE_URL=https://jiko-official.top/delta/downloads
```

其中 `HELPER_SERVER_CONTAINER_NAME` 默认是 `delta-harmonica-macro`。正式站点的宿主机项目目录没有挂载为容器静态目录，因此只执行 `scp` 不足以让下载地址生效；发布脚本会额外执行 `docker cp`，将 ZIP 同步到容器内的 `/app/downloads/`。

### 服务器完整备份

使用项目根目录的 `backup-server.sh` 可以一次性拉取服务器项目文件、Docker 持久化数据、容器下载文件和运行配置：

```bash
./backup-server.sh
```

备份默认保存到项目同级的 `delta-harmonica-backups/`，也可以指定目录：

```bash
./backup-server.sh --output-dir /Users/jikoschnee/Documents/delta-server-backups
```

生成的压缩包包含 `project/`、`data/`、`runtime-downloads/`、`container-inspect.json`、`container-env.txt` 和 `volume-inspect.json`。其中 `container-env.txt` 可能包含认证密钥和 SMTP 密码，请妥善保管备份文件。

### 助手发布失败排查

先确认 GitHub Release 资产和服务器下载地址分别可访问：

```bash
curl -fL --retry 5 --retry-delay 3 \
  https://github.com/JikoSchnee/delta-harmonica-macro/releases/download/helper-v2.0.0/2.0.0-HarmonicaRecorder-win-x64.zip \
  -o /tmp/helper-github.zip

curl -fL --retry 5 --retry-delay 3 \
  https://jiko-official.top/delta/downloads/2.0.0-HarmonicaRecorder-win-x64.zip \
  -o /tmp/helper-server.zip
```

如果 GitHub Release 页面已经有 ZIP，但服务器地址返回 404，通常是 ZIP 只存在于宿主机、尚未复制进运行中的容器。可在服务器上手动修复：

```bash
ssh root@47.102.211.4 \
  "docker cp /opt/delta-harmonica-macro/downloads/2.0.0-HarmonicaRecorder-win-x64.zip \
  delta-harmonica-macro:/app/downloads/2.0.0-HarmonicaRecorder-win-x64.zip"
```

如果刚创建 GitHub Release 后立即校验出现 404，先等待 GitHub 资产传播，或重新执行带 `--skip-github` 的发布命令；脚本本身也会对远程校验进行重试。

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

`tools/local_library_server.py` 会把文本类资源（HTML、JS、CSS、JSON、SVG）在客户端支持时用 gzip 发送，压缩结果按 `(mtime, size)` 缓存在内存里，只有文件变化时才会重新压缩。缓存策略分三档：带 `?v=` 发布标记的资源（`app.js`、`styles.css`）和 `.zip` 安装包返回 `public, max-age=31536000, immutable`；`data/` 下的曲库数据和其余静态文件仍返回 `no-cache, must-revalidate` 做重新验证；`index.html` 与所有 `/api/` 响应保持 `no-store`，因此正式站点普通刷新即可获取新版本。`?v=` 标记由 `./deploy.sh --bump-version <新版本>` 自动改写，不需要手工维护。GitHub Pages 无法由本项目控制响应头，走 Pages 发布时仍需自行确认缓存行为。管理员账号按邮箱识别，当前管理员为 `274492469@qq.com`；管理员登录后可在曲库中维护「推荐」曲库。

发布新网页版本时，请同步更新 `app.js`、`index.html`、`README.md` 和根目录 `version.json` 中的网站版本号；根目录 `version.json` 还应填写更新标题、摘要和变更列表，供在线页面自动提示用户刷新。录制助手只维护 `recording-helper/version.json`，发布时执行 `./release-helper.sh <助手版本>`，脚本会构建并生成 `<助手版本>-HarmonicaRecorder-win-x64.zip`、下载链接和 SHA-256。助手版本必须使用三段式数字版本号，例如 `2.0.0`。

执行 `./deploy.sh` 时会先比较本地根目录 `version.json` 与正式站点版本；版本未更新或低于线上版本会停止部署，并提示 `./deploy.sh --bump-version <新版本> && ./deploy.sh`。`bump` 命令会同步更新网页版本文件、`index.html`、`app.js` 和 README；确认变更后再执行 `./deploy.sh`。

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

反向代理建议加一层按 IP 的限流兜底，替代"排队等待"类方案。放在代理的 `http {}` 与 `/delta/` 的 `server {}` 中（正式站点与其它项目共用同一个代理容器，改动前先确认 `limit_req_zone` 名称不冲突，改完先 `nginx -t` 再 `nginx -s reload`）：

```nginx
limit_req_zone  $binary_remote_addr zone=delta_api:10m rate=10r/s;
limit_conn_zone $binary_remote_addr zone=delta_conn:10m;

location /delta/api/ {
    limit_req        zone=delta_api burst=40 nodelay;
    limit_conn       delta_conn 32;
    limit_req_status 429;
    limit_conn_status 429;
    proxy_pass http://delta-harmonica-macro:8765/api/;
    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

`burst=40` 是给"一次打开多个标签页"留的余量：首页加载会在两秒内打完 7 个数据接口，正常用户不会触发 429，而脚本式刷接口会被限制在每秒 10 次以内。服务端本身还有 128 个请求线程的硬上限，超出会直接断开连接，所以限流应当放在代理层。

验证码为 6 位、有效期 10 分钟、最多尝试 5 次，并按邮箱与 IP 限流。首次注册要求唯一用户 ID（3–24 个中文、字母、数字或下划线字符）；改名会同步已直传曲谱的署名，旧 ID 永久保留。465 端口设 `DELTA_SMTP_SSL=true`；默认 587 使用 STARTTLS。

验证码邮件由内置发信队列异步投递（2 个 worker、队列上限 64、单次 SMTP 超时 15 秒）。`POST /api/auth/request-code` 返回邮件票据与初始状态，网页据此轮询 `GET /api/auth/mail-status?ticket=...` 展示「排队中／正在发送／已发送／发送失败」。票据状态只保存在内存中，不读写 SQLite，15 分钟后自动清理，因此轮询开销可以忽略。

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

## 匿名数据分析

内置分析默认关闭。设置管理令牌后启用：

```bash
DELTA_ANALYTICS_ADMIN_TOKEN='请使用随机长令牌' \
python3 tools/local_library_server.py --public --trust-proxy --port 8765
```

Docker 方式增加 `-e DELTA_ANALYTICS_ADMIN_TOKEN='请使用随机长令牌'`。后台地址为 `/admin/analytics.html`，可查看最近 7、30 或 90 天数据。令牌只由浏览器提交给本站接口，不会写入前端代码或 Git。

分析仅记录临时匿名会话 ID、匿名谱子标识、来源类别、入口选择、曲库来源类别、输入模式、试听、编辑打开/保存、导出格式和投稿成功等事件；不记录 IP、曲名、谱子内容、搜索词、MIDI 文件名、上传文件或剪贴板内容。已登录账号只在服务端生成不可读的稳定匿名标识，用于同一账号对同一曲谱的导出量去重，不会写入邮箱或用户 ID。后台会按匿名谱子标识聚合载入、编辑和去重后的宏导出量；导出量只来自导出区成功产出宏的操作，包括复制 Lua，不包含 `.deltamusic` 分享下载、打开导出区、切换板块或查看键盘谱。未登录用户每个匿名 session 最多成功导出 3 次宏（所有曲谱和格式合计）；达到上限后网页会引导注册或登录。认证未启用或认证状态不可用时不限制匿名导出；该配额是体验限制，不是防刷机制。曲目卡片的导出量从原始分析事件统计，服务端缓存 10 分钟后刷新；公开接口不会读取每日热榜快照。热门曲库每天按服务器本地时间凌晨 0 点计算一次，结果保存在 `data/hot-rankings.sqlite3`，统计口径变化时会自动刷新当天缓存，页面不会实时重排。分析数据按天存于 `data/analytics/`，默认保留 90 天，可用 `--analytics-retention-days 1..365` 调整。请在站点隐私说明中告知访客。

首页的三个公开统计接口（`/api/analytics/summary`、`/api/public-rankings`、`/api/analytics/score-exports`）都通过 `SingleFlightCache` 做 single-flight：缓存到期时只允许一个请求去重算，其余请求等待并复用同一份结果，避免多个标签页同时刷新把一次重算放大成多次。三个接口只读的日志范围也已收窄：`/api/public-rankings` 的"昨日导出榜"只读覆盖目标本地日的那一到两个日志文件（此前会遍历整个保留期目录），导出总量按保留期扫描一次后在三个接口间共享，且所有扫描都会先用子串预筛掉占绝大多数的 heartbeat 行，再交给 JSON 解析器。

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
