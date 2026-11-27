#!/usr/bin/env python3
"""Propose new ports.txt entries from VitaDB.

VitaDB (https://www.rinnegatamante.eu/vitadb/) lists PS Vita homebrew. Entries of type 2 are ports;
their names are often nicknames ("NFSU2 Vita"), but the description usually names the original game
("Port of Need for Speed Underground 2 for PSVita."). For every port whose title ID is not yet in
ports.txt (or ignore.txt), this script:

  1. takes candidate names: the game named in the description, then VitaDB's name without "Vita"-style
     suffixes;
  2. searches SteamGridDB for each candidate; a result whose name matches closely is VERIFIED and added
     to ports.txt under SteamGridDB's own spelling (what Shell UI / Aurora searches with);
  3. lists everything else in review.md with the best guesses, for a person to decide.

Environment: SGDB_KEY (SteamGridDB API key). Standard library only.
Usage: python3 scripts/ports_sync.py [--limit N] [--dry-run]
"""
import difflib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTS = os.path.join(ROOT, "ports.txt")
IGNORE = os.path.join(ROOT, "ignore.txt")
REVIEW = os.path.join(ROOT, "review.md")
VITADB_LIST = "https://www.rinnegatamante.eu/vitadb/list_hbs_json_simple.php"
SGDB_SEARCH = "https://www.steamgriddb.com/api/v2/search/autocomplete/"
UA = "shellui-data-ports-sync/1.0"
PORTS_HEADER = "# ---- Ports / remakes"
TID_RE = re.compile(r"^[A-Z0-9]{9}$")


def http_json(url, method="GET", headers=None, data=None):
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": UA, **(headers or {})})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429 or e.code >= 500:
                time.sleep(2 + attempt * 3)
                continue
            raise
        except urllib.error.URLError:
            time.sleep(2 + attempt * 3)
    raise RuntimeError("giving up on " + url)


# ---------------------------------------------------------------- names
def fix_text(s):
    """VitaDB text is sometimes UTF-8 decoded as Latin-1 one or more times; undo that."""
    for _ in range(4):
        try:
            t = s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if t == s:
            break
        s = t
    return s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"^the ", "", s)
    return re.sub(r"\s+", " ", s)


ABBREV = re.compile(r"\b(vs|vol|dr|mr|mrs|st|jr|no|ft)\.", re.I)
LEAD = re.compile(
    r"(?i)\b(?:unofficial\s+|native\s+|vita\s+|psvita\s+|ps\s?vita\s+|source\s+|engine\s+|full\s+|a\s+)?"
    r"(?:port(?:ed version)?|remake|recreation|reimplementation|decompilation|recompilation|conversion)\s+of\s+"
    r"(?:the\s+(?:original\s+|classic\s+|famous\s+|popular\s+)?(?:game\s+)?)?"
    r"(?:(?:pc|dos|n64|nintendo 64|gamecube|wii|ps2|ps1|psx|xbox|android|ios|snes|nes|gba|ds|switch|windows|mobile)\s+(?:game\s+|version\s+of\s+)?)?")
STOP = re.compile(r"(?i)\s+(?:for|to|on)\s+(?:the\s+)?(?:ps\s?vita|psv|vita|playstation vita)\b|\s+by\s+|\s+\(|\.\s|\.$|,|;|\n|\s+-\s+|!|$")
SUFFIX = re.compile(r"(?i)[\s_-]*(?:ps\s?vita|psv|vita|ve|port|remastered vita)$")


def from_description(desc):
    d = ABBREV.sub(lambda m: m.group(1) + "\u2024", fix_text(desc or ""))   # keep "vs." inside names
    m = LEAD.search(d)
    if not m:
        return None
    rest = d[m.end():].lstrip(" \"'")
    end = STOP.search(rest)
    name = rest[: end.start()] if end else rest
    name = name.replace("\u2024", ".").strip(" \"'.:")
    name = re.sub(r"(?i)^(?:the\s+)?(?:game|videogame|video game)\s+", "", name)
    return name if 2 <= len(name) <= 80 else None


def from_name(name):
    n = fix_text(name or "").strip()
    for _ in range(3):
        n2 = SUFFIX.sub("", n).strip()
        if n2 == n:
            break
        n = n2
    return n if len(n) >= 3 else None


