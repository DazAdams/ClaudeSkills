#!/usr/bin/env python3
"""Back up Chrome bookmarks and reading list into a single zip (stdlib only).

Passwords are deliberately NOT handled here: Chrome's password store is
encrypted with keys this script must not extract. See SKILL.md for the
export-and-encrypt flow (scripts/Protect-File.ps1).

Usage:
  chrome_backup.py backup --out DIR [--profiles all|Default,"Profile 1"] [--keep N]
  chrome_backup.py list   --archive FILE.zip
  chrome_backup.py profiles
"""
import argparse, csv, datetime as dt, hashlib, html, io, json, os, shutil, struct, sys, tempfile, zipfile

WIN_EPOCH_OFFSET = 11644473600  # seconds between 1601-01-01 and 1970-01-01


# ---------------------------------------------------------------- Chrome paths
def chrome_dir(override=None):
    if override:
        return override
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")


def profile_info(cdir):
    """Map profile dir name -> {name, email} from Local State."""
    try:
        with open(os.path.join(cdir, "Local State"), encoding="utf-8") as f:
            cache = json.load(f).get("profile", {}).get("info_cache", {})
    except Exception:
        cache = {}
    return {k: {"name": v.get("name", ""), "email": v.get("user_name", "")} for k, v in cache.items()}


def find_profiles(cdir, wanted):
    info = profile_info(cdir)
    found = [d for d in sorted(os.listdir(cdir))
             if (d == "Default" or d.startswith("Profile ")) and os.path.isdir(os.path.join(cdir, d))]
    if wanted != "all":
        names = [w.strip() for w in wanted.split(",") if w.strip()]
        found = [d for d in found if d in names or info.get(d, {}).get("name") in names]
    return found, info


# ---------------------------------------------------------------- time helpers
def webkit_to_dt(us):
    try:
        return dt.datetime.fromtimestamp(int(us) / 1e6 - WIN_EPOCH_OFFSET, dt.timezone.utc)
    except Exception:
        return None


def webkit_to_unix(us):
    try:
        return max(0, int(int(us) / 1e6 - WIN_EPOCH_OFFSET))
    except Exception:
        return 0


# ---------------------------------------------------------------- bookmarks
def count_urls(node):
    if node.get("type") == "url":
        return 1
    return sum(count_urls(c) for c in node.get("children", []))


def load_json(path):
    with open(path, "rb") as f:  # Chrome opens these with sharing, so a plain read works
        return json.loads(f.read().decode("utf-8"))


def netscape_html(sources, reading=None):
    """sources: list of (label, bookmarks_json). Returns Netscape bookmark HTML."""
    out = ['<!DOCTYPE NETSCAPE-Bookmark-file-1>',
           '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
           '<TITLE>Bookmarks</TITLE>', '<H1>Bookmarks</H1>', '<DL><p>']

    def walk(node, depth):
        pad = "    " * depth
        if node.get("type") == "url":
            out.append(f'{pad}<DT><A HREF="{html.escape(node.get("url", ""), quote=True)}" '
                       f'ADD_DATE="{webkit_to_unix(node.get("date_added", 0))}">{html.escape(node.get("name", ""))}</A>')
        else:
            out.append(f'{pad}<DT><H3 ADD_DATE="{webkit_to_unix(node.get("date_added", 0))}">{html.escape(node.get("name", ""))}</H3>')
            out.append(f"{pad}<DL><p>")
            for c in node.get("children", []):
                walk(c, depth + 1)
            out.append(f"{pad}</DL><p>")

    for label, data in sources:
        out.append(f'    <DT><H3>{html.escape(label)}</H3>')
        out.append("    <DL><p>")
        for root in data.get("roots", {}).values():
            if isinstance(root, dict) and count_urls(root):
                walk(root, 2)
        out.append("    </DL><p>")
    if reading:
        out.append("    <DT><H3>Reading List</H3>")
        out.append("    <DL><p>")
        for e in reading:
            out.append(f'        <DT><A HREF="{html.escape(e["url"], quote=True)}" ADD_DATE="{e.get("added_unix", 0)}">'
                       f'{html.escape(e.get("title") or e["url"])}</A>')
        out.append("    </DL><p>")
    out.append("</DL><p>")
    return "\n".join(out)


