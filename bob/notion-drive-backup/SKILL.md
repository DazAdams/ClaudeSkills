---
name: notion-drive-backup
description: Back up Notion pages and databases to Google Drive as Markdown files, and restore them from Drive back into Notion. Use whenever the user wants to back up, export, archive, protect, snapshot or migrate Notion content (their Private section, a page tree, a database), says they are changing their Notion login/account/workspace, or asks to restore, recover or re-import Notion pages from a Drive backup — even if they never say "skill", "Markdown" or "Drive folder".
---

# Notion ⇄ Google Drive backup and restore

Backs up Notion content into a dated Google Drive folder as one Markdown file per page, with a manifest that makes restoring possible later. Also restores from that folder.

Needs a connected Notion connector (`notion-fetch`, `notion-list-private-pages`, `notion-query-data-sources`; for restore also `notion-create-pages`, `notion-create-database`) and a Google Drive connector (`create_file`, `search_files`, `read_file_content` or `download_file_content`, `update_file`). If a deferred tool's schema isn't loaded, load it with ToolSearch first. If two Notion servers are listed and one says it needs authorization, use the one that is already connected (check with `notion-get-self`).

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
Say what's in the folder and link it. State the gaps plainly: sub-levels not followed, images and attachments, comments, page history, sharing permissions, unreadable blocks. Say that a restore hasn't been tested unless you tested it. Remind the user to keep the folder private if it holds sensitive pages, and to move any redacted credentials into a password manager.

## Restore

1. Find the backup folder (`search_files` on the folder title) and read `00-MANIFEST-and-RESTORE.md` with `read_file_content`. If there are several backups, ask which date.
2. Ask where to restore to and whether the original pages still exist. Restoring creates new pages with new IDs and URLs; it can't revive deleted ones or overwrite existing ones safely. Before creating anything, search Notion for pages with the same title so the user isn't left with duplicates, and confirm if any exist.
3. Restore parents before children, following each file's `parent:` header. Create each page with `notion-create-pages` using the file's title and body (strip the front matter). Recreate databases with `notion-create-database` from the schema file, then add rows from the row files.
4. Skip or flag: `[REDACTED]` values (they restore as placeholders), placeholders for images/attachments, and anything the manifest lists as not backed up.
5. Report what was created (with links), what was skipped and why, and which links inside pages still point at the old URLs.

Creating many pages in someone's workspace is hard to undo, so show the plan (page count, destination) and get a clear yes before the first create.

## Things that went wrong before
- Drive converting Markdown to a Google Doc → always set `disableConversionToGoogleType: true`.
- Assuming one pass was enough → page trees nest several levels; keep following `<page url>` links until none are new, and list the rest as gaps.
- Editing a manifest in place → not possible; write it last.
- Very large pages → write the file in one `create_file` call; don't summarise to make it fit.
