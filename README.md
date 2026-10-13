# FIS Nordic Combined results

Scrapes the result PDFs of the Nordic Combined World Cup and Continental Cup
from fis-ski.com, parses them and builds a database for the web app.

```
fis_nk_scraper.py / fis_nk_coc_scraper.py     PDFs      → fis_nk_pdfs/, fis_nk_coc_pdfs/
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

- Only the official result lists (ROF) are validated. Jump, training, trial and
  cross-country lists are loaded with a row-level check (valid name, known nation).
- 6 result lists fail validation and are not loaded; none is a regular World Cup /
  Continental Cup list:
  WC 2014/15 codex 4186–4189 (children's event, ranks per age class) and
  WC 2023/24 codex 4130–4131 (Junior World Championships team sprint).
- The Lillehammer lists by K-Jump print 'Firstname Surname'. The loader matches them to
  known athletes by their words; for an athlete seen nowhere else it takes the last word
  as the surname (listed in the loader's report — correct them in `db/aliases/athletes.csv`).
- Team results are shown on the competition page; an athlete's page lists individual results only.
