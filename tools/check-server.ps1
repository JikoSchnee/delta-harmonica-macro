#Requires -Version 5.1
<#
  只读巡检：阿里云服务器 + Docker 配置 + 正式站点。

  用法（在仓库根目录）：
    powershell -ExecutionPolicy Bypass -File tools\check-server.ps1
    powershell -ExecutionPolicy Bypass -File tools\check-server.ps1 -SkipRemote   # 只看网站
    powershell -ExecutionPolicy Bypass -File tools\check-server.ps1 -SkipWeb      # 只看服务器

  脚本不会修改服务器上的任何内容，全部命令都是读取状态。
#>
[CmdletBinding()]
param(
  [string]$SshTarget = 'root@47.102.211.4',
  [string]$IdentityFile = "$env:USERPROFILE\.ssh\id_ed25519_aliyun",
  [string]$SiteBaseUrl = 'https://jiko-official.top/delta',
  [int]$LogLines = 25,
  [switch]$SkipRemote,
  [switch]$SkipWeb
)

$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Write-Section([string]$Title) {
  Write-Host ''
  Write-Host ("===== $Title =====") -ForegroundColor Cyan
}

function Write-Hint([string]$Text) {
  Write-Host $Text -ForegroundColor Yellow
}

function Get-WebsiteStatus {
  Write-Section '网站状态（本机直接访问）'

  $paths = @(
    @{ Path = '/';                             Label = '首页 index.html' },
    @{ Path = '/version.json';                 Label = '版本信息' },
    @{ Path = '/api/public-library/status';    Label = '曲库接口' },
    @{ Path = '/app.js';                       Label = '前端脚本' },
    @{ Path = '/styles.css';                   Label = '样式表' }
  )

  foreach ($item in $paths) {
    $url = $SiteBaseUrl + $item.Path
    $probe = & curl.exe -sS -o NUL --max-time 20 `
      -w '%{http_code}|%{time_total}|%{size_download}' $url 2>&1
    $code = $LASTEXITCODE

    if ($code -ne 0 -or $probe -notmatch '^(\d{3})\|([\d.]+)\|(\d+)$') {
      Write-Host ('  {0,-14} 访问失败：{1}' -f $item.Label, ($probe -join ' ')) -ForegroundColor Red
      continue
    }

    $status = [int]$Matches[1]
    $seconds = [double]$Matches[2]
    $bytes = [int64]$Matches[3]
    $color = if ($status -eq 200) { 'Green' } else { 'Red' }
    Write-Host ('  {0,-14} HTTP {1}  {2,6:N0} ms  {3,9:N0} 字节' -f `
        $item.Label, $status, ($seconds * 1000), $bytes) -ForegroundColor $color
  }

  try {
    # 走临时文件而不是管道：cmdlet 之外的解码受控制台代码页影响，中文会变乱码。
    $tempFile = [System.IO.Path]::GetTempFileName()
    try {
      & curl.exe -sS --max-time 20 -o $tempFile ($SiteBaseUrl + '/version.json') 2>$null | Out-Null
      $remoteVersion = [System.IO.File]::ReadAllText($tempFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    } finally {
      Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
    }
    $localVersionPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'version.json'
    $localVersion = if (Test-Path $localVersionPath) {
      [System.IO.File]::ReadAllText($localVersionPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    } else {
      $null
    }

    Write-Host ''
    Write-Host ('  线上版本：{0}  {1}' -f $remoteVersion.version, $remoteVersion.title)
    if ($localVersion) {
      Write-Host ('  本地版本：{0}  {1}' -f $localVersion.version, $localVersion.title)
      if ($localVersion.version -ne $remoteVersion.version) {
        Write-Hint '  提示：本地 version.json 与线上不一致，说明线上还没部署最新提交。'
      }
    }
  } catch {
    Write-Hint "  无法解析版本信息：$($_.Exception.Message)"
  }
}

function Get-RemoteStatus {
  Write-Section '服务器状态（SSH 只读巡检）'

  if (-not (Test-Path $IdentityFile)) {
    Write-Hint "找不到私钥：$IdentityFile"
    Write-Hint '请先运行 ssh-keygen 生成密钥，并把 .pub 内容加到服务器的 /root/.ssh/authorized_keys。'
    return
  }

  $payload = @'
set -u
app_container=delta-harmonica-macro
docker_network=study-desk-webdav_default
proxy_info=$(docker ps --format '{{.Names}}|{{.Image}}' 2>/dev/null | awk -F'|' 'tolower($2) ~ /nginx|caddy|traefik/ {print $1 "|" $2; exit}')
proxy_container=${proxy_info%%|*}
proxy_image=${proxy_info#*|}
proxy_kind=$(printf '%s' "$proxy_image" | tr 'A-Z' 'a-z' | grep -oE 'nginx|caddy|traefik' | head -n1)
proxy_kind=${proxy_kind:-unknown}

hdr() { printf '\n--- %s ---\n' "$1"; }
indent() { sed 's/^/  /'; }

hdr '主机'
printf '  主机名：%s\n' "$(hostname)"
if [ -r /etc/os-release ]; then
  . /etc/os-release
  printf '  系统：%s\n' "${PRETTY_NAME:-$NAME}"
else
  printf '  系统：%s\n' "$(uname -srm)"
fi
printf '  内核：%s    CPU：%s 核\n' "$(uname -r)" "$(nproc 2>/dev/null || echo '?')"
printf '  负载：%s\n' "$(cut -d' ' -f1-3 /proc/loadavg)"
printf '  运行时长：%s\n' "$(uptime -p 2>/dev/null || uptime)"
free -m 2>/dev/null | awk '/^Mem:/ {printf "  内存：已用 %s MB / 共 %s MB（可用 %s MB）\n", $3, $2, $7}'
df -h / /var/lib/docker 2>/dev/null | awk 'NR>1 && !seen[$6]++ {printf "  磁盘 %s：已用 %s / 共 %s（%s）\n", $6, $3, $2, $5}'

hdr 'Docker 引擎'
docker version --format '  引擎版本：{{.Server.Version}}（API {{.Server.APIVersion}}）' 2>/dev/null || echo '  无法读取 docker 版本'
printf '  容器总数：%s（运行中 %s）\n' "$(docker ps -aq 2>/dev/null | wc -l)" "$(docker ps -q 2>/dev/null | wc -l)"
printf '  镜像总数：%s\n' "$(docker images -q 2>/dev/null | wc -l)"

hdr '全部容器'
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' 2>/dev/null | indent

hdr "应用容器 $app_container"
if docker inspect "$app_container" >/dev/null 2>&1; then
  printf '  镜像：%s\n' "$(docker inspect -f '{{.Config.Image}}' "$app_container")"
  printf '  状态：%s\n' "$(docker inspect -f '{{.State.Status}}' "$app_container")"
  printf '  启动于：%s\n' "$(docker inspect -f '{{.State.StartedAt}}' "$app_container")"
  printf '  重启次数：%s\n' "$(docker inspect -f '{{.RestartCount}}' "$app_container")"
  printf '  启动策略：%s\n' "$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$app_container")"
  printf '  宿主端口映射：%s\n' "$(docker inspect -f '{{if .HostConfig.PortBindings}}有{{else}}无（仅容器网络可达）{{end}}' "$app_container")"
  printf '  所属网络：%s\n' "$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{$v.IPAddress}} {{end}}' "$app_container")"
  printf '  数据卷：%s\n' "$(docker inspect -f '{{range .Mounts}}{{.Type}}:{{.Name}}->{{.Destination}} {{end}}' "$app_container")"
  printf '  启动命令：%s\n' "$(docker inspect -f '{{join .Config.Cmd " "}}' "$app_container")"
  printf '  维护标记：%s\n' "$(docker exec "$app_container" sh -c 'ls -l /app/data/.maintenance 2>/dev/null || echo "（无，站点正常对外）"')"

  echo '  环境变量（密钥类已隐藏）：'
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$app_container" 2>/dev/null \
    | sed -E 's/^([A-Z0-9_]*(SECRET|PASSWORD|TOKEN|KEY)[A-Z0-9_]*)=.*/\1=****（已隐藏）/' \
    | sed '/^$/d' | sort | indent
else
  echo '  找不到该容器'
fi

hdr '网络与容器连通性'
docker network inspect "$docker_network" --format '  网络 {{.Name}}（{{.Driver}}）中的容器：{{range $k, $v := .Containers}}{{$v.Name}} {{end}}' 2>/dev/null \
  || echo "  找不到网络 $docker_network"
if docker exec "$app_container" python3 -c 'import urllib.request,sys; sys.exit(0 if urllib.request.urlopen("http://127.0.0.1:8765/api/public-library/status", timeout=3).status == 200 else 1)' 2>/dev/null; then
  echo '  容器内自检／api/public-library/status：正常'
else
  echo '  容器内自检／api/public-library/status：失败'
fi

hdr '反向代理'
if [ -n "$proxy_container" ]; then
  printf '  容器：%s（%s）\n' "$proxy_container" "$proxy_image"
  printf '  启动命令：%s\n' "$(docker inspect -f '{{join .Config.Cmd " "}}' "$proxy_container" 2>/dev/null)"
  printf '  挂载配置：%s\n' "$(docker inspect -f '{{range .Mounts}}{{.Source}}->{{.Destination}} {{end}}' "$proxy_container" 2>/dev/null)"

  case "$proxy_kind" in
    nginx)
      docker exec "$proxy_container" nginx -v 2>&1 | sed 's/^/  /'
      echo '  配置校验：'
      docker exec "$proxy_container" nginx -t 2>&1 | sed 's/^/    /'
      echo '  /delta/ 相关配置：'
      docker exec "$proxy_container" nginx -T 2>&1 | grep -E -B4 -A22 'location /delta' | sed 's/^/    /'
      echo '  限流与上传上限：'
      docker exec "$proxy_container" nginx -T 2>&1 | grep -E 'limit_req_zone|limit_conn_zone|client_max_body_size' | sed 's/^/    /'
      if docker exec "$proxy_container" nginx -T 2>&1 | grep -q 'proxy_add_x_forwarded_for'; then
        echo '  提醒：配置里用了 $proxy_add_x_forwarded_for。服务端以 --trust-proxy 运行并取 X-Forwarded-For 第一段做限流，客户端自带的头会被追加到最前面，可被伪造绕过；建议改为 $remote_addr。'
      fi
      ;;
    caddy)
      printf '  版本：%s\n' "$(docker exec "$proxy_container" caddy version 2>&1 | head -n1)"
      caddy_conf=$(docker exec "$proxy_container" sh -c 'for f in /etc/caddy/Caddyfile /config/caddy/Caddyfile; do [ -f "$f" ] && { echo "$f"; break; }; done' 2>/dev/null)
      if [ -n "$caddy_conf" ]; then
        echo "  配置文件：$caddy_conf"
        echo '  配置校验：'
        docker exec "$proxy_container" caddy validate --config "$caddy_conf" --adapter caddyfile 2>&1 | sed 's/^/    /'
        echo '  /delta 相关配置：'
        docker exec "$proxy_container" sh -c "cat '$caddy_conf'" 2>&1 | grep -n -B2 -A12 'delta' | sed 's/^/    /'
        echo '  代理与转发指令：'
        docker exec "$proxy_container" sh -c "cat '$caddy_conf'" 2>&1 | grep -nE 'reverse_proxy|trusted_proxies|header_up|rate_limit|encode|client_ip|handle_path' | sed 's/^/    /'
      else
        echo '  没有在容器内找到 Caddyfile，配置可能是内联参数或来自其它路径。'
      fi
      ;;
    *)
      echo '  未识别的代理类型，仅列出容器信息。'
      ;;
  esac
