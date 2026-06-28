---
description: Back up scores.json and events.log from the live server
---

Back up runtime data files from mccontek.com to the local project folder.

## Steps

1. **Read server config** — open `.claude/skills/deploy/server.env` and parse `DEPLOY_HOST` and `DEPLOY_USER`.

2. **Back up scores.json** — run:
   ```
   scp DEPLOY_USER@DEPLOY_HOST:/home/poppop/PopPopsGames/scores.json ./scores_backup.json
   ```
   Report success or failure. If it fails because the file doesn't exist, note that (not an error).

3. **Back up events.log** — run:
   ```
   scp DEPLOY_USER@DEPLOY_HOST:/home/poppop/PopPopsGames/events.log ./events_backup.log
   ```
   Report success or failure. If it fails because the file doesn't exist, note that (not an error).

4. **Report result** — show the file sizes of both local backups (if they exist) and the timestamp of when the backup was taken.

## Notes
- Both files are gitignored — the local backups will never be committed
- Safe to run at any time; it only reads from the server, never writes
- Run before making any manual edits to scores or clearing old logs
