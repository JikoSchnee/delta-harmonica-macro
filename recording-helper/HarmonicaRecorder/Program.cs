using System.Runtime.InteropServices;
using System.Diagnostics;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace HarmonicaRecorder;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        var request = PlaybackRequest.FromProtocolArgument(args.FirstOrDefault());
        var updateCompleted = args.Any(argument => string.Equals(argument, "--update-complete", StringComparison.OrdinalIgnoreCase));
        Application.Run(new RecorderForm(request, updateCompleted));
    }
}

internal sealed class PlaybackRequest
{
    internal static string HelperVersion => typeof(PlaybackRequest).Assembly.GetName().Version is System.Version version
        ? $"{version.Major}.{version.Minor}.{Math.Max(0, version.Build)}"
        : "0.0.0";

    [JsonPropertyName("v")]
    public int Version { get; init; }

    [JsonPropertyName("wv")]
    public string? WebVersion { get; init; }

    [JsonPropertyName("hc")]
    public List<string> CompatibleHelperPrefixes { get; init; } = [];

    [JsonPropertyName("title")]
    public string Title { get; init; } = "当前曲谱";

    [JsonPropertyName("events")]
    public List<PlaybackEvent> Events { get; init; } = [];

    public long TotalDurationMs => Math.Max(1, Events.Sum(item => item.IsRest ? (long)item.WaitMs : (long)item.HoldMs + item.WaitMs));

    internal bool IsVersionCompatible
    {
        get
        {
            var helperPrefix = VersionPrefix(HelperVersion);
            if (helperPrefix is null) return false;
            if (CompatibleHelperPrefixes.Count > 0)
            {
                return CompatibleHelperPrefixes.Any(prefix => string.Equals(prefix?.Trim(), helperPrefix, StringComparison.OrdinalIgnoreCase));
            }
            // Older webpages did not send an explicit compatibility matrix.
            // Keep accepting their original major/minor matching rule.
            return VersionPrefix(WebVersion) is string webPrefix && webPrefix == helperPrefix;
        }
    }

    internal string CompatibleHelperVersionLabel => CompatibleHelperPrefixes.Count > 0
        ? string.Join(" / ", CompatibleHelperPrefixes.Select(prefix => $"v{prefix}.x"))
        : $"v{VersionPrefix(HelperVersion)}.x";

    public static PlaybackRequest? FromProtocolArgument(string? argument)
    {
        if (string.IsNullOrWhiteSpace(argument) || !Uri.TryCreate(argument.Trim('"'), UriKind.Absolute, out var uri) || uri.Scheme != "harmonica-recorder") return null;
        var query = uri.Query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries)
            .Select(pair => pair.Split('=', 2))
            .Where(pair => pair.Length == 2)
            .ToDictionary(pair => pair[0], pair => pair[1], StringComparer.OrdinalIgnoreCase);
        query.TryGetValue("payload", out var payload);
        if (string.IsNullOrWhiteSpace(payload)) return null;

        try
        {
            var base64 = payload.Replace('-', '+').Replace('_', '/');
            base64 = base64.PadRight(base64.Length + (4 - base64.Length % 4) % 4, '=');
            var jsonBytes = Convert.FromBase64String(base64);
            if (query.TryGetValue("encoding", out var encoding) && encoding.Equals("gzip", StringComparison.OrdinalIgnoreCase))
            {
                using var compressed = new MemoryStream(jsonBytes);
                using var gzip = new GZipStream(compressed, CompressionMode.Decompress);
                using var decompressed = new MemoryStream();
                gzip.CopyTo(decompressed);
                jsonBytes = decompressed.ToArray();
            }
            var request = JsonSerializer.Deserialize<PlaybackRequest>(jsonBytes);
            return request?.IsValid() == true ? request : null;
        }
        catch (Exception)
        {
            return null;
        }
    }

    private bool IsValid() => Version == 1 && Events.Count is > 0 and <= 5000 && Events.All(item => item.IsValid());

    private static string? VersionPrefix(string? version)
    {
        var parts = version?.Trim().Split('.', StringSplitOptions.RemoveEmptyEntries);
        return parts is { Length: >= 2 } && int.TryParse(parts[0], out var major) && int.TryParse(parts[1], out var minor)
            ? $"{major}.{minor}"
            : null;
    }
}

internal sealed class PlaybackEvent
{
    [JsonPropertyName("k")]
    public string? Key { get; init; }

    [JsonPropertyName("m")]
    public string? Modifiers { get; init; }

    [JsonPropertyName("l")]
    public int LeadMs { get; init; }

    [JsonPropertyName("h")]
    public int HoldMs { get; init; }

    [JsonPropertyName("w")]
    public int WaitMs { get; init; }

    public bool IsRest => string.IsNullOrEmpty(Key);

    public bool IsValid()
    {
        if (LeadMs < 0 || HoldMs < 0 || WaitMs < 0 || LeadMs > 30_000 || HoldMs > 600_000 || WaitMs > 600_000) return false;
        if (IsRest) return WaitMs > 0;
        var modifiers = Modifiers ?? string.Empty;
        return Key is "z" or "x" or "c" or "v" or "b" or "n" or "m" or ","
            && modifiers.All(modifier => modifier is 'L' or 'M' or 'R')
            && new HashSet<char>(modifiers).Count == modifiers.Length
            && !(modifiers.Contains('L') && modifiers.Contains('R'));
    }
}

internal sealed class RecorderForm : Form
{
    private const string QqGroup = "1102489399";
    private const string UpdateManifestUrl = "https://jiko-official.top/delta/recording-helper/version.json";
    private const int HotKeyId = 1;
    private const int WmHotKey = 0x0312;
    private readonly PlaybackRequest? request;
    private readonly bool updateCompleted;
    private readonly Label titleLabel = new();
    private readonly Label detailsLabel = new();
    private readonly Label statusLabel = new();
    private readonly Label hotKeyLabel = new();
    private readonly TextBox hotKeyBox = new();
    private readonly Label inputModeLabel = new();
    private readonly ComboBox inputModeBox = new();
    private readonly Label progressLabel = new();
    private readonly ProgressBar progressBar = new();
    private readonly Label remainingLabel = new();
    private readonly Button startButton = new();
    private readonly Button stopButton = new();
    private CancellationTokenSource? cancellation;
    private string? activeKey;
    private readonly List<char> activeModifiers = [];
    private HotKeyOption activeHotKey = null!;
    private InputInjectionMode activeInputMode = null!;
    private InputInjectionMode activePlaybackInputMode = null!;
    private bool hotKeyRegistered;
    private long lastProgressReport = -1;

