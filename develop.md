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

`deploy.sh` 的目标为 `jiko-official.top`。脚本只打包并上传代码，不包含 `data/` 下的用户、曲库和统计数据；生产数据由 Docker 持久化卷独立保存。打包同样排除 `downloads/`、`recording-helper/downloads/` 与 `server-backups/`：录制助手安装包每个约 60 MB 且由 `release-helper.sh` 单独发布到服务器，备份残留只会拖慢上传并被 `COPY . .` 打进镜像。为此首次在一台新服务器上部署时，需要先执行一次 `release-helper.sh`（或手工把 ZIP 放到服务器 `/opt/delta-harmonica-macro/downloads/` 并用 `docker cp` 同步进容器），否则「服务器下载」链接会 404。脚本会先构建新镜像，构建期间旧容器继续提供服务。切换容器前会启用维护标记，新容器就绪后自动清除标记，访客在切换窗口看到“正在更新”页面而不是 502。脚本最后请求 `https://jiko-official.top/delta/api/public-library/status` 验证服务。

`.dockerignore` 另外排除 `server-backups/` 与 `recording-helper/downloads/`，避免备份残留和重复的安装包副本进入镜像；对外只使用 `downloads/` 这一份安装包。

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

正式站点 `jiko-official.top` 由阿里云 ECS（`47.102.211.4`）上的独立 Caddy 反向代理（镜像 `caddy:2`）。Caddyfile 放在服务器宿主机的 `/opt/delta-proxy/Caddyfile`，以只读方式挂载为容器内的 `/etc/caddy/Caddyfile`。应用容器不发布宿主机端口，只挂在 `delta-production` 网络上，因此代理直接用容器名寻址：

```caddyfile
{$DOMAIN} {
  route {
    redir /delta /delta/ 308
    handle_path /delta/* {
      reverse_proxy delta-harmonica-macro:8765
    }
    respond 404
  }
}
```

`handle_path` 会剥掉 `/delta` 前缀再转发，等价于 nginx 中带尾斜杠的 `proxy_pass`。Caddy 默认用真实客户端地址覆盖 `X-Forwarded-For`（除非请求来自 `trusted_proxies` 中声明的上游代理），所以配合 `--trust-proxy` 拿到的是真实客户端 IP，客户端伪造转发头无法绕过按 IP 的限流。

改动 Caddyfile 后先校验再热重载，不要跳过校验直接重启容器：

