# htTamer changelog

## Nov 18, 2026 - Network name and port

- **Tools → Network name** sets the address phones and computers use, `http://<name>.local:<port>`. On the Pi a new name
  renames the Pi and a new port restarts htTamer on it (a Pi updated from an earlier version can do this after one more
  update). The MCP page's client setup follows the port.
- **Windows can open to your home network.** The installer has a Network page (network mode on or off, the name and port),
  also changeable under Tools → Network name. In network mode htTamer answers its name itself and asks for a PIN,
  chosen on the Windows computer before anyone else can sign in.

## Nov 18, 2026 - One name everywhere

- Everything is now named **httamer**: the Pi image (`httamer-<version>.img.xz`, at `http://httamer.local:8765`), the program
  folder `/opt/httamer`, the data folder `/var/lib/httamer`, the `httamer` service and account, the `HTTAMER_*` settings for
  developers, the settings file (`httamer-config-...json`) and the test sound files. The project's earlier name is gone.
- **An htTamer you already run moves itself over.** It takes two updates: the first installs this version the old way, the
  second moves the program, your data, the account and the services to the new names (your tunes, settings, keys and PIN
  move with them). Its address on your network does not change. Logs are then `journalctl -u httamer`.
- Settings files and backups saved before the rename still load.
- If you put an MCP token in a file in your home folder, rename it to `~/.httamer-mcp-token`.
- **Installing on a Pi or Linux box you already run** is now described in the README, next to the recommended SD card image.

## Nov 17, 2026 - Easier to read and to press

- Grey text, blue buttons and links are darker (lighter in the dark theme) so everything meets the usual 4.5:1 reading contrast; links have one colour everywhere; keyboard focus shows a clear ring.
- On a phone or touch screen nothing you press is under 36 px tall, the Beta badges in the menu are readable, and the Room page's buttons wrap instead of running off the edge.
- **Basic is the starting view** on every device that has not chosen one (a calibrated system used to open in Advanced). Your choice is remembered per device.
- The status pill at the top says **Idle** when nothing is running (it said "Ready" even when Home said "Not ready"). Home no longer shows an empty card while the latest result loads.

## Nov 17, 2026 - Maths review

- **Ring times you can rely on**: below about 40 Hz the analysis filter rings longer than most rooms, so no ring time is given there any more; a time that reaches the end of the recording says "at least". The waterfall stops at 300 ms, where a stored sweep stops being the room.
- **Blend loss** is measured against the true perfect sum of speakers and subs (it read up to 3 dB too high).
- **Live music check** plays your song as mono on every speaker, so the coherence it shows is noise and echoes, not the difference between left and right.
- **Sound field**: the subs are driven with the playing tune's levels, delays and polarity (they were all driven equally); the bass ring time comes from your own measurements where they can tell, and the textbook estimate is labeled as rough; what goes through the walls is a rough dB figure, no longer a percentage.
- **One waterfall**: the System report's Waterfall button opens Bass analysis, which now also shows the whole system. **One trust answer** per mic spot, from noise and take-to-take agreement together.
- **Tuning: boosts are always broad.** An EQ boost is never narrower than Q 3 (cuts may still be narrow): a narrow boost only fills a dip at one seat, rings, and costs headroom. The tuning engine also has its own offline test now (limits on boost, level, delay).
- The room's Schroeder frequency uses the room's own ring-time estimate, not a fixed 0.4 s.
- **Safety**: removing the protective limiters, the live analyzer, the live music check, the blend test and the level check can no longer touch or play through the original preset (slot 1) by accident.

## Nov 20, 2026 - Live music check (two-channel)

