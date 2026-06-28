---
description: Deploy Pop Pop's Games to mccontek.com
---

Deploy the current codebase to the live server at mccontek.com.

## Steps

1. **Read server config** — open `.claude/skills/deploy/server.env` and parse `DEPLOY_HOST` and `DEPLOY_USER`. If either is still set to a placeholder value (contains `YOUR_` or is empty), stop and tell the user to fill in the real server IP and username.

2. **Check for uncommitted changes** — run `git status --short`. If there are any changes:
   - Ask the user: "What should the commit message be?"
   - Run: `git add -A` then `git commit -m "<their message>"`

3. **Push to GitHub** — run `git push origin main`. If it fails because no remote is configured, tell the user they need to complete Phase 1 of the deployment plan (create a GitHub repo and add it as the remote).

4. **Deploy to server** — run:
   ```
   ssh DEPLOY_USER@DEPLOY_HOST "cd ~/PopPopsGames && git pull && sudo systemctl restart poppopsgames"
   ```
   Replace `DEPLOY_USER` and `DEPLOY_HOST` with the values from `server.env`.

5. **Report result** — show whether each step succeeded. If SSH fails with "connection refused" or "no route to host", tell the user the server may be down or the SSH key may not be set up yet.

## Notes
- `scores.json` is gitignored and is never touched — grandkids' scores are always safe
- The deploy SSH session runs as root (set in `server.env`)
- Static file changes are live immediately after restart; players just need a hard-refresh (Ctrl+F5)