# ---------------------------------------------------------------- LevelDB reader (read-only, minimal)
def varint(buf, pos):
    shift = result = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def snappy_decompress(data):
    length, pos = varint(data, 0)
    out = bytearray()
    while pos < len(data):
        tag = data[pos]
        pos += 1
        kind = tag & 3
        if kind == 0:
            n = tag >> 2
            if n >= 60:
                extra = n - 59
                n = int.from_bytes(data[pos:pos + extra], "little")
                pos += extra
            n += 1
            out += data[pos:pos + n]
            pos += n
        else:
            if kind == 1:
                n = ((tag >> 2) & 7) + 4
                off = ((tag >> 5) << 8) | data[pos]
                pos += 1
            elif kind == 2:
                n = (tag >> 2) + 1
                off = int.from_bytes(data[pos:pos + 2], "little")
                pos += 2
            else:
                n = (tag >> 2) + 1
                off = int.from_bytes(data[pos:pos + 4], "little")
                pos += 4
            for _ in range(n):  # byte-wise: copies may overlap
                out.append(out[-off])
    if len(out) != length:
        raise ValueError("snappy length mismatch")
    return bytes(out)


def block_entries(block):
    n_restarts = struct.unpack("<I", block[-4:])[0]
    end = len(block) - 4 - 4 * n_restarts
    pos, key = 0, b""
    while pos < end:
        shared, pos = varint(block, pos)
        non_shared, pos = varint(block, pos)
        vlen, pos = varint(block, pos)
        key = key[:shared] + block[pos:pos + non_shared]
        pos += non_shared
        yield key, block[pos:pos + vlen]
        pos += vlen


def read_block(data, offset, size):
    raw = data[offset:offset + size]
    kind = data[offset + size]
    return snappy_decompress(raw) if kind == 1 else raw


def read_ldb(path):
    """Yield (user_key, seq, type, value) from a .ldb table. type 1=put, 0=delete."""
    with open(path, "rb") as f:
        data = f.read()
    footer = data[-48:]
    _, p = varint(footer, 0)   # metaindex offset
    _, p = varint(footer, p)   # metaindex size
    idx_off, p = varint(footer, p)
    idx_size, p = varint(footer, p)
    for _, handle in block_entries(read_block(data, idx_off, idx_size)):
        off, q = varint(handle, 0)
        size, _ = varint(handle, q)
        for ikey, val in block_entries(read_block(data, off, size)):
            if len(ikey) < 8:
                continue
            trailer = struct.unpack("<Q", ikey[-8:])[0]
            yield ikey[:-8], trailer >> 8, trailer & 0xFF, val


def read_log(path):
    """Yield (user_key, seq, type, value) from a .log write-ahead file."""
    with open(path, "rb") as f:
        data = f.read()
    records, cur, pos = [], b"", 0
    while pos + 7 <= len(data):
        block_left = 32768 - (pos % 32768)
        if block_left < 7:
            pos += block_left
            continue
        length = struct.unpack("<H", data[pos + 4:pos + 6])[0]
        rtype = data[pos + 6]
        chunk = data[pos + 7:pos + 7 + length]
        pos += 7 + length
        if rtype == 1:
            records.append(chunk)
        elif rtype == 2:
            cur = chunk
        elif rtype == 3:
            cur += chunk
        elif rtype == 4:
            records.append(cur + chunk)
            cur = b""
    for rec in records:
        if len(rec) < 12:
            continue
        seq, count = struct.unpack("<QI", rec[:12])
        p = 12
        for i in range(count):
            t = rec[p]
            p += 1
            klen, p = varint(rec, p)
            key = rec[p:p + klen]
            p += klen
            val = b""
            if t == 1:
                vlen, p = varint(rec, p)
                val = rec[p:p + vlen]
                p += vlen
            yield key, seq + i, t, val


