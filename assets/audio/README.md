# 口琴试听样片

`harmonica-vcsl-preview.wav` 和 `harmonica-vcsl-preview.mp3` 使用 VCSL 的 C 调 Hohner Special 20 口琴采样制作，仅用于试听。

播放器使用 `harmonica/60.wav`（C4）、`64.wav`（E4）、`72.wav`（C5）、`76.wav`（E5）、`79.wav`（G5）和 `84.wav`（C6）六个实际音高采样点。低音区使用实际音高对应的 C4/E4 采样后再按目标音符降调，避免把文件名误当成 C3/E3 导致低音高一个八度；每个项目音符会选择最近采样并进行变调。

目录中的 `48.wav` 与 `52.wav` 是原始下载样片，频谱确认其实际音高仍为 C4/E4，因此不作为 C3/E3 采样点使用。

试听顺序：低音 C3 → E3 → C4 → E4 → C5 → E5 → G5 → C6。低音 C3/E3 会从 C4/E4 采样正确降调生成，每个音之间有短暂停顿。

来源：<https://github.com/sgossner/VCSL/tree/master/Aerophones/Free%20Aerophones/Harmonica-Hohner-Special20-C/Sustains/Normal>

项目内的预览样片来自同一套 VCSL C 调 Hohner Special 20 采样。

来源说明标注为 Creative Commons CC0 1.0。正式集成前仍应保留来源说明，并按实际采样文件清单配置播放器。

## 钢琴试听

`piano/` 存放默认试听所用的 Salamander Grand Piano v3 采样。原始 48 kHz / 24-bit 录音按 SFZ 映射每小三度采样一次；播放器使用 C3、D♯3、F♯3、A3、C4、D♯4、F♯4、A4、C5、D♯5、F♯5、A5、C6 共 13 个中间力度（v8）音符，变调覆盖 C3–C6。采样转为 48 kHz、112 kbps MP3，以便网页快速加载。

来源：Alexander Holm, *Salamander Grand Piano v3*，由 kinwie 整理为 SFZ，<https://github.com/sfzinstruments/SalamanderGrandPiano>。改编：仅保留 v8 力度层采样并转为 MP3，网页按音高变调播放。授权：Creative Commons Attribution 3.0 Unported（CC BY 3.0）；授权全文见 `piano/LICENSE.txt`。
