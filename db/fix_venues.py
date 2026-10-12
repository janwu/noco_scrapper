"""Fix and deduplicate venues in noco.db."""
import sqlite3

DB = "c:/dev/projects/fis/noco_scrapper/db/noco.db"

def merge_into(cur, keep_id, drop_ids, new_name=None):
    """Redirect all competitions from drop_ids to keep_id, delete drop_ids."""
    for drop_id in drop_ids:
        cur.execute("UPDATE competitions SET venue_id=? WHERE venue_id=?", (keep_id, drop_id))
        print(f"  Merged venue {drop_id} -> {keep_id}")
    cur.execute("DELETE FROM venues WHERE id IN ({})".format(",".join("?" * len(drop_ids))), drop_ids)
    if new_name:
        cur.execute("UPDATE venues SET name=? WHERE id=?", (new_name, keep_id))
        print(f"  Renamed venue {keep_id} to '{new_name}'")


conn = sqlite3.connect(DB)
cur = conn.cursor()

print("=== Fixing non-venue entries (WEHLING / NEUMAYER) ===")

# venue 56 = Race Director WEHLING Ulrich — remap each competition to correct venue
codex_to_venue = {
    # RUKA
    "4108": 30, "4109": 30,
    # LILLEHAMMER
    "4147": 48, "4148": 48,
    # RAMSAU
    "4103": 29,
    # OBERHOF
    "4125": 61,
    # RUHPOLDING
    "4126": 57,
    # SCHONACH
    "4127": 54,
    # PREDAZZO -> Val di Fiemme (will be merged below anyway)
    "4133": 62, "4134": 62,
    # HARRACHOV -> Karpacz/Harrachov
    "4173": 15, "4174": 15,
    # SEEFELD
    "4104": 58, "4105": 58,
    # LAHTI
    "4110": 44, "4111": 44,
    # OSLO
    "4149": 60, "4150": 60,
    # SAPPORO
    "4143": 71, "4144": 71,
}

cur.execute("SELECT id, fis_codex FROM competitions WHERE venue_id=56")
for comp_id, codex in cur.fetchall():
    target = codex_to_venue.get(str(codex))
    if target:
        cur.execute("UPDATE competitions SET venue_id=? WHERE id=?", (target, comp_id))
        print(f"  Comp {comp_id} (codex {codex}) -> venue {target}")
    else:
        print(f"  WARNING: no mapping for codex {codex}")

# Delete the now-empty non-venue entries
cur.execute("DELETE FROM venues WHERE id=56")
print("  Deleted venue 56 (Race Director WEHLING Ulrich)")

# venue 55 = Coordinator NEUMAYER Michael — all are Lillehammer COC 2026
cur.execute("UPDATE competitions SET venue_id=48 WHERE venue_id=55")
cur.execute("DELETE FROM venues WHERE id=55")
print("  venue 55 (Coordinator NEUMAYER Michael) -> Lillehammer (48)")

# venue 1 = in Park City -> Park City (45)
cur.execute("UPDATE competitions SET venue_id=45 WHERE venue_id=1")
cur.execute("DELETE FROM venues WHERE id=1")
print("  venue 1 (in Park City) -> Park City (45)")

# venue 2 = in Vancouver-Whistler -> Whistler Olympic Park (49)
cur.execute("UPDATE competitions SET venue_id=49 WHERE venue_id=2")
cur.execute("DELETE FROM venues WHERE id=2")
print("  venue 2 (in Vancouver-Whistler) -> Whistler Olympic Park (49)")

print("\n=== Deduplicating venues ===")

# Chaikovsky (24) <- Chaikovski (70)
merge_into(cur, 24, [70])

# Chaux-Neuve (33) <- Chaux Neuve (66)
merge_into(cur, 33, [66])

# Hoedalsmo (16, rename from Hoeydalsmo) <- Hoydalsmo (9), Höydalsmo (26)
merge_into(cur, 16, [9, 26], new_name="Hoedalsmo")

# Otepaeae (41) <- Otepaa (34), Otepää (13)
merge_into(cur, 41, [34, 13])

# Park City (45) <- all Utah/Soldier Hollow variants
merge_into(cur, 45, [19, 18, 11, 23, 31, 42, 40])

# Ruka (30) <- Kuusamo (17), Kuusamo,Ruka (53)
merge_into(cur, 30, [17, 53])

# Val di Fiemme (62) <- Predazzo (21)
merge_into(cur, 62, [21])

# Nizhny Tagil (35) <- Nizhniy Tagil (38), Nizhny Tagli (46)
merge_into(cur, 35, [38, 46])

# Steamboat Springs (36) <- Steamboat Ski and Resort / Howelsen Hill (39)
merge_into(cur, 36, [39])

# Ramsau (29) <- Ramsau am Dachstein (68)
merge_into(cur, 29, [68])

# Lake Placid (rename 12 from "Lake Placid, NY") <- Lake Placid/ORDA (50)
merge_into(cur, 12, [50], new_name="Lake Placid")

conn.commit()
conn.close()
print("\nDone.")
