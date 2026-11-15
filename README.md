# htTamer

htTamer tunes the subwoofers of a home theater. It measures each sub with a UMIK-1
mic, writes gain, delay, polarity and EQ into a miniDSP 2x4HD, blends the subs with
the speakers through the receiver, and offers a live EQ with a live analyzer and an
assistant. It runs on a Raspberry Pi (or Windows) and is used from a web page.

## Download

Get the latest build from the repository's **Releases** page:

- **Raspberry Pi**: `bassblend-<version>.img.xz`. Write it to an SD card with Raspberry Pi Imager
  (it can add Wi-Fi and SSH), plug in the miniDSP and the UMIK-1, then open `http://bassblend.local:8765`.
  See [docs/RASPBERRY_PI.md](docs/RASPBERRY_PI.md).
- **Windows 10/11 (64-bit)**: `htTamer-<version>-windows-setup.exe`. Installs for your user only
  (no admin rights), with Start-menu and desktop shortcuts. Start htTamer and the dashboard opens
  in your browser; keep its window open while you use it. Settings and measurements live in
  `%LOCALAPPDATA%\htTamer` and survive updates. The miniDSP is reached over USB with no driver.

Releases are built by `.github/workflows/release.yml` when a `v*` tag is pushed (the Windows
installer); the Pi image is built with `deploy/pi-gen/build-image.sh` and uploaded to the same release.

## Documentation

- User manual: `subtune/web/manual.html` (in the app under System → Manual, or at `/manual`)
- Raspberry Pi install: [docs/RASPBERRY_PI.md](docs/RASPBERRY_PI.md)
- Receiver setup: [docs/RECEIVER_SETUP.md](docs/RECEIVER_SETUP.md)
- Changes: [docs/CHANGELOG.md](docs/CHANGELOG.md)

Infrastructure names (the `subtune` Python package, `bassblend` paths, host and
service) come from the project's earlier name and are kept on purpose.

## Tests

Offline tests need no hardware and play no sound:

```
python tests/test_liveeq.py      # each tests/test_*.py file runs on its own
```

On the Pi, `subtune smoke` checks the hardware silently (miniDSP, receiver, mic,
HDMI); see the manual.

## License

htTamer is **source-available for non-commercial use** under the
[PolyForm Noncommercial License 1.0.0](LICENSE.md). You may use, change and share it
for any non-commercial purpose (personal use, study, hobby projects, charities,
schools and the like). Commercial use needs separate permission from the copyright
holder.

This is not an OSI "open source" license, because those allow commercial use.

Third-party components keep their own licenses. They are installed separately, not
included in this repository: numpy and scipy (BSD), sounddevice (MIT), the anthropic
SDK (MIT) and minidsp-rs (fetched by the setup scripts; see its project for its license).
