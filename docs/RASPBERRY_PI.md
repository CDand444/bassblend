# BassBlend on a Raspberry Pi

Status: the code runs on Linux and has a setup script, but it has **not been tried on a real Pi
yet**. Expect a first session of small fixes, ideally with Claude connected to the Pi (below).

## What you need
- Raspberry Pi 4 (2 GB+) or Pi 5, with **Raspberry Pi OS Lite (64-bit)**. 32-bit won't work.
- Wired network if the Pi sits near the rack (Wi-Fi works too).
- The miniDSP and UMIK-1 plugged into the Pi's USB ports.

## First install
1. Write Raspberry Pi OS Lite (64-bit) to the SD card with **Raspberry Pi Imager**. In its settings,
   set the hostname to `bassblend`, create your user, turn on **SSH**, and add Wi-Fi if needed.
2. Boot the Pi and copy the BassBlend folder to it, e.g. with git:
   `git clone <your repo> ~/bassblend` (or copy the folder over).
3. On the Pi:
   ```
   cd ~/bassblend
   sudo ./deploy/linux/install.sh
   ```
   It installs everything and starts BassBlend.
4. Open **http://bassblend.local:8765** on your phone or PC. The first visit opens a short
   **setup guide**: choose your PIN, add the mic calibration file, find the receiver, and
   (optionally) add your AI key. Do this straight away: until a PIN is chosen, anyone on your
   network who opens the page could choose it. After that, everyone has to sign in.
   (`--pin` makes the script ask for the PIN in the terminal instead.)

To bring your tunes over from Windows, copy the contents of the BassBlend `data` folder into
`/var/lib/bassblend` on the Pi, run `sudo chown -R bassblend: /var/lib/bassblend`, restart
(`sudo systemctl restart bassblend`), then upload the mic calibration file again from the
Setup checklist. Your API key has to be added again in AI analysis (it is never copied).

## Developing with Claude on the Pi (live changes)
Use the **dev** install, which runs BassBlend straight from your checkout as your own user, so edits
take effect after a restart:
```
cd ~/bassblend
sudo ./deploy/linux/install.sh --dev
```
Then in the Claude desktop app, start a Code session **over SSH** to the Pi, in `~/bassblend`.
Claude can edit, run `tests/`, `sudo systemctl restart bassblend`, read `journalctl -u bassblend`,
and check the dashboard in the browser pane at http://bassblend.local:8765.

## What's different from Windows
| | Windows | Pi |
|---|---|---|
| Dashboard | this PC only, no sign-in | your network, PIN required |
| Audio | Windows WASAPI | ALSA, direct hardware (no resampling) |
| miniDSP tool | `tools/minidsp/minidsp.exe` | minidsp-rs Linux build, installed by the script |
| Data | `data/` in the project | `/var/lib/bassblend` (`BASSBLEND_DATA`) |
| API key / PIN | `%LOCALAPPDATA%\subtune` | `/var/lib/bassblend/config` (`BASSBLEND_CONFIG`) |
| Receiver test files | needed a firewall rule | no firewall by default |

## Things to check on the first real run
- `minidsp probe` finds the 2x4HD (the USB permission rule is in `/etc/udev/rules.d/60-bassblend-minidsp.rules`).
- Both the miniDSP and the UMIK-1 open at 48 kHz on ALSA.
- A self-test (Manual steps) still measures −10 dB and 5 ms.
- The receiver can fetch the blend test file from the Pi.

## Later: a ready-made SD card image
Once the above works, a pi-gen build can bake the same steps into an image you just write to a card.
