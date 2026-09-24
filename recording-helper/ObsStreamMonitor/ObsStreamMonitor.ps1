Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object Windows.Forms.Form
$form.Text = 'Delta Harmonica · OBS 开播监听'
$form.Size = New-Object Drawing.Size(590, 440)
$form.MinimumSize = New-Object Drawing.Size(590, 440)
$form.StartPosition = 'CenterScreen'
$form.BackColor = [Drawing.Color]::FromArgb(11, 31, 27)
$form.ForeColor = [Drawing.Color]::FromArgb(223, 237, 224)
$form.Font = New-Object Drawing.Font('Microsoft YaHei UI', 9)

function Add-Label([string]$text, [int]$x, [int]$y, [int]$width = 150) {
    $label = New-Object Windows.Forms.Label
    $label.Text = $text; $label.Location = New-Object Drawing.Point($x, $y)
    $label.Size = New-Object Drawing.Size($width, 24); $label.ForeColor = [Drawing.Color]::FromArgb(183, 207, 190)
    $form.Controls.Add($label); return $label
}
function Add-Input([string]$value, [int]$x, [int]$y, [int]$width, [bool]$secret = $false) {
    $box = New-Object Windows.Forms.TextBox
    $box.Text = $value; $box.Location = New-Object Drawing.Point($x, $y)
    $box.Size = New-Object Drawing.Size($width, 26); $box.BackColor = [Drawing.Color]::FromArgb(5, 20, 17)
    $box.ForeColor = [Drawing.Color]::FromArgb(231, 242, 229); $box.BorderStyle = 'FixedSingle'
    $box.UseSystemPasswordChar = $secret; $form.Controls.Add($box); return $box
}

Add-Label '本站地址' 24 24
$siteBox = Add-Input 'https://jiko-official.top/delta' 170 22 380
Add-Label '主播设备令牌' 24 66
$tokenBox = Add-Input '' 170 64 380 $true
Add-Label 'OBS WebSocket 地址' 24 108
$obsBox = Add-Input 'ws://127.0.0.1:4455' 170 106 380
Add-Label 'OBS WebSocket 密码' 24 150
$passwordBox = Add-Input '' 170 148 380 $true

$status = New-Object Windows.Forms.Label
$status.Text = '填写合作页生成的设备令牌，并在 OBS 设置中启用 WebSocket。'
$status.Location = New-Object Drawing.Point(24, 198); $status.Size = New-Object Drawing.Size(526, 55)
$status.ForeColor = [Drawing.Color]::FromArgb(194, 215, 192); $form.Controls.Add($status)
$detail = New-Object Windows.Forms.Label
$detail.Text = '开播后自动领取本周期兑换码，并同步到 OBS 当前场景文字源。'
$detail.Location = New-Object Drawing.Point(24, 253); $detail.Size = New-Object Drawing.Size(526, 30)
$detail.ForeColor = [Drawing.Color]::FromArgb(137, 166, 151); $form.Controls.Add($detail)

$connectButton = New-Object Windows.Forms.Button
$connectButton.Text = '连接并开始监听'; $connectButton.Location = New-Object Drawing.Point(24, 306)
$connectButton.Size = New-Object Drawing.Size(190, 40); $connectButton.FlatStyle = 'Flat'
$connectButton.BackColor = [Drawing.Color]::FromArgb(37, 99, 83); $connectButton.ForeColor = [Drawing.Color]::White
$form.Controls.Add($connectButton)
$disconnectButton = New-Object Windows.Forms.Button
$disconnectButton.Text = '断开'; $disconnectButton.Location = New-Object Drawing.Point(226, 306)
$disconnectButton.Size = New-Object Drawing.Size(110, 40); $disconnectButton.FlatStyle = 'Flat'
$disconnectButton.BackColor = [Drawing.Color]::FromArgb(54, 68, 59); $disconnectButton.ForeColor = [Drawing.Color]::White
$form.Controls.Add($disconnectButton)

$script:socket = $null
$script:lastLive = $null
$script:lastPulse = [DateTime]::MinValue
$script:obsCodeSourceName = 'DeltaHarmonicaDailyCode'
$timer = New-Object Windows.Forms.Timer
$timer.Interval = 2500

