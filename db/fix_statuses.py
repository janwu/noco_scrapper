"""
Fix NULL statuses in combined_results by reading ROF JSON files
and updating DNS/DNF/DSQ rows that were loaded with NULL status.
"""
import glob
import json
import os
import re
import sqlite3

DB = "c:/dev/projects/fis/noco_scrapper/db/noco.db"
OUTPUT_DIR = "c:/dev/projects/fis/noco_scrapper/output"


def filename_meta(path):
    norm = path.replace("\\", "/")
    fname = os.path.basename(norm).replace(".json", "")
    circuit = "WC" if "fis_nk_pdfs/" in norm and "fis_nk_coc_pdfs/" not in norm else "COC"
    m = re.match(r"(\d+)_", fname)
    codex = m.group(1) if m else None
    m = re.search(r"_(\d{4})NK", fname)
    if m:
        end_year = int(m.group(1))
        season_start = end_year - 1
    else:
        season_start = None
    return {"circuit": circuit, "codex": codex, "season_start": season_start}


conn = sqlite3.connect(DB)
conn.execute("PRAGMA foreign_keys=ON")
cur = conn.cursor()

rof_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "**/*ROF*.json"), recursive=True))
print(f"Found {len(rof_files)} ROF files")

updated = 0
skipped = 0

for path in rof_files:
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)

    meta = filename_meta(path)
    if not meta["codex"] or not meta["season_start"]:
        continue

    # Find the competition_id
    cur.execute(
        "SELECT c.id FROM competitions c "
        "JOIN seasons s ON c.season_id = s.id "
        "WHERE c.fis_codex = ? AND s.start_year = ?",
        (meta["codex"], meta["season_start"]),
    )
    row = cur.fetchone()
    if not row:
        skipped += 1
        continue
    competition_id = row[0]

    for r in doc.get("combined_results") or []:
        status = (r.get("status") or "").strip().upper()
        if status not in ("DNS", "DNF", "DSQ", "DNQ"):
            continue
        name = (r.get("name") or "").strip()
        if not name:
            continue

        # Find athlete_id by name
        cur.execute(
            "SELECT id FROM athletes WHERE full_name = ?", (name,)
        )
        ath = cur.fetchone()
        if not ath:
            # Try via name variants
            cur.execute(
                "SELECT athlete_id FROM athlete_name_variants WHERE name_variant = ?", (name,)
            )
            ath = cur.fetchone()
        if not ath:
            continue
        athlete_id = ath[0]

        cur.execute(
            "UPDATE combined_results SET status = ? "
            "WHERE competition_id = ? AND athlete_id = ? AND (status IS NULL OR status = '')",
            (status, competition_id, athlete_id),
        )
        updated += cur.rowcount

conn.commit()
conn.close()
print(f"Updated {updated} rows. Skipped {skipped} files (no matching competition).")
