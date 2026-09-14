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
    private readonly Button startButton = new();
    private readonly Button stopButton = new();
    private CancellationTokenSource? cancellation;
    private string? activeKey;
    private readonly List<char> activeModifiers = [];

    public RecorderForm(PlaybackRequest? request)
    {
        this.request = request;
        Text = "Harmonica Recorder";
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = true;
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(510, 302);
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
        startButton.SetBounds(278, 225, 138, 42);
        startButton.Text = "开始倒计时";
        startButton.BackColor = Color.FromArgb(0, 123, 120);
        startButton.ForeColor = Color.White;
        startButton.FlatStyle = FlatStyle.Flat;
        startButton.FlatAppearance.BorderColor = Color.FromArgb(91, 185, 178);
        stopButton.SetBounds(426, 225, 62, 42);
        stopButton.Text = "停止";
        stopButton.Enabled = false;
        stopButton.FlatStyle = FlatStyle.Flat;
        stopButton.FlatAppearance.BorderColor = Color.FromArgb(137, 92, 153);

        Controls.AddRange([banner, titleLabel, detailsLabel, statusLabel, startButton, stopButton]);
        startButton.Click += async (_, _) => await StartPlaybackAsync();
        stopButton.Click += (_, _) => StopPlayback("已停止，并已释放本助手按下的按键。");
        FormClosing += (_, _) => StopPlayback("正在退出。");

        if (request is null)
        {
            titleLabel.Text = "等待从网页导入曲谱";
            detailsLabel.Text = "请在网站的「口琴鼠标宏录制助手」卡片中点击“导出到独立助手”。";
            statusLabel.Text = "首次使用：先运行安装包中的 Install.cmd 注册网页调用权限。\n紧急停止快捷键：Ctrl + Alt + End";
            startButton.Enabled = false;
        }
        else
        {
            titleLabel.Text = request.Title;
            detailsLabel.Text = $"已导入 {request.Events.Count} 个事件 · 将在 5 秒倒计时后开始模拟输入";
            statusLabel.Text = "先在目标鼠标软件创建“单次播放”宏并开启录制。\n开始后切回录制器；请勿让游戏获得焦点。紧急停止：Ctrl + Alt + End";
        }
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        NativeInput.RegisterHotKey(Handle, HotKeyId, NativeInput.ModControl | NativeInput.ModAlt, NativeInput.VkEnd);
    }

    protected override void OnHandleDestroyed(EventArgs e)
    {
        NativeInput.UnregisterHotKey(Handle, HotKeyId);
        base.OnHandleDestroyed(e);
    }

    protected override void WndProc(ref Message message)
    {
        if (message.Msg == WmHotKey && message.WParam.ToInt32() == HotKeyId) StopPlayback("已通过 Ctrl + Alt + End 停止。");
        base.WndProc(ref message);
    }

    private async Task StartPlaybackAsync()
    {
        if (request is null || cancellation is not null) return;
        cancellation = new CancellationTokenSource();
        startButton.Enabled = false;
        stopButton.Enabled = true;
        try
        {
            for (var seconds = 5; seconds >= 1; seconds--)
            {
                statusLabel.Text = $"倒计时 {seconds} 秒：现在切换到鼠标宏录制器。\n紧急停止：Ctrl + Alt + End";
                await Task.Delay(1000, cancellation.Token);
            }
            statusLabel.Text = "正在模拟输入… 按 Ctrl + Alt + End 可立即停止。";
            await Task.Run(() => Play(request.Events, cancellation.Token), cancellation.Token);
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
        }
    }

    private void Play(IEnumerable<PlaybackEvent> events, CancellationToken token)
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
                NativeInput.Mouse(modifier, true);
                activeModifiers.Add(modifier);
            }
            Wait(item.LeadMs, token);
            activeKey = item.Key;
            NativeInput.Key(item.Key!, true);
            Wait(Math.Max(0, item.HoldMs - item.LeadMs), token);
            NativeInput.Key(item.Key!, false);
            activeKey = null;
            for (var index = activeModifiers.Count - 1; index >= 0; index--) NativeInput.Mouse(activeModifiers[index], false);
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
            NativeInput.Key(activeKey, false);
            activeKey = null;
        }
        for (var index = activeModifiers.Count - 1; index >= 0; index--) NativeInput.Mouse(activeModifiers[index], false);
        activeModifiers.Clear();
    }
}

internal static class NativeInput
{
    internal const uint ModAlt = 0x0001;
    internal const uint ModControl = 0x0002;
    internal const uint VkEnd = 0x23;
    private const uint InputMouse = 0;
    private const uint InputKeyboard = 1;
    private const uint KeyUp = 0x0002;
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

    internal static void Key(string key, bool down)
    {
        var virtualKey = key switch { "z" => 0x5A, "x" => 0x58, "c" => 0x43, "v" => 0x56, "b" => 0x42, "n" => 0x4E, "m" => 0x4D, "," => 0xBC, _ => throw new ArgumentOutOfRangeException(nameof(key)) };
        Send([new INPUT { Type = InputKeyboard, Union = new InputUnion { Keyboard = new KEYBDINPUT { VirtualKey = (ushort)virtualKey, Flags = down ? 0 : KeyUp } } }]);
    }

    internal static void Mouse(char modifier, bool down)
    {
        var flag = modifier switch { 'L' => down ? LeftDown : LeftUp, 'M' => down ? MiddleDown : MiddleUp, 'R' => down ? RightDown : RightUp, _ => throw new ArgumentOutOfRangeException(nameof(modifier)) };
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
