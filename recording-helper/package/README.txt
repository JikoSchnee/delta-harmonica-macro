HARMONICA RECORDER — Windows independent input helper

1. Extract this ZIP to a permanent folder.
2. Run Install.cmd once. This lets the website open the helper with the current score.
3. Open recording in the target macro software.
4. Return to the helper and click the start button. Wait for recording to finish. During recording, do not touch the mouse or keyboard, and keep the mouse focus on the helper.
5. After completion, stop and save the macro in the target software, then delete the initial mouse down/up pair caused by clicking the helper's start button.

Emergency stop: Ctrl + Alt + End by default. Click the shortcut field and press any key combination to replace it; the setting is saved for later launches.

Version compatibility: the webpage reads the current helper release lines from recording-helper/version.json. Web and helper versions are maintained independently. QQ feedback group: 1102489399.
The helper checks the update manifest at startup. If a newer version is available, you can confirm the download; the package is hash-checked and the helper restarts after replacing itself.

For general recording, use the default mode. For MCHOSE recording, select “MCHOSE compatible · SendInput scan code”; this sends keyboard scan codes through the modern SendInput API, which is more likely to be captured by MCHOSE. If an older helper does not show this option, select “Standard SendInput” as a fallback. Use “Standard SendInput” for other recorders if needed.

This program only uses standard Windows keyboard and left/middle/right mouse simulation APIs.
Some target applications may ignore synthetic input. Do not use it in a focused game window.

Uninstall.cmd removes the webpage integration. Deleting the extracted folder removes the app.