# ---------------------------------------------------------------- SteamGridDB
class Sgdb:
    def __init__(self, key):
        self.key = key
        self.cache = {}

    def search(self, term):
        if term in self.cache:
            return self.cache[term]
        time.sleep(0.25)
        r = http_json(SGDB_SEARCH + urllib.parse.quote(term, safe=""), headers={"Authorization": "Bearer " + self.key})
        res = [(g["name"], g["id"]) for g in (r or {}).get("data", [])] if r and r.get("success") else []
        self.cache[term] = res
        return res


def verify(sg, cand):
    """(SteamGridDB name, id, score) of the best result; score 1.0 = same name after normalising"""
    best = None
    for name, gid in sg.search(cand)[:8]:
        a, b = norm(cand), norm(name)
        score = 1.0 if a == b else difflib.SequenceMatcher(None, a, b).ratio()
        if not best or score > best[2]:
            best = (name, gid, score)
    return best


# ---------------------------------------------------------------- files
def read_ids(path):
    ids = set()
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            m = re.match(r"\s*([A-Z0-9]{9})\s*(=|$|\s)", line)
            if m:
                ids.add(m.group(1))
    return ids


def add_ports(new):
    """insert `TID = name` lines into the Ports section, keeping that section sorted"""
    lines = open(PORTS, encoding="utf-8").read().split("\n")
    start = lines.index(PORTS_HEADER) + 1
    end = start
    while end < len(lines) and lines[end].strip() and not lines[end].startswith("# ----"):
        end += 1
    section = lines[start:end] + [f"{tid} = {name}" for tid, name in new]
    section.sort(key=lambda l: l.split("=", 1)[0].strip())
    lines[start:end] = section
    with open(PORTS, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))


def md(s):
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def main():
    key = os.environ.get("SGDB_KEY", "").strip()
    if not key:
        sys.exit("SGDB_KEY is not set")
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    dry = "--dry-run" in sys.argv

    db = http_json(VITADB_LIST, method="POST", data=b"")
    known = read_ids(PORTS) | read_ids(IGNORE)
    todo = [e for e in db if str(e.get("type")) == "2" and TID_RE.match(e.get("titleid") or "") and e["titleid"] not in known]
    seen, uniq = set(), []
    for e in sorted(todo, key=lambda e: e["titleid"]):   # one entry per title id (re-uploads share ids)
        if e["titleid"] not in seen:
            seen.add(e["titleid"])
            uniq.append(e)
    if limit:
        uniq = uniq[:limit]
    print(f"VitaDB: {len(db)} entries, {len(uniq)} ports not in ports.txt / ignore.txt")

    sg = Sgdb(key)
    added, review = [], []
    for e in uniq:
        cands = []
        for c in (from_description(e.get("description")), from_name(e.get("name"))):
            if c and norm(c) not in [norm(x) for x in cands]:
                cands.append(c)
        best = None
        for c in cands:
            v = verify(sg, c)
            if v and (not best or v[2] > best[1][2]):
                best = (c, v)
            if v and v[2] >= 0.97:
                break
        if best and best[1][2] >= 0.97:
            added.append((e["titleid"], best[1][0]))
            print(f"  + {e['titleid']} = {best[1][0]}   (from '{best[0]}')")
        else:
            review.append((e, cands, best))

    if dry:
        print(f"dry run: {len(added)} verified, {len(review)} to review")
        return
    if added:
        add_ports(added)
    with open(REVIEW, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# Ports to review\n\n")
        fh.write("Written by `scripts/ports_sync.py` (weekly GitHub Action). These VitaDB ports could not be matched\n"
                 "to a SteamGridDB game automatically. For each one: add `TITLEID = <SteamGridDB name>` to\n"
                 "`ports.txt`, or add the title ID to `ignore.txt` so it is not proposed again.\n\n")
        fh.write(f"{len(review)} ports. Best SteamGridDB guess shown with its similarity (1.00 = same name).\n\n")
        fh.write("| Title ID | VitaDB name | Original game (from VitaDB) | Best SteamGridDB guess |\n|---|---|---|---|\n")
        for e, cands, best in review:
            guess = f"[{md(best[1][0])}](https://www.steamgriddb.com/game/{best[1][1]}) ({best[1][2]:.2f})" if best else "none"
            fh.write(f"| `{e['titleid']}` | [{md(fix_text(e.get('name')))}](https://www.rinnegatamante.eu/vitadb/#/info/{e.get('id')}) "
                     f"| {md(cands[0]) if cands else ''} | {guess} |\n")
    print(f"{len(added)} added to ports.txt, {len(review)} listed in review.md")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write(f"added={len(added)}\nreview={len(review)}\n")


if __name__ == "__main__":
    main()
