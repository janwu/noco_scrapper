# FIS Nordic Combined results

Scrapes the result PDFs of the Nordic Combined World Cup and Continental Cup
from fis-ski.com, parses them and builds a database for the web app.

```
fis_nk_scraper.py / fis_nk_coc_scraper.py     PDFs      → fis_nk_pdfs/, fis_nk_coc_pdfs/
   (both run fis_nk_pdf_scraper.py)
run_parser.py            (fis_parser/)        PDFs      → output/**/*.json
db/load_json.py          (db/aliases/*.csv)   JSON      → db/noco.db
webapp/                                       db/noco.db → Vaadin site

fis_nk_standings_scraper.py                   FIS database → fis_nk_standings/*.json
                                              (official cup standings, also read by load_json.py)
```

The PDFs, `output/` and the database are not in the repository: the PDFs can
be downloaded again, everything else is rebuilt from them.

Cup standings are not computed from the results. The points rules changed over
the years and tours such as the Seefeld Triple score differently, so the final
standings FIS publishes are downloaded and loaded as they are
(`python fis_nk_standings_scraper.py --seasons 2026` refreshes a season).

## A new season

```
python fis_nk_scraper.py --seasons 2027 --dry-run      # what is new on the FIS pages
python fis_nk_scraper.py --seasons 2027                 # World Cup
python fis_nk_coc_scraper.py --seasons 2027             # Continental Cup
python fis_nk_standings_scraper.py --seasons 2027       # cup standings, once the season is over
python run_parser.py --workers 7 --errors-only          # parses only the new PDFs
python db/load_json.py --sqlite db/noco.db
```

Without `--seasons` the scrapers go through all seasons up to the current one;
files already on disk are recognised by their FIS name (e.g. `2026NK4117ROF.pdf`)
and not downloaded again. How the FIS pages are read is described at the top of
`fis_nk_pdf_scraper.py`.

## Rebuilding the data

```
pip install -r requirements.txt
python run_parser.py --workers 7 --overwrite --errors-only     # ~10 min
python db/load_json.py --sqlite db/noco.db                     # ~20 s, full rebuild
python -m unittest discover -s tests
```

`run_parser.py` ends with a summary of validation errors and warnings by
kind; `load_json.py` ends with what it did not load and why.

## Where corrections go

The database is never edited by hand — the next rebuild would undo it.

| Problem | Fix it in |
|---|---|
| A PDF is read wrongly | `fis_parser/` (add the PDF to `tests/test_rof_parser.py`) |
| Two spellings of one athlete | `db/aliases/athletes.csv` |
| Two names for one venue | `db/aliases/venues.csv` |

Alias files have four columns: the name and nation as printed, then the
name and nation to use instead. Lines starting with `#` are comments.

## Known gaps

- Since 2026 the FIS event pages describe a race more briefly ('Individual Compact Large
  Hill/7.5 km', no 'HS142'), so file names of new downloads carry no hill size. The hill
  size is read from the jump lists; a competition without one takes it from the other
  competitions on the same hill at the same event (`fill_hill_sizes` in the loader).

- Jump lists (RL, RL1, RLQ, PCR) are read by `fis_parser/extractors/jump_lines.py`, which
  anchors every jump on the judges' marks, and checked like the result lists (style points =
  middle marks, total = its parts, ranks); 1,291 of 1,295 pass. The four that do not are no
  jump lists (two early mass start overviews, two 2012 penalty race lists with doubled glyphs).
- **Training and trial round lists (RLT, RLTR) are mostly not loaded.** Their parsers predate the
  rewrite; up to three rounds side by side and two athletes per line (trial rounds) need a
  parser that works on word positions. Only the lists that pass validation are loaded
  (133 of 445 RLT, 36 of 599 RLTR).
- Cross-country lists of mass starts (RLLL) are not validated.
- 6 result lists fail validation and are not loaded; none is a regular World Cup /
  Continental Cup list:
  WC 2014/15 codex 4186–4189 (children's event, ranks per age class) and
  WC 2023/24 codex 4130–4131 (Junior World Championships team sprint).
- The Lillehammer lists by K-Jump print 'Firstname Surname'. The loader matches them to
  known athletes by their words; for an athlete seen nowhere else it takes the last word
  as the surname (listed in the loader's report — correct them in `db/aliases/athletes.csv`).
- Team results are shown on the competition page; an athlete's page lists individual results only.
