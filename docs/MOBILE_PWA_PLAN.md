# htTamer on your phone: plan

**Goal:** run htTamer from your phone while you sit at the listening position: start a tune,
answer "move the mic" prompts, switch slots for A/B listening, set AVR levels with the meter,
and install it on the home screen like an app.

**What doesn't change:** the PC stays the engine. It's the only thing plugged into the miniDSP
(USB control and audio) and the UMIK-1. The phone is a remote control for the same dashboard.
The phone's own microphone is **not** used for measuring: it isn't calibrated and it applies
automatic gain, so its readings would be wrong.

---

## Phase 1: phone remote on your home Wi-Fi (about half a day)

1. **LAN mode, off by default.** `subtune serve --lan` listens on the PC's network address
   as well as localhost. Normal `serve` stays local-only.
2. **Pairing instead of passwords.** In LAN mode the dashboard shows a QR code holding the
   address plus a one-time pairing token. Scanning it stores a long random device key on
   the phone. Every API call from another device must carry that key; calls from the
   PC itself don't. A "Paired devices" list in the menu can revoke a phone.
3. **Safety rules enforced on the server, not just in the page:**
   * anything that plays sound or writes to the DSP still needs a confirm tap;
   * writing slot 1 (your original setup) keeps its explicit confirmation;
   * one action at a time (already true), and a phone can always press **Stop**.
4. **Touch polish:** a bottom bar on narrow screens (Tune · Result · Slots · Menu), bigger
   tap targets, and the "move the mic" prompt as a full-screen card with a big button.
5. **Keep the phone awake** during a measurement run (Screen Wake Lock), so the
   prompt is still on screen when you come back from moving the mic.

## Phase 2: installable app (PWA)

1. **Web app manifest:** name, icons (192/512 px plus maskable), theme colors matching
   the dashboard, `display: standalone`, so it opens full-screen from the home screen.
2. **Service worker:** caches the app shell so it opens instantly, and shows a friendly
   "Can't reach your htTamer PC" page when the PC is off. Measurements and DSP writes always
   go live to the PC, never from a cache.
3. **HTTPS is required.** Phones only allow installing, service workers and wake lock on
   secure pages, and a plain `http://192.168.x.x` address doesn't count. Options:

   | Option | Setup | Works away from home | iPhone | Verdict |
   |---|---|---|---|---|
   | **Tailscale** (free) + `tailscale cert` | install on PC and phone, one command | yes, privately | yes | **recommended** |
   | mkcert local certificate | install a root certificate on each phone | no | yes, but fiddly | fallback |
   | Self-signed certificate | none | no | install blocked | no |

4. **Optional notifications:** "Your measurement needs you: move the mic to spot 3" or
   "Check-up finished". Uses Web Push, which needs HTTPS. On iPhone it works only for apps
   added to the home screen (iOS 16.4+).

## Phase 3 (only if ever needed): app-store app
Wrap the same pages with Capacitor for an App Store or Play Store listing, background tasks,
or a native widget (e.g. slot switching from the lock screen). Not needed for anything above.

---

## Security notes
* LAN mode is opt-in, and the device key is required for every request from another device.
* Never forward the port to the internet. For remote access, use Tailscale (private network, real TLS).
* The Anthropic API key stays on the PC and is never sent to the phone.

## Questions to settle before building
1. iPhone or Android? This affects install steps and notifications.
2. Is installing Tailscale on the PC and phone OK? It's the simplest way to get HTTPS.
3. Should the phone be allowed to start measurements and apply tunes, or only switch
   slots, run the meter and show results?
