---
name: claude-history-backup
description: Back up and restore Claude Code conversation history (session transcripts, prompt history, file-history, plans) from ~/.claude to a zip archive. Use whenever the user wants to back up, export, archive, snapshot, migrate, or restore their Claude history/sessions/transcripts, is moving to a new machine or reinstalling, or worries about losing past Claude conversations — even if they don't say "skill" or "zip".
---

# Claude history backup & restore

History lives under `%USERPROFILE%\.claude`. This skill packages it into a single zip and can put it back. The bundled script does the work so behaviour is identical every time.

Script: `scripts/claude-history.ps1` (relative to this skill's folder). Run it with PowerShell.

## What is included (and why)
`projects/` (session transcripts), `history.jsonl` (prompt history), `file-history/`, `plans/`, `todos/`, `sessions/`, `stats-cache.json`.
Deliberately **excluded**: `.credentials.json`, settings, MCP config, plugins, caches. Backups often get copied to cloud drives or USB sticks, so secrets stay out; settings/plugins are reinstallable and aren't "history".

## Backup
1. Ask where to save it only if the user hasn't said; default is `%USERPROFILE%\claude-history-backups`. Suggest a location outside the profile (other drive/OneDrive) if the goal is protection from disk loss.
2. Run:
   ```powershell
   & "<skill-dir>\scripts\claude-history.ps1" -Action backup -Destination <folder>
   ```
3. Report the archive path, file count and size. Files locked by a live session are read with shared access; any skipped file is warned about — mention it. The current session's transcript may be mid-write, so tell the user a later backup will capture the rest.

## Restore
1. Preview first: `-Action list -Archive <zip>` shows files and size per top-level folder.
2. Confirm with the user before restoring, since it writes into `.claude`.
3. Run `-Action restore -Archive <zip>`. Default is non-destructive: it never deletes, and skips any file already present that is the same age or newer. Add `-Overwrite` only if the user explicitly wants the archive to win.
4. Tell the user to restart Claude Code / reopen the app so the sessions list reloads. Transcripts are keyed by project path, so on a new machine they only show for projects at the same path (e.g. `C:\dev\v4`).

## Options
`-ClaudeDir` overrides the source/target (useful for restoring into a different profile).
