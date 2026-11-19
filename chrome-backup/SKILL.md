---
name: chrome-backup
description: Back up Chrome bookmarks and reading list (and optionally a passphrase-encrypted copy of exported passwords) to Google Drive by default, or to a local folder. Use whenever the user wants to back up, export, archive, snapshot, protect or migrate Chrome bookmarks, the Chrome reading list, saved passwords, or a Chrome profile's browsing data, is changing machine/account/browser, or worries about losing Chrome data — even if they don't say "skill", "zip" or "Drive".
---

# Chrome backup

Backs up bookmarks and the reading list for every Chrome profile into one timestamped zip, then puts it on Google Drive (default) or a local folder. Passwords are a separate, opt-in, guided flow (see below).

Script: `scripts/chrome_backup.py` (Python 3, standard library only). Run it with `python -I`.
Settings: `config.json` next to this file. If missing, use the defaults shown there.

## What the zip contains, per profile
- `Bookmarks.json` and `AccountBookmarks.json`: raw copies. Signed-in profiles keep synced bookmarks in `AccountBookmarks`, local-only ones in `Bookmarks`; either can be the one with the data, so both are taken. This is the faithful backup.
- `bookmarks-import.html`: Netscape-format export that Chrome, Edge, Firefox etc. can import. The reading list is included as a "Reading List" folder.
- `reading-list.json` / `reading-list.csv`: title, URL, date added, read state.
- `manifest.json`: profiles, account, counts per source, Chrome version, notes.

**Reading list caveat:** Chrome has no export for it and it isn't in the Bookmarks file. The script reads it from Chrome's local sync cache (`Sync Data/LevelDB`) with its own minimal reader, so it reflects what Chrome last synced. After a backup, tell the user the count and suggest comparing it with the number in Chrome's reading list; flag any mismatch rather than assuming it is complete. Profiles without sync have no reading list to read.

**Sensitive content:** bookmark and reading-list URLs can contain tokens (for example `access_token=` in a shared link). Treat the zip as private: keep the Drive folder unshared, never put it in a public or team-shared folder.

## Backup
1. Read `config.json`. Say in one line where the backup will go (default: Drive folder `Chrome Backups`) and let the user change it for this run ("local instead", another folder). Changing it for one run changes nothing on disk; "always use local" or "change the folder" updates `config.json`.
2. Run `python -I scripts/chrome_backup.py profiles` if the user hasn't said which profiles; the default is all. Backup works while Chrome is open, because Chrome keeps these files readable, but recent changes may still be in memory, so suggest closing Chrome first for a guaranteed-current copy.
3. **Local destination:**
   ```powershell
   python -I "<skill-dir>\scripts\chrome_backup.py" backup --out "<local.path expanded>" --keep <local.keep>
   ```
   Report the archive path and size.
4. **Drive destination:** stage the zip in the scratchpad (or a temp folder), then upload it:
   ```powershell
   python -I "<skill-dir>\scripts\chrome_backup.py" backup --out "<scratchpad>\chrome-backup-staging"
   ```
   The script prints `ARCHIVE=`, `SIZE=` and `SHA256=`. Then, with the Google Drive connector (load deferred tools with ToolSearch if needed):
   - `search_files` for the folder (`title = '<drive.folderName>' and mimeType = 'application/vnd.google-apps.folder' and parentId = '<drive.parentFolderId>'`); create it with `create_file` (`mimeType` folder) if absent. If Drive reports the folder is shared with others, tell the user and ask before uploading.
   - `create_file` with `title` = the zip's file name, `parentId` = the folder id, `contentMimeType: application/zip`, `disableConversionToGoogleType: true`, and `base64Content` set to the file reference `sha256:<SHA256>:<ARCHIVE path with / separators>` (the app fills in the bytes, so don't base64 it yourself).
   - Confirm by `search_files` on the new file and compare size to `SIZE=`.
   - If `drive.keepLocalCopy` is false, delete the staged zip afterwards. Keep it if the upload failed, and say so.
   If the Drive connector is missing or failing, stop and say which; offer the local destination instead rather than silently switching.
5. Report: profiles with bookmark counts and reading-list count, destination (Drive link or path), size, and any notes from the script.

## Restore
Restoring is manual by design, because writing into a live Chrome profile can corrupt it. Offer the least risky route: open `bookmarks-import.html` in Chrome via Bookmarks → Import bookmarks and settings (the reading list lands as a bookmarks folder). Use `python -I scripts/chrome_backup.py list --archive <zip>` to preview contents. Only copy a raw `Bookmarks.json` over a profile's `Bookmarks` file if the user explicitly asks, with Chrome fully closed and the existing file kept as `Bookmarks.old`.

## Passwords (opt-in, guided, never plaintext in Drive)
Do not read or decrypt Chrome's `Login Data` file, and do not look for ways around Chrome's app-bound encryption: the file is tied to the Windows account and is useless as a backup on another machine anyway. Two safe routes:
1. **Primary copy:** if the profile is signed in with sync on (check `profiles` output for an account), passwords already live in the user's Google Password Manager. Say so.
2. **Offline copy via Chrome's own export:**
   - The user opens `chrome://password-manager/settings` → Export passwords, authenticates, and saves the CSV (usually to Downloads). You can't and shouldn't do this step.
   - Encrypt it with `scripts/Protect-File.ps1`. It prompts for a passphrase, so it must run in a terminal the user can type into: use the app's Terminal panel (`mcp__terminal__run_in_terminal`) or hand the user the command. Never ask for the passphrase in chat and never pass it as an argument.
     ```powershell
     pwsh -File "<skill-dir>\scripts\Protect-File.ps1" -Action encrypt -Path "<csv path>" -OutDir "<passwords.path expanded>"
     ```
     It verifies the encrypted file decrypts before it overwrites and deletes the plaintext CSV.
   - Default destination for the `.enc` file is local (`passwords.path`). Uploading it to Drive is allowed only if the user asks and only the `.enc` file, never the CSV; tell them it is only as safe as the passphrase, and that losing the passphrase means losing the file.
   - After the run, check the CSV is gone from Downloads and the Recycle Bin is not holding it.
   - Decrypt later with `-Action decrypt`; the plaintext it produces must be deleted after use.
   Suggest a dedicated password manager (Bitwarden, 1Password) as the long-term answer; it has its own encrypted export and backup.

## Options and notes
- `--profiles "Default,Tempcover"` takes profile folder names or display names. `--no-reading-list` skips the sync-cache read. `--chrome-dir` points at a different `User Data` folder (for example Edge or Chromium; reading list layout may differ).
- Non-Windows paths aren't built in; pass `--chrome-dir` explicitly on other platforms.
