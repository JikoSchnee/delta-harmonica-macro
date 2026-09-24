DELTA HARMONICA OBS STREAM MONITOR — WINDOWS

Requirements
- Windows 10 or later with Windows PowerShell 5.1.
- OBS Studio with WebSocket Server enabled (OBS 28 and later include it).

Start
1. Extract this ZIP to a folder you control.
2. Run Start.cmd.
3. On the website, sign in and open Cooperation > Creator Console > Generate Device Token.
4. Copy the device token into the monitor. The token is shown only once; create a new token if it is lost.
5. In OBS, open Tools > WebSocket Server Settings, enable the server, and copy its password. The default address is ws://127.0.0.1:4455.
6. Enter the OBS password and click Connect.

When OBS starts streaming, the monitor asks the website for the streamer's code for the current 05:00 Beijing-time cycle. The code is generated automatically if needed and stays the same as the code shown in the creator console. The monitor creates or updates a white text source named "DeltaHarmonicaDailyCode" in the current OBS scene. It checks every 25 seconds, so a new code is synced after the daily 05:00 reset. When streaming stops, the text source is hidden. You can move or resize the source in OBS like any other text source.

The monitor reports stream status to the website every 25 seconds so the cooperation page can mark stale connections offline. Closing the monitor attempts to report offline and hide the code source. Revoke a device token from the signed-in creator console to stop future reports from that installation.

The site address and device token are sent only to the site's HTTPS status endpoint. OBS credentials and device tokens are kept in memory for this session and are not saved in this folder. Never share your device token. The monitor does not record or transmit video or audio.

Troubleshooting
- Check OBS WebSocket is enabled and the address/port match OBS.
- Check the OBS password carefully.
- Confirm the device token is active in the creator console.
- Allow outbound HTTPS to the site and local WebSocket access to OBS.
