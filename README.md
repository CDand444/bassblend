# htTamer

htTamer tunes the subwoofers of a home theater. It measures each sub with a UMIK-1
mic, writes gain, delay, polarity and EQ into a miniDSP 2x4HD, blends the subs with
the speakers through the receiver, and offers a live EQ with a live analyzer and an
assistant. It runs on a Raspberry Pi (or Windows) and is used from a web page.

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
