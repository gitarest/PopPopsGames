---
description: Back up scores.json and events.log from the live server
---

Back up runtime data files from mccontek.com to the local project folder.

## Steps

1. **Read server config** — open `.claude/skills/deploy/server.env` and parse `DEPLOY_HOST` and `DEPLOY_USER`.

2. **Back up game.db** — run:
   ```
   scp DEPLOY_USER@DEPLOY_HOST:/home/poppop/PopPopsGames/game.db ./game_backup.db
   ```
   Report success or failure. If it fails because the file doesn't exist, note that (not an error — may not exist yet if server hasn't been restarted after the SQLite migration deploy).

3. **Back up scores.json** — run:
   ```
   scp DEPLOY_USER@DEPLOY_HOST:/home/poppop/PopPopsGames/scores.json ./scores_backup.json
   ```
   Report success or failure. If it fails because the file doesn't exist, note that (not an error — expected once migrated to SQLite).

4. **Back up events.log** — run:
   ```
   scp DEPLOY_USER@DEPLOY_HOST:/home/poppop/PopPopsGames/events.log ./events_backup.log
   ```
   Report success or failure. If it fails because the file doesn't exist, note that (not an error).

5. **Report result** — show the file sizes of all local backups (if they exist) and the timestamp of when the backup was taken.

## Notes
- All files are gitignored — the local backups will never be committed
- Safe to run at any time; it only reads from the server, never writes
- Run before making any manual edits to scores or clearing old logs
- `game.db` contains all player scores (authoritative after migration); `scores.json` is kept for legacy/recovery
