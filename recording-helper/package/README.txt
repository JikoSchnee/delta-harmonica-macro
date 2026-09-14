HARMONICA RECORDER — Windows independent input helper

1. Extract this ZIP to a permanent folder.
2. Run Install.cmd once. This lets the website open the helper with the current score.
3. Open recording in the target macro software.
4. Return to the helper and click the start button. Wait for recording to finish. During recording, do not touch the mouse or keyboard, and keep the mouse focus on the helper.
5. After completion, stop and save the macro in the target software, then delete the initial mouse down/up pair caused by clicking the helper's start button.

Emergency stop: Ctrl + Alt + End by default. Click the shortcut field and press any key combination to replace it; the setting is saved for later launches.

For Logitech G HUB recording, use the default “G HUB compatible” input mode. It sends keyboard scan-code events and legacy mouse events, matching the compatibility path commonly used by macro tools. Use “Standard SendInput” only for other recorders if needed.

This program only uses standard Windows keyboard and left/middle/right mouse simulation APIs.
Some target applications may ignore synthetic input. Do not use it in a focused game window.

Uninstall.cmd removes the webpage integration. Deleting the extracted folder removes the app.
