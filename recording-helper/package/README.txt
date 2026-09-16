HARMONICA RECORDER — Windows independent input helper

1. Extract this ZIP to a permanent folder.
2. Run Install.cmd once. This lets the website open the helper with the current score.
3. Open recording in the target macro software.
4. Return to the helper and click the start button. Wait for recording to finish. During recording, do not touch the mouse or keyboard, and keep the mouse focus on the helper.
5. After completion, stop and save the macro in the target software, then delete the initial mouse down/up pair caused by clicking the helper's start button.

Emergency stop: Ctrl + Alt + End by default. Click the shortcut field and press any key combination to replace it; the setting is saved for later launches.

Version compatibility: the webpage reads the current helper release lines from recording-helper/version.json. Web and helper versions are maintained independently. QQ feedback group: 1102489399.
The helper checks the update manifest at startup. If a newer version is available, you can confirm the download; the package is hash-checked and the helper restarts after replacing itself.

The “Input compatibility mode” menu contains eight Windows built-in input combinations. Test them with a short score when the target recorder does not react:
1. Default compatibility: keybd_event scan code + mouse_event.
2. Compatibility virtual key: keybd_event virtual key + mouse_event.
3. Standard SendInput: SendInput virtual key + SendInput mouse.
4. MCHOSE compatibility: SendInput scan code + SendInput mouse.
5. Hybrid A: keybd_event scan code + SendInput mouse.
6. Hybrid B: keybd_event virtual key + SendInput mouse.
7. Hybrid C: SendInput virtual key + mouse_event.
8. Hybrid D: SendInput scan code + mouse_event.
After changing the mode, click Start again. For MCHOSE, try mode 4 first, then the remaining modes in order. These are all standard user-mode Windows input APIs; software that uses driver-level interception may still ignore them.

This program only uses standard Windows keyboard and left/middle/right mouse simulation APIs.
Some target applications may ignore synthetic input. Do not use it in a focused game window.

Uninstall.cmd removes the webpage integration. Deleting the extracted folder removes the app.