    public RecorderForm(PlaybackRequest? request, bool updateCompleted = false)
    {
        this.request = request;
        this.updateCompleted = updateCompleted;
        Text = "Harmonica Recorder";
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = true;
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(510, 388);
        BackColor = Color.FromArgb(8, 39, 37);
        ForeColor = Color.FromArgb(216, 255, 255);
        Font = new Font("Microsoft YaHei UI", 10F);

        var banner = new Label { Dock = DockStyle.Top, Height = 39, Text = $"  HARMONICA RECORDER.EXE  ·  v{PlaybackRequest.HelperVersion}  ·  QQ {QqGroup}", BackColor = Color.FromArgb(0, 123, 120), ForeColor = Color.White, Font = new Font("Consolas", 9F, FontStyle.Bold), TextAlign = ContentAlignment.MiddleLeft };
        titleLabel.SetBounds(22, 58, 466, 31);
        titleLabel.Font = new Font("Microsoft YaHei UI", 16F, FontStyle.Bold);
        detailsLabel.SetBounds(22, 96, 466, 38);
        detailsLabel.ForeColor = Color.FromArgb(170, 205, 202);
        detailsLabel.Font = new Font("Consolas", 9F);
        statusLabel.SetBounds(22, 147, 466, 55);
        statusLabel.BackColor = Color.FromArgb(12, 63, 60);
        statusLabel.BorderStyle = BorderStyle.FixedSingle;
        statusLabel.Padding = new Padding(10, 8, 10, 8);
        statusLabel.Font = new Font("Microsoft YaHei UI", 9F);
        hotKeyLabel.SetBounds(22, 214, 184, 27);
        hotKeyLabel.Text = "紧急停止快捷键（点击后按键）";
        hotKeyLabel.TextAlign = ContentAlignment.MiddleLeft;
        hotKeyBox.SetBounds(208, 211, 280, 29);
        hotKeyBox.ReadOnly = true;
        hotKeyBox.TabStop = true;
        hotKeyBox.TextAlign = HorizontalAlignment.Center;
        hotKeyBox.Text = "正在读取快捷键…";
        activeHotKey = EmergencyStopHotKeySettings.Load() ?? HotKeyOption.Default;
        hotKeyBox.Text = activeHotKey.DisplayName;
        inputModeLabel.SetBounds(22, 247, 184, 27);
        inputModeLabel.Text = "输入兼容模式（可逐项测试）";
        inputModeLabel.TextAlign = ContentAlignment.MiddleLeft;
        inputModeBox.SetBounds(208, 244, 280, 29);
        inputModeBox.DropDownStyle = ComboBoxStyle.DropDownList;
        inputModeBox.FlatStyle = FlatStyle.Flat;
        inputModeBox.DropDownWidth = 420;
        inputModeBox.Items.AddRange(InputInjectionMode.All);
        activeInputMode = InputInjectionMode.Default;
        inputModeBox.SelectedItem = activeInputMode;
        progressLabel.SetBounds(22, 280, 184, 27);
        progressLabel.Text = "录制进度 / 剩余时间";
        progressLabel.TextAlign = ContentAlignment.MiddleLeft;
        progressBar.SetBounds(208, 282, 180, 22);
        progressBar.Minimum = 0;
        progressBar.Maximum = 1000;
        progressBar.Value = 0;
        remainingLabel.SetBounds(394, 280, 94, 27);
        remainingLabel.Text = "剩余 --:--";
        remainingLabel.TextAlign = ContentAlignment.MiddleRight;
        startButton.SetBounds(278, 323, 138, 42);
        startButton.Text = "开始录制";
        startButton.BackColor = Color.FromArgb(0, 123, 120);
        startButton.ForeColor = Color.White;
        startButton.FlatStyle = FlatStyle.Flat;
        startButton.FlatAppearance.BorderColor = Color.FromArgb(91, 185, 178);
        stopButton.SetBounds(426, 323, 62, 42);
        stopButton.Text = "停止";
        stopButton.Enabled = false;
        stopButton.FlatStyle = FlatStyle.Flat;
        stopButton.FlatAppearance.BorderColor = Color.FromArgb(137, 92, 153);

        Controls.AddRange([banner, titleLabel, detailsLabel, statusLabel, hotKeyLabel, hotKeyBox, inputModeLabel, inputModeBox, progressLabel, progressBar, remainingLabel, startButton, stopButton]);
        startButton.Click += async (_, _) => await StartPlaybackAsync();
        stopButton.Click += (_, _) => StopPlayback("已停止，并已释放本助手按下的按键。");
        hotKeyBox.Enter += (_, _) => hotKeyBox.SelectAll();
        hotKeyBox.KeyDown += CaptureEmergencyStopHotKey;
        inputModeBox.SelectedIndexChanged += (_, _) => UpdateInputMode();
        FormClosing += (_, _) => StopPlayback("正在退出。");
        Shown += async (_, _) => await CheckForUpdatesAsync();
        if (updateCompleted) Shown += (_, _) => ShowUpdateCompletedNotice();

        if (request is null)
        {
            titleLabel.Text = "等待从网页导入曲谱";
            detailsLabel.Text = "请在网站的「口琴鼠标宏录制助手」卡片中点击“导出到宏录制助手”。";
            statusLabel.Text = $"首次使用：先运行安装包中的 Install.cmd 注册网页调用权限。\n紧急停止：{activeHotKey.DisplayName} · 反馈 QQ 群：{QqGroup}";
            startButton.Enabled = false;
        }
        else if (!request.IsVersionCompatible)
        {
            titleLabel.Text = "网页与助手版本不匹配";
            detailsLabel.Text = $"网页 v{request.WebVersion ?? "未知"} · 本助手 v{PlaybackRequest.HelperVersion}";
            statusLabel.Text = $"本网页声明兼容助手版本：{request.CompatibleHelperVersionLabel}，当前无法导入。\n请下载匹配版本的助手并运行 Install.cmd；反馈 QQ 群：{QqGroup}";
            startButton.Enabled = false;
            Shown += (_, _) => MessageBox.Show(this, $"网页版本：{request.WebVersion ?? "未知"}\n助手版本：{PlaybackRequest.HelperVersion}\n网页兼容范围：{request.CompatibleHelperVersionLabel}\n\n请下载兼容范围内的助手版本，并运行 Install.cmd。\n反馈 QQ 群：{QqGroup}", "版本不匹配", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
        else
        {
            titleLabel.Text = request.Title;
            detailsLabel.Text = $"已导入 {request.Events.Count} 个事件 · 总时长 {FormatDuration(request.TotalDurationMs)} · v{PlaybackRequest.HelperVersion}";
            statusLabel.Text = $"先在目标宏软件中打开录制，再回到本助手点击“开始录制”。\n录制期间请勿操作鼠标或键盘，并让鼠标焦点始终停留在本助手；紧急停止：{activeHotKey.DisplayName}";
        }
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        if (!RegisterEmergencyStopHotKey())
        {
            statusLabel.Text = $"无法注册紧急停止快捷键 {activeHotKey.DisplayName}。它可能已被其他软件占用，请选择其他组合。";
        }
    }

    private async Task CheckForUpdatesAsync()
    {
        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(6) };
            client.DefaultRequestHeaders.UserAgent.ParseAdd($"HarmonicaRecorder/{PlaybackRequest.HelperVersion}");
            var manifestJson = await client.GetStringAsync(UpdateManifestUrl);
            var manifest = JsonSerializer.Deserialize<RecorderUpdateManifest>(manifestJson);
            if (manifest is null || !Version.TryParse(manifest.Version, out var latest) || !Version.TryParse(PlaybackRequest.HelperVersion, out var current) || latest <= current) return;
            if (!Uri.TryCreate(manifest.DownloadUrl, UriKind.Absolute, out var downloadUri) || downloadUri.Scheme != Uri.UriSchemeHttps || string.IsNullOrWhiteSpace(manifest.Sha256)) return;

            var choice = MessageBox.Show(this, $"发现录制助手新版本 v{manifest.Version}。\n当前版本：v{PlaybackRequest.HelperVersion}\n\n是否下载并覆盖更新？", "发现新版本", MessageBoxButtons.YesNo, MessageBoxIcon.Information);
            if (choice == DialogResult.Yes)
            {
                var currentExecutable = Application.ExecutablePath;
                if (!ConfirmUpdatePreflight(currentExecutable)) return;
                await DownloadAndInstallUpdateAsync(manifest, downloadUri);
            }
        }
        catch (Exception)
        {
            // Update checks are best-effort and must not prevent recording when offline.
        }
    }