function Get-ObsTextMessage([Net.WebSockets.ClientWebSocket]$ws) {
    $buffer = New-Object byte[] 8192
    $stream = New-Object IO.MemoryStream
    do {
        $receiveTask = $ws.ReceiveAsync([ArraySegment[byte]]::new($buffer), [Threading.CancellationToken]::None)
        if (-not $receiveTask.Wait(6000)) { throw '读取 OBS WebSocket 超时。' }
        $result = $receiveTask.GetAwaiter().GetResult()
        if ($result.MessageType -eq [Net.WebSockets.WebSocketMessageType]::Close) { throw 'OBS 已关闭 WebSocket 连接。' }
        $stream.Write($buffer, 0, $result.Count)
    } while (-not $result.EndOfMessage)
    return [Text.Encoding]::UTF8.GetString($stream.ToArray()) | ConvertFrom-Json
}
function Send-ObsJson([Net.WebSockets.ClientWebSocket]$ws, $object) {
    $bytes = [Text.Encoding]::UTF8.GetBytes(($object | ConvertTo-Json -Depth 8 -Compress))
    $task = $ws.SendAsync([ArraySegment[byte]]::new($bytes), [Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None)
    if (-not $task.Wait(6000)) { throw '发送 OBS WebSocket 请求超时。' }
    $task.GetAwaiter().GetResult()
}
function Invoke-ObsRequest([Net.WebSockets.ClientWebSocket]$ws, [string]$requestType, $requestData = @{}) {
    $requestId = [Guid]::NewGuid().ToString()
    Send-ObsJson $ws @{ op = 6; d = @{ requestType = $requestType; requestId = $requestId; requestData = $requestData } }
    for ($i = 0; $i -lt 20; $i++) {
        $message = Get-ObsTextMessage $ws
        if ($message.op -eq 7 -and $message.d.requestId -eq $requestId) {
            if (-not $message.d.requestStatus.result) { throw "OBS 请求失败：$($message.d.requestStatus.comment)" }
            return $message.d.responseData
        }
    }
    throw "没有收到 OBS 请求 $requestType 的响应。"
}
function Get-ObsStreamActive([Net.WebSockets.ClientWebSocket]$ws) {
    $response = Invoke-ObsRequest $ws 'GetStreamStatus'
    return [bool]$response.outputActive
}
function Sync-ObsCodeOverlay([Net.WebSockets.ClientWebSocket]$ws, [bool]$visible, [string]$code = '') {
    $scene = Invoke-ObsRequest $ws 'GetCurrentProgramScene'
    $sceneName = [string]$scene.currentProgramSceneName
    if (-not $sceneName) { throw 'OBS 当前没有可用场景。' }
    $sceneData = Invoke-ObsRequest $ws 'GetSceneItemList' @{ sceneName = $sceneName }
    $item = @($sceneData.sceneItems | Where-Object { $_.sourceName -eq $script:obsCodeSourceName } | Select-Object -First 1)
    if (-not $visible) {
        if ($item.Count -gt 0) {
            Invoke-ObsRequest $ws 'SetSceneItemEnabled' @{ sceneName = $sceneName; sceneItemId = $item[0].sceneItemId; sceneItemEnabled = $false } | Out-Null
        }
        return
    }

    $overlayText = "主播积分兑换码`r`n$code`r`n每日 05:00 更新"
    $inputList = Invoke-ObsRequest $ws 'GetInputList'
    $existingInput = @($inputList.inputs | Where-Object { $_.inputName -eq $script:obsCodeSourceName } | Select-Object -First 1)
    if ($existingInput.Count -gt 0 -and $existingInput[0].inputKind -ne 'text_gdiplus') {
        throw "OBS 中已存在同名的非文字源 $($script:obsCodeSourceName)，请先重命名该来源。"
    }

    if ($item.Count -gt 0) {
        $itemId = $item[0].sceneItemId
    } elseif ($existingInput.Count -gt 0) {
        $createdItem = Invoke-ObsRequest $ws 'CreateSceneItem' @{ sceneName = $sceneName; sourceName = $script:obsCodeSourceName }
        $itemId = $createdItem.sceneItemId
    } else {
        $createdItem = Invoke-ObsRequest $ws 'CreateInput' @{
            sceneName = $sceneName
            inputName = $script:obsCodeSourceName
            inputKind = 'text_gdiplus'
            inputSettings = @{
                text = $overlayText
                color = 4294967295
                font = @{ face = 'Microsoft YaHei UI'; size = 42; style = 'Regular'; flags = 0 }
            }
            sceneItemEnabled = $true
        }
        $itemId = $createdItem.sceneItemId
    }
    Invoke-ObsRequest $ws 'SetInputSettings' @{ inputName = $script:obsCodeSourceName; inputSettings = @{ text = $overlayText }; overlay = $true } | Out-Null
    Invoke-ObsRequest $ws 'SetSceneItemEnabled' @{ sceneName = $sceneName; sceneItemId = $itemId; sceneItemEnabled = $true } | Out-Null
}
function Send-SitePulse([bool]$isLive) {
    $root = $siteBox.Text.Trim().TrimEnd('/')
    $token = $tokenBox.Text.Trim()
    if (-not $root.StartsWith('https://') -and -not $root.StartsWith('http://localhost')) { throw '本站地址须使用 HTTPS。' }
    if ($token.Length -lt 32) { throw '请填写合作页刚生成的设备令牌。' }
    $body = @{ isLive = $isLive } | ConvertTo-Json -Compress
    return Invoke-RestMethod -Method Post -Uri "$root/api/cooperate/obs/pulse" -Headers @{ Authorization = "Streamer $token" } -ContentType 'application/json; charset=utf-8' -Body $body -TimeoutSec 6
}
function Stop-Monitor {
    $timer.Stop()
    if ($null -ne $script:socket) {
        try { if ($script:socket.State -eq [Net.WebSockets.WebSocketState]::Open) { Sync-ObsCodeOverlay $script:socket $false } } catch { }
        try { if ($script:lastLive -eq $true) { Send-SitePulse $false | Out-Null } } catch { }
        try { $script:socket.Abort(); $script:socket.Dispose() } catch { }
        $script:socket = $null
    }
    $script:lastLive = $null
    $status.Text = '已断开监听。'
    $connectButton.Enabled = $true
}

$connectButton.Add_Click({
    $connectButton.Enabled = $false
    try {
        $ws = New-Object Net.WebSockets.ClientWebSocket
        $ws.Options.KeepAliveInterval = [TimeSpan]::FromSeconds(15)
        $uri = [Uri]$obsBox.Text.Trim()
        $connectTask = $ws.ConnectAsync($uri, [Threading.CancellationToken]::None)
        if (-not $connectTask.Wait(8000)) { $ws.Abort(); throw '连接 OBS 超时，请检查地址、端口和防火墙。' }
        $hello = Get-ObsTextMessage $ws
        if ($hello.op -ne 0) { throw 'OBS WebSocket 握手无效。' }
        $identify = @{ op = 1; d = @{ rpcVersion = 1; eventSubscriptions = 1 } }
        if ($hello.d.authentication) {
            $password = $passwordBox.Text
            if (-not $password) { throw 'OBS 已设置 WebSocket 密码，请填写密码。' }
            $sha = [Security.Cryptography.SHA256]::Create()
            $firstBytes = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($password + $hello.d.authentication.salt))
            $secret = [Convert]::ToBase64String($firstBytes)
            $authBytes = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($secret + $hello.d.authentication.challenge))
            $identify.d.authentication = [Convert]::ToBase64String($authBytes)
            $sha.Dispose()
        }
        Send-ObsJson $ws $identify
        $identified = $false
        for ($i = 0; $i -lt 20; $i++) { $message = Get-ObsTextMessage $ws; if ($message.op -eq 2) { $identified = $true; break } }
        if (-not $identified) { throw 'OBS 未完成 WebSocket 认证。' }
        $script:socket = $ws
        $script:lastLive = $null
        $status.Text = '已连接 OBS，检测到开播后将自动同步每日兑换码。'
        $timer.Start()
    } catch {
        if ($null -ne $ws) { try { $ws.Dispose() } catch { } }
        $status.Text = $_.Exception.Message
        $connectButton.Enabled = $true
    }
})
$timer.Add_Tick({
    try {
        if ($null -eq $script:socket -or $script:socket.State -ne [Net.WebSockets.WebSocketState]::Open) { throw 'OBS WebSocket 已断开，请重新连接。' }
        $isLive = Get-ObsStreamActive $script:socket
        if ($script:lastLive -ne $isLive -or ([DateTime]::UtcNow - $script:lastPulse).TotalSeconds -ge 25) {
            $pulse = Send-SitePulse $isLive; $script:lastPulse = [DateTime]::UtcNow
            if ($isLive) {
                if (-not $pulse.code) { throw '网站没有返回主播每日兑换码。' }
                Sync-ObsCodeOverlay $script:socket $true ([string]$pulse.code)
                $status.Text = "● OBS 正在直播 · 兑换码 $($pulse.code) 已同步到当前场景"
            } else {
                Sync-ObsCodeOverlay $script:socket $false
                $status.Text = '○ OBS 当前未直播 · 兑换码文字源已隐藏'
            }
        }
        $script:lastLive = $isLive
    } catch { $status.Text = $_.Exception.Message; Stop-Monitor }
})
$disconnectButton.Add_Click({ Stop-Monitor })
$form.Add_FormClosing({ Stop-Monitor })
[void]$form.ShowDialog()