- **Live music check** (Verify → Bass analysis): pick a WAV of a song you know, press Start, and htTamer plays it through the receiver (the Pi's HDMI or the network player) while it records the mic. The music itself is the reference channel, so you get the system's response, phase and **coherence** (how much of what the mic heard is your music rather than room noise or late echoes) from 20 Hz to 20 kHz, measured with real music. It finds the player's delay, corrects the small clock drift between player and mic, can set the test volume (guarded, put back after), and restores the receiver as every test does. Nothing plays until you press Start.

## Nov 20, 2026 - Bass analysis

- **New page: Verify → Bass analysis**, made from the sweeps htTamer already takes (nothing plays):
  - **How long the bass rings**: a waterfall of the first 300 ms after the sound stops, for all subs with the playing tune, all subs as measured, or one sub, at each mic spot; plus the ring time (time to fall 20 dB) and the frequencies that ring longest, with what to do about a long one.
  - **Subs and speakers: in phase?** For each seat of the blend test: the speakers, the subs and the two together, the phase between them where both play, and how much they lose to cancelling, as measured and with the blend test's best delay and polarity.
  - **Can this measurement be trusted?** Measuring now records how much two takes of the same reference sweep disagree at each frequency; the page names the frequencies where they disagreed by more than 1.5 dB.

## Nov 20, 2026 - starter database

- **More makers in the starter hardware database** (read only from each maker's own page or spec sheet, every number checked against the text): KEF (Q, R, Reference, Blade, LS50/LSX, Kube and KC subs, Ci in-wall and in-ceiling), Polk Audio, Definitive Technology, ELAC, Q Acoustics, Bowers & Wilkins (600/700/800 series, DB and ASW subs), PS Audio, the SVS Ultra Evolution speakers, and about 70 more Klipsch (Heritage towers, Forte, Heresy, Cornwall, Klipschorn, KD, CP, CS, DS, Flexus subs and others). Sizes a maker gives only in mm or kg are converted. 94 subs and 392 speakers in all. JL Audio, Monoprice, Focal, Arendal and Yamaha publish specs only through scripts or block automated reading, so they are still not in; add your model with Remember size.

## Nov 19, 2026 - better on a phone

- **Room editor on a phone** fills the screen: a short header (Undo, Redo, Cancel, Apply), one row of things to add that scrolls sideways, the room as big as it fits, and the side panel only while something is picked. Finger drags move things the same way as the mouse.
- **Subs page** no longer runs off the side of a phone (the sub cards were at least 400 px wide).
- **Room page**: the rows of buttons above the plan scroll sideways instead of taking four lines.
- **Long introductions** on the pages show three lines on a phone; a tap opens the rest.
- Wall and ceiling speakers, lights and the screen are no longer reported as "partly outside the room" in the editor when they sit against a wall.

## Nov 19, 2026 - review fixes

- **Live EQ can no longer touch slot 1**: every live EQ write now selects htTamer's slot first, and switching the live EQ off while you listen to another slot (your original slot 1 included) writes to htTamer's slot and then puts back what was playing. Before, a write between the 15-second checks, or "Live EQ off", went to whatever slot was playing.
- **Settings, the room and saved tunes are written safely**: a temporary file is swapped in, so a power cut or a page reading at the wrong moment never finds a half-written file (which could stop the app until repaired).
- A broken riser sent to the re-fit now gets a plain error instead of a server error; leftover and duplicate helpers removed.
- **Faster riser auto-wrap**: after a move, only the risers the moved item could touch are re-fitted (one request each), so dragging things around on the Pi stays quick.

## Nov 19, 2026 - the room editor moves speakers, fixtures and the screen

- **Speakers in the room editor**: drag them like everything else. In-wall and on-wall speakers stay on the nearest wall and slide along it; ceiling and height speakers can pass over furniture; floor speakers count as solid for the overlap check. Apply saves their positions (their kind, height and aim stay on the Speakers page).
- **Fixtures in the room editor**: lights, a projector, vents and the rest move too, and a ceiling light, projector or wall light can be added from the palette; wall lights stay on a wall.
- **The screen** slides along the front wall in the editor.
- Risers re-fitted in the editor now keep clear of the speakers where you have just moved them.

## Nov 19, 2026 - Klipsch and REL in the starter database

- **Klipsch** (67 models, from each product's own spec sheet): the Reference and Reference Premiere subs (R-100SW to RP-1600SW, SPL-100/120/150), bookshelf, center, Atmos elevation, on-wall, in-wall and in-ceiling speakers, with sensitivity, impedance, power handling, frequency response, size and weight; the spec sheet is linked as the manual.
- **REL** (15 subs: Serie T/x, HT, S, the No. series, Classic, 212 and Carbon Special Black Label): cabinet size and weight from each page, and amplifier power where the page's comparison lists it.
- 62 subs and 113 speakers in all. KEF, Polk, Definitive Technology, JL Audio and Monoprice publish their specs only through scripts or block automated reading, so they are not in yet; add your model with Remember size.

## Nov 19, 2026 - room editor in 3D, smoother risers, one sub picker

- **Room editor in 3D**: a Top / 3D switch in the editor. In 3D, drag an item to move it across the floor (it pulls to walls and neighbours the same way), drag empty space to turn the view, drop new items from the palette onto the floor; the selected item is outlined.
- **Smoother riser outlines**: a riser along a slanted wall is one straight edge (no staircase), and the editor centres the room.
- **One sub picker**: the separate "Catalog model" list on each sub card is gone. Pick (or type) the model once; when htTamer has a controls guide for it (Hsu VTF-3 MK5 HP, SVS PB-2000 Pro, SB-1000, Rythmik F12), its knobs appear by themselves. "Remember size" on a sub now also saves its driver, enclosure, rated low end and amp power, and the model list updates.
- **Treatment page**: "See the bounces with and without it" opens the Sound field comparing the bare room with your treatment.

## Nov 19, 2026 - flooring, room modeler, speaker aim in 3D

- **Room page is now tabs beside a plan that stays in view**: Size and floor, Shape, Where you live, Screen, Seats, Furniture, Fixtures. The plan / 3D stays on the left (and follows you down the page) while you change things on the right; on a phone the plan sits above the tabs. The tab you were on is remembered.
- **Room editor (stage 1)**: an "Edit layout" button opens a pop-out, top-down editor. Drag couches, risers, subs and seat positions; add a couch, loveseat, sectional, recliner, riser or seat by clicking or dragging it onto the room; items pull in to walls and each other (hold Alt to place freely); R turns, Delete removes, arrow keys nudge, Ctrl+Z / Ctrl+Y undo and redo; problems (outside the room, overlapping) are flagged. Apply writes it into the Room card; Save room keeps it.
- **Risers are now fluid shapes**: a riser can take the shape of the room instead of boxes: it follows an angled wall or notch exactly, and a door's swing is cut away as the quarter circle the door sweeps (two half-width leaves for a double door). It wraps around subs, floor-standing speakers and any couch standing in its way, and re-fits itself in the editor when anything moves. A riser with a sub or column standing inside it falls back to a few touching boxes.
- **Riser top surface**: wood, carpeted, painted/laminate or concrete. It changes the ring-time estimate (the riser's top replaces the floor under it) and the riser's color in the plan and 3D.
- The assistant and the setup text no longer name the AI model or its maker: they say "the AI" or "the AI assistant" (outside apps such as Claude Desktop are still named where you connect them).

- **Risers wrap around walls and obstacles**: the modeler (measurements and AI) now cuts each tier to the room's outline (angled walls, notches, alcoves) and around doors (their swing), subs, floor-standing speakers and any furniture already placed, as a few touching boxes at one height; the tier is left whole when nothing is in the way. "Wrap around walls and obstacles" can be turned off. A riser can now be as small as 1 ft (a cut piece), and a room holds up to 40 furniture items. The AI can name obstacles it is told about (a column, a fireplace) and the risers are cut around them.
- **More SVS subwoofers in the starter database**: the original SB-1000, SB-2000, SB-3000, SB-4000, PB-2000, PB-3000, PB-4000, PC-2000, PC-4000, SB13-Ultra, PB13-Ultra, PB16-Ultra, SB16-Ultra, PB12-NSD and PB12-Plus (33 subs in all).

- **Starter hardware database filled in**: 18 subwoofers (SVS, Hsu Research) and 60 speakers (SVS Prime, Revel in-room and architectural) with size, driver, rated low end, amp power, sensitivity, weight, frequency response and each maker's page (and owner's manual where the page links one). Every number is checked against the maker's own page text before it is accepted; nothing is estimated.
- **Sub cards use the database**: each sub on the Room page now has a model drop-down (like the Speakers page); picking one fills the driver, enclosure, cabinet size, rated low end and amp power. Choose Other to type one.

- **A backup before the AI changes anything stored**: the first time the assistant (or an AI client over MCP) edits the room, speakers, tune settings, live EQ and the like, htTamer makes a backup first (one per 10 quiet minutes, shown in Backups as "before the AI changed something"). If the backup can't be made, the change isn't made. Frequent AI backups never push out your newest update, weekly or manual one.
- **The modeler follows your room**: with "Place rows under my seats" (on by default) the tiers go under your seat rows, as high as the seats' head heights say, and are kept inside an angled or notched outline instead of the bounding box; the text path is told the outline and seat heights too.
- **Sound field, with and without treatment**: a With / Without / Compare switch; Compare lays the bare room's bounces (red dashed) under the treated ones, thickness showing loudness, with a before/after table.
- The assistant no longer ends every reply by offering a sweep.

- **Flooring** on the Room card (carpet, hardwood, laminate, vinyl, tile, bare concrete) and an **area rug** box. The ring-time estimate, treatment plan (no rug suggested over carpet or a rug; tile and concrete called out), sound field, 3D floor color, apartment tips and the assistant all use it.
- **Room modeler** (Room card, under Furniture): build a stepped riser with a couch on each tier from measurements (rows, width, depth, first riser height, step; no AI) or from a plain-text description (the AI assistant, one request). The proposal appears in the form, plan and 3D view, is not saved until Save room, and has an Undo. Up to 24 furniture items now.
- **Speaker aim in 3D**: each speaker has an Aimed pick (Auto, at the main seat, straight down, up and bouncing off the ceiling to the seat, custom Faces plus Tilt). Auto aims atmos modules up at the ceiling bounce point and in-ceiling speakers down. The Speakers page, Treatment/3D views (with an aim beam) and the sound field follow it.

## Nov 18, 2026 - Sound field viewer, speaker facing in 3D

- **Sound field** (Survey → Sound field): views from above, from the side, from the end and in 3D (WebGL, three slices you can turn), with **Bass** and **Treble** as separate layers. Bass is the room's standing waves driven by your subs (ring time worked out from the room's surfaces and your treatment); Treble follows a chosen speaker's direct sound and reflections to your seat (image-source method, exact for a box) as paths, pulses and wavefronts, losing what each wall or panel absorbs at that frequency, with a table of the strongest early reflections; **what goes through the walls** shows the mass-law leakage. Earlier note: a map of the room's bass seen from above. Drag the frequency slider and the loud spots (red) and quiet spots (blue) move; pick the height of the slice; switch between a level map and a moving wave; click a room mode to jump to it; set the room's damping. The line chart shows what the same model says at your seat with your measured response laid over it. It is the standard standing-wave (modal) model for the room's box (the main rectangle for an irregular room), driven by your subs. Treble (reflections off walls and panels) is not in this version.
- **Speakers honor Faces in 3D**: the Treatment view did not redraw after a speaker was edited, and the Room page's 3D ignored the saved direction; both fixed.

## Nov 18, 2026 - speaker models from the database, assistant dimensions

- **Speakers page model drop-down**: pick a speaker from the hardware database (its size and kind fill in), or choose Other and type one; Remember adds a typed model to the list.
- **The assistant can set speaker and sub dimensions**: it takes width, height and depth in inches, cm, mm, feet or metres, or a string like "230 x 1020 x 300 mm", and a field it doesn't know is now an error it can read (before, it was silently ignored, so the assistant reported success while nothing changed).
- **The assistant docks properly on very wide screens** (no more narrow column).

## Nov 18, 2026 - the Speakers page

- **Angle to the main seat** on every speaker: how far left or right of straight ahead, how far above or below ear height, how far away, and whether that is inside Dolby's range for the channel, updating as you type. A new **Faces** field says which way the speaker points (blank = at the seat) and the row shows how far off the seat that is; the 3D view turns the speaker to match.
- **The page fills the width**: one row per speaker with fields that flow to the screen (stacked on a phone) instead of a wide table that scrolled sideways.

## Nov 18, 2026 - Sub workshop

- **Sub workshop** (Tune → Sub workshop), two guided workflows with a measurement after every change, plain feedback after each, retests and a verification:
  - **Tune the sub's own controls**: for a sub picked from the catalog (a Hsu VTF-3: ports, then the EQ switch, then Q). One control at a time: you set it, press Measure, and htTamer scores it against the target curve (shape, ripple, reach), says what changed, keeps the best, and finishes with a verification of the winners. **Record these on the Subs card** writes down the settings (nothing is sent to the sub).
  - **Sub crawl**: the sub at the seat, the mic at places a sub could go (eight default spots, or your own with positions); the smoothest spots win, then verify at the seat after moving the sub. The best spot can be set as the sub's position.
  - Every trial has Measure again (is it repeatable?), a chart overlays them, and the assistant can read and explain a session. Each measurement is one sweep through one sub and only starts when you press Measure; night mode blocks it.

## Nov 18, 2026 - fixtures and wall or ceiling speakers in the treatment plan

- **Fixtures** on the Room page: lights, a ceiling projector, fans, vents, sprinkler heads and wall lights, each with a position and size. The plan keeps clouds and panels clear of them (a recessed light, the projector's beam to the screen, 18 in round a sprinkler head, a foot round a vent), reduces panel counts where a wall light or speaker covers the zone, and gives plain guidance for working around each. They appear on the plans and in 3D, where treatment never passes through them.
- **Speakers on walls and in the ceiling** (set their kind on the Speakers page) are obstacles too: panels leave about 5 in round an on-wall or in-wall speaker and clouds stay clear of in-ceiling and height speakers.

## Nov 18, 2026 - full-stack review fixes

- **Home type on Setup** (reachable in Basic): a quick question that saves by itself, shared with the Room page block.
- **Remember size**: save a sub's or speaker's cabinet size to the hardware database from its card or row.
- **Assistant**: a set_quiet_hours tool (guarded, asks first, refused in read-only mode) and the prompt knows the new treatment items and the picker.
- **Phones**: the header wraps in Advanced mode instead of running off the screen. **Settings file**: the Windows HDMI output name is not carried to another computer.
- **Installed treatment**: records for doors, windows, stand-ins and soffit panels match only by plan id, so a panel on a wall is no longer counted twice.

## Nov 18, 2026 - choose what to show on the Treatment page

- **What to show**: beside the plan or 3D view, every item of the treatment plan has a check box (all on by default), grouped by value (Do first, Next, Nice to have, Already installed) with a check box per group and All / None. The plan drawing, the 3D view, the cost and the buy list follow your choice, which is remembered on this device. The summary says how much the shown items still cost and about what share of the plan's benefit they bring.
- **Buy list**: identical panels are bought together (for example 12 absorber panels, 2 x 4 ft, 4 in + 2 in gap, with what each is for), with a cost range and a Copy as text button.
- **Ceiling cloud** follows a sloped ceiling tile by tile and keeps clear of the height speakers as well as soffits.
- **Open back**: when the room opens behind the seats, a freestanding panel or heavy curtain on stands stands in for the missing back wall.

## Nov 18, 2026 - doors, windows and soffits in the treatment plan

- **Doors get treatment**: a double door always gets a panel or heavy curtain on each leaf (big, hard, thin and it rattles); a single door gets one when a reflection lands on it. Windows in a reflection zone get a heavy curtain item. The 3D view draws them on the door or over the glass.
- **Wall panel counts leave doors, windows and openings out** (the item says how much wall that is).
- **Soffit undersides** get a thin-panel item (low priority), drawn in 3D under the soffit.

## Nov 18, 2026 - Dropbox backups

- **Dropbox as a backup copy**: Tools → Backups → Keep a copy in Dropbox. You make a small free Dropbox app once (App folder, files.content read and write), paste its App key, allow access on dropbox.com and paste the code. Every new backup is then also sent to /htTamer-backups (the newest five stay, plus the one made before an update); a failed copy is shown on the card and never stops the backup. Send the newest now, see what is in Dropbox, bring one back (then Restore as usual), or disconnect. Only a refresh token is kept, in the config folder like an AI key: never in settings and never in a backup.

## Nov 18, 2026 - speaker placement in 3D, soffits everywhere

- **Speaker placement has a 3D view**: the recommended spots as pale speaker cabinets, yours (where recorded) as dark ones, dashed lines from the seat, and a green, orange or red line from each recommended spot to where yours is.
- **Soffits are acknowledged**: ceiling speakers hang from a soffit's underside where one is overhead (in 3D and in the plan, with a note saying so), and the placement and treatment plan drawings show soffit footprints.

## Nov 18, 2026 - cabinet sizes, sub aim, screen frame, soffit-aware treatment

- **Double door** in the openings catalog (Room → shape → Openings, doors and windows): an Add double door button (5 ft, two leaves on the plan and in 3D), the same panel advice as a door, and the phone builder and assistant know it.
- **Ceiling treatment respects soffits**: the ceiling cloud is trimmed to stay clear of every soffit (the plan says which), and the 3D view leaves no tile where one hangs.
- **Sub aim**: each sub has a "Points at" pick and an angle (0 = back wall, 90 = left, 180 = screen, 270 = right; blank = at the main seat). The plan shows an arrow, the 3D sub turns to face it, the card says which wall it points at and how far, and the treatment plan warns when one fires into a wall a few inches away.
- **Cabinet sizes**: subs and speakers take a width, height and depth in inches, from you, from the hardware database (new fields on subs and speakers, which the assistant can fill in), or a labeled typical size. The 3D views draw the real size.
- **Screen frame**: the screen has a frame or bezel width; the plan, the 3D view and the treatment plan use the whole outer size, and front-wall panels stay off the screen and its frame (unless it is acoustically transparent).

## Nov 18, 2026 - a better 3D view, treatment in 3D, risers

- **Treatment in 3D**: the Treatment page has a Plan / 3D switch. Wall panels, ceiling clouds, the rug and corner traps are drawn where the plan puts them, with your couches, speakers and subs.
- **A fuller 3D view** (Room and Treatment): shaded solid objects with ground shadows; speakers as cabinets with a cone facing your seat; ceiling speakers hung from the ceiling; subs as cubes; couches with arms, cushion and back; your view angle is kept; double-click resets it.
- **Risers**: couches sit on risers by themselves (they rise with them in 3D, stay inside the edges, follow when the riser moves), a new couch lands on a riser, a new riser fits under a couch, and the page says when a couch hangs off its riser. Added Sit on a riser and Fit to couch.

## Nov 17, 2026 - house, apartment or condo

- **Where you live** on the Room page: home type, floor, who shares your floor, ceiling or walls, wood or concrete. Shared buildings get
  a gentler bass-lift step on Home, a quiet-hours suggestion, test-timing and sub-placement tips, rental-friendly treatment notes and a
  structure note on room modes. The assistant can record it too.
- **Quiet hours**: night mode can switch itself on at a set time (Automation); turning it off yourself overnight is respected.

## Nov 17, 2026 - 1080p review, folded AI suggestions

- **AI suggestions are folded and closed by default** (suggested setup, per-sub suggestions, room analysis, the phone builder's assumptions
  and questions); the room analysis says when it is older than the current tune. The AI settings sit in a fold too.
- **Layout at 1080p**: Subs shows two wide cards per row (the page is a third shorter); the automation inputs are a grid instead of one
  long list; the treatment page folds Before and after, Your constraints and What you have installed and has a jump bar; the couch
  reflection note appears once, not once per seat; the Home cards that repeat Results start folded.

## Nov 17, 2026 - Windows: HDMI, the miniDSP lock and wording

- **No Pi wording off the Pi**: pages, messages, the assistant and the CLI say "this computer" unless htTamer runs on a Raspberry Pi.
- **PC HDMI on Windows**: receiver tests, including the 7.1 all-speakers check, can play through the PC's own HDMI output (WASAPI), with
  an output chooser, a 7.1 setup hint and a swap for surround and surround back. The silent check tests it.
- **miniDSP lock on Windows**: commands from different processes (a job and the live EQ) now wait for each other, as on Linux.
- **Firewall help** has a Copy button; the release build's smoke test now runs the silent check and fails if the bundle is missing the
  miniDSP tool or the audio library.

## Nov 16, 2026 (night) - a beginner view, one results screen, readiness

Built and tested offline and in a browser against copies of real results; the real-hardware protocol is in `docs/dev/HARDWARE_VALIDATION.md`.

- **Basic / Advanced**: Basic shows Home, Setup, Calibrate, Results and Compare; everything else is behind "Show all pages". New
  systems start in Basic, calibrated ones keep Advanced.
- **Results** (Verify): the response before and after, seat consistency, crossover integration and the listening comparison on one page,
  with what improved, what did not and what is not measured. Expected numbers are labelled as expected until a verify measures them.
- **Is it ready?** (Home): connected, set up, verified (with when) and never tested, and a ready / caution / blocked verdict; a hardware
  check that is old is shown as unknown.
- **Your first calibration**: one button, one mic spot, no room, speaker or furniture details needed first.
- `scripts/validation_snapshot.py` snapshots and compares repeated hardware runs against limits.

## Nov 16, 2026 - room details, backups, receiver setup sheet

Built and tested offline (the offline tests and a headless browser); the receiver setup sheet, a real backup restore and the
new room details are still to be tried on the real system.

- **Room page**: a **Screen** section (TV or projector screen, size and shape, acoustically transparent or not, front speakers
  behind it), **Furniture** (couches with fabric and size, risers), **Soffits** along walls (trimmed to their wall and blended
  into angled walls), a jump bar, and "Pick screen wall". Plan and 3D draw everything; pointing at a soffit, opening or corner
  row lights it up on the plan and in 3D. Room and Subs are now two pages.
- **Treatment and layout**: couches, risers, soffits and the screen add notes (ring-time estimate, couch back at the ears, a
  front-wall soffit, viewing angle, what an AT screen does); front speakers sit close behind an AT screen.
- **Backups** (Tools, Beta): weekly, before an update and on demand; the newest five are kept; restore with a safety copy first;
  never holds keys, PIN or tokens; optional second copy to a USB stick or share.
- **Receiver setup sheet** (after the all-speakers check): level and distance changes per channel in the receiver's words,
  final numbers from the values recorded at measurement time, tonal match and bass extension per channel; printable at `/channels`.
- **Assistant and MCP**: update_room records the screen, furniture and soffits; list_backups, make_backup and restore_backup
  (the last needs your approval). The phone room builder can also propose the screen, couches, risers and soffits.
- **Layout**: pages scale to wide screens; Speaker placement and Room treatment use a plan-and-table layout.

## Nov 14, 2026 (overnight) - pro views, placement, headroom, all speakers, offline helper

Built and tested offline (simulations and the browser); nothing played on the real system.

- **Offline helper**: with no AI provider, the chat answers from htTamer's own data (next steps,
  latest report, sub settings with warnings, receiver processing, playing tune) and a glossary.
- **Settings files** carry system reports, report history, the last fixes and the tuning journal.
- **System report pro views**: phase, group delay, impulse and step response, bass waterfall
  (0-300 ms), and REW export (frequency, SPL, phase per channel).
- **Multi-spot average**: with reports at 2+ spots, an "All spots (average)" view shows the
  response over the listening area, spot-to-spot spread, and marks treble findings seen at one
  spot only as mic-position effects.
- **Speaker placement** (Setup): Dolby-guideline positions for the layout from the room and main
  seat, each within its allowed angle on its own wall, with notes (e.g. your MLP sits near the
  room's first bass null, and front speakers fit at 23-25 degrees rather than 30).
- **Sub headroom** (Measure, not yet run): rising tone bursts at 25/40/63 Hz per sub with automatic
  stops (5-10% distortion, 3 dB compression, mic overload, 105 dB, -12 dBFS).
- **All speakers** (Measure, experimental, not yet run): the receiver's network player is
  stereo-only (it lists 1-2 channel PCM), so a 7.1 WAV is played by the owner from an HDMI source
  or USB stick; every bed speaker and the LFE are checked against the front left for level,
  arrival, polarity and whether it played. Heights need Atmos content and aren't covered.
- **Sub catalog**: SVS PB-2000 Pro (port plugs vs the app's Standard/Sealed mode) and Rythmik F12
  (extension, damping, rumble, low-pass mode), from the makers' pages and guides.
- Tests: `test_helper.py`, `test_layout.py`, `test_headroom.py`, `test_allspk.py`, additions to
  `test_deepcheck.py`, `test_bundle.py` and `test_vendors.py`.

## Nov 14, 2026 - tuning coach, journal and a holistic assistant

- **Tuning coach** (`subtune/coach.py`): ranked next steps from all the data, in the order the
  chain depends on (safety and wiring, sub hardware, sub tune, blend, receiver, Dirac, verify and
  listen); each says why, who does it, whether it plays sound and the tool to use. Shown as a
  "Next steps" card on the main page (no AI needed) and given to the assistant. Never offers a
  blend fix the playing tune already contains; asks for a fresh report when the last one predates
  the current htTamer.
- **Tuning journal** (`subtune/journal.py`): knob changes, tunes applied, receiver level and
  processing changes, Dirac runs, target changes, verifications, reports and fixes with their key
  numbers; on the main page and in the assistant's overview.
- **Assistant rewritten** as a tuning engineer: live system facts instead of a hard-coded
  description, an explicit loop (assess, propose one step, act, measure, compare, keep or undo),
  work ordered across the chain, a concrete next suggestion in every reply, a quiet mode for "no
  sound now", and new tools `get_tuning_plan` and `get_journal`.
- Tests: `test_coach.py` (12).

## Nov 13, 2026 (evening) - vendor-aware subs, AI providers, receiver control and fixes

- **Vendor-aware subs**: Room & subs shows each catalog model's own controls. Hsu VTF-3 MK5 HP
  (from Hsu's manual): ports, EQ1/EQ2, Q 0.3-0.7, crossover In/Out and frequency, phase 0/180,
  volume, power; the five operating modes; a danger warning for both ports open with EQ1. SVS
  SB-1000: volume, low-pass/LFE, phase. Stacked-crossover warnings. Ported modes get no EQ boost
  below a conservative limit. The assistant sees settings, modes and the maker's guidance.
- **AI providers**: Anthropic (default), OpenAI, Google Gemini or a local OpenAI-compatible
  server (Ollama, LM Studio). Key per provider, models from the provider's live list (a sensible
  one is picked automatically), Test button; assistant tools and analysis work with all of them.
  Provider choice and (optionally) keys travel in the settings file.
- **Receiver control**: centre level; sound processing (bass/treble, Late Night, Cinema Filter,
  Music Optimizer, dialogue enhance, dimmer) plus temperature and input signal, all confirmed
  supported by the TX-RZ50's own capability list. Tests switch the colouring processing off and
  restore it afterwards.
- **Fix what htTamer can** (System report): receiver sub level to the target (max +3 dB up),
  left+right blend test with the blend fix applied when it helps (never slot 1), then a new report
  with before/after. Receiver advice with exact menu numbers (distance, level) and Dirac notes.
- **Report history** with a before/after overlay; Dirac target "Matched to your speakers" (the
  measured in-room treble slope), recommended Dirac settings, Hsu auto-EQ reminder.
- **8 s lead-in** on the test files (the receiver skipped the start of network playback, losing
  the left sweep's deepest bass); the report flags a clipped start.
- Tests: `test_vendors.py`, `test_ai.py` (fake provider server, full tool loop), `test_fixup.py`,
  receiver processing in `test_deepcheck.py`.

## Nov 13, 2026 — system report, automatic receiver volume, header SPL meter, target slot

- **System report** (menu → Measure): a 20 Hz-20 kHz sweep on the left speaker, the right, then
  both, through the receiver in Stereo with the subs on. Plain-language findings with why they
  matter and what to do: tone per range vs the target, peaks and dips classified (room
  resonance, wall cancellation with distance, reflection ripple), left/right level, timing (seat
  centring) and polarity (a speaker wired backwards), RT60 per octave, early reflections,
  distortion, noise and hum, measurement reliability, bass extension. Chart, detail tables,
  glossary, **Print / Save as PDF**. The assistant can read and run it. Front L/R and subs only.
- **Automatic receiver volume** for the system report and the blend test: pink noise, then the
  volume steps (at most 3 at a time) to the test level at the mic (75 dB C default), never above
  the max you set (default: your volume + 12, never above 70), turning down and stopping if the
  mic overloads; your volume, input and mode are put back afterwards.
- **Receiver restore fix**: the before-test snapshot now retries and refuses to start a test
  without knowing the volume and input (a slow reply had left the receiver at the test volume);
  a receiver that was in standby gets its volume back before going back to standby.
- **SPL meter in the header**: always on while the dashboard is open, fed by the test itself
  while sweeps or tones play ("TEST"); the mic is reserved for the whole job, and measurements
  wait up to 5 s for it (on the Pi only one program can hold the mic).
- **Tune into slot 2, 3 or 4**: auto-tune's whole run (reset, sweeps, apply, verify) uses the
  chosen slot; slot 1 can't be picked.
- Tests: `test_deepcheck.py` (12, synthetic room with planted problems), `test_slot.py`,
  `test_spl_tap.py`.

## Nov 13, 2026 — settings file and over-the-air updates

- **Settings file**: menu → Settings file saves room, speaker layout, subs, receiver, mic
  calibration and (by default) tunes, slot contents, the current result and measurements to one
  `.json`. PIN (as its hash) and API key only when ticked. Import it from the same page, the
  first-boot setup page, or `subtune import-config`. Machine-specific settings (USB path, audio
  device names) are never carried, so a Windows file works on the Pi. A file can't give htTamer
  slot 1, and only known data files are written.
- **First boot**: `httamer-config.json` on a fresh card's boot drive is imported automatically
  and removed from the boot drive. `HTTAMER_SETTINGS=` bakes one into an image build.
- **Over-the-air updates**: `deploy/push-update.sh [--watch]` sends the code over SSH;
  `httamer-update` on the Pi checks it compiles, installs, restarts only for Python changes and
  rolls back if the new version doesn't start.
- The version shows in the dashboard; image builds write it to `HTTAMER.txt` (was "dev").
- The saved API key file is owner-only on Linux. 6 checks in `tests/test_bundle.py`.
- **Pi fix: miniDSP "not detected"**. Without a cached address, minidsp-rs also searched the
  network for ~10 s on every call, so the dashboard's status check kept the USB device busy and
  other commands (slot switches) failed with "No devices found". Calls now look only over USB
  (`--usb 2752:0011`, ~0.1 s), take turns (thread + file lock shared with job subprocesses), and
  retry briefly when the device is busy.

## Nov 13, 2026 — first-boot setup in the browser (for a ready-made SD card)

- A fresh htTamer in network mode (no PIN yet) shows a **setup guide** instead of the dashboard:
  1. choose a PIN, 2. add the mic calibration file, 3. find the receiver (automatic search, or by
  hand), 4. add the AI key (optional). Steps can be skipped or changed later; "Finish later and
  open htTamer" lands on the Setup checklist.
- The first PIN can only be chosen once; after that the page needs signing in, and someone else
  on the network can't replace it. Until setup is finished, signed-in visits to the dashboard
  come back to the guide once.
- The Linux setup script no longer asks for a PIN in the terminal (`--pin` still does). This is
  what lets an SD card image need no terminal at all.
- Tested end to end on an isolated "fresh card" copy, with phone and dark layouts checked.
  12 checks in `tests/test_portable.py`.

## Nov 13, 2026 — ready for Linux / Raspberry Pi (silent)

- **git**: the project is now a git repository (nothing committed yet). Your `data/` folder and the
  downloaded `tools/` are excluded; shell scripts keep Unix line endings.
- **Runs on Windows or Linux** without changing settings:
  - audio devices are found by name on either system ("auto" audio system; old Windows settings still work on Linux);
  - the right minidsp-rs build is picked per system, and a USB address saved on Windows is ignored on Linux;
  - `HTTAMER_DATA` and `HTTAMER_CONFIG` move the data and the API key/PIN folder (used on the Pi);
  - a missing mic calibration file now shows in the Setup checklist and gives a clear message.
- **Network mode with a PIN**: `python -m subtune set-pin`, then `serve --lan`. Sign-in page, 30-day
  sessions, wrong-PIN lockout, HttpOnly SameSite cookies, a same-site check on every action, and
  "Sign out" in the menu. This PC's normal mode is unchanged (local only, no sign-in).
- **Linux setup script** `deploy/linux/install.sh` (normal and `--dev`), with a service, a USB
  permission rule and the minidsp-rs download. Guide: `docs/RASPBERRY_PI.md`.
- New offline tests: `tests/test_portable.py` (11 checks). Sign-in tested end to end on an isolated
  copy. Not yet run on a real Pi.

## Nov 13, 2026 — speaker layout and working alongside Dirac Live (silent)

- **Your speakers** (Receiver screen): choose the layout (set to 7.3.4), crossover, and whether you
  use Dirac Live and its Bass Control. htTamer only uses this to guide you; it changes nothing in
  the receiver. Includes a "Receiver settings to check once" list built from the layout.
- **Dirac Live step in the wizard** (shown when you use Dirac): what to check first, a download of
  htTamer's target as a Dirac target-curve file (Flat / Gentle / Warm treble, with a small graph),
  seven plain steps for running Dirac, and an "I've run Dirac Live" button.
- htTamer remembers which sub tune Dirac was run with. A blend fix keeps it valid (it only shifts
  timing); a new sub tune asks you to run Dirac again. Marking Dirac as run clears older blend
  measurements, since the speakers then sound different.
- Setup checklist has a "Speakers and Dirac Live" line; the system map shows the layout and Dirac state.
- The assistant knows the layout, the Dirac order of steps, and that it can't operate Dirac itself.
- Fixes: the system map could show "Not set by htTamer" until the slot names loaded.
- New offline tests: `tests/test_dirac.py` (6 checks: file layout, curve shape, layout names, when
  Dirac needs re-running). All 23 offline checks pass.
- Not verified: Dirac Live actually importing the file. Dirac publishes no format spec; the file
  follows the layout Dirac Live 2/3 files use.

## Nov 13, 2026 — left + right blend, interface polish (silent)

**Project moved** to `C:\Users\<you>\repo\httamer`. Start the dashboard from that folder
(`subtune.cmd serve`); the app's preview launcher was still pointing at the old session folder.

**New: blend with both front speakers**
- The blend test can now play the left speaker, then the right, then left again with the subs
  (about 40 s; "Left + right" is the default, "Left only" is still there). The subs get the same
  bass whichever speaker plays, so one "with subs" pass covers both.
- Single-seat and all-seats answers average over both speakers, so the fix doesn't favour one side.
- The graphs show the right speaker too; the all-seats graph has a Left / Right switch.
- A second test file (`httamer_blend_test_left_right.wav`) for the USB-stick option, made on demand.
- The assistant can choose left or both, and is told to prefer both.
- New offline tests: `tests/test_blend_measure.py` simulates a full mic recording (separate filter,
  delay and level for left, right and subs, plus noise) and checks the analysis recovers all three,
  including their relative timing, and that the subs are unmuted inside the gap. 6 checks, all pass.

**Fixes**
- The "What the tune did" colour key had collapsed into a narrow column (a style-name clash with
  the new seat bars).
- Room-mode labels on graphs no longer print on top of each other.
- Activity log: times ran into the labels; labels are now plain words (miniDSP, measured, setting).
- AI analysis: `*italic*` text now renders instead of showing asterisks.

**Polish**
- The Ask htTamer button shrinks to an icon on narrower windows so it doesn't cover the page.
- Plain names on the result tiles: Average unevenness, Difference between seats, Biggest swing,
  Turned down for EQ (same names in the tunes comparison).
- "Slot" everywhere instead of a mix of "preset" and "slot"; the tune step names the real slot.
- Receiver screen explains itself when the receiver is in standby.

## Nov 13, 2026 — overnight polish (silent: code, UI and offline tests only)

**Fixes**
- The single-seat blend fix could be applied twice, stacking the delay. It is now tied to the tune
  it was measured with, and marked "Applied" once used.
- Blend fixes now save as a clean new tune (the old tune's slot/time/id are no longer copied in).

**Multi-seat blend**
- Tune building moved into `blend_tune()` (cli.py), so it can be tested without hardware.
- New offline tests: `tests/test_blendmulti.py`, 11 checks using simulated seats (all-pass filter
  maths, the miniDSP coefficient format, optimiser behaviour, MLP weighting, seat storage, tune
  building and refusals). All pass.
- The AI assistant now knows about seats: how to measure them, what "miniDSP fix" vs "receiver
  change" means, and that applying uses the all-seats answer. The overview it reads includes the
  all-seats result.
- Wizard step 3 shows "N of 3 seats measured" and counts as done once seats are measured with the
  playing tune.

**Polish**
- Filters view shows blend all-pass filters ("phase only", with a short explanation) and the slot
  that's actually playing instead of a fixed "preset 4". Numbers no longer wrap mid-value.
- The blend card's network note is calmer now that the firewall is sorted.
- With no seats measured, the stray "Mic at MLP next" button is gone (Run blend test already starts there).

Checked in light, dark and phone layouts with no console errors. Nothing played, nothing was written
to the miniDSP, and the receiver wasn't changed.

## Nov 12, 2026
- Multi-seat blend: each blend test is saved as a seat; one setting (delay, polarity, optional
  all-pass) is chosen for all seats, MLP weighted most. "All seats" view in the blend card.
- Mic calibration upload in the Setup checklist (validated before use).
- Home redesign: system map, health score, 4-step "Tune my system" wizard, Setup checklist,
  "Ask about this" buttons, assistant docks beside the page on wide screens.