    private void ShowUpdateCompletedNotice()
    {
        statusLabel.Text = $"更新完成。当前版本：v{PlaybackRequest.HelperVersion}，新版本已经启动，可以继续使用。";
        MessageBox.Show(this,
            $"录制助手已更新完成。\n当前版本：v{PlaybackRequest.HelperVersion}\n\n新版本已经启动，可以继续使用。",
            "更新完成",
            MessageBoxButtons.OK,
            MessageBoxIcon.Information);
    }

    private async Task DownloadAndInstallUpdateAsync(RecorderUpdateManifest manifest, Uri downloadUri)
    {
        var updateRoot = Path.Combine(Path.GetTempPath(), $"HarmonicaRecorder-update-{Guid.NewGuid():N}");
        Directory.CreateDirectory(updateRoot);
        var archivePath = Path.Combine(updateRoot, "HarmonicaRecorder.zip");
        try
        {
            PrepareUpdateProgress(manifest.Version);
            using var client = new HttpClient { Timeout = TimeSpan.FromMinutes(5) };
            client.DefaultRequestHeaders.UserAgent.ParseAdd($"HarmonicaRecorder/{PlaybackRequest.HelperVersion}");
            using var response = await client.GetAsync(downloadUri, HttpCompletionOption.ResponseHeadersRead);
            response.EnsureSuccessStatusCode();
            var totalBytes = response.Content.Headers.ContentLength;
            var downloadedBytes = 0L;
            if (totalBytes is null or <= 0) progressBar.Style = ProgressBarStyle.Marquee;
            await using (var input = await response.Content.ReadAsStreamAsync())
            await using (var output = File.Create(archivePath))
            {
                var buffer = new byte[64 * 1024];
                int bytesRead;
                while ((bytesRead = await input.ReadAsync(buffer.AsMemory(0, buffer.Length))) > 0)
                {
                    await output.WriteAsync(buffer.AsMemory(0, bytesRead));
                    downloadedBytes += bytesRead;
                    if (totalBytes is > 0)
                    {
                        var percent = (int)Math.Clamp(downloadedBytes * 100 / totalBytes.Value, 0, 100);
                        progressBar.Value = percent;
                        remainingLabel.Text = $"{percent}%";
                        statusLabel.Text = $"正在下载助手 v{manifest.Version}… {FormatBytes(downloadedBytes)} / {FormatBytes(totalBytes.Value)}";
                    }
                    else
                    {
                        statusLabel.Text = $"正在下载助手 v{manifest.Version}… 已下载 {FormatBytes(downloadedBytes)}";
                    }
                }
            }

            progressBar.Style = ProgressBarStyle.Continuous;
            progressBar.Value = 85;
            remainingLabel.Text = "85%";
            statusLabel.Text = "正在校验更新包…";
            await using (var archive = File.OpenRead(archivePath))
            {
                var actualHash = Convert.ToHexString(await SHA256.HashDataAsync(archive));
                if (!actualHash.Equals(manifest.Sha256.Trim(), StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("更新包校验失败。");
            }

            progressBar.Value = 95;
            remainingLabel.Text = "95%";
            statusLabel.Text = "正在准备覆盖安装…";
            var extractRoot = Path.Combine(updateRoot, "new");
            ZipFile.ExtractToDirectory(archivePath, extractRoot);
            var newExecutable = Path.Combine(extractRoot, "HarmonicaRecorder.exe");
            if (!File.Exists(newExecutable)) throw new FileNotFoundException("更新包中没有找到 HarmonicaRecorder.exe。", newExecutable);

            var currentExecutable = Application.ExecutablePath;
            var scriptPath = Path.Combine(updateRoot, "update.ps1");
            await File.WriteAllTextAsync(scriptPath, BuildUpdateScript(), new UTF8Encoding(encoderShouldEmitUTF8Identifier: true));
            var updater = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                UseShellExecute = false,
                CreateNoWindow = true
            };
            updater.ArgumentList.Add("-NoProfile");
            updater.ArgumentList.Add("-ExecutionPolicy");
            updater.ArgumentList.Add("Bypass");
            updater.ArgumentList.Add("-File");
            updater.ArgumentList.Add(scriptPath);
            updater.ArgumentList.Add("-ProcessId");
            updater.ArgumentList.Add(Environment.ProcessId.ToString());
            updater.ArgumentList.Add("-SourcePath");
            updater.ArgumentList.Add(newExecutable);
            updater.ArgumentList.Add("-TargetPath");
            updater.ArgumentList.Add(currentExecutable);
            updater.ArgumentList.Add("-ExpectedVersion");
            updater.ArgumentList.Add(manifest.Version);
            Process.Start(updater);
            progressBar.Value = 100;
            remainingLabel.Text = "100%";
            statusLabel.Text = "更新已下载，正在覆盖安装并重启…";
            Application.Exit();
        }
        catch (Exception error)
        {
            RestoreRecorderProgress();
            statusLabel.Text = "更新失败，当前版本仍可继续使用。";
            MessageBox.Show(this, $"自动更新失败：{error.Message}\n\n请从网页重新下载最新版助手。", "更新失败", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }

    private bool ConfirmUpdatePreflight(string currentExecutable)
    {
        var blockingIssues = new List<string>();
        var warnings = new List<string>();
        var otherInstances = FindOtherHelperInstances(currentExecutable);
        if (otherInstances.Count > 0)
        {
            var processLabel = otherInstances.Count == 1 ? "1 个" : $"{otherInstances.Count} 个";
            blockingIssues.Add($"检测到同一安装目录还有 {processLabel} HarmonicaRecorder.exe 进程运行。\n请先关闭其他助手窗口后再更新。\n\n这会导致旧 EXE 仍被占用，覆盖安装无法完成。");
        }

        var targetDirectory = Path.GetDirectoryName(currentExecutable);
        if (string.IsNullOrWhiteSpace(targetDirectory))
        {
            blockingIssues.Add("无法确定助手所在目录，暂时不能安全更新。");
        }
        else
        {
            if (IsProtectedInstallDirectory(targetDirectory))
            {
                blockingIssues.Add($"助手位于受保护目录：\n{targetDirectory}\n\nProgram Files 或 Windows 目录通常不允许普通用户直接覆盖 EXE。请把助手移动到“文档”等可写目录后，再运行 Install.cmd。");
            }
            else if (!CanWriteToDirectory(targetDirectory))
            {
                blockingIssues.Add($"当前账号没有权限写入助手目录：\n{targetDirectory}\n\n请将助手移动到有写权限的目录，或检查文件夹安全权限。");
            }

            var specialCharacters = FindCommandSpecialCharacters(currentExecutable);
            if (specialCharacters.Length > 0)
            {
                warnings.Add($"检测到安装路径包含命令特殊字符：{specialCharacters}\n本次将使用安全的字面量路径更新方式；如果仍失败，建议移动到不含这些字符的目录。");
            }
        }

        if (blockingIssues.Count > 0)
        {
            MessageBox.Show(this, string.Join("\n\n", blockingIssues), "无法开始自动更新", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return false;
        }

        if (warnings.Count > 0)
        {
            var choice = MessageBox.Show(this, string.Join("\n\n", warnings) + "\n\n是否继续更新？", "更新路径检查", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
            return choice == DialogResult.Yes;
        }

        return true;
    }

    private static List<int> FindOtherHelperInstances(string currentExecutable)
    {
        var currentPath = NormalizePath(currentExecutable);
        var processName = Path.GetFileNameWithoutExtension(currentExecutable);
        var matches = new List<int>();
        foreach (var process in Process.GetProcessesByName(processName))
        {
            try
            {
                if (process.Id == Environment.ProcessId) continue;
                var processPath = process.MainModule?.FileName;
                if (string.IsNullOrWhiteSpace(processPath) || string.Equals(NormalizePath(processPath), currentPath, StringComparison.OrdinalIgnoreCase)) matches.Add(process.Id);
            }
            catch (Exception)
            {
                // An inaccessible same-named process may still be holding the EXE.
                matches.Add(process.Id);
            }
            finally
            {
                process.Dispose();
            }
        }

        return matches;
    }

    private static bool CanWriteToDirectory(string directory)
    {
        var probePath = Path.Combine(directory, $".harmonica-recorder-write-test-{Guid.NewGuid():N}.tmp");
        try
        {
            using (new FileStream(probePath, FileMode.CreateNew, FileAccess.Write, FileShare.None, 1, FileOptions.SequentialScan)) { }
            File.Delete(probePath);
            return true;
        }
        catch (Exception) when (File.Exists(probePath))
        {
            try { File.Delete(probePath); } catch { }
            return false;
        }
        catch (UnauthorizedAccessException)
        {
            return false;
        }
        catch (IOException)
        {
            return false;
        }
    }

    private static bool IsProtectedInstallDirectory(string directory)
    {
        var protectedDirectories = new[]
        {
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
            Environment.GetFolderPath(Environment.SpecialFolder.Windows)
        };
        return protectedDirectories.Any(path => !string.IsNullOrWhiteSpace(path) && IsPathWithin(directory, path));
    }

    private static bool IsPathWithin(string path, string parent)
    {
        var normalizedPath = NormalizePath(path);
        var normalizedParent = NormalizePath(parent);
        return string.Equals(normalizedPath, normalizedParent, StringComparison.OrdinalIgnoreCase)
            || normalizedPath.StartsWith(normalizedParent + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
    }

    private static string FindCommandSpecialCharacters(string path)
    {
        return new string(path.Where(character => character is '%' or '!' or '&' or '^' or '(' or ')').Distinct().ToArray());
    }

    private static string NormalizePath(string path)
    {
        return Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
    }

    private static string BuildUpdateScript()
    {
        return """
param(
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [Parameter(Mandatory = $true)][string]$SourcePath,
    [Parameter(Mandatory = $true)][string]$TargetPath,
    [Parameter(Mandatory = $true)][string]$ExpectedVersion
)

$ErrorActionPreference = 'Stop'
$maxAttempts = 20
$attempt = 0

function Show-UpdateFailure([string]$Details) {
    $message = "自动更新失败。`n`n可能原因：`n· 还有其他 HarmonicaRecorder 窗口或进程运行；`n· 安装目录没有写权限；`n· Windows Defender 或杀毒软件暂时锁定了文件。`n`n请关闭所有助手窗口，确认目录可写；如果仍失败，请把助手移动到“文档”等普通目录后重试。`n`n详细信息：$Details"
    try {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($message, 'Harmonica Recorder 更新失败', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
    } catch {
        Write-Error $message
    }
}

try {
    while (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        Start-Sleep -Milliseconds 250
    }

    $targetFullPath = [IO.Path]::GetFullPath($TargetPath)
    $processName = [IO.Path]::GetFileNameWithoutExtension($TargetPath)
    $conflicts = @(Get-Process -Name $processName -ErrorAction SilentlyContinue | Where-Object {
        if ($_.Id -eq $ProcessId) { return $false }
        try { return [string]::Equals([IO.Path]::GetFullPath($_.Path), $targetFullPath, [StringComparison]::OrdinalIgnoreCase) }
        catch { return $true }
    })
    if ($conflicts.Count -gt 0) { throw "检测到其他 HarmonicaRecorder 进程仍在运行。" }

    do {
        try {
            Copy-Item -LiteralPath $SourcePath -Destination $TargetPath -Force -ErrorAction Stop
            $attempt = $maxAttempts
        } catch {
            $attempt++
            if ($attempt -ge $maxAttempts) { throw }
            Start-Sleep -Milliseconds 750
        }
    } while ($attempt -lt $maxAttempts)

    if (-not (Test-Path -LiteralPath $TargetPath -PathType Leaf)) { throw '覆盖后没有找到 HarmonicaRecorder.exe。' }
    $actualVersion = [version](Get-Item -LiteralPath $TargetPath).VersionInfo.FileVersion
    if ($actualVersion -lt [version]$ExpectedVersion) { throw "覆盖后的助手版本仍为 $actualVersion，期望至少为 $ExpectedVersion。" }
    Start-Process -FilePath $TargetPath -ArgumentList '--update-complete'
} catch {
    Show-UpdateFailure $_.Exception.Message
    try { Start-Process -FilePath $TargetPath } catch { }
}

try { Remove-Item -LiteralPath $PSScriptRoot -Recurse -Force -ErrorAction SilentlyContinue } catch { }
""";
    }

    private void PrepareUpdateProgress(string version)
    {
        progressLabel.Text = "更新进度";
        progressBar.Style = ProgressBarStyle.Continuous;
        progressBar.Value = 0;
        remainingLabel.Text = "0%";
        statusLabel.Text = $"正在下载助手 v{version}… 请稍候。";
        startButton.Enabled = false;
        stopButton.Enabled = false;
        inputModeBox.Enabled = false;
        hotKeyBox.Enabled = false;
    }

    private void RestoreRecorderProgress()
    {
        progressLabel.Text = "录制进度 / 剩余时间";
        progressBar.Style = ProgressBarStyle.Continuous;
        progressBar.Value = 0;
        remainingLabel.Text = request is null ? "剩余 --:--" : $"剩余 {FormatDuration(request.TotalDurationMs)}";
        startButton.Enabled = request?.IsVersionCompatible == true;
        stopButton.Enabled = false;
        inputModeBox.Enabled = true;
        hotKeyBox.Enabled = true;
    }

    private static string FormatBytes(long bytes)
    {
        if (bytes < 1024 * 1024) return $"{Math.Max(1, bytes / 1024)} KB";
        return $"{bytes / 1024d / 1024d:0.0} MB";
    }

    protected override void OnHandleDestroyed(EventArgs e)
    {
        if (hotKeyRegistered) NativeInput.UnregisterHotKey(Handle, HotKeyId);
        hotKeyRegistered = false;
        base.OnHandleDestroyed(e);
    }

    protected override void WndProc(ref Message message)
    {
        if (message.Msg == WmHotKey && message.WParam.ToInt32() == HotKeyId) StopPlayback($"已通过 {activeHotKey.DisplayName} 停止。");
        base.WndProc(ref message);
    }

    private void CaptureEmergencyStopHotKey(object? sender, KeyEventArgs e)
    {
        e.SuppressKeyPress = true;
        e.Handled = true;
        if (e.KeyCode is Keys.ControlKey or Keys.ShiftKey or Keys.Menu or Keys.LWin or Keys.RWin) return;

        var modifiers = NativeInput.ModifiersFromKeys(e.Modifiers);
        var selectedHotKey = new HotKeyOption(HotKeyOption.FormatDisplayName(modifiers, (uint)e.KeyCode), modifiers, (uint)e.KeyCode);
        if (selectedHotKey == activeHotKey) return;
        var previousHotKey = activeHotKey;
        activeHotKey = selectedHotKey;
        if (IsHandleCreated && !RegisterEmergencyStopHotKey())
        {
            activeHotKey = previousHotKey;
            hotKeyBox.Text = previousHotKey.DisplayName;
            RegisterEmergencyStopHotKey();
            MessageBox.Show(this, $"无法注册 {selectedHotKey.DisplayName}，它可能已被其他软件占用。已恢复为 {previousHotKey.DisplayName}。", "快捷键不可用", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        hotKeyBox.Text = activeHotKey.DisplayName;
        EmergencyStopHotKeySettings.Save(activeHotKey);
        if (cancellation is null) statusLabel.Text = $"紧急停止快捷键已设为 {activeHotKey.DisplayName}。";
    }

    private bool RegisterEmergencyStopHotKey()
    {
        if (hotKeyRegistered) NativeInput.UnregisterHotKey(Handle, HotKeyId);
        hotKeyRegistered = NativeInput.RegisterHotKey(Handle, HotKeyId, activeHotKey.Modifiers | NativeInput.ModNoRepeat, activeHotKey.VirtualKey);
        return hotKeyRegistered;
    }

    private void UpdateInputMode()
    {
        if (inputModeBox.SelectedItem is not InputInjectionMode selectedInputMode) return;
        activeInputMode = selectedInputMode;
        if (cancellation is null) statusLabel.Text = $"已选择：{activeInputMode.DisplayName}\n{activeInputMode.Description}";
    }

    private async Task StartPlaybackAsync()
    {
        if (request is null || cancellation is not null) return;
        cancellation = new CancellationTokenSource();
        activePlaybackInputMode = activeInputMode;
        lastProgressReport = -1;
        startButton.Enabled = false;
        stopButton.Enabled = true;
        inputModeBox.Enabled = false;
        hotKeyBox.Enabled = false;
        progressBar.Value = 0;
        remainingLabel.Text = $"剩余 {FormatDuration(request.TotalDurationMs)}";
        try
        {
            statusLabel.Text = $"正在录制… {activePlaybackInputMode.DisplayName}\n请勿操作鼠标或键盘，并保持鼠标焦点在本助手。紧急停止：{activeHotKey.DisplayName}";
            await Task.Run(() => Play(request.Events, cancellation.Token, activePlaybackInputMode, ReportPlaybackProgress), cancellation.Token);
            if (!cancellation.IsCancellationRequested)
            {
                ApplyPlaybackProgress(request.TotalDurationMs, completed: true);
                statusLabel.Text = "录制完成。请回到宏软件停止录制并保存。";
                var result = MessageBox.Show(this, "录制完成。\n\n请回到宏录制软件停止录制并保存宏。\n录制开头由你点击本助手“开始录制”产生的一次鼠标按下/放开，请删除这两个事件。\n\n点击“确定”后关闭本助手。", "录制完成", MessageBoxButtons.OK, MessageBoxIcon.Information);
                if (result == DialogResult.OK) Close();
            }
        }
        catch (OperationCanceledException) { }
        finally
        {
            ReleaseActiveInputs();
            cancellation?.Dispose();
            cancellation = null;
            startButton.Enabled = request is not null;
            stopButton.Enabled = false;
            inputModeBox.Enabled = true;
            hotKeyBox.Enabled = true;
        }
    }

    private void Play(IEnumerable<PlaybackEvent> events, CancellationToken token, InputInjectionMode inputMode, Action<long> reportProgress)
    {
        var clock = Stopwatch.StartNew();
        var plannedElapsed = 0L;
        var highResolutionTimer = NativeInput.BeginHighResolutionTimer();
        try
        {
            foreach (var item in events)
            {
                token.ThrowIfCancellationRequested();
                if (item.IsRest)
                {
                    plannedElapsed = Wait(item.WaitMs, token, clock, plannedElapsed, reportProgress);
                    continue;
                }
                foreach (var modifier in item.Modifiers ?? string.Empty)
                {
                    NativeInput.Mouse(modifier, true, inputMode);
                    activeModifiers.Add(modifier);
                }
                plannedElapsed = Wait(item.LeadMs, token, clock, plannedElapsed, reportProgress);
                activeKey = item.Key;
                NativeInput.Key(item.Key!, true, inputMode);
                plannedElapsed = Wait(Math.Max(0, item.HoldMs - item.LeadMs), token, clock, plannedElapsed, reportProgress);
                NativeInput.Key(item.Key!, false, inputMode);
                activeKey = null;
                for (var index = activeModifiers.Count - 1; index >= 0; index--) NativeInput.Mouse(activeModifiers[index], false, inputMode);
                activeModifiers.Clear();
                plannedElapsed = Wait(item.WaitMs, token, clock, plannedElapsed, reportProgress);
            }
        }
        finally
        {
            if (highResolutionTimer) NativeInput.EndHighResolutionTimer();
        }
    }

    private void ReportPlaybackProgress(long elapsedMilliseconds)
    {
        if (elapsedMilliseconds - lastProgressReport < 50 && elapsedMilliseconds > 0) return;
        lastProgressReport = elapsedMilliseconds;
        if (!IsHandleCreated || IsDisposed) return;
        try { BeginInvoke(new Action(() => ApplyPlaybackProgress(elapsedMilliseconds))); } catch (InvalidOperationException) { }
    }

    private void ApplyPlaybackProgress(long elapsedMilliseconds, bool completed = false)
    {
        if (request is null || cancellation?.IsCancellationRequested == true) return;
        var total = request.TotalDurationMs;
        var elapsed = Math.Clamp(elapsedMilliseconds, 0, completed ? total : Math.Max(0, total - 1));
        progressBar.Value = (int)Math.Clamp(elapsed * progressBar.Maximum / total, 0, progressBar.Maximum);
        remainingLabel.Text = $"剩余 {FormatDuration(completed ? 0 : Math.Max(1, total - elapsed))}";
    }

    private static long Wait(int milliseconds, CancellationToken token, Stopwatch clock, long plannedStart, Action<long> reportProgress)
    {
        var target = plannedStart + Math.Max(0, milliseconds);
        while (true)
        {
            token.ThrowIfCancellationRequested();
            var remaining = target - clock.ElapsedMilliseconds;
            if (remaining <= 0) break;
            // Sleep in short slices against an absolute deadline.  The
            // elapsed clock, rather than the requested sleep duration, is the
            // source of truth, so OS timer rounding cannot accumulate drift.
            NativeInput.SleepMilliseconds((uint)Math.Min(remaining, remaining > 2 ? 2 : 1));
            reportProgress(Math.Min(target, clock.ElapsedMilliseconds));
        }
        reportProgress(Math.Min(target, clock.ElapsedMilliseconds));
        return target;
    }

    private static string FormatDuration(long milliseconds)
    {
        var seconds = Math.Max(0, (milliseconds + 999) / 1000);
        return $"{seconds / 60:00}:{seconds % 60:00}";
    }

    private void StopPlayback(string message)
    {
        cancellation?.Cancel();
        ReleaseActiveInputs();
        statusLabel.Text = message;
    }

    private void ReleaseActiveInputs()
    {
        if (activeKey is not null)
        {
            NativeInput.Key(activeKey, false, activePlaybackInputMode);
            activeKey = null;
        }
        for (var index = activeModifiers.Count - 1; index >= 0; index--) NativeInput.Mouse(activeModifiers[index], false, activePlaybackInputMode);
        activeModifiers.Clear();
    }
}

internal sealed record RecorderUpdateManifest(
    [property: JsonPropertyName("version")] string Version,
    [property: JsonPropertyName("downloadUrl")] string DownloadUrl,
    [property: JsonPropertyName("sha256")] string Sha256);

internal sealed record HotKeyOption(string DisplayName, uint Modifiers, uint VirtualKey)
{
    internal static readonly HotKeyOption Default = new("Ctrl + Alt + End", NativeInput.ModControl | NativeInput.ModAlt, NativeInput.VkEnd);

    internal static string FormatDisplayName(uint modifiers, uint virtualKey)
    {
        var parts = new List<string>();
        if ((modifiers & NativeInput.ModControl) != 0) parts.Add("Ctrl");
        if ((modifiers & NativeInput.ModAlt) != 0) parts.Add("Alt");
        if ((modifiers & NativeInput.ModShift) != 0) parts.Add("Shift");
        if ((modifiers & NativeInput.ModWin) != 0) parts.Add("Win");
        var key = (Keys)virtualKey;
        parts.Add(key switch
        {
            Keys.Return => "Enter",
            Keys.Prior => "PageUp",
            Keys.Next => "PageDown",
            Keys.PrintScreen => "PrintScreen",
            Keys.Oemcomma => ",",
            Keys.OemPeriod => ".",
            _ => key.ToString()
        });
        return string.Join(" + ", parts);
    }

    public override string ToString() => DisplayName;
}

internal enum KeyboardInjectionMode
{
    LegacyScanCode,
    LegacyVirtualKey,
    SendInputVirtualKey,
    SendInputScanCode
}

internal enum MouseInjectionMode
{
    LegacyMouseEvent,
    SendInput
}

internal sealed record InputInjectionMode(
    string DisplayName,
    string Description,
    KeyboardInjectionMode KeyboardMode,
    MouseInjectionMode MouseMode)
{
    internal static readonly InputInjectionMode Default = new(
        "默认兼容 · keybd_event 扫描码 + mouse_event",
        "旧式扫描码键盘 + 旧式鼠标事件；建议先从这里开始。",
        KeyboardInjectionMode.LegacyScanCode,
        MouseInjectionMode.LegacyMouseEvent);

    internal static readonly InputInjectionMode LegacyVirtualKey = new(
        "兼容虚拟键 · keybd_event 虚拟键 + mouse_event",
        "旧式虚拟键键盘 + 旧式鼠标事件；适合只识别虚拟键的录制器。",
        KeyboardInjectionMode.LegacyVirtualKey,
        MouseInjectionMode.LegacyMouseEvent);

    internal static readonly InputInjectionMode StandardSendInput = new(
        "标准 SendInput · 虚拟键 + SendInput 鼠标",
        "现代虚拟键键盘 + 现代鼠标事件；适合大多数通用宏软件。",
        KeyboardInjectionMode.SendInputVirtualKey,
        MouseInjectionMode.SendInput);

    internal static readonly InputInjectionMode MchoseCompatible = new(
        "迈从兼容 · SendInput 扫描码 + 鼠标",
        "现代扫描码键盘 + 现代鼠标事件；迈从可优先尝试。",
        KeyboardInjectionMode.SendInputScanCode,
        MouseInjectionMode.SendInput);

    internal static readonly InputInjectionMode LegacyKeyboardSendInputMouse = new(
        "混合 A · keybd_event 扫描码 + SendInput 鼠标",
        "旧式扫描码键盘 + 现代鼠标事件；用于拆开排查键盘或鼠标捕获。",
        KeyboardInjectionMode.LegacyScanCode,
        MouseInjectionMode.SendInput);

    internal static readonly InputInjectionMode LegacyVirtualKeySendInputMouse = new(
        "混合 B · keybd_event 虚拟键 + SendInput 鼠标",
        "旧式虚拟键键盘 + 现代鼠标事件；用于拆开排查键盘或鼠标捕获。",
        KeyboardInjectionMode.LegacyVirtualKey,
        MouseInjectionMode.SendInput);

    internal static readonly InputInjectionMode SendInputKeyboardLegacyMouse = new(
        "混合 C · SendInput 虚拟键 + mouse_event",
        "现代虚拟键键盘 + 旧式鼠标事件；兼容只抓取传统鼠标事件的录制器。",
        KeyboardInjectionMode.SendInputVirtualKey,
        MouseInjectionMode.LegacyMouseEvent);

    internal static readonly InputInjectionMode SendInputScanCodeLegacyMouse = new(
        "混合 D · SendInput 扫描码 + mouse_event",
        "现代扫描码键盘 + 旧式鼠标事件；迈从仍无响应时可尝试。",
        KeyboardInjectionMode.SendInputScanCode,
        MouseInjectionMode.LegacyMouseEvent);

    internal static readonly InputInjectionMode[] All =
    [
        Default,
        LegacyVirtualKey,
        StandardSendInput,
        MchoseCompatible,
        LegacyKeyboardSendInputMouse,
        LegacyVirtualKeySendInputMouse,
        SendInputKeyboardLegacyMouse,
        SendInputScanCodeLegacyMouse
    ];

    public override string ToString() => DisplayName;
}

internal static class EmergencyStopHotKeySettings
{
    private const string FileName = "emergency-stop-hotkey.json";

    internal static HotKeyOption? Load()
    {
        try
        {
            var saved = JsonSerializer.Deserialize<StoredHotKey>(File.ReadAllText(SettingsPath));
            if (saved is null || saved.VirtualKey == 0) return null;
            var displayName = string.IsNullOrWhiteSpace(saved.DisplayName)
                ? HotKeyOption.FormatDisplayName(saved.Modifiers, saved.VirtualKey)
                : saved.DisplayName;
            return new HotKeyOption(displayName, saved.Modifiers, saved.VirtualKey);
        }
        catch (Exception)
        {
            return null;
        }
    }

    internal static void Save(HotKeyOption hotKey)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
            File.WriteAllText(SettingsPath, JsonSerializer.Serialize(new StoredHotKey(hotKey.DisplayName, hotKey.Modifiers, hotKey.VirtualKey)));
        }
        catch (Exception)
        {
            // The selection remains active for this run even if Windows blocks settings persistence.
        }
    }

    private static string SettingsPath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "HarmonicaRecorder", FileName);

    private sealed record StoredHotKey(string? DisplayName, uint Modifiers, uint VirtualKey);
}

internal static class NativeInput
{
    internal const uint ModAlt = 0x0001;
    internal const uint ModControl = 0x0002;
    internal const uint ModShift = 0x0004;
    internal const uint ModWin = 0x0008;
    internal const uint ModNoRepeat = 0x4000;
    internal const uint VkEnd = 0x23;
    internal const uint VkPause = 0x13;

    internal static uint ModifiersFromKeys(Keys modifiers)
    {
        var result = 0u;
        if ((modifiers & Keys.Control) != 0) result |= ModControl;
        if ((modifiers & Keys.Alt) != 0) result |= ModAlt;
        if ((modifiers & Keys.Shift) != 0) result |= ModShift;
        if ((modifiers & Keys.LWin) != 0 || (modifiers & Keys.RWin) != 0) result |= ModWin;
        return result;
    }
    private const uint InputMouse = 0;
    private const uint InputKeyboard = 1;
    private const uint KeyUp = 0x0002;
    private const uint KeyScanCode = 0x0008;
    private const uint LeftDown = 0x0002;
    private const uint LeftUp = 0x0004;
    private const uint MiddleDown = 0x0020;
    private const uint MiddleUp = 0x0040;
    private const uint RightDown = 0x0008;
    private const uint RightUp = 0x0010;

    [DllImport("kernel32.dll")]
    private static extern void Sleep(uint milliseconds);

    [DllImport("winmm.dll")]
    private static extern uint timeBeginPeriod(uint period);

    [DllImport("winmm.dll")]
    private static extern uint timeEndPeriod(uint period);

    [DllImport("user32.dll", SetLastError = true)]
    internal static extern bool RegisterHotKey(IntPtr handle, int id, uint modifiers, uint key);

    [DllImport("user32.dll", SetLastError = true)]
    internal static extern bool UnregisterHotKey(IntPtr handle, int id);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint inputCount, INPUT[] inputs, int size);

    [DllImport("user32.dll")]
    private static extern void keybd_event(byte virtualKey, byte scanCode, uint flags, UIntPtr extraInfo);

    [DllImport("user32.dll")]
    private static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extraInfo);

    internal static void SleepMilliseconds(uint milliseconds) => Sleep(milliseconds);

    internal static bool BeginHighResolutionTimer() => timeBeginPeriod(1) == 0;

    internal static void EndHighResolutionTimer() => timeEndPeriod(1);

    internal static void Key(string key, bool down, InputInjectionMode inputMode)
    {
        var (virtualKey, scanCode) = key switch
        {
            "z" => (0x5A, 44), "x" => (0x58, 45), "c" => (0x43, 46), "v" => (0x56, 47),
            "b" => (0x42, 48), "n" => (0x4E, 49), "m" => (0x4D, 50), "," => (0xBC, 51),
            _ => throw new ArgumentOutOfRangeException(nameof(key))
        };
        var flags = down ? 0u : KeyUp;
        switch (inputMode.KeyboardMode)
        {
            case KeyboardInjectionMode.LegacyScanCode:
                keybd_event(0, (byte)scanCode, KeyScanCode | flags, UIntPtr.Zero);
                return;
            case KeyboardInjectionMode.LegacyVirtualKey:
                keybd_event((byte)virtualKey, 0, flags, UIntPtr.Zero);
                return;
            case KeyboardInjectionMode.SendInputScanCode:
                Send([new INPUT { Type = InputKeyboard, Union = new InputUnion { Keyboard = new KEYBDINPUT { VirtualKey = 0, ScanCode = (ushort)scanCode, Flags = KeyScanCode | flags } } }]);
                return;
            case KeyboardInjectionMode.SendInputVirtualKey:
                Send([new INPUT { Type = InputKeyboard, Union = new InputUnion { Keyboard = new KEYBDINPUT { VirtualKey = (ushort)virtualKey, Flags = flags } } }]);
                return;
            default:
                throw new ArgumentOutOfRangeException(nameof(inputMode.KeyboardMode));
        }
    }

    internal static void Mouse(char modifier, bool down, InputInjectionMode inputMode)
    {
        var flag = modifier switch { 'L' => down ? LeftDown : LeftUp, 'M' => down ? MiddleDown : MiddleUp, 'R' => down ? RightDown : RightUp, _ => throw new ArgumentOutOfRangeException(nameof(modifier)) };
        if (inputMode.MouseMode == MouseInjectionMode.LegacyMouseEvent)
        {
            mouse_event(flag, 0, 0, 0, UIntPtr.Zero);
            return;
        }
        Send([new INPUT { Type = InputMouse, Union = new InputUnion { Mouse = new MOUSEINPUT { Flags = flag } } }]);
    }

    private static void Send(INPUT[] inputs)
    {
        var sent = SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<INPUT>());
        if (sent != (uint)inputs.Length)
        {
            var error = Marshal.GetLastWin32Error();
            throw new InvalidOperationException($"Windows 拒绝了模拟输入（错误码 {error}）。");
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct INPUT { public uint Type; public InputUnion Union; }

    [StructLayout(LayoutKind.Explicit)]
    private struct InputUnion { [FieldOffset(0)] public MOUSEINPUT Mouse; [FieldOffset(0)] public KEYBDINPUT Keyboard; }

    [StructLayout(LayoutKind.Sequential)]
    private struct MOUSEINPUT { public int Dx; public int Dy; public uint MouseData; public uint Flags; public uint Time; public IntPtr ExtraInfo; }

    [StructLayout(LayoutKind.Sequential)]
    private struct KEYBDINPUT { public ushort VirtualKey; public ushort ScanCode; public uint Flags; public uint Time; public IntPtr ExtraInfo; }
}
