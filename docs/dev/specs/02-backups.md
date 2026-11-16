# Spec 02: automatic backups and one-click restore

**Goal:** the owner's tunes, measurements, room, equipment and settings are backed up automatically, and any backup can be restored from the page. A bad SD card or update must never cost them their work.

**Why:** there's no backup today. Earlier a display bug made the owner think their data was wiped. See `docs/dev/ROADMAP.md`, item 4.

## Behavior

- **What's in a backup:** the data folder's state (measurements, results, saved tunes and slots, room, equipment, reports, the fix log, journal, hardware database, chat history) and the settings file. **Never** in a backup: API keys, the GitHub, MCP or Home Assistant tokens or their hashes, the sign-in PIN or its hash, the local MCP key. A backup file must be safe to copy anywhere.
- **When:** automatically once a week; before every in-app update installs (`subtune/update.py`, just before the download is handed over); and on demand from the page.
- **Where:** `DATA/backups/` as `htTamer-backup-<version>-<YYYYMMDD-HHMM>.zip`. Keep the newest 5 automatic ones (on-demand and pre-update backups count too; never delete the most recent pre-update one).
- **A copy off the device:** optional setting `backup_copy_dir` (a folder path: a USB stick the Pi has mounted, or a network share). When set, every new backup is also copied there (and the same rotation applies). A copy failure is logged and shown, never fatal.
- **Restore:** the page lists backups (date, size, version, what's in it). Choosing one shows a summary, asks for confirmation, makes a fresh safety backup of the current state first, restores, and tells the owner htTamer restarted its page. Restoring never touches keys, tokens or the PIN. Refuse a file that isn't a valid htTamer backup or comes from a newer version than the running one.
- **Download / upload:** a button to download a backup, and one to restore from an uploaded file (limit 50 MB).

## Build on what exists

`subtune/bundle.py` already exports and imports the settings file (`STATE_KEYS`, export/import, `/api/config/export` and `/api/config/import`). Read it first; reuse its rules for what is included rather than writing a second exporter. Check how it treats keys and make sure a backup excludes them.

## Files

- New `subtune/backup.py` (under 400 lines): `make(reason) -> path`, `list_backups()`, `restore(name_or_path)`, `rotate()`, `copy_off_device(path)`, `secrets_check(zip)`.
- A background weekly check: add to the existing automation loop (`subtune/automation.py`, `tick`) or a small thread started in `server.serve`, using state key `last_backup`.
- Endpoints: `GET /api/backups`, `POST /api/backups` (actions: `make`, `restore`, `delete`), download as `GET /api/backups/download?name=...`. These need the sign-in and the terms gate like every action. Validate `name` against the list: never build a path from user input.
- Page: a card **Tools → Backups** (`index.html`, `MENU` in `js/nav.js`, render code in the right `js/` part), with a Beta label.
- `subtune/web/manual.html`: a "Backups" section.
- Settings: `backup_copy_dir` (validated: an existing folder), `backup_weekly` (default on).

## Tests (`tests/test_backup.py`, offline, temp data folders)

- Round trip: make a backup, change the data, restore, the data matches the original.
- A backup contains no secret: write fake keys/tokens/PIN files into the temp config folder, make a backup, scan every file in the zip for them.
- Rotation keeps 5; the latest pre-update backup survives.
- Restore refuses: a non-htTamer zip, a path-traversal entry (`../x`), a zip from a newer version.
- Copy to `backup_copy_dir` works; a missing folder is reported, not fatal.
- An update calls `backup.make("before update")` (fake the download).

## Out of scope

Cloud accounts (Google Drive, Dropbox), encryption, scheduling options beyond weekly.