else
  echo '  没有发现运行中的 nginx / caddy / traefik 容器；代理可能装在宿主机上，或使用其它软件。'
  echo '  宿主机进程检查：'
  (ss -tlnp 2>/dev/null | grep -E ':(80|443)\b' || echo '    未监听 80/443') | indent
fi

hdr 'SSH 授权密钥审计（能直连 root 的钥匙）'
if [ -r /root/.ssh/authorized_keys ]; then
  printf '  .ssh 目录：%s\n' "$(stat -c '%A %U:%G' /root/.ssh 2>/dev/null)"
  printf '  授权文件：%s\n' "$(stat -c '%A %U:%G，%s 字节，最后修改 %y' /root/.ssh/authorized_keys 2>/dev/null)"
  printf '  条目数量：%s\n' "$(grep -cvE '^[[:space:]]*(#|$)' /root/.ssh/authorized_keys 2>/dev/null)"
  echo '  指纹与注释：'
  ssh-keygen -lf /root/.ssh/authorized_keys 2>&1 | sed 's/^/    /'
  echo '  逐条摘要（密钥正文已截断）：'
  grep -vE '^[[:space:]]*(#|$)' /root/.ssh/authorized_keys 2>/dev/null \
    | sed -E 's/AAAA[A-Za-z0-9+\/=]{12}[A-Za-z0-9+\/=]+/{已截断}/g' | sed 's/^/    /'
  if grep -qE '^[[:space:]]*(command=|from=|restrict|no-pty|no-port-forwarding|permitopen=)' /root/.ssh/authorized_keys 2>/dev/null; then
    echo '  注意：存在带限制选项的条目（command= / from= / restrict 等），已在上面的摘要里一并列出。'
  fi
  echo '  其它可能生效的授权文件：'
  other_keys=0
  for f in /root/.ssh/authorized_keys2 /etc/ssh/authorized_keys /etc/ssh/authorized_keys.root; do
    if [ -f "$f" ]; then
      printf '    %s（%s 条）\n' "$f" "$(grep -cvE '^[[:space:]]*(#|$)' "$f" 2>/dev/null)"
      other_keys=1
    fi
  done
  if [ "$other_keys" -eq 0 ]; then echo '    无'; fi
  echo '  sshd 当前生效的登录策略：'
  sshd -T 2>/dev/null | grep -E '^(permitrootlogin|pubkeyauthentication|passwordauthentication|kbdinteractiveauthentication|authorizedkeysfile|allowusers|denyusers|authenticationmethods|maxauthtries)' | sed 's/^/    /'
