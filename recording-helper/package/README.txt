HARMONICA RECORDER — Windows independent input helper

1. Extract this ZIP to a permanent folder.
2. Run Install.cmd once from that permanent folder as the same Windows user who uses the browser. It prints the registered EXE path and reports a failure if registration did not succeed. Re-run it whenever the folder moves.
3. Right-click HarmonicaRecorder.exe, choose Properties > Compatibility, and enable “Run this program as an administrator”.
4. Open recording in the target macro software.
5. Return to the helper, choose the keyboard and mouse methods separately, and click Test Input to verify the selected pair without importing a song.
6. Click the start button. Wait for recording to finish. During recording, do not touch the mouse or keyboard, and keep the mouse focus on the helper.
7. After completion, stop and save the macro in the target software, then delete the initial mouse down/up pair caused by clicking the helper's start button.

Emergency stop: Ctrl + Alt + End by default. Click the shortcut field and press any key combination to replace it; the setting is saved for later launches.

Version compatibility: the webpage reads the current helper release lines from recording-helper/version.json. Web and helper versions are maintained independently. QQ feedback group: 1102489399.
The helper checks the update manifest at startup. If a newer version is available, you can confirm the download; the package is hash-checked and the helper restarts after replacing itself.

The helper has separate keyboard and mouse method menus. The keyboard menu contains keybd_event scan code, keybd_event virtual key, SendInput virtual key, and SendInput scan code. The mouse menu contains mouse_event and SendInput. After changing either method, click Test Input first; it sends a short sequence covering normal notes and L/M/R/LM/RM modifier combinations. These are all standard user-mode Windows input APIs; software that uses driver-level interception may still ignore them.

The helper reuses an already running background instance when the website sends another score. If it is currently recording, the new import is rejected without interrupting the current recording; try again after it finishes. “Close helper after imported recording” is enabled by default. Uncheck it to keep the helper open for another import.

This program only uses standard Windows keyboard and left/middle/right mouse simulation APIs.
Some target applications may ignore synthetic input. Do not use it in a focused game window.

Uninstall.cmd removes the webpage integration. Deleting the extracted folder removes the app.