def read_leveldb_dir(path):
    """Newest-wins merge of every table/log in a LevelDB directory -> {key: value}."""
    latest = {}
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        try:
            if name.endswith(".ldb") or name.endswith(".sst"):
                it = read_ldb(full)
            elif name.endswith(".log"):
                it = read_log(full)
            else:
                continue
            for key, seq, t, val in it:
                if key not in latest or seq >= latest[key][0]:
                    latest[key] = (seq, t, val)
        except Exception as e:
            print(f"  warning: could not read {name}: {e}", file=sys.stderr)
    return {k: v[2] for k, v in latest.items() if v[1] == 1}


# ---------------------------------------------------------------- reading list
def pb_fields(buf):
    """Minimal protobuf walk -> {field_no: [values]}. Returns {} on malformed input."""
    fields, pos = {}, 0
    try:
        while pos < len(buf):
            tag, pos = varint(buf, pos)
            fno, wt = tag >> 3, tag & 7
            if wt == 0:
                v, pos = varint(buf, pos)
            elif wt == 1:
                v, pos = buf[pos:pos + 8], pos + 8
            elif wt == 2:
                n, pos = varint(buf, pos)
                v, pos = buf[pos:pos + n], pos + n
            elif wt == 5:
                v, pos = buf[pos:pos + 4], pos + 4
            else:
                return {}
            fields.setdefault(fno, []).append(v)
    except Exception:
        return {}
    return fields


def extract_reading_list(profile_path, tmp):
    src = os.path.join(profile_path, "Sync Data", "LevelDB")
    if not os.path.isdir(src):
        return None, "no Sync Data/LevelDB (profile not signed in to sync?)"
    snap = os.path.join(tmp, "leveldb-" + os.path.basename(profile_path).replace(" ", "_"))
    os.makedirs(snap, exist_ok=True)
    for name in os.listdir(src):
        if name == "LOCK":
            continue
        try:
            shutil.copyfile(os.path.join(src, name), os.path.join(snap, name))
        except Exception as e:
            print(f"  warning: could not snapshot {name}: {e}", file=sys.stderr)
    entries = []
    marker = b"reading_list-dt-"
    for key, val in read_leveldb_dir(snap).items():
        i = key.find(marker)
        if i < 0:
            continue
        key_url = key[i + len(marker):].decode("utf-8", "replace")
        f = pb_fields(val)
        # The specifics may be wrapped in an outer message; unwrap one level if needed.
        if not f.get(1) and not f.get(2):
            for inner in (v for vs in f.values() for v in vs if isinstance(v, bytes)):
                g = pb_fields(inner)
                if g.get(2) or g.get(3):
                    f = g
                    break
        def s(n):
            v = f.get(n, [b""])[0]
            return v.decode("utf-8", "replace") if isinstance(v, bytes) else ""
        url = s(3) or s(1) or key_url
        created = f.get(4, [0])[0] if f.get(4) and isinstance(f.get(4)[0], int) else 0
        status = f.get(6, [None])[0]
        # Sync stores this in microseconds; observed as Unix epoch, but fall back to the
        # Windows epoch if that gives an implausible year.
        added_unix = int(created / 1e6) if created else 0
        if added_unix and not (2000 <= dt.datetime.fromtimestamp(added_unix, dt.timezone.utc).year <= 2100):
            added_unix = webkit_to_unix(created)
        entries.append({
            "url": url, "title": s(2),
            "added": dt.datetime.fromtimestamp(added_unix, dt.timezone.utc).isoformat() if added_unix else "",
            "added_unix": added_unix,
            "read": {0: False, 1: True, 2: False}.get(status) if isinstance(status, int) else None,
        })
    entries.sort(key=lambda e: e["added_unix"], reverse=True)
    return entries, None


