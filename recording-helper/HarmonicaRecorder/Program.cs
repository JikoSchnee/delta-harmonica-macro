using System.Runtime.InteropServices;
using System.IO.Compression;
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
        Application.Run(new RecorderForm(request));
    }
}

internal sealed class PlaybackRequest
{
    [JsonPropertyName("v")]
    public int Version { get; init; }

    [JsonPropertyName("title")]
    public string Title { get; init; } = "当前曲谱";

    [JsonPropertyName("events")]
    public List<PlaybackEvent> Events { get; init; } = [];

    public long TotalDurationMs => Math.Max(1, Events.Sum(item => item.IsRest ? (long)item.WaitMs : (long)item.HoldMs + item.WaitMs));

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
    private const int HotKeyId = 1;
    private const int WmHotKey = 0x0312;
    private readonly PlaybackRequest? request;
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

    public RecorderForm(PlaybackRequest? request)
    {
        this.request = request;
        Text = "Harmonica Recorder";
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = true;
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(510, 388);
        BackColor = Color.FromArgb(8, 39, 37);
        ForeColor = Color.FromArgb(216, 255, 255);
        Font = new Font("Microsoft YaHei UI", 10F);

        var banner = new Label { Dock = DockStyle.Top, Height = 39, Text = "  HARMONICA RECORDER.EXE  ·  INPUT ONLY", BackColor = Color.FromArgb(0, 123, 120), ForeColor = Color.White, Font = new Font("Consolas", 9F, FontStyle.Bold), TextAlign = ContentAlignment.MiddleLeft };
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
        inputModeLabel.Text = "输入兼容模式";
        inputModeLabel.TextAlign = ContentAlignment.MiddleLeft;
        inputModeBox.SetBounds(208, 244, 280, 29);
        inputModeBox.DropDownStyle = ComboBoxStyle.DropDownList;
        inputModeBox.FlatStyle = FlatStyle.Flat;
        inputModeBox.Items.Add(InputInjectionMode.GHubCompatible);
        inputModeBox.Items.Add(InputInjectionMode.StandardSendInput);
        activeInputMode = InputInjectionMode.GHubCompatible;
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

        if (request is null)
        {
            titleLabel.Text = "等待从网页导入曲谱";
            detailsLabel.Text = "请在网站的「口琴鼠标宏录制助手」卡片中点击“导出到宏录制助手”。";
            statusLabel.Text = $"首次使用：先运行安装包中的 Install.cmd 注册网页调用权限。\n紧急停止快捷键：{activeHotKey.DisplayName}";
            startButton.Enabled = false;
        }
        else
        {
            titleLabel.Text = request.Title;
            detailsLabel.Text = $"已导入 {request.Events.Count} 个事件 · 总时长 {FormatDuration(request.TotalDurationMs)}";
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
        if (cancellation is null) statusLabel.Text = $"已选择 {activeInputMode.DisplayName}。G HUB 录制请优先使用“G HUB 兼容”。";
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
            statusLabel.Text = $"正在录制… 请勿操作鼠标或键盘，并保持鼠标焦点在本助手。\n紧急停止：{activeHotKey.DisplayName}";
            await Task.Run(() => Play(request.Events, cancellation.Token, activePlaybackInputMode, ReportPlaybackProgress), cancellation.Token);
            if (!cancellation.IsCancellationRequested)
            {
                ApplyPlaybackProgress(request.TotalDurationMs, completed: true);
                statusLabel.Text = "录制完成。请回到宏软件停止录制并保存。";
                MessageBox.Show(this, "录制完成。\n\n请回到宏录制软件停止录制并保存宏。\n录制开头由你点击本助手“开始录制”产生的一次鼠标按下/放开，请删除这两个事件。", "录制完成", MessageBoxButtons.OK, MessageBoxIcon.Information);
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
        var plannedElapsed = 0L;
        foreach (var item in events)
        {
            token.ThrowIfCancellationRequested();
            if (item.IsRest)
            {
                plannedElapsed = Wait(item.WaitMs, token, plannedElapsed, reportProgress);
                continue;
            }
            foreach (var modifier in item.Modifiers ?? string.Empty)
            {
                NativeInput.Mouse(modifier, true, inputMode);
                activeModifiers.Add(modifier);
            }
            plannedElapsed = Wait(item.LeadMs, token, plannedElapsed, reportProgress);
            activeKey = item.Key;
            NativeInput.Key(item.Key!, true, inputMode);
            plannedElapsed = Wait(Math.Max(0, item.HoldMs - item.LeadMs), token, plannedElapsed, reportProgress);
            NativeInput.Key(item.Key!, false, inputMode);
            activeKey = null;
            for (var index = activeModifiers.Count - 1; index >= 0; index--) NativeInput.Mouse(activeModifiers[index], false, inputMode);
            activeModifiers.Clear();
            plannedElapsed = Wait(item.WaitMs, token, plannedElapsed, reportProgress);
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

    private static long Wait(int milliseconds, CancellationToken token, long plannedStart, Action<long> reportProgress)
    {
        var remaining = milliseconds;
        var progressed = 0;
        while (remaining > 0)
        {
            token.ThrowIfCancellationRequested();
            var slice = Math.Min(remaining, 10);
            Thread.Sleep(slice);
            remaining -= slice;
            progressed += slice;
            reportProgress(plannedStart + progressed);
        }
        return plannedStart + milliseconds;
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

internal sealed record InputInjectionMode(string DisplayName, bool UseLegacyScanCodeEvents)
{
    internal static readonly InputInjectionMode GHubCompatible = new("G HUB 兼容 · 扫描码事件（推荐）", true);
    internal static readonly InputInjectionMode StandardSendInput = new("标准 SendInput · 通用软件", false);

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

    internal static void Key(string key, bool down, InputInjectionMode inputMode)
    {
        var (virtualKey, scanCode) = key switch
        {
            "z" => (0x5A, 44), "x" => (0x58, 45), "c" => (0x43, 46), "v" => (0x56, 47),
            "b" => (0x42, 48), "n" => (0x4E, 49), "m" => (0x4D, 50), "," => (0xBC, 51),
            _ => throw new ArgumentOutOfRangeException(nameof(key))
        };
        if (inputMode.UseLegacyScanCodeEvents)
        {
            keybd_event(0, (byte)scanCode, KeyScanCode | (down ? 0 : KeyUp), UIntPtr.Zero);
            return;
        }
        Send([new INPUT { Type = InputKeyboard, Union = new InputUnion { Keyboard = new KEYBDINPUT { VirtualKey = (ushort)virtualKey, Flags = down ? 0 : KeyUp } } }]);
    }

    internal static void Mouse(char modifier, bool down, InputInjectionMode inputMode)
    {
        var flag = modifier switch { 'L' => down ? LeftDown : LeftUp, 'M' => down ? MiddleDown : MiddleUp, 'R' => down ? RightDown : RightUp, _ => throw new ArgumentOutOfRangeException(nameof(modifier)) };
        if (inputMode.UseLegacyScanCodeEvents)
        {
            mouse_event(flag, 0, 0, 0, UIntPtr.Zero);
            return;
        }
        Send([new INPUT { Type = InputMouse, Union = new InputUnion { Mouse = new MOUSEINPUT { Flags = flag } } }]);
    }

    private static void Send(INPUT[] inputs)
    {
        if (SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<INPUT>()) != (uint)inputs.Length) throw new InvalidOperationException("Windows 拒绝了模拟输入。");
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
