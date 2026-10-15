#!/usr/bin/env python3
"""
Suggest display names with native letters for athletes: 'BJOERNSTAD Espen'
(NOR) → 'BJØRNSTAD Espen', 'FRENZEL Eric' unchanged, 'MUEHLBACHER Lukas'
(AUT) → 'MÜHLBACHER Lukas'.

FIS writes names in ASCII, and the database keeps them so; the web app shows
the display name from db/aliases/athlete_display_names.csv instead.  This
script adds suggestions for the athletes of db/noco.db that have no line in
that file yet; it never changes a line that is there (correct those by hand).

The rules depend on the nation, and leave alone what is not a transliteration:

    NOR, DEN       oe → ø, ae → æ; aa → å in given names (the surname keeps it: Graabak)
    GER, AUT, SUI  ae → ä, oe → ö, ue → ü  (not in Michael, Manuel, Bauer, Neuer)
    FIN, EST, SWE  ae → ä, oe → ö          (not in Joensuu, Mikael)

    python db/suggest_display_names.py            # append suggestions, print them
    python db/suggest_display_names.py --dry-run
"""
import argparse
import csv
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(HERE, "aliases", "athlete_display_names.csv")

RULES = {
    "nordic": [("oe", "ø"), ("ae", "æ")],
    "german": [("ae", "ä"), ("oe", "ö"), ("ue", "ü")],
    "finnic": [("ae", "ä"), ("oe", "ö")],
}
NATIONS = {"NOR": "nordic", "DEN": "nordic",
           "GER": "german", "AUT": "german", "SUI": "german", "LIE": "german",
           "FIN": "finnic", "EST": "finnic", "SWE": "finnic"}
# words in which the letters are no transliteration
KEEP = {"michael", "mikael", "rafael", "raphael", "raffael", "gael", "ismael", "israel", "joel", "noel", "zoe",
        "chloe", "manuel", "emanuel", "immanuel", "samuel", "lemuel", "joensuu", "aeschbacher", "raphaela",
        "noe", "moen"}
# Norwegian surnames ending in -moen ('moor') are spelled so
KEEP_ENDINGS = ("moen",)


def native(word: str, rules) -> str:
    if word.lower() in KEEP or word.lower().endswith(KEEP_ENDINGS):
        return word
    out, i = [], 0
    while i < len(word):
        pair = word[i:i + 2]
        hit = next((to for frm, to in rules if pair.lower() == frm), None)
        # 'ue' after a vowel or q is a diphthong or 'qu': Bauer, Neuer, Quentin
        if hit == "ü" and i > 0 and word[i - 1].lower() in "aeq":
            hit = None
        if hit:
            out.append(hit.upper() if pair[0].isupper() else hit)
            i += 2
        else:
            out.append(word[i])
            i += 1
    return "".join(out)


def suggest(name: str, nation: str) -> str:
    family = NATIONS.get(nation, "")
    rules = RULES.get(family, [])
    if not rules:
        return name
    words = []
    for w in name.split(" "):
        # Norwegian given names: aa → å (Haavard → Håvard, Luraas → Lurås); not the surname
        # in capitals, many of which keep 'aa' (GRAABAK)
        word_rules = rules + [("aa", "å")] if family == "nordic" and not w.isupper() else rules
        words.append("-".join(native(part, word_rules) for part in w.split("-")))
    return " ".join(words)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", default=os.path.join(HERE, "noco.db"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    known = set()
    if os.path.exists(FILE):
        with open(FILE, encoding="utf-8", newline="") as fh:
            for row in csv.reader(fh):
                if len(row) >= 2 and not row[0].startswith("#"):
                    known.add((row[0], row[1]))
    db = sqlite3.connect(args.db)
    new = []
    for name, nation in db.execute("SELECT full_name, nationality FROM athletes ORDER BY nationality, full_name"):
        if (name, nation) in known:
            continue
        shown = suggest(name, nation)
        if shown != name:
            new.append((name, nation, shown))
    for row in new:
        print(f"  {row[1]}  {row[0]:35} → {row[2]}")
    print(f"{len(new)} suggestions" + (" (not written)" if args.dry_run else f" appended to {FILE}"))
    if new and not args.dry_run:
        exists = os.path.exists(FILE)
        with open(FILE, "a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            if not exists:
                w.writerow(["name", "nation", "display_name"])
            w.writerows(new)


if __name__ == "__main__":
    main()
