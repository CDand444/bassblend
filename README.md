# htTamer

htTamer tunes the subwoofers of a home theater. It measures each sub with a UMIK-1
mic, writes gain, delay, polarity and EQ into a miniDSP 2x4HD, blends the subs with
the speakers through the receiver, and offers a live EQ with a live analyzer and an
assistant. It runs on a Raspberry Pi (or Windows) and is used from a web page.

> **Use at your own risk.** htTamer plays loud test sound, changes your receiver's volume and input, and
> writes settings to your miniDSP. Loud bass can damage speakers, amplifiers and hearing. htTamer is provided
> "as is", without warranty of any kind (see [LICENSE.md](LICENSE.md)); the htTamer authors are not liable for
> any damage or loss. It asks you to accept this the first time it opens. Not affiliated with or endorsed by
> Onkyo, Denon, Marantz, JBL, miniDSP, Dirac or any other maker it works with.

## Download

Get the latest build from **[Releases](https://github.com/danand444/bassblend/releases/latest)**. Installed copies update themselves from there (Tools → Updates), with nothing to set up:

- **Raspberry Pi**: `bassblend-<version>.img.xz`. Write it to an SD card with Raspberry Pi Imager
  (it can add Wi-Fi and SSH), plug in the miniDSP and the UMIK-1, then open `http://bassblend.local:8765`.
  See [docs/RASPBERRY_PI.md](docs/RASPBERRY_PI.md).
- **Windows 10/11 (64-bit)**: `htTamer-<version>-windows-setup.exe`. Installs for your user only
  (no admin rights), with Start-menu and desktop shortcuts. Start htTamer and the dashboard opens
  in your browser; keep its window open while you use it. Settings and measurements live in
  `%LOCALAPPDATA%\htTamer` (keys and PIN in its own `config` folder, never shared with a
  developer copy) and survive updates. The miniDSP is reached over USB with no driver.

Releases are built by `.github/workflows/release.yml` when a `v*` tag is pushed (the Windows
installer); the Pi image is built with `deploy/pi-gen/build-image.sh` and uploaded to the same release.

## Documentation

- User manual: `subtune/web/manual.html` (in the app under System → Manual, or at `/manual`)
- Raspberry Pi install: [docs/RASPBERRY_PI.md](docs/RASPBERRY_PI.md)
- Receiver setup: [docs/RECEIVER_SETUP.md](docs/RECEIVER_SETUP.md)
- Changes: [docs/CHANGELOG.md](docs/CHANGELOG.md)

Infrastructure names (the `subtune` Python package, `bassblend` paths, host and
service) come from the project's earlier name and are kept on purpose.

## Using htTamer from an AI client (MCP)

htTamer has an MCP server, so an AI client such as Claude Desktop or Claude Code can read its
state and run its actions with the same tools as the in-app assistant. Turn it on under
**Tools → MCP** (off by default); that page shows the config to copy. Two transports:

- **stdio**: `python -m subtune mcp` (the installed Windows app: `htTamer.exe mcp`; a Pi: the same
  command over `ssh`). It forwards each request to the running dashboard.
- **Streamable HTTP**: `http://<host>:8765/mcp` with `Authorization: Bearer <token>`.

Every `/mcp` request needs a credential, even from the same computer: the MCP token (made on
that page, shown once, stored only as a hash, revocable), a signed-in dashboard session, or the
local key in htTamer's config folder that `subtune mcp` uses when run as the same user. Over ssh
to a Pi, `subtune mcp` reads the token from `$HTTAMER_MCP_TOKEN` or `~/.httamer-mcp-token`.

Tools that play sound or write the miniDSP or receiver are refused unless the owner allows
actions on that page: either htTamer asks the owner each time (MCP elicitation, through the stdio
command) or it relies on the client's own approval prompt. Slot 1 is never written, receiver volume
can only be lowered, and keys and tokens are scrubbed from results.

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