```bash
docker exec delta-proxy-caddy-1 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker exec delta-proxy-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

Caddy 官方镜像不自带 `rate_limit` 指令，要加代理层限流需自行编译插件，因此当前站点依靠服务端自身的 128 个请求线程上限和认证接口限流兜底。如果将来改用 nginx 承接，可参考下面的写法，注意 `X-Forwarded-For` 必须用 `$remote_addr` 覆盖：服务端取该头的第一段做限流，而 `$proxy_add_x_forwarded_for` 会把客户端自带的头排在前面，等于给出可伪造的空间。

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
    proxy_set_header X-Forwarded-For   $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

`burst=40` 是给"一次打开多个标签页"留的余量：首页加载会在两秒内打完 7 个数据接口，正常用户不会触发 429，而脚本式刷接口会被限制在每秒 10 次以内。

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

后台控制台 `/admin/console.html` 另有「运行时状态」页：集中显示服务器负载、内存、磁盘、请求线程占用，验证码邮件的队列深度与投递计数，以及当前线程列表。页内按钮可开启每 5 秒自动刷新，再次点击即停止，离开该页也会自动停止。数据来自只读的 `GET /api/admin/runtime`，与其它管理接口共用同一个令牌，只读取内存计数与系统信息，不写入任何数据。

分析仅记录临时匿名会话 ID、匿名谱子标识、来源类别、入口选择、曲库来源类别、输入模式、试听、编辑打开/保存、导出格式和投稿成功等事件；不记录 IP、曲名、谱子内容、搜索词、MIDI 文件名、上传文件或剪贴板内容。已登录账号只在服务端生成不可读的稳定匿名标识，用于同一账号对同一曲谱的导出量去重，不会写入邮箱或用户 ID。后台会按匿名谱子标识聚合载入、编辑和去重后的宏导出量；导出量只来自导出区成功产出宏的操作，包括复制 Lua，不包含 `.deltamusic` 分享下载、打开导出区、切换板块或查看键盘谱。公共曲库中他人的曲谱须登录并首次消耗 10 积分解锁；本地导入、原创和自己的曲谱免费。曲目卡片的导出量从原始分析事件统计，服务端缓存 10 分钟后刷新；公开接口不会读取每日热榜快照。热门曲库每天按服务器本地时间凌晨 0 点计算一次，结果保存在 `data/hot-rankings.sqlite3`，统计口径变化时会自动刷新当天缓存，页面不会实时重排。分析数据按天存于 `data/analytics/`，默认保留 90 天，可用 `--analytics-retention-days 1..365` 调整。请在站点隐私说明中告知访客。

首页的三个公开统计接口（`/api/analytics/summary`、`/api/public-rankings`、`/api/analytics/score-exports`）都通过 `SingleFlightCache` 做 single-flight：缓存到期时只允许一个请求去重算，其余请求等待并复用同一份结果，避免多个标签页同时刷新把一次重算放大成多次。三个接口只读的日志范围也已收窄：`/api/public-rankings` 的"昨日导出榜"只读覆盖目标本地日的那一到两个日志文件（此前会遍历整个保留期目录），导出总量按保留期扫描一次后在三个接口间共享，且所有扫描都会先用子串预筛掉占绝大多数的 heartbeat 行，再交给 JSON 解析器。首页榜单同屏展示三个榜：贡献榜、昨日导出榜和使用榜（不再用标签切换）。贡献榜仍是"上传曲目累计导出量"，使用榜按账号统计保留期内去重后的导出量——同一账号对同一曲谱只计一次，未登录的导出只计入曲目总量、不归属到具体账号；两个榜共用一次日志扫描（`EXPORT_EVENT_COUNT_CACHE`），不会重复遍历保留期。

## 打赏与用户 ID 特效

### 曲谱积分

积分规则配置在服务端 `POINT_RULES`：注册 30、Star 500、老用户更新奖励 100、首次投稿 50、有效邀请 20；他人公共曲谱首次解锁消耗 10；作者名下曲谱每被一位不同账号首次解锁即时奖励 1（积分参考值记录「解锁者账号 + 曲谱」，账本唯一键保证同一次解锁只入账一次，删掉曲目清理记录后再解锁也不会重复发放）。历史导出在更新迁移时按去重后的有效导出次数以 1 次 = 1 积分一次性结算给原作者，迁移只执行一次，并在日志中标记为“历史导出结算”；老用户首次读取账号资料时领取注册奖励，已有投稿者另领取一次首次投稿奖励。积分流水、解锁、邀请、作者计数和永久打赏权益存于 `data/auth.sqlite3`。`GET /api/points` 查询状态，`POST /api/points/unlock` 提交 `{"remixCode":"..."}` 永久解锁；同一曲谱重复提交不重复扣费。更新说明在账号首次登录后展示一次，`POST /api/points/notice` 按账号记录已阅读状态，换设备登录也不会重复弹出。

GitHub Star 奖励需要创建 GitHub OAuth App，回调 URL 配为站点的 `/api/points/github/callback`，并设置 `DELTA_GITHUB_CLIENT_ID`、`DELTA_GITHUB_CLIENT_SECRET`、`DELTA_GITHUB_REDIRECT_URI`。默认仓库为 `JikoSchnee/delta-harmonica-macro`，可用 `DELTA_GITHUB_STAR_REPO=owner/repo` 修改。未配置时页面不显示领取按钮。GitHub 授权只验证账号身份和 Star 状态；每个 GitHub 账号、站内账号只能领取一次。同一个 OAuth 应用同时用于「GitHub 快捷登录」与账号绑定，回调地址仍然是 `/api/points/github/callback`，不需要在 GitHub 侧新增回调配置：入口 `/api/auth/github/start` 在已登录时进入绑定流程、未登录时进入登录流程，回调按 state 里记录的用途分发。GitHub 登录只允许进入**已绑定**的站内账号（未绑定会提示先用邮箱验证码登录再到「账户资料」绑定），不会创建新账号；绑定关系双向唯一，一个 GitHub 账号只对应一个站内账号。验证 Star 奖励时会自动绑定并记录 GitHub 账号名，账户资料里也会显示已绑定的 GitHub 账号。打赏金额大于零经后台确认后，永久获得免扣权益；此权益与当前展示的打赏金额分别保存。管理令牌可读取 `GET /api/admin/points` 的近 14 日积分发放、消耗、解锁和邀请汇总；积分不足次数在现有数据分析事件中查看。

本地固定测试登录可在 `--auth-code-log-only` 模式下设置 `DELTA_FIXED_TEST_LOGIN_EMAIL` 和 `DELTA_FIXED_TEST_LOGIN_CODE`。指定账号必须已经存在，登录时可直接填写邮箱和固定 6 位验证码，无需先请求验证码；缺少日志测试模式时服务会拒绝启动，避免正式环境误开固定验证码。

### 打赏记录

后台「用户管理」页可以为账号登记打赏金额（按元填写，支持两位小数，填 0 即清除），数据保存在 `data/auth.sqlite3` 的 `donations` 表。公开接口 `GET /api/public-donors` 只返回用户名，不返回金额与邮箱，结果缓存 60 秒；金额本身只用于解锁打赏档特效和在后台查看，不会出现在页面上。打赏档的解锁判据是"该账号收到过金额大于 0 的打赏"，撤销打赏后特效会自动回落。

### 用户 ID 特效

- 配色与解锁门槛集中在服务端的 `USER_ID_EFFECT_UNLOCKS`：贡献达到 50 / 100 / 500 次分别解锁冰蓝、紫电、红橙三档，进入打赏名单解锁青碧档。这里的"贡献"指该账号已发布曲目在分析保留期内的去重导出量。
- 账号选择的特效保存在 `account_effects` 表，通过 `POST /api/auth/effect` 保存；服务端会按当前解锁状态二次校验，未达标返回 400，因此不能靠改前端绕过。
- 首次解锁时网页弹窗提醒一次，展示后由 `POST /api/auth/effect-notice` 记入 `effect_unlock_notices`，换浏览器或换设备都不会重复提醒。
- 全站用户 ID 统一按账号当前特效渲染，包括榜单人名、曲库卡片与推荐位的"共享人"、打赏名单、导出卡片上的信息提供人；`GET /api/public-rankings` 通过 `userEffects` 下发非默认配色的映射，未登录访客也能看到他人的配色。
- 资格失效时（例如打赏被撤销、贡献随保留期滑落到阈值以下）`account_effect_state` 会让显示回落到默认效果，但保留账号已保存的选择，重新达标即恢复。
- 补充配色表（`styles.css` 中的 `user-id--*`）另有 gold、rose 两套备用，尚未接入解锁表；新增配色时同步改 `USER_ID_EFFECT_UNLOCKS` 与网页的 `USER_ID_EFFECT_META`。

### 本地预览的静态资源缓存

本地预览（未开启 `--public`）时，带 `?v=` 版本标记的静态资源返回 `no-cache`，避免改完 `app.js` / `styles.css` 后浏览器仍读取旧缓存；正式部署仍按一年 `immutable` 缓存，由发版脚本改写版本标记来刷新。

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

生产环境的投稿保存在 Docker 卷，使用服务器备份保留私有副本。`tools/sync_community_to_github.sh` 已停用：公开仓库的 `track` 分支及其 Git 历史对任何人可见，不能用作私有曲库备份。仅在审核并确认允许公开后，手动导出选定曲谱到公开仓库。

已有 `track` 泄漏需要在服务器停用同步定时任务，并从远端删除该分支；删除分支不能撤回已被克隆或缓存的内容。若曲库不能公开，还须检查 `main` 的历史及 `data/community-songs.js`、`data/community-scores/` 和站点接口，并迁移到私有存储。改写公开 Git 历史前先备份并协调所有协作者。
