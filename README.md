# Harmonica Deck

将三角洲行动口琴数字简谱转换为 Logitech G HUB Lua 脚本、实验性的 Razer Synapse 3/4 XML 宏文件，以及 ROG Armoury Crate GMAC 宏配置文件。

## 在线站点与 QQ 群

- 在线站点：[三角洲口琴演奏家](https://jiko-official.top/delta/)
- 备用站点(可能需要翻墙)：[备用站点](https://jikoschnee.github.io/delta-harmonica-macro/)
- QQ 群号：`1102489399`
- 也可以直接查看[入群二维码](assets/qq-group-qr.jpeg)。

## 静态部署与公共上传

仓库已配置 `.github/workflows/deploy-pages.yml`：推送到 `main` 分支后，GitHub Actions 会自动发布当前静态文件到 GitHub Pages。

首次启用时，请在仓库的 **Settings → Pages → Build and deployment** 中将 **Source** 设为 **GitHub Actions**。之后每次 push 到 `main` 都会触发部署；也可以在 Actions 页面手动运行工作流。

页面右上角的「GitHub · Star」入口会打开本项目仓库，欢迎顺手点亮 Star。

GitHub Pages 只承载静态页面，不能发送验证码、保存登录会话或接收用户写入；在该部署方式下「登录」和「上传到曲库」会自动隐藏。正式站点请用仓库内置服务部署。服务会把合格投稿写入 `data/community-scores/`、重建 `data/community-songs.js` 并立即展示；公共直传必须完成邮箱验证，服务器会以已登录用户 ID 写入“共享人”。

最小部署方式：

```bash
DELTA_AUTH_SECRET='请使用随机长密钥' \
DELTA_SMTP_HOST='smtp.example.com' \
DELTA_SMTP_PORT='587' \
DELTA_SMTP_USERNAME='smtp-user' \
DELTA_SMTP_PASSWORD='smtp-password' \
DELTA_SMTP_FROM='三角洲口琴演奏家 <noreply@example.com>' \
python3 tools/local_library_server.py --public --trust-proxy --port 8765
```

将 HTTPS 反向代理指向该端口，并让反向代理与此服务运行的用户具有 `data/` 目录写权限。`--public` 会监听所有网卡并启用公共直传；`--trust-proxy` 会用反向代理传入的 `X-Forwarded-For` 区分用户 IP，只有在端口未直接暴露、该请求头由你自己的代理覆盖时才能启用。生产环境必须使用 HTTPS：登录 Cookie 默认带 `Secure` 标记。服务会在 `data/auth.sqlite3` 保存邮箱、账户、会话和投稿归属关系；该文件应随 Docker 数据卷持久化且不能提交 Git。

验证码为 6 位、10 分钟有效、最多尝试 5 次；邮箱和 IP 均有一小时发送限额。用户首次验证邮箱时设置唯一 ID（3–24 位字母、数字或下划线）；可在账户中改名，已直传谱子的署名会同步更新，旧 ID 不会再分配给其他人。使用 465 端口时设置 `DELTA_SMTP_SSL=true`；默认使用 587 端口的 STARTTLS。开发环境可加 `--auth-code-log-only --insecure-auth-cookies`，验证码会仅打印到终端，切勿用于公网。

也可直接构建 Docker 镜像。首次挂载空的命名卷时，Docker 会用镜像中的初始 `data/` 内容初始化该卷，之后的用户投稿会持续保留：

```bash
docker build -t delta-harmonica-macro .
docker run -d --name delta-harmonica-macro --restart unless-stopped -p 127.0.0.1:8765:8765 -v delta-harmonica-data:/app/data -e DELTA_AUTH_SECRET='随机长密钥' -e DELTA_SMTP_HOST='smtp.example.com' -e DELTA_SMTP_PORT=587 -e DELTA_SMTP_USERNAME='smtp-user' -e DELTA_SMTP_PASSWORD='smtp-password' -e DELTA_SMTP_FROM='三角洲口琴演奏家 <noreply@example.com>' delta-harmonica-macro --public --trust-proxy --port 8765
```

### 内置匿名数据分析

内置服务可记录聚合访问量、功能使用漏斗和常见用户路径。它默认关闭；设置管理令牌后才会启用，以避免未配置后台时累积无用数据：

```bash
DELTA_ANALYTICS_ADMIN_TOKEN='请使用随机长令牌' \
python3 tools/local_library_server.py --public --trust-proxy --port 8765
```

Docker 部署时增加 `-e DELTA_ANALYTICS_ADMIN_TOKEN='请使用随机长令牌'`。随后访问 `/admin/analytics.html`，输入该令牌即可查看最近 7、30 或 90 天的数据。令牌只在浏览器当前页面提交给本站接口，不会写入网页代码或 Git。

### 本地预览访问数据

不要直接双击 `index.html`：它没有统计接口，Header 中的访问量会保持隐藏。在项目根目录运行：

```bash
./preview.sh
```

然后打开脚本输出的本地站点地址。统计会立刻记录本机浏览器访问，Header 会显示当前/今日访问量；在 `http://127.0.0.1:8765/admin/analytics.html` 输入 `local-preview-analytics` 可预览完整分析后台。该令牌仅用于本机；要换端口或令牌，可分别设置 `DELTA_PREVIEW_PORT` 与 `DELTA_LOCAL_ANALYTICS_TOKEN`。

### 一键部署到服务器

本项目根目录的 `deploy.sh` 已写入当前服务器地址、容器名称和 Caddy 所用 Docker 网络。首次运行一次即可授权 SSH，之后在本机项目根目录执行：

```bash
./deploy.sh
```

脚本会打包、上传、在服务器构建镜像、替换容器，并请求 `https://jiko-official.top/delta/api/public-library/status` 验证结果。它会在替换容器前自动保留已有的 `DELTA_ANALYTICS_ADMIN_TOKEN`，不会把令牌写入项目或压缩包。

分析只记录临时匿名会话 ID、访问来源类别（直接、搜索、社交、引荐）、入口选择、曲库来源类别、输入模式、试听、导出格式及投稿成功等允许的事件。不会记录 IP、曲名、谱子内容、搜索词、MIDI 文件名、上传文件或剪贴板内容。事件按天保存在 `data/analytics/`，默认 90 天自动清除；可用 `--analytics-retention-days 1..365` 调整。请在站点隐私说明中告知访客这一匿名统计用途。

### 同步公共投稿到 GitHub

服务器上的公开投稿保存在 Docker 卷中，不会自动进入 Git。可使用 `tools/sync_community_to_github.sh` 同步 `data/community-scores/` 和 `data/community-songs.js`：脚本仅在内容有变化时创建 `chore: sync community songs` 提交，并推送到 `track` 分支。请先为该 GitHub 仓库创建具有写权限的 Deploy Key，再将私钥保存为 `/root/.ssh/delta_harmonica_github`；部署服务器可每 10 分钟运行一次该脚本，维护者审核后手动将 `track` 合并回目标分支。

## MIDI 一键导入

在「谱子输入」区域点击 **导入 MIDI**，选择本地 `.mid` 或 `.midi` 文件，即可直接生成可编辑的数字简谱；文件只在浏览器本地读取，不会上传。导入时会自动：

- 跳过打击乐轨，优先选择音符更集中、较像主旋律的音轨；默认会将和弦（含约 1/64 拍内的轻微错开）取最高音。
- 读取文件开头的 BPM、拍号和调号，并在需要时以八度移调到游戏口琴可演奏的范围。
- 保留音符时值和休止；如果源 MIDI 包含变速，当前版本会采用起始 BPM，并在页面提示中说明。

每条可转换音轨右侧还有「精确选中」：打开全屏钢琴卷帘后可逐个保留或取消原始 MIDI 音符。它默认预选每组和弦的最高音；同一和弦组一次只能保留一个音，以确保生成的口琴宏仍可播放。确认后仅转换已选音符，并保留它们之间的休止。导入完成后仍可在简谱、精确或三角洲键盘模式微调。复杂多轨编曲的自动主旋律判断并非绝对，建议试听后确认。

默认开启的「流畅演奏」会将两音之间不超过一拍的短空拍并入前一个音，仅留下极短换气缝，适合原始 MIDI 使用大量断音的情况；关闭后会保留原始断音。切换开关会自动重新转换刚导入的 MIDI。

## 四种输入模式

四种模式是同一份当前曲谱的不同编辑视图。切换模式时，网页会先校验当前内容，再自动转换为目标模式的写法；旋律、休止和拍数保持一致。若当前内容有错误，将阻止切换以免覆盖原文。曲库载入时也会同时填充四种视图。

编辑区的「全谱移调」可将整首谱子逐半音升高或降低，并同步更新四种输入视图与可识别的调号。每次移调都会检查所有非休止音；若下一步会超出口琴可表达的音域，对应的升降按钮会自动停用，因此不会生成无法演奏的按键组合。

### 1. 简谱模式

面向直接照谱录入，裸音默认一拍：

```text
1=C 4/4
5_ #4_ 5_ 0_ 7_ 1'_ 7 | 3. 7_ 7_ 0.
```

- `0` 是休止符，`-` 将前一音延长一拍。
- `_`、`__` 分别是半拍和四分之一拍；`.`、`..` 分别增加二分之一和四分之三原时值。
- `#4` / `♭7` 表示升降号；`1'` / `,1` 表示高低八度。
- `~` 可连接相同音高并合并时值；不同音高之间仍按无空档连奏。
- 无法用常用符号精确表示的小数拍，可写成 `音符:拍数`，例如 `5:1.25`；这是模式自动转换时使用的无损写法。
- `()` 可标记连奏分句；`|`、`||:`、`:||` 可作为小节与反复线。反复线目前只作分隔，不会自动展开重复段。
- 支持写入 `1=C`、`4/4`、`♩=96` 等谱头标记；实际播放速度仍以 BPM 输入框为准。
- 若某个音需要同时按两种鼠标变调键、超出游戏当前映射，编辑器会指出具体位置。

### 2. 录制模式

录制页会先加载同一份当前曲谱的精确写法。按住实体键盘或页面琴键实时发声，按多久就记录多久；直接切换到下一音时，前一音会持续到切换时刻。完成录制后按当前 BPM 量化，并将结果同步到全部模式。

### 3. 精确模式

每个音符采用 `前缀音符/拍数`：

```text
1/1 M2/0.5 R3/0.5 L4/2 | 5/1 6/1 7/1 1'/2
```

- `1–7` 映射到 `Z–M`；`1'` 映射到英文逗号 `,`。
- `L`、`M`、`R` 分别在按音符时按住鼠标左、中、右键。
- `LM`、`RM` 表示同时按住两个修饰键，可表达低/高八度中的升半音，例如 `LM4/0.5`。
- `0/拍数` 表示休止；它会保留原谱空拍，但不会生成任何按键事件。
- `|` 是可选小节线；空白和换行都可分隔音符。
- 拍数必须大于 0。默认 120 BPM；导出的按键会按该音符的完整时值持续按住，并在下一音前立即切换。

### 4. 三角洲键盘模式

面向需要在第三方宏工具中手动逐项录入的场景；每行显示一项按键组合和完整时值：

```text
Z / 500ms
左键 + 中键 + Z / 250ms
等待 / 500ms
```

- 可用键位是 `Z X C V B N M ,`，分别对应 `1–7` 和高音 `1′`。
- `左键`、`中键`、`右键`代表演奏该音时需要同时按住的鼠标变调键；可使用“左键 + 中键”或“右键 + 中键”，不能重复键位，也不能同时使用左键与右键。
- `等待 / 时值ms` 表示休止，不会生成按键事件。每行时值必须是正整数毫秒。
- 键盘页中的毫秒会按当前 BPM 换算为内部拍数；因此修改 BPM 后，重新切换或同步到键盘页时会显示新的毫秒时值。键盘页显示的是完整音乐时值，不会展示导出器内部的极短换气间隔。

## 网页试听

点击「试听整段」可在浏览器中听到基于簧片泛音与气流噪声合成的口琴音色预览，播放时会高亮当前时间线音符。每个试听音会覆盖到下一个音的起始时刻，并留极短交叠，避免旋律中途断开。试听采用 `L=-12`、`M=+1`、`R=+12` 半音的近似音高，用来校验旋律和节奏；这是轻量的浏览器合成音色，不是录音采样，也不会连接游戏或鼠标驱动。

自定义区的「播放谱子」会直接开始试听；若谱子格式非法，则显示精确到行列的错误且不会播放。

## 内置曲库

《口琴按键映射测试》按固定顺序演奏 48 个音：自然音、低音、半音、高音、低音半音和高音半音各 8 个键位。建议先用此曲导出宏，逐组确认 L、M、R 鼠标映射正确后再播放正式曲目。测试中形如 `L1'`、`RM1'` 的写法表示“按住变调键后按物理 `1'` 键”，避免被普通简谱误判为同一音同时标记高、低八度。

曲库是独立板块。选择曲目后会载入同一份当前曲谱，并自动填充四种编辑模式。现收录《夏日午后的童谣（天使爱美丽插曲）》《天空之城》《皇后大道东》《父亲》和《贝加尔湖畔》的图片录入主旋律版本，不写入伴奏声部；《夏日午后的童谣》省略谱面开头四小节全休止，并已展开反复段与第一、第二结尾。《皇后大道东》按图片中的 1=G、4/4 谱面逐行校对低音点，无法发音的节奏口令段以休止小节保留位置。《父亲》按用户提供的 1=E、4/4 简谱录入，保留高低八度、休止、附点与延音，并把反复段展开为可直接试听的顺序。《贝加尔湖畔》使用用户最新提供的 1=C、4/4 主旋律校订版，保留低音点、高音点、休止、下划线、附点、延长线与同音连线；图片未标注速度，曲库使用临时 76 BPM，可在载入后修改。

## 驱动兼容性

- **G HUB**：导出的 Lua 固定为单次播放。“启动真实按键事件号”填写实体鼠标键在日志中的原始 `arg`，例如实体 G10 常为 `10`；这是唯一需要按真实按键填写的项目。“停止 Lua 状态号”默认是 `5`，只能填写 `1–5`，它不是 G11 等实体按键编号，通常无需修改。只有按住你选定的实体停止键时，探测日志没有出现 `states=5`，才按日志改为 `1–4`。播放中该状态会中止当前 Lua 并释放正在按住的琴键和变调键。
- **Synapse 3/4**：两套驱动导出格式不互通。本项目未使用实机样本，XML 仅导出原始事件序列；导入后请在对应 Synapse 版本中手动绑定鼠标键与触发模式。导入失败时请用你自己驱动版本导出的最小宏文件校准。
- **ROG Armoury Crate**：下载 `.gmac` 后，在 Macro 页面选择 Import，再将导入的宏绑定给支持宏功能的 ROG 外设按键。导出保留音符、鼠标变调、时值和换气间隔，并将重复次数固定为单次播放。不同 Armoury Crate 版本或外设支持的宏事件可能不同；导入失败时，请录制并导出一个单键宏作为格式校准样本。
- **口琴鼠标宏录制助手（测试版）**：优先使用本站的 [独立 Windows 录制助手](downloads/HarmonicaRecorder-win-x64.zip)：解压并运行一次 `Install.cmd` 后，导出区的「导出到独立助手」会把当前曲谱直接交给它。该程序仅通过 Windows `SendInput` 模拟键盘与左／中／右鼠标输入，提供 5 秒倒计时与 `Ctrl + Alt + End` 紧急停止；不需要 AutoHotkey。若你更倾向使用脚本，仍可下载 `.ahk` 并使用 **AutoHotkey v2** 运行（不兼容 v1）。导出区也提供本站镜像的 [AutoHotkey v2.0.28 便携 ZIP](downloads/AutoHotkey_2.0.28-windows-portable.zip)，原文件来自官网并保留其中的 `license.txt`；也可从 [AutoHotkey 官网下载页](https://www.autohotkey.com/download/) 获取最新稳定版。先在目标鼠标宏软件中创建单次播放宏并启动录制，再关闭助手提示并在 5 秒倒计时内回到录制界面；部分鼠标软件可能忽略系统模拟输入，请先录制短谱，并确保游戏窗口没有焦点。

宏绑定设置只用于 G HUB Lua 导出，不会写入谱子分享文件；Synapse XML 与 ROG GMAC 导出不受绑定键设置影响。

停止 Lua 状态号默认为 `5`，不能留空；停止键只负责停止当前导出的 Lua，G HUB Lua 无法从一个脚本强制关闭其他独立脚本或设备宏。默认变调占用 `1`、`2`、`3` 时，状态号 `5` 通常可用；若探测日志显示实体停止键只命中 `4`，再将它改为 `4`。

请自行确认游戏规则允许使用宏。

## 导入 PDMX 热门曲目

曲库支持由 `tools/import_pdmx.py` 生成的浏览器数据文件。脚本按 PDMX 的浏览量、收藏数、评分数和平均评分计算热度，并只保留无许可冲突、存在 MXL、去重后的最佳编曲。每首曲目会选择音符最多的可演奏声部，自动移调到当前口琴的 C3–B5 范围，再转换为本工具的简谱格式。

PDMX 的完整索引约 225 MB，MXL 压缩包约 1.9 GB；脚本不会把这些原始文件放进网页。推荐先手动从 [Zenodo PDMX v9](https://zenodo.org/records/15571083) 下载 `PDMX.csv` 和 `mxl.tar.gz`，然后运行：

```bash
python3 tools/import_pdmx.py \
  --csv /path/to/PDMX.csv \
  --mxl-archive /path/to/mxl.tar.gz \
  --output data/pdmx-top-1000.js
```

也支持包含旧版 MusicRender JSON 的单一 PDMX 镜像，例如 Hugging Face 的 [openmusic/pdmx](https://huggingface.co/datasets/openmusic/pdmx)：

```bash
python3 tools/import_pdmx.py \
  --pdmx-archive /path/to/PDMX.tar.gz \
  --output data/pdmx-top-1000.js
```

也可以让脚本下载文件；其中 `--download-mxl` 会下载约 1.9 GB：

```bash
python3 tools/import_pdmx.py --download-csv --download-mxl
```

完成后重新打开 `index.html`，曲库会显示内置曲目加上 1000 首 PDMX 曲目。由于 PDMX 的公开许可字段和文件内部版权字段存在已知冲突，脚本默认使用 `no_license_conflict`（当前字段存在时），并要求候选项存在可解析的乐谱数据；PDMX 项目也建议优先使用这个无冲突子集。使用或再分发前仍应核验具体曲目的许可信息。

## 社区谱子投稿与维护

页面中的“分享 .deltamusic”会生成 `.deltamusic` 文件。文件包含歌名、歌手/作者、共享人、调号、拍号、BPM 与标准化数字简谱；还可选填展示视频 HTTPS 链接。链接会随导入、再次导出和社区收录保留，并在曲库卡片底部显示为「展示视频」。留空不会写入文件。旧版 `.harmonica-score.json` 仍可导入，但新的分享文件统一使用 `.deltamusic`。

在启用了公共曲库服务的站点中，编辑器操作行会显示「上传到曲库」按钮：填写共享信息后即可直接上传，合格曲目会立即公开。请只上传你有权分享的原创或已获授权谱面。静态 GitHub Pages 不显示该按钮；投稿者仍可加入 QQ 群 `1102489399` 发送 `.deltamusic` 文件，或 Fork 本仓库，将文件上传到 `data/community-scores/` 后创建 Pull Request。每个 PR 会自动校验谱子格式；只有维护者审核并合并后，GitHub Pages 才会发布该谱子。

建议使用 `歌名-作者-你的昵称.deltamusic` 作为文件名。不要直接编辑 `data/community-songs.js`：部署时会从已审核的源文件自动生成它。维护者审核时可在 PR 的 Actions 里下载 `community-review` 报告，试听确认后再合并。

维护者可先只生成审核报告：

```bash
python3 tools/import_community_scores.py submissions \
  --report community-review.json
```

确认无误后生成公开曲库数据：

```bash
python3 tools/import_community_scores.py approved \
  --report community-review.json \
  --output data/community-songs.js
```

脚本会校验文件版本、必填元数据、调号、拍号、BPM、可选展示视频 HTTPS 链接与简谱符号，并拒绝本批次中歌名、歌手/作者和共享人均相同的重复投稿。将生成的 `data/community-songs.js` 提交到 GitHub 后，GitHub Pages 会随部署更新公共曲库。

### 本地维护者快速入库

维护者可在仓库根目录启动仅限本机访问的维护服务：

```bash
python3 tools/local_library_server.py
```

然后打开 `http://127.0.0.1:8765/`。曲库标题旁会出现仅本地可见的「收录当前曲目」按钮；它会复用当前谱子、共享信息和可选展示视频链接，写入 `data/community-scores/` 并重建 `data/community-songs.js`。歌名、歌手/作者、共享人三项都相同的曲目会覆盖原版本；共享人不同的版本会同时保留。

该按钮不会创建 Git 提交或推送远程仓库。确认改动后请自行执行 `git status`、`git add`、`git commit` 和 `git push`。GitHub Pages 与直接打开 `index.html` 时不会显示这个维护入口，也不会提供任何远程写入能力。
