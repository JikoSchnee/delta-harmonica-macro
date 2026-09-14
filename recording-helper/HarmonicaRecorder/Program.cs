using System.Runtime.InteropServices;
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

    public static PlaybackRequest? FromProtocolArgument(string? argument)
    {
        if (string.IsNullOrWhiteSpace(argument) || !Uri.TryCreate(argument.Trim('"'), UriKind.Absolute, out var uri) || uri.Scheme != "harmonica-recorder") return null;
        var payload = uri.Query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries)
            .Select(pair => pair.Split('=', 2))
            .FirstOrDefault(pair => pair.Length == 2 && pair[0] == "payload")?[1];
        if (string.IsNullOrWhiteSpace(payload)) return null;

        try
        {
            var base64 = payload.Replace('-', '+').Replace('_', '/');
            base64 = base64.PadRight(base64.Length + (4 - base64.Length % 4) % 4, '=');
            var request = JsonSerializer.Deserialize<PlaybackRequest>(Convert.FromBase64String(base64));
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
    private readonly ComboBox hotKeyBox = new();
    private readonly Label inputModeLabel = new();
    private readonly ComboBox inputModeBox = new();
    private readonly Button startButton = new();
    private readonly Button stopButton = new();
    private readonly List<HotKeyOption> hotKeyOptions =
    [
        new("Ctrl + Alt + End", NativeInput.ModControl | NativeInput.ModAlt, NativeInput.VkEnd),
        new("Ctrl + Alt + Pause", NativeInput.ModControl | NativeInput.ModAlt, NativeInput.VkPause),
        new("Ctrl + Shift + End", NativeInput.ModControl | NativeInput.ModShift, NativeInput.VkEnd),
        new("Ctrl + Shift + Pause", NativeInput.ModControl | NativeInput.ModShift, NativeInput.VkPause)
    ];
    private CancellationTokenSource? cancellation;
    private string? activeKey;
    private readonly List<char> activeModifiers = [];
    private HotKeyOption activeHotKey = null!;
    private InputInjectionMode activeInputMode = null!;
    private InputInjectionMode activePlaybackInputMode = null!;
    private bool hotKeyRegistered;
    private bool restoringHotKeySelection;

    public RecorderForm(PlaybackRequest? request)
    {
        this.request = request;
        Text = "Harmonica Recorder";
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = true;
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(510, 354);
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
        hotKeyLabel.Text = "紧急停止快捷键";
        hotKeyLabel.TextAlign = ContentAlignment.MiddleLeft;
        hotKeyBox.SetBounds(208, 211, 280, 29);
        hotKeyBox.DropDownStyle = ComboBoxStyle.DropDownList;
        hotKeyBox.FlatStyle = FlatStyle.Flat;
        hotKeyOptions.ForEach(option => hotKeyBox.Items.Add(option));
        activeHotKey = EmergencyStopHotKeySettings.Load(hotKeyOptions) ?? hotKeyOptions[0];
        hotKeyBox.SelectedItem = activeHotKey;
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
        startButton.SetBounds(278, 289, 138, 42);
        startButton.Text = "开始倒计时";
        startButton.BackColor = Color.FromArgb(0, 123, 120);
        startButton.ForeColor = Color.White;
        startButton.FlatStyle = FlatStyle.Flat;
        startButton.FlatAppearance.BorderColor = Color.FromArgb(91, 185, 178);
        stopButton.SetBounds(426, 289, 62, 42);
        stopButton.Text = "停止";
        stopButton.Enabled = false;
        stopButton.FlatStyle = FlatStyle.Flat;
        stopButton.FlatAppearance.BorderColor = Color.FromArgb(137, 92, 153);

        Controls.AddRange([banner, titleLabel, detailsLabel, statusLabel, hotKeyLabel, hotKeyBox, inputModeLabel, inputModeBox, startButton, stopButton]);
        startButton.Click += async (_, _) => await StartPlaybackAsync();
        stopButton.Click += (_, _) => StopPlayback("已停止，并已释放本助手按下的按键。");
        hotKeyBox.SelectedIndexChanged += (_, _) => UpdateEmergencyStopHotKey();
        inputModeBox.SelectedIndexChanged += (_, _) => UpdateInputMode();
        FormClosing += (_, _) => StopPlayback("正在退出。");

        if (request is null)
        {
            titleLabel.Text = "等待从网页导入曲谱";
            detailsLabel.Text = "请在网站的「口琴鼠标宏录制助手」卡片中点击“导出到独立助手”。";
            statusLabel.Text = $"首次使用：先运行安装包中的 Install.cmd 注册网页调用权限。\n紧急停止快捷键：{activeHotKey.DisplayName}";
            startButton.Enabled = false;
        }
        else
        {
            titleLabel.Text = request.Title;
            detailsLabel.Text = $"已导入 {request.Events.Count} 个事件 · 将在 5 秒倒计时后开始模拟输入";
            statusLabel.Text = $"G HUB 请保持在录制界面，并使用“G HUB 兼容”模式。\n紧急停止：{activeHotKey.DisplayName}";
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

    private void UpdateEmergencyStopHotKey()
    {
        if (restoringHotKeySelection || hotKeyBox.SelectedItem is not HotKeyOption selectedHotKey || selectedHotKey == activeHotKey) return;
        var previousHotKey = activeHotKey;
        activeHotKey = selectedHotKey;
        if (IsHandleCreated && !RegisterEmergencyStopHotKey())
        {
            activeHotKey = previousHotKey;
            restoringHotKeySelection = true;
            hotKeyBox.SelectedItem = previousHotKey;
            restoringHotKeySelection = false;
            RegisterEmergencyStopHotKey();
            MessageBox.Show(this, $"无法注册 {selectedHotKey.DisplayName}，它可能已被其他软件占用。已恢复为 {previousHotKey.DisplayName}。", "快捷键不可用", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        EmergencyStopHotKeySettings.Save(activeHotKey);
        if (cancellation is null) statusLabel.Text = $"紧急停止快捷键已设为 {activeHotKey.DisplayName}。";
    }

    private bool RegisterEmergencyStopHotKey()
    {
        if (hotKeyRegistered) NativeInput.UnregisterHotKey(Handle, HotKeyId);
        hotKeyRegistered = NativeInput.RegisterHotKey(Handle, HotKeyId, activeHotKey.Modifiers, activeHotKey.VirtualKey);
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
        startButton.Enabled = false;
        stopButton.Enabled = true;
        inputModeBox.Enabled = false;
        try
        {
            for (var seconds = 5; seconds >= 1; seconds--)
            {
                statusLabel.Text = $"倒计时 {seconds} 秒：现在切换到鼠标宏录制器。\n紧急停止：{activeHotKey.DisplayName}";
                await Task.Delay(1000, cancellation.Token);
            }
            statusLabel.Text = $"正在模拟输入… 按 {activeHotKey.DisplayName} 可立即停止。";
            await Task.Run(() => Play(request.Events, cancellation.Token, activePlaybackInputMode), cancellation.Token);
            if (!cancellation.IsCancellationRequested) statusLabel.Text = "输入完成。请停止鼠标软件的录制，并保存该宏。";
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
        }
    }

    private void Play(IEnumerable<PlaybackEvent> events, CancellationToken token, InputInjectionMode inputMode)
    {
        foreach (var item in events)
        {
            token.ThrowIfCancellationRequested();
            if (item.IsRest)
            {
                Wait(item.WaitMs, token);
                continue;
            }
            foreach (var modifier in item.Modifiers ?? string.Empty)
            {
                NativeInput.Mouse(modifier, true, inputMode);
                activeModifiers.Add(modifier);
            }
            Wait(item.LeadMs, token);
            activeKey = item.Key;
            NativeInput.Key(item.Key!, true, inputMode);
            Wait(Math.Max(0, item.HoldMs - item.LeadMs), token);
            NativeInput.Key(item.Key!, false, inputMode);
            activeKey = null;
            for (var index = activeModifiers.Count - 1; index >= 0; index--) NativeInput.Mouse(activeModifiers[index], false, inputMode);
            activeModifiers.Clear();
            Wait(item.WaitMs, token);
        }
    }

    private static void Wait(int milliseconds, CancellationToken token)
    {
        while (milliseconds > 0)
        {
            token.ThrowIfCancellationRequested();
            var slice = Math.Min(milliseconds, 10);
            Thread.Sleep(slice);
            milliseconds -= slice;
        }
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

    internal static HotKeyOption? Load(IEnumerable<HotKeyOption> options)
    {
        try
        {
            var saved = JsonSerializer.Deserialize<StoredHotKey>(File.ReadAllText(SettingsPath));
            return saved is null
                ? null
                : options.FirstOrDefault(option => option.Modifiers == saved.Modifiers && option.VirtualKey == saved.VirtualKey);
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
            File.WriteAllText(SettingsPath, JsonSerializer.Serialize(new StoredHotKey(hotKey.Modifiers, hotKey.VirtualKey)));
        }
        catch (Exception)
        {
            // The selection remains active for this run even if Windows blocks settings persistence.
        }
    }

    private static string SettingsPath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "HarmonicaRecorder", FileName);

    private sealed record StoredHotKey(uint Modifiers, uint VirtualKey);
}

internal static class NativeInput
{
    internal const uint ModAlt = 0x0001;
    internal const uint ModControl = 0x0002;
    internal const uint ModShift = 0x0004;
    internal const uint VkEnd = 0x23;
    internal const uint VkPause = 0x13;
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