else
  echo '  读不到 /root/.ssh/authorized_keys（可能尚未创建）'
fi

hdr '资源占用（快照）'
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' 2>/dev/null | indent
docker system df 2>/dev/null | indent

hdr '空间与日志'
printf '  日志尾 %s 行（%s）：\n' '__LOG_LINES__' "$app_container"
docker logs --tail __LOG_LINES__ "$app_container" 2>&1 | tail -n __LOG_LINES__ | indent
'@

  $payload = $payload.Replace('__LOG_LINES__', [string]$LogLines)
  # 远程 bash 不认 CRLF，结尾的 \r 会让函数名和参数解析失败。
  $payload = $payload -replace "`r`n", "`n"
  # Windows PowerShell 5.1 往原生命令 stdin 写入时会在末尾补一个 CRLF，
  # 用一行不带换行的注释收尾，让补出来的 \r 落在注释里而不是自成一行。
  $payload = $payload + "`n# end"

  $output = $payload | & ssh.exe -i $IdentityFile -o BatchMode=yes -o ConnectTimeout=10 `
    -o StrictHostKeyChecking=accept-new $SshTarget 'bash -s' 2>&1
  $exitCode = $LASTEXITCODE
  $text = ($output | Out-String)

  if ($exitCode -ne 0 -and $text -match 'Permission denied') {
    Write-Hint 'SSH 登录被拒绝：服务器只接受公钥认证，这台机器的公钥还没装到服务器上。'
    Write-Hint '请先在有权限的机器（或阿里云控制台 VNC）上执行：'
    Write-Hint ("  echo '{0}' >> /root/.ssh/authorized_keys" -f (Get-Content "$IdentityFile.pub" -Raw).Trim())
    Write-Hint '完成后重新运行本脚本即可。'
    return
  }

  foreach ($line in $output) { Write-Host $line }

  if ($exitCode -ne 0) {
    Write-Hint "SSH 巡检未正常结束（退出码 $exitCode）。"
  }
}

Write-Host "巡检目标：$SiteBaseUrl  ·  $SshTarget" -ForegroundColor DarkGray

if (-not $SkipWeb) { Get-WebsiteStatus }
if (-not $SkipRemote) { Get-RemoteStatus }

Write-Host ''
