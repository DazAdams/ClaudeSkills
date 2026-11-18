---
name: notion-drive-backup
description: Back up Notion pages and databases to Google Drive as Markdown files, and restore them from Drive back into Notion. Use whenever the user wants to back up, export, archive, protect, snapshot or migrate Notion content (their Private section, a page tree, a database), says they are changing their Notion login/account/workspace, or asks to restore, recover or re-import Notion pages from a Drive backup — even if they never say "skill", "Markdown" or "Drive folder".
---

# Notion ⇄ Google Drive backup and restore

Backs up Notion content into a dated Google Drive folder as one Markdown file per page, with a manifest that makes restoring possible later. Also restores from that folder.

Needs a connected Notion connector (`notion-fetch`, `notion-list-private-pages`, `notion-query-data-sources`; for restore also `notion-create-pages`, `notion-create-database`) and a Google Drive connector (`create_file`, `search_files`, `read_file_content` or `download_file_content`, `update_file`). Run the access check below first. If a deferred tool's schema isn't loaded, load it with ToolSearch first.

## Preflight: check access to Notion and Drive (backup and restore)
Run this before anything else, every time. A backup or restore that fails halfway through leaves a partial folder or a partial set of pages.
1. **Find the tools.** Look for a Notion connector (`notion-fetch`, `notion-search`, `notion-get-self`; for restore also `notion-create-pages`, `notion-create-database`, `notion-move-pages`) and a Google Drive connector (`search_files`, `read_file_content`, `download_file_content`; for backup also `create_file`, `update_file`). Schemas of deferred tools must be loaded with ToolSearch first. If two Notion servers are listed, use the one that is already connected.
2. **Prove they work, with one cheap call each.** Notion: `notion-get-self` (it also tells you which workspace you'd be writing to, so say it). Drive: `search_files` with a small `pageSize` (for example `title contains 'Notion Backup'` with `excludeContentSnippets: true`). A tool being listed is not proof it is connected: an expired or unauthorised connector fails on the first real call.
3. **If either is missing or failing, stop and tell the user which one.** Say what you saw (no tools found, or the exact error), and ask them to connect or re-authorise it (the app's connector settings), then tell you to retry. Do not try workarounds such as searching Drive through Notion's connector search, which can't read or write backup files. Don't continue with only one side working: backup needs both, and restore needs both.
4. **Retry when told.** Tools often appear only after the user connects the connector; call ToolSearch again, then repeat step 2.
5. **Restore only:** confirm the Notion workspace is the one the user wants to restore into. A backup taken from one workspace is often restored into another (for example after a login change), and the manifest names the source workspace.

## Run log (configurable, skippable)
Each backup or restore can write a log of what it did, kept private and apart from the backup folders themselves. The user chooses where it goes: **Drive**, **Notion**, or **both**.

**Settings** live in `config.json` next to this file: `log.enabled`, `log.destination` (`drive`, `notion` or `both`), `log.driveFolderName`, `log.driveParentFolderId`, `log.notionLogPageTitle`, `log.notionParentPageId` (null = a private page at workspace level), `log.fileNamePattern`, `log.includePageUrls`. Defaults: enabled, destination `drive`, folder `Notion Backup Logs` in My Drive (`root`), file name `{date}-{operation}-log.md`. If the file is missing, use those defaults.
- **At the start of a run (after the preflight), say in one line that a log will be written and where, and let the user skip or change it** ("skip the log", "Notion instead", "both", a different folder or page name, or turn it off permanently). A change for this run only changes nothing on disk; "turn it off", "always use Notion" or "change the folder" updates `config.json`. Don't ask more than that. Before the first run with no saved choice, offer Drive / Notion / Both as the one question.
- If logging is off or skipped, don't create the folder, page or file, and don't mention logging again in the final report except one line saying it was skipped.
- If the chosen destination can't be written (for example Notion is the choice but the Notion connector failed mid-run), write the other one if it is enabled, and tell the user which destination failed. Don't silently drop the log.

**Creating the log (Drive)**
1. Find the folder with `search_files` (`title = '<driveFolderName>' and mimeType = 'application/vnd.google-apps.folder'`, parent `driveParentFolderId`); create it with `create_file` if absent. Keep it private: do not share it, and don't put it inside a backup folder. If the folder turns out to be shared with anyone, tell the user rather than writing to it.
2. Drive's `update_file` can't change content, so write **one new file per run, at the end** (`create_file`, `contentMimeType: text/markdown`, `disableConversionToGoogleType: true`), not appended to earlier logs. If the run is interrupted, write what you have and mark it `status: incomplete`.

**Creating the log (Notion)**
1. Find a private page titled `notionLogPageTitle` (`notion-search`), or under `notionParentPageId` if set; create it with `notion-create-pages` in draft mode (`creation_mode: "draft"`) if absent, with a short line saying what it is. Never share it or change its permissions.
2. Add **one new sub-page per run**, titled `{date} {operation} log`, containing the same content as the Drive log in Notion markdown. Pass the log text as page content; links to pages created by the run can be written as normal Notion links or `<mention>` tags. If the run is interrupted, write what you have and mark it `status: incomplete`.
3. With **both**, write the Drive and Notion logs from the same content so they match, and report both links.
3. **Contents:** date and time; operation (backup or restore); for a restore, the diff-check result (counts of new, identical, differs and unclear) and what was skipped, copied or overwritten; Notion workspace and the account used; source and destination (backup folder name and ID, or Notion parent page); the scope chosen and groups left out; counts (pages, databases, rows) created, skipped and failed; each created page's title and URL if `includePageUrls` is true; redactions (which page, never the value); gaps and placeholders; pages moved or deleted afterwards at the user's request; verification status (what was compared and what wasn't); and any problems met, such as truncated reads or failed creates.
4. **Never put secrets or page body text in the log.** Titles, URLs, counts and file names only. The log must be safe to keep even if the backup is deleted.
5. Tell the user where the log is (a link for each destination) in the final report.

## Progress visual (backup and restore)
Show the user how far along a run is. Keep it light: update at stage and group boundaries, not after every page.
1. **Plan the stages up front** and show them once, with a count for each. Backup: access check, scope, create folder, read pages (by level), write files, redact, manifest, report. Restore: access check, scope, diff check, plan approved, create parent, restore groups (one row per group, with page count), move into place, verification, log. Also keep the app's task list (`update_plan`) in step when it is available.
2. **Render a progress visual.** If an inline visual tool is available (`mcp__visualize__show_widget`, after `read_me`), show a compact panel: an overall bar (done / total pages), one row per stage or group with a state (waiting, running, done, skipped, failed) and its count, and a line for anything needing attention (failures, skipped pages). Use the host's theme variables so it works in light and dark. Re-render at each stage or group boundary and once at the end; don't redraw on every call.
3. **Fallback: a text bar.** Without a visual tool, print the same thing as plain text, for example:
   `Restore  [██████████░░░░░░░░░░] 50%  32/64 pages`
   `  ✔ Go notes 11/11   ▶ Scratchpad 4/11   · HR & PIPs 0/20   · Mentoring 0/5`
4. **With parallel agents** (see "Large restores"), each group is a row; mark it running when you launch its agent and done when its report arrives. Only mark a group done from the agent's report, and show failures or skipped pages plainly. Never show 100% until the verification step has run; before that say "created, not yet verified".
5. **Counts must be real:** use numbers from tool results (pages created, files written), not estimates. If a count is unknown, say so instead of guessing.
6. The final report repeats the finished visual (or text bar) with the totals, skipped items and verification status.

## Backup

### 1. Confirm scope before reading anything
Default scope is the user's Private section plus everything nested under it. Say that, and note two things in one short message: sub-pages will be included, and anything sensitive (HR, performance, credentials) gets copied into Drive, so the Drive folder should stay private. Don't ask more than that unless the scope is genuinely unclear.

### 2. Create the destination folder
Create `Notion Backup YYYY-MM-DD` in My Drive with `create_file` (mimeType `application/vnd.google-apps.folder`). Keep the returned folder ID; every file goes in it via `parentId`.

### 3. Read the content
- List top-level items with `notion-list-private-pages` (or fetch the page/database the user named).
- Fetch each page with `notion-fetch` — independent fetches go in parallel in one turn.
- Pages link their children as `<page url=...>title</page>`. Treat every such link as a child to fetch next. Work level by level (top level → children → grandchildren…), because each level reveals the next.
- For a database: fetch it for the schema and views, then read rows with `notion-query-data-sources` in `rows` mode (`data_source_url` = the `collection://` URL). Row *properties* come from the query; each row's *body* is a page you fetch separately.
- Check `truncated` / `unknown_block_ids` in each result. Those blocks (buttons, Slack/Linear previews, external objects) can't be read — record them as gaps rather than ignoring them.

### 4. Write the files
Use `create_file` with `contentMimeType: text/markdown` and **`disableConversionToGoogleType: true`** (otherwise Drive turns the file into a Google Doc and the Markdown is mangled). Several `create_file` calls can go in one turn.

File name: `NN-<Parent>--<Title>.md`, with the number grouping by depth so the folder sorts sensibly (01–09 top level, 10–29 children, 30–49 grandchildren, 50+ database rows and deeper). Strip characters that are awkward in file names.

Every file starts with front matter so a restore knows where it belongs:

```
---
notion_title: "..."
notion_url: https://app.notion.com/p/...
notion_type: page | database | page (row of <Database>)
parent: Scratchpad / Learning notes
last_edited: 2026-07-06T16:00:19Z
backed_up: YYYY-MM-DD
note: <anything not captured: images, attachments, unreadable blocks>
---
```

Then the page body. Convert Notion's HTML-ish tags (`<b>`, `<code>`, `<p />`, `<callout>`) into plain Markdown, and keep the text otherwise unchanged — a backup that quietly rewrites content is worse than none. Where a block can't be captured (image, embed, attachment, external object), leave a visible placeholder such as `[image: not included in backup]` so nobody mistakes the gap for the original.

For a page whose children weren't fetched, write an index file that lists each child's title and URL, so nothing silently disappears from the record.

For a database, write one file with the schema (property names, types, select/status options), the views, and a table of the rows' properties, then each row's body as its own file.

### 5. Redact secrets
Scan what you've read for credentials: passwords, API keys, connection strings, tokens, access keys, private keys. Replace the secret value with `[REDACTED]`, keep the surrounding structure, say so in the file's `note:` and in the file name (`...-REDACTED.md`). Reason: copying live production credentials into a second location widens the blast radius, and the originals are still in Notion. Tell the user which page was redacted and offer to include the values verbatim if they want. Never print the secret values back in chat.

### 6. Write the manifest last
Drive's `update_file` only changes metadata, not content, so a manifest can't be edited in place. Write `00-MANIFEST-and-RESTORE.md` once, after everything else, listing: files by number range, redactions, what was NOT backed up (with URLs), and the restore instructions. If you must replace one, create the new file and rename the old one `ZZ-superseded-….md` with `update_file`.

### 7. Report honestly
Write the run log first if logging is on (see "Run log"). Say what's in the folder and link it, plus the log. State the gaps plainly: sub-levels not followed, images and attachments, comments, page history, sharing permissions, unreadable blocks. Say that a restore hasn't been tested unless you tested it. Remind the user to keep the folder private if it holds sensitive pages, and to move any redacted credentials into a password manager.

## Restore

1. Find the backup folder (`search_files` on the folder title) and read `00-MANIFEST-and-RESTORE.md`. If there are several backups, ask which date. **Read backup files with `download_file_content`, not `read_file_content`.** `read_file_content` silently truncates long files (it can stop mid-row or mid-sentence), and restoring from a truncated read loses content without any error. `download_file_content` saves the full file to disk and returns the path; open that with Read. If a file read ends mid-sentence, treat it as truncated and re-read it via download. To list the folder, use `search_files` with `parentId = '<folderId>'` and `excludeContentSnippets: true`; if the result is too large it is saved to a file, so parse it with PowerShell/Python rather than reading it raw.
2. **Present a restore scope and let the user choose.** Don't offer "everything or nothing". Group the manifest's files by what they are (for example top-level pages, Scratchpad pages, learning notes, a database such as the Go catalog, sensitive material like HR/PIPs/mentoring, pages that came from outside the Private section) and ask which groups to restore, with multi-select. For each group give the file range, the page count, and any flag: contains `[REDACTED]` values, is sensitive, or probably already exists in the target workspace (check with a title search, see below). Recommend a default, but leave sensitive groups unselected unless the user picks them. Say what will not be restored (the unchosen groups and the manifest's "NOT backed up" list). After the restore, offer the groups that were left out again. Then settle where the pages go (see "Parent placement" below) and whether the original pages still exist.

### Parent placement
- **Default: restore under a new private parent page** in the destination workspace (for example "Notion pages (restored from Notion Backup YYYY-MM-DD)"), created with `creation_mode: "draft"` so it is private. Never restore straight into an existing page or into Private/workspace root unless the user names that place. Keep the original hierarchy inside the new parent, following each file's `parent:` header; if a named parent page has no backup file, create a plain container page with that title.
- **Why:** a new parent can't clash with existing pages, makes the whole restore easy to find, review and (if needed) trash in one go, and nothing existing is changed.
- **Afterwards, offer to move pages into place.** When the restore is done, say where each group landed and ask whether to move any of it (for example "Scratchpad pages into your current Scratchpad", "Go notes under Learning notes") with `notion-move-pages`. Check the target first: moving pages gives them the access of their new parent, so say so if the target is shared. Move the top page of a group; its children follow.
- **After moving**, the temporary parent (and any holder pages you made as parents) is usually empty. Fetch it to confirm it has no sub-pages, then offer to move it to Trash; only trash it when the user says yes. If it still has pages, say so and offer to move them first.
- Record the final locations, moves and trashed holder pages in the run log. Restoring creates new pages with new IDs and URLs; it can't revive deleted ones. Before creating anything, run the diff check below so the user isn't left with duplicates, and let them choose what happens to pages that already exist.

### Diff check before restoring (quick, then ask)
Run this on the files in the chosen scope, after the scope is agreed and before the first create. It is on by default; if `restore.diffCheck` is `false` in `config.json`, or the user says to skip it, run only a title search and tell the user duplicates are possible.
1. **Find existing counterparts.** For each page or database to restore, search the destination workspace with `notion-search` (title query, small `page_size` of about 5) and run all the searches in parallel first; only fetch pages that have a candidate.
   - **Match on exact title** (case-insensitive, trimmed) taken from the result list. Do not rely on `filters.title_only`: it can be ignored on some plans and returns loose relevance hits (for example "Email Sender Service" for "Insure Service Support Q&As"), so discard non-exact hits yourself.
   - **Use the page path to choose between same-title hits** (for example `Scratchpad / Learning notes` against an unrelated page in another section), and prefer the hit whose path matches the file's `parent:` header. Several exact hits with no clear path match = **unclear**. Empty starter pages with the same title (an empty "Scratchpad" or "1:1 notes") are a match on title only; check their content before calling them counterparts.
   - **The ID in the file's `notion_url` only works if that page still exists in the same workspace.** After a restore, or when restoring into a different workspace, restored pages get new IDs, so fetching the old ID returns a 404 (`object_not_found`). A 404 here is expected and means "no ID match", not an error; fall back to title plus path.
   - Ignore trashed pages. If the user says earlier restore pages are the target, treat those as the counterparts.
2. **Classify each item** as: **new** (no match), **identical** (match, same text and same headings), **structure differs** (same text, different layout), **differs** (match, content changed), or **unclear** (several matches, or the match can't be read). Compare cheaply: `notion-fetch` the match, normalise both sides, and compare plain text and headings. Fetch each page once; fetch only pages with a candidate; stop at the first clear difference.
   - **Normalise before comparing:** strip the front matter and Notion tags; unescape `\[ \]` and `\<`; treat `<br />` as a newline and `<code>` as backticks; collapse whitespace.
   - **Expected differences, not changes** (list them, don't count them as "differs"): `[image: not included in backup]`, `[button: ...]`, `[embed: ...]` and `[REDACTED]` placeholders; Notion's auto-appended child-page list on parent pages; links rewritten (`notion.so` to `app.notion.com`, relative to absolute, or replaced by "[link to original page not restored]"); dropped empty bullets; collapsible sections turned into toggles; a space added before italic links; callouts that the backup wrote as block quotes (and the reverse); (a link that exists only on the page, not in the backup, is a defect to fix on a restored copy, but is normal on an original page); cover images and icons, which the backup doesn't capture.
   - **Report as "structure differs", not "differs":** list nesting depth, quote nesting (one quote per message against one quote with line breaks), callout against block quote, and link form, when the text itself matches. When the existing page is the original and has real callouts or a cover image the backup lacks, say so: the original is the richer copy, so skipping is almost always right.
   - **Compare headings explicitly** (backup `#` lines outside code fences against the page's headings). A missing, extra, renamed or re-levelled heading makes the item **differs** even when the body text matches, because a restore can silently lose a heading (this has happened: a `# Sources` heading was dropped).
   - **Which side is newer:** compare the backup's `last_edited` with the page's *created* time, not its last edit time. A page made by an earlier restore always has a recent edit time and would wrongly look newer than its backup. If the page was created after the backup was taken and sits under the user's restore target, say it is a prior restore and don't offer "existing is newer" as a reason to skip.
   - For "differs" items, note in one line what differs (for example "backup has 3 extra sections", "heading `# Sources` missing", "titles match but the bodies are unrelated").
3. **Show a summary table** (counts by class, then the items that are not "new") and ask the user what to do, per class or per item (multi-select or one question per class):
   - **Skip** (default for identical items and for anything the user is unsure about): create nothing.
   - **Create a copy**: restore next to the existing page, titled `<title> (restored)`.
   - **Overwrite**: replace the existing page's content with the backup (`notion-update-page`, replacing content). This destroys what is there now, so **offer it only when at least one item is "differs"; leave it out of the options entirely when every item is identical or structure-only** (offer only skip, copy and per-page), and for "differs" items state that Notion's page history can bring the old version back, and require an explicit choice for each page or class. Never overwrite where the existing page is newer than the backup without saying so.
   - **Ask me per page**, for classes with a few items.
   Databases: compare the schema (property names, types, select options and colours), the **views** (names, types, filters and sorts), and the row titles. `notion-fetch` on a database does not list its rows, so query them with `notion-query-data-sources` (and use the row count). Some property details (for example a person property's limit) don't show in fetch output; list those as "couldn't confirm" instead of "differs". Views the backup had that are missing from the page make the database **differs**. Never overwrite a database that has rows the backup doesn't have. Offer skip or copy.
4. **Act on the answers** and record them in the run log (what was skipped, copied and overwritten).
3. Restore parents before children, following each file's `parent:` header. Create each page with `notion-create-pages` using the file's title and body (strip the front matter). Recreate databases with `notion-create-database` from the schema file, then add rows from the row files.
4. Skip or flag: `[REDACTED]` values (they restore as placeholders), placeholders for images/attachments, and anything the manifest lists as not backed up.
5. Write the run log if logging is on (see "Run log"), including any moves or deletes the user asks for after the restore. Report what was created (with links), what was skipped and why, which links inside pages still point at the old URLs, and where the log is.

Creating many pages in someone's workspace is hard to undo, so show the plan (page count, destination) and get a clear yes before the first create.

### Large restores: split across parallel agents
For more than about 15 pages, don't create everything serially in one context. Each page costs a download, a read and a full-content create call, so a big restore floods the main context.
1. **Create the structure first, yourself.** Make the private root page (see "Parent placement"), and any parent page that other groups hang children off (for example the Scratchpad page, or a database that rows go into). Parents must exist, with known page IDs, before the children are created.
2. **Split the rest into independent groups** by parent: files that share a parent, or a parent and its children, stay together. No two groups touch the same files or the same parent.
3. **Launch one agent per group in a single message** (fork agents inherit the loaded tool schemas and the method). Each brief must name the parent page ID, list every file by name and Drive file ID, and repeat the rules: use `download_file_content`, strip front matter, take the title from `notion_title` (a leading emoji becomes the icon), full body verbatim, one create call per page with `allow_async: false`, keep `[REDACTED]` and placeholders as they are, touch no other pages, delete nothing, spawn no agents, and finish with a short report listing created pages with URLs and anything odd or skipped.
   Also tell each agent to keep **every heading** (`#` to `####`) from the backup file: a restore agent once silently dropped a `# Sources` heading while the body text came through intact.
4. **Don't trust agent reports as verification.** They confirm that create calls succeeded, not that the pages render like the originals. After the restore, run a quick **heading check** over every restored page (backup `#` lines against the page's headings, read-only, split across agents by group the same way) and a spot-check of one page per group with `notion-fetch`; fix any lost heading, and say in your report which pages were not compared. In the same pass, **scan the fetched pages for auto-links the backup didn't have**: Notion turns text that looks like a web address into a link when it creates a page, for example a filename such as `TcCopyFiles.exe.config.LIVE_DO_NOT_DELETE` becoming `[TcCopyFiles.exe.config.LIVE](http://TcCopyFiles.exe.config.LIVE)`. Compare the links in each fetched page with the links in its backup file (the backup only has links the original had). Rewriting an extra link as plain text does not work: Notion re-links address-like text (`errors.Is`, `t.Run`, `ASP.NET`, a filename ending `.LIVE`) and email addresses on every write, so skip that and **wrap the text in inline code** with `notion-update-page` (`update_content` for page text, `update_properties` for a database property's text), which stops the linking; tell the user it now shows as code. Leave `mailto:` links on email addresses alone unless the user asks, since they are harmless and code-formatting a whole table column of addresses looks worse than the link. List what you changed in the report and the log. Filenames with dotted extensions and all-caps suffixes (`.LIVE`, `.COM`, `.IO`) are the usual cause.
5. Skip groups the user didn't choose, especially sensitive ones (HR, PIPs, mentoring, credentials). Offer them again afterwards; restoring them later is the same process.

## Things that went wrong before
- Drive converting Markdown to a Google Doc → always set `disableConversionToGoogleType: true`.
- Assuming one pass was enough → page trees nest several levels; keep following `<page url>` links until none are new, and list the rest as gaps.
- Editing a manifest in place → not possible; write it last.
- Very large pages → write the file in one `create_file` call; don't summarise to make it fit.
- Starting without checking access → the Drive connector was missing at first and a workaround through Notion's connector search found nothing. Run the preflight and ask the user to connect what's missing.
- Reading backup files with `read_file_content` → it truncates long files without an error, so restores quietly lose content. Use `download_file_content` and Read the saved file.
- Notion auto-linking filenames on create → text like `TcCopyFiles.exe.config.LIVE_DO_NOT_DELETE` comes back with a link the original never had. It's cosmetic but wrong. Check restored pages for links that aren't in the backup file and fix them (see the verification step in "Large restores").
- One long serial restore → floods the context. Create the parents yourself, then split the rest across parallel agents by group (see "Large restores").
