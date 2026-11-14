# htTamer on a Raspberry Pi

Status: the code runs on Linux and has a setup script, but it has **not been tried on a real Pi
yet**. Expect a first session of small fixes, ideally with Claude connected to the Pi (below).

## What you need
- Raspberry Pi 4 (2 GB+) or Pi 5, with **Raspberry Pi OS Lite (64-bit)**. 32-bit won't work.
- Wired network if the Pi sits near the rack (Wi-Fi works too).
- The miniDSP and UMIK-1 plugged into the Pi's USB ports.

## First install
1. Write Raspberry Pi OS Lite (64-bit) to the SD card with **Raspberry Pi Imager**. In its settings,
   set the hostname to `bassblend`, create your user, turn on **SSH**, and add Wi-Fi if needed.
2. Boot the Pi and copy the htTamer folder to it, e.g. with git:
   `git clone <your repo> ~/bassblend` (or copy the folder over).
3. On the Pi:
   ```
   cd ~/bassblend
   sudo ./deploy/linux/install.sh
   ```
   It installs everything and starts htTamer.
4. Open **http://bassblend.local:8765** on your phone or PC. The first visit opens a short
   **setup guide**: choose your PIN, add the mic calibration file, find the receiver, and
   (optionally) add your AI key. Do this straight away: until a PIN is chosen, anyone on your
   network who opens the page could choose it. After that, everyone has to sign in.
   (`--pin` makes the script ask for the PIN in the terminal instead.)

## Your settings in one file (no typing on a new card)
The dashboard menu has **Settings file**. **Download** saves one `.json` with:
- settings: subs, owned slot, target curve, optimiser limits, receiver, speaker layout and Dirac choices;
- the room (size, seats, where each sub is and what it is);
- the mic calibration file itself;
- ticked by default: saved tunes, slot contents, the current result and its measurements;
- only if you tick them: the PIN (as its hash, never the PIN) and the Anthropic API key.

It never carries what belongs to one computer (the miniDSP's USB path, audio device names),
sign-ins, the activity log or chats.

Load it with **Import settings file** (on that same page, or on the first-boot setup page after
choosing a PIN), or from a terminal: `python -m subtune import-config FILE`
(`export-config` makes one).

**On a freshly written SD card**, copy the file onto the card's boot drive (the drive Windows shows
after writing) as `bassblend-config.json` before the first start. It is imported on first boot
and then removed from the boot drive. With the PIN in the file, there is no setup to do at all.
To bake it into an image: `BASSBLEND_SETTINGS=path/to/file.json deploy/pi-gen/build-image.sh`
(anyone with that image can read the file).

## Over-the-air updates from your computer
With SSH set up (`ssh bassblend` works), send this folder's code to the Pi:
```
deploy/push-update.sh            # once
deploy/push-update.sh --watch    # every time you save a file (Ctrl+C to stop)
```
It sends the tracked and new files (uncommitted edits included; never `data/`, `tools/` or keys).
On the Pi, `bassblend-update` checks the code compiles, installs it into `/opt/bassblend`
(keeping the Python environment, the miniDSP tool and your data), installs Python packages only if
`requirements.txt` changed, and restarts only if Python code changed: web page edits show on the
next refresh. If the new version doesn't start within 30 seconds, the previous one is put back.
The version shows at the bottom of the Settings file page.

## Developing with Claude on the Pi (live changes)
Use the **dev** install, which runs htTamer straight from your checkout as your own user, so edits
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

## A ready-made SD card image
`deploy/pi-gen/build-image.sh` builds one (Docker; 1-2 hours). Write it with Raspberry Pi Imager
("Use custom"), then copy your settings file onto the card as above.
