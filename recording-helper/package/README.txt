HARMONICA RECORDER — Windows independent input helper

1. Extract this ZIP to a permanent folder.
2. Run Install.cmd once. This lets the website open the helper with the current score.
3. On the website, open the “Harmonica Macro Recording Helper” card and choose “Export to Independent Helper”.
4. In the helper, first click record in the macro software, return to the helper, and click “Start Input”.
5. During playback do not touch the mouse or keyboard, and do not move the mouse focus back to the macro software. When playback finishes, stop and save the macro, then delete the initial mouse down/up pair caused by clicking “Start Input”.

Emergency stop: Ctrl + Alt + End by default. Click the shortcut field and press any key combination to replace it; the setting is saved for later launches.

For Logitech G HUB recording, keep G HUB focused on its recording screen and use the default “G HUB compatible” input mode. It sends keyboard scan-code events and legacy mouse events, matching the compatibility path commonly used by macro tools. Use “Standard SendInput” only for other recorders if needed.

This program only uses standard Windows keyboard and left/middle/right mouse simulation APIs.
Some target applications may ignore synthetic input. Do not use it in a focused game window.

Uninstall.cmd removes the webpage integration. Deleting the extracted folder removes the app.
