# Spec 12: bass shakers (tactile transducers)

**Goal:** the owner can drive bass shakers (ButtKicker, Aura and similar, bolted to a couch or riser and fed by
their own amp) from a free miniDSP output. htTamer feeds them the same bass the subs get, band-limited, at
their own level, and lined up in time with the subs' sound at the main seat. Night mode can keep them on
while the subs are muted (feel the bass without waking the house).

## Data

- Settings (`config.py` DEFAULTS, `server.SETTABLE`):
  - `shakers`: list of 0-based miniDSP outputs (default `[]`). Never overlaps `subs`; at most `N_OUTPUTS - 1`
    in total with the subs (at least one sub stays).
  - `shaker_gain_db` (default -6, range -30 to 0): output gain.
  - `shaker_hpf_hz` (default 15, 5-40): Butterworth 24 dB/oct high-pass (`biquad.bw4_highpass`), keeps the
    amp from wasting power below what can be felt.
  - `shaker_lpf_hz` (default 80, 40-150): Linkwitz-Riley 24 dB/oct low-pass (`biquad.lr4_lowpass`).
  - `shaker_delay_ms` (default null = automatic, else 0-30): see Timing.
  - `shaker_night` (default true): night mode leaves the shakers on.
- `subtune/shakers.py` (new, pure where it can be): `outputs(s)`, `add(output)` / `remove(output)` (like
  `subouts.add/remove`: refuse an output that is a sub output, nothing written to the miniDSP, journal line),
  `delay_ms(result, s, room)`, `slot_cmds(d, result, s)`, `tone_range(s)`.

## Timing

A shaker is felt at once; the subs' sound reaches the seat after the tune's delay plus the travel time.
`delay_ms`: with `shaker_delay_ms` set, that number plus the mean of the tuned subs' `delay_ms`. Automatic:
the mean over tuned subs of `delay_ms + distance(sub, main seat) / 0.343` (m to ms) when the room has the
sub and seat positions; otherwise the mean `delay_ms` alone. Clamp 0-30 ms. Pure function, tested.

## What it changes

1. **Applying a tune** (`cli.full_slot_cmds`): each shaker output is routed from inputs 0 and 1 (gain 0), gets
   `shaker_gain_db`, the delay above, no invert, all PEQ bands flat and bypassed, crossover group 0 = the
   low-pass, group 1 = the high-pass (both via `MiniDSP.write_sub_filters` with empty biquads), FIR bypassed,
   unmuted. The applied result stores `shakers: [{output, gain_db, delay_ms, hpf_hz, lpf_hz}]` (measured, not
   current: tones and the page read it from the result). Not in the library fingerprint. Outputs that are
   neither subs nor shakers stay muted as now.
2. **Measuring and the fit:** unchanged. `Rig.prepare` already mutes every output that isn't a sub, so the
   shakers never play sweeps; the optimizer never sees them.
3. **Test tones:** a shaker output may take a test tone in `shaker_hpf_hz`-`shaker_lpf_hz` (clamped to 15-150),
   only when the playing result has it in `shakers` (else the same "tune again" refusal as a sub). The page's
   tone checks, `cli cmd_tone`, `server.start_tone` and `guard` (test_tone) all go through one check function.
4. **Night mode** (`automation.py`): one helper `night_cmds(on, s)` used by `set_night`, the slot-change
   path, the watchdog, `abtest.py` and `server.py`. Without shakers, or with `shaker_night` off: the master
   mute, exactly as now. With shakers and `shaker_night` on: master mute stays off, each sub output is muted
   (`c_out_mute`), shakers untouched; turning night mode off unmutes the sub outputs. Output mutes live in the
   slot, so this only happens while htTamer's own slot plays (never slot 1); any other slot gets the master mute.
   After every slot switch `after_switch_cmds` puts the right state back. The miniDSP's status can't report
   output mutes, so the watchdog quietly re-sends them each pass in that case.
5. **Page:** Room and subs gets a "Bass shakers" block: pick free outputs (not sub outputs), gain, high-pass,
   low-pass, delay (Auto or a number, shows the automatic value), "keep on in night mode", and a Play test
   tone per shaker (same confirm as the subs). A notice when shakers were changed after the playing tune:
   "Apply the tune again to send the shakers their bass" (no new measuring needed: re-apply the current tune).
6. **Assistant:** the shaker settings in `set_target_settings`'s schema; test_tone accepts a shaker output.
7. **Manual + CHANGELOG:** a short "Bass shakers" section: what they get, timing, night mode, tones.

## Steps (one local-model session each)

1. Settings + `shakers.py` (add/remove, `delay_ms`, `slot_cmds`, `tone_range`) + `full_slot_cmds` hook +
   `tests/test_shakers.py` (overlap refused, delay auto/manual/clamped, slot writes: routing, LPF on group 0,
   HPF on group 1, unmuted; no shakers = the exact same commands as before; slot 1 never).
2. Tones (one check for page/cli/server/guard) and night mode (`night_cmds` everywhere) + tests.
3. Page block, API routes (`/api/shakers` add/remove like the sub outputs), assistant schema, manual,
   changelog; manager runs the browser check.

## Out of scope

Measuring shakers (an accelerometer), per-seat shaker groups with different levels, shaker EQ bands.