# ---------------------------------------------------------------- backup / list
def backup(args):
    cdir = chrome_dir(args.chrome_dir)
    if not os.path.isdir(cdir):
        sys.exit(f"Chrome user data not found: {cdir}")
    profiles, info = find_profiles(cdir, args.profiles)
    if not profiles:
        sys.exit("No matching Chrome profiles")
    os.makedirs(args.out, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = os.path.join(args.out, f"chrome-backup-{stamp}.zip")
    manifest = {"created": dt.datetime.now().isoformat(timespec="seconds"), "chrome_dir": cdir,
                "chrome_version": "", "profiles": {}, "notes": []}
    try:
        with open(os.path.join(cdir, "Last Version"), encoding="utf-8") as f:
            manifest["chrome_version"] = f.read().strip()
    except Exception:
        pass

    tmp = tempfile.mkdtemp(prefix="chrome-backup-")
    try:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for prof in profiles:
                ppath = os.path.join(cdir, prof)
                label = info.get(prof, {}).get("name") or prof
                pm = {"name": label, "email": info.get(prof, {}).get("email", ""), "bookmarks": {}, "reading_list": None}
                sources = []
                # Signed-in profiles keep synced bookmarks in AccountBookmarks and local-only
                # ones in Bookmarks; either (or both) can hold the real data, so take both.
                for fname in ("Bookmarks", "AccountBookmarks"):
                    p = os.path.join(ppath, fname)
                    if not os.path.isfile(p):
                        continue
                    try:
                        data = load_json(p)
                    except Exception as e:
                        manifest["notes"].append(f"{prof}/{fname}: unreadable ({e})")
                        continue
                    n = count_urls({"children": [r for r in data.get("roots", {}).values() if isinstance(r, dict)]})
                    pm["bookmarks"][fname] = n
                    z.write(p, f"{prof}/{fname}.json")
                    if n:
                        sources.append((f"{label} ({fname})", data))

                reading, err = (None, "skipped") if args.no_reading_list else extract_reading_list(ppath, tmp)
                if reading is not None:
                    pm["reading_list"] = len(reading)
                    z.writestr(f"{prof}/reading-list.json", json.dumps(reading, indent=2, ensure_ascii=False))
                    buf = io.StringIO()
                    w = csv.DictWriter(buf, fieldnames=["title", "url", "added", "read"], extrasaction="ignore")
                    w.writeheader()
                    w.writerows(reading)
                    z.writestr(f"{prof}/reading-list.csv", buf.getvalue())
                elif err != "skipped":
                    manifest["notes"].append(f"{prof}: reading list not captured: {err}")

                if sources or reading:
                    z.writestr(f"{prof}/bookmarks-import.html", netscape_html(sources, reading))
                manifest["profiles"][prof] = pm
            manifest["notes"].append(
                "Reading list is read from Chrome's sync cache; compare the count with chrome://bookmarks "
                "side panel. Passwords are not included (see SKILL.md).")
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if args.keep:
        old = sorted(f for f in os.listdir(args.out) if f.startswith("chrome-backup-") and f.endswith(".zip"))
        for f in old[:-args.keep]:
            os.remove(os.path.join(args.out, f))
            print(f"pruned {f}")

    sha = hashlib.sha256(open(archive, "rb").read()).hexdigest()
    for prof, pm in manifest["profiles"].items():
        print(f"profile {prof} ({pm['name']}, {pm['email'] or 'no account'}): "
              f"bookmarks {pm['bookmarks']}, reading list {pm['reading_list']}")
    for n in manifest["notes"]:
        print("note:", n)
    print(f"ARCHIVE={archive}")
    print(f"SIZE={os.path.getsize(archive)}")
    print(f"SHA256={sha}")


def list_archive(args):
    with zipfile.ZipFile(args.archive) as z:
        for i in z.infolist():
            print(f"{i.file_size:>10}  {i.filename}")
        if "manifest.json" in z.namelist():
            print(json.dumps(json.loads(z.read("manifest.json")), indent=2))


def show_profiles(args):
    cdir = chrome_dir(args.chrome_dir)
    found, info = find_profiles(cdir, "all")
    for p in found:
        print(f"{p}: {info.get(p, {}).get('name', '?')} <{info.get(p, {}).get('email', '')}>")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chrome-dir")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--out", required=True)
    b.add_argument("--profiles", default="all")
    b.add_argument("--keep", type=int, default=0, help="keep only the newest N archives in --out (0 = keep all)")
    b.add_argument("--no-reading-list", action="store_true")
    b.set_defaults(fn=backup)
    l = sub.add_parser("list")
    l.add_argument("--archive", required=True)
    l.set_defaults(fn=list_archive)
    pr = sub.add_parser("profiles")
    pr.set_defaults(fn=show_profiles)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
