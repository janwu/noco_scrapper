# FIS Nordic Combined results

Scrapes the result PDFs of the Nordic Combined World Cup and Continental Cup
from fis-ski.com, parses them and builds a database for the web app.

```
fis_nk_scraper.py / fis_nk_coc_scraper.py     PDFs      → fis_nk_pdfs/, fis_nk_coc_pdfs/
   (both run fis_nk_pdf_scraper.py)
run_parser.py            (fis_parser/)        PDFs      → output/**/*.json
db/load_json.py          (db/aliases/*.csv)   JSON      → db/noco.db
webapp/                                       db/noco.db → Vaadin site

fis_nk_wcb_scraper.py                         weltcup-b.org + FIS → fis_nk_wcb_pdfs/
   (World Cup B 2000/01–2007/08, the Continental Cup before it was renamed)
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
python db/suggest_display_names.py                     # display names for new athletes; check them
python db/load_json.py --sqlite db/noco.db
```

Without `--seasons` the scrapers go through all seasons up to the current one;
files already on disk are recognised by their FIS name (e.g. `2026NK4117ROF.pdf`)
and not downloaded again. How the FIS pages are read is described at the top of
`fis_nk_pdf_scraper.py`.

## World Cup B (2000/01 – 2007/08)

The second league was called World Cup B until 2008/09, when it became the
Continental Cup. FIS has PDFs of only part of it (from 2004/05); the former
coordinator of the series keeps all results at www.weltcup-b.org. Both go to
`fis_nk_wcb_pdfs/`, in the layout of the other circuits:

```
python fis_nk_pdf_scraper.py --circuit WCB --from-season 2001 --to-season 2008   # FIS PDFs
python fis_nk_wcb_scraper.py           # weltcup-b.org PDFs → fis_nk_wcb_pdfs/_raw/
python fis_nk_wcb_scraper.py --fis-results   # rankings of the FIS database → <codex>…FDB.json
python fis_nk_wcb_scraper.py --file    # codex and date from the FIS database → fis_nk_wcb_pdfs/<season>/
python run_parser.py --workers 7 --errors-only
python db/load_json.py --sqlite db/noco.db
```

The site names its files by venue and number ('Karpacz1.pdf', '_SP' / '_Sprung',
'_Lauf', '_Training'); `fis_nk_wcb_files.py` gives each the codex of its
competition (see there how) and skips lists FIS has itself. The lists of
weltcup-b.org come from the organisers and have many different layouts, so
`fis_nk_wcb_fisdb.py` also saves the ranking of each individual race from the
FIS database (doc type FDB: rank, name, nation, gap; no jump or cross-country).
`run_parser.py` copies these JSON files to `output/`.

In the database World Cup B is the Continental Cup (circuit `COC`, seasons
2000/01 – 2007/08); the web app calls those seasons "World Cup B". `load_json.py`
takes the result of a competition from its PDF and only where that could not be
read from the FDB ranking (it reports how often, and where both disagree). The
other lists of the competition (jump, cross-country, team) take the FIS spelling
of the names from the ranking (`fis_spelling`), and athletes the FIS database
now gives as 'AIN' get the nation printed in the lists of those years. Team
competitions have no FDB ranking; where the organiser's list is not read, they
have no result.

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
| Name to show with native letters (Bjørnstad, Otepää) | `db/aliases/athlete_display_names.csv`, `venue_display_names.csv` |

Alias files have four columns: the name and nation as printed, then the
name and nation to use instead. Lines starting with `#` are comments.

The database keeps every name as FIS writes it ('BJOERNSTAD Espen', 'Otepaeae'); the
display-name files (three columns: name and nation as stored, name to show) only change
what the web app shows, and its search finds both spellings. `python
db/suggest_display_names.py` appends suggestions for athletes without a line, by the rules of
their nation (NOR ø/æ/å, GER/AUT/SUI ä/ö/ü, FIN/EST/SWE ä/ö); it never changes a line that is
there, so corrections by hand stay. Names with other accents (Czech, Slovenian, Polish) have
no rule and are added by hand.

`load_json.py` warns about athletes that may be one person (same name words in
the same nation, or the same name in two nations). An athlete who changed nation
is aliased to the last one; every result keeps the nation it was printed with,
and the web app shows that one.

## Known gaps

- Since 2026 the FIS event pages describe a race more briefly ('Individual Compact Large
  Hill/7.5 km', no 'HS142'), so file names of new downloads carry no hill size. The hill
  size is read from the jump lists; a competition without one takes it from the other
  competitions on the same hill at the same event (`fill_hill_sizes` in the loader).

- Jump lists (RL, RL1, RLQ, PCR) are read by `fis_parser/extractors/jump_lines.py`, which
  anchors every jump on the judges' marks, and checked like the result lists (style points =
  middle marks, total = its parts, ranks); 1,291 of 1,295 pass. The four that do not are no
  jump lists (two early mass start overviews, two 2012 penalty race lists with doubled glyphs).
- Training and trial round lists (RLT, RLTR) are read by word position
  (`fis_parser/extractors/training_words.py`): up to three rounds side by side, two athletes
  per line in trial rounds; 1,042 of 1,044 pass validation. Their rows link only to athletes of
  the result and competition jump lists, so someone who only trained is not added as an athlete.
  The web app reads all jumps through the view `v_all_jumps`.
- Cross-country lists of mass starts (RLLL) are validated (ranks, athletes, times that grow with
  the rank, gaps); 27 of 64 pass (all World Cup lists since 2021/22), the older layouts are
  read wrongly. The web app shows the race of a mass start from the official result list,
  which has race time and race rank of every athlete, and from the cross-country list where
  the result list has none (Ruka 2025: jumping cancelled, race held). FIS may rank a slower time first after a photo finish
  (COC 2018–2021); the result lists print it so.
- 6 result lists fail validation and are not loaded; none is a regular World Cup /
  Continental Cup list:
  WC 2014/15 codex 4186–4189 (children's event, ranks per age class) and
  WC 2023/24 codex 4130–4131 (Junior World Championships team sprint).
- The Lillehammer lists by K-Jump print 'Firstname Surname'. The loader matches them to
  known athletes by their words; for an athlete seen nowhere else it takes the last word
  as the surname (listed in the loader's report — correct them in `db/aliases/athletes.csv`).
- Team results are shown on the competition page; an athlete's page lists individual results only.
