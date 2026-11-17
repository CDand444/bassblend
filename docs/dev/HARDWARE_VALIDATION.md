# Real-hardware validation: the full workflow, repeated

Everything in htTamer is tested offline, in a browser and on real hardware piece by piece. What has not been shown is the **whole
workflow from a fresh image, three times in a row, with the same result**. This is the protocol for that. It needs the owner at the
room (it plays sound); nothing here is automated except reading and comparing what the app stored.

**Safety rules still apply:** sound only when the owner starts it; miniDSP slot 1 is never written; the receiver volume is only raised
by the guarded auto-level; the receiver is put back exactly as it was.

## 0. Before you start

- Note the receiver's input, volume, sub level, listening mode and Dirac slot (write them down or photograph the display): step 5
  compares against this.
- Note what miniDSP slot 1 holds (do not touch it).
- Mic at the main seat, ear height, pointing up. The UMIK-1 calibration file for that exact mic is at hand.

## 1. Fresh Pi image

| Step | Do | Pass when |
|---|---|---|
| 1.1 | Write `bassblend-<version>.img.xz` to a new SD card (Raspberry Pi Imager; add Wi-Fi and SSH). Check the `.sha256` first. | the checksum matches |
| 1.2 | Boot with the miniDSP and UMIK-1 plugged in; open `http://bassblend.local:8765`. | the page opens within 3 minutes; the safety notice shows |
| 1.3 | Accept the notice, choose a PIN, press **Run the silent check** on Home. | miniDSP, Mic and Storage show Ready (the silent check plays nothing) |
| 1.4 | Home should open in **Basic** with the **Your first calibration** card. | Basic menu: Home, Setup, Calibrate, Results, Compare |

## 1b. The Windows installer (same protocol on a clean Windows 10/11 machine)

Run the installer from the release on a PC that has never had htTamer or Python, with the miniDSP and UMIK-1 plugged in.

| Step | Do | Pass when |
|---|---|---|
| W.1 | Install (no admin needed), start htTamer, **Run the silent check**. | miniDSP Ready (no driver prompt), Mic Ready, Storage Ready |
| W.2 | Plug the PC's HDMI cable into a receiver input. In Windows Sound settings pick that output, **Configure speakers**, choose 7.1. | the check's HDMI row reads "<output>, 8 channels" |
| W.3 | Blend test and Speaker check with **PC HDMI**; pick the receiver input the PC is plugged into. | all channels are heard; **front left, center, right, surrounds and backs are the right speakers** (if the receiver shows surround and surround back swapped, tick *Swap surround and surround back*, then repeat once) |
| W.4 | Start a calibration and, while it runs, open the Live EQ page and apply a change. | no "resource busy" errors in Activity: the miniDSP calls queue behind each other |
| W.5 | If a network test can't reach the receiver: run the firewall command from the help (Copy the command; PowerShell as administrator). | the receiver fetches the test file |

## 2. USB devices and HDMI routing

- Unplug and replug the UMIK-1 and the miniDSP once each; run the silent check again. Both come back without restarting anything.
- Plug the Pi's micro-HDMI port (next to the USB-C power) into a receiver HDMI input; pick that input once on a test page.
  **HDMI** shows Ready; the all-speakers check ("Speaker check") later plays through it. (On Windows the PC's own HDMI output plays;
  see 1b.)
- Pass when: each device is found by name every time, and a wrong or missing cable shows a clear message instead of a hang.

## 3. First calibration (Basic mode, no room details entered)

1. Add the calibration file, choose the sub outputs, enter the receiver's address. Nothing else.
2. Home: **Calibrate my subs** (one seat). Watch the stages: Reset preset, Measure, Optimize, Apply, Verify, Back to AVR.
3. Open **Results**.

Pass when: the run finishes without errors in **Tools → Activity**; the Results headline says what improved with the basis
"measured after the tune"; slot 3 (not 1) holds the tune; the receiver is back where it was.

## 4. A Dirac-assisted tune

1. Run the calibration with Dirac switched on in the receiver (Setup → Speakers and Dirac), then run Dirac Live with the tune playing.
2. Run the **blend test** (Pi HDMI) and the **Speaker check**; open **Results** and the receiver setup sheet.

Pass when: the blend loss and the verify are recorded for the playing tune; the sheet says "verify, not change" for levels and
distances Dirac owns; nothing is written to the receiver that you did not approve.

## 5. Receiver restoration

After every test that switched the receiver (calibration, blend test, speaker check, headroom): input, volume, listening mode,
sub level and Dirac slot are what you noted in step 0. The receiver's sub level resets on an input change by design; htTamer sets it
again afterwards. Pass when all five match, and Stop pressed mid-test also restores them.

## 6. miniDSP writes

Pass when: the pre-check ("EQ and delay writes verified") shows a measured cut and delay within 0.5 dB and 0.5 ms of what was
written; slot 1 is unchanged; the filters shown under Tools → Filters equal the tune's.

## 7. Repeat three times, then compare

Do steps 3 to 6 three times (clear the tune between runs by calibrating again; keep the mic and the room as they are). After each
run, on this computer:

```bash
python scripts/validation_snapshot.py snap ssh://bassblend run1      # then run2, run3
python scripts/validation_snapshot.py compare validation/run1.json validation/run2.json validation/run3.json
```

`compare` checks that the numbers that should repeat do (limits in the tool): the measured flatness at the main seat after the tune
within 0.7 dB across runs, the bass lost at the crossover within 1.5 dB, each sub's gain within 1 dB and delay within 0.5 ms, the same
polarity every time, no hardware check reporting a failure, and every run verified with a real measurement. A FAIL names the number.

**Overall pass** = every step above passes in all three runs and `compare` says PASS. File what failed as an issue with the
snapshot JSON attached (it holds no keys, PIN or personal details).

## 8. Sub workshop (not yet tried on real hardware)

The Sub workshop (Tune → Sub workshop) measures with `Rig.probe`: one normal sweep through one sub, with the others muted. Everything else is
tested offline with synthetic curves. On real hardware check, for one sub from the catalog (a Hsu VTF-3, say):

1. **Tuning**: start a Tuning session; Measure should play a single sweep on only that sub and return to the page with a score and feedback; the other subs stay muted
   and are unmuted afterwards; the receiver input is put back. Run the first Ports choice twice with **Measure again**: the feedback should say it repeats within about 1 dB.
2. **A real change shows**: plug a port, measure; the feedback should say what moved (less bass at 20 to 30 Hz, a smoother response) in the direction a ported-to-sealed change does.
3. **Crawl**: put the sub at the seat, measure two mic spots a few feet apart; the scores should differ and the plot should show different curves. Nothing plays unless you press Measure.
4. **Night mode on**: Measure is refused with the night-mode message.

## What the app records for you

- **Home → Is it ready?** shows what was connected, set up, verified (with when) and never tested, and whether it is safe to proceed.
- **Verify → Results** shows the before and after and says what did not improve.
- `scripts/validation_snapshot.py` turns both into one small JSON per run for the comparison above.
