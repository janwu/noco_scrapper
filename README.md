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
fis_nk_fisdb.py --circuit WC / WSC            FIS database → FDB rankings (World Cup 1983/84–2000/01,
                                              which has no PDFs; World Championships 1924–2025)
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

## World Cup 1983/84 – 2000/01

FIS has result PDFs of the World Cup from 2001/02. For the seasons before, the
FIS database has the ranking of each individual race; until 1998/99 mostly the
first 15 only, the ones that scored World Cup points:

```
python fis_nk_fisdb.py --circuit WC                       # rankings → fis_nk_pdfs/<season>/…FDB.json
python fis_nk_standings_scraper.py --from-season 1984 --to-season 2001
python run_parser.py --workers 7 --errors-only            # copies the rankings to output/
python db/load_json.py --sqlite db/noco.db
```

Races of those years have no codex; their race id in the FIS database stands in
for it. The ranking has rank, name, year of birth, nation and, depending on the
year, the gap to the winner or the World Cup points of the race. The points stay
in the JSON: the points rules changed several times (25-20-15… in the 1980s,
from 1993/94 hundreds of points, today 100-90-80…), so the database has the
official final standings of FIS only and never adds up points itself. Team
competitions are not in these rankings, and seven races of 1999/2000 and
2000/01 have no ranking in the FIS database.

Athletes appear under nations that split or united: GDR and FRG, later GER;
TCH, later CZE and SVK; SOV, CIS/GUS, later RUS, EST and others; YUG. `load_json.py`
takes the same name within one such lineage as one athlete, of the last nation
(`NATION_LINEAGE`, `nation_changes`); every result keeps the nation it was printed
with. Venues are aliased to their country of today (Schonach BRD → GER).

## World Championships (1924 – 2025)

The Nordic combined of every World Championships, and of the Olympic Winter Games
until 1980, which counted as World Championships (1924, 1928, … 1980; from 1982
they are held apart). FIS lists all of them in its World Championship calendar
(category WSC), whatever season is asked for; the scrapers keep the events of the
season asked for (`seasoncode` of the event link).

```
python fis_nk_pdf_scraper.py --circuit WSC --seasons 2003 2005 … 2025   # result PDFs, from 2003
python fis_nk_fisdb.py --circuit WSC                  # rankings of every race → fis_nk_wsc_pdfs/<year>/…FDB.json
python run_parser.py --workers 7 --errors-only
python db/load_json.py --sqlite db/noco.db
```

In the database the circuit is `WSC`; a World Championships is one season (1924 =
season 1923/24), the web app names it by its year and marks the Olympic years.
Until 1984 a competition was jump and cross-country in points (format
"Individual"); the early FIS database has the first six to fifteen only. Team
competitions come from the FIS database too (`team_ranking`: a team line, then its
athletes), also for the World Cup and World Cup B where no team PDF can be read.
Teams of two nations run as 'FIS' in the database; their athletes keep their own
nation.

## Olympic Winter Games (1924 – 2026)

Like the World Championships, from the FIS calendar of category OWG (PDFs from 2002):

```
python fis_nk_pdf_scraper.py --circuit OWG --seasons 2002 2006 … 2026
python fis_nk_fisdb.py --circuit OWG
```

Circuit `OWG` in the database. Until 1980 the Olympic competitions were the World
Championships as well; FIS lists them in both calendars and so does the database:
the same competition once as `OWG`, once as `WSC` (same codex: competitions are
keyed by circuit, codex and season), and the web app notes it on both. The venue
is the one of the Nordic combined (Torino → Pragelato, Beijing → Zhangjiakou, …);
Russians of 2018–2022 (OAR, ROC) count for Russia like AIN and RSF.

### Olympedia (Olympic Games 1924 – 1998)

FIS has no result PDF of the Games before 2002, and its database the first 6 to 15
only, often with initials ('HAUG Th'). Olympedia has the full result of every
Olympic competition — all athletes with jump points, cross-country time, DNS / DNF,
the teams with their athletes — and the full names and birth dates:

```
python fis_nk_olympedia.py                 # after fis_nk_fisdb.py --circuit OWG and WSC
python run_parser.py --workers 7 --errors-only
python db/load_json.py --sqlite db/noco.db
```

Each competition goes next to its FIS ranking as doc type OLY (until 1980 also into
`fis_nk_wsc_pdfs/`, the same competition being the World Championships). Olympedia
allows a slow client only (one page every three seconds; it answers 429 otherwise);
the athlete pages are cached in `fis_nk_owg_pdfs/_olympedia_athletes.json`.
`load_json.py` takes a competition's result from a result list that was read, else
from Olympedia, else from the FIS database; and a name with initials in the FIS
database of those years takes the full name of the one Olympian of that nation and
surname whose given names start with them (`olympedia_names`) — in every list.

## World Cup B of the 1990s (1990/91 – 1999/2000)

The FIS database has the World Cup B from 1990/91 — the podium of each competition
only, no PDFs. `fis_nk_fisdb.py --circuit WCB` stores these rankings with the later
ones. weltcup-b.org has the full lists of twelve competitions of 1996/97 –
1999/2000 (Klingenthal, Lake Placid, Zakopane, Reit im Winkl), from the organisers
in several layouts:

```
python fis_nk_fisdb.py --circuit WCB --seasons 1991 1992 … 2000
python fis_nk_wcb_1990s.py            # weltcup-b.org lists → …WBL.json next to the FIS ranking
python run_parser.py --workers 7 --errors-only
python db/load_json.py --sqlite db/noco.db
```

A list is matched to its FIS competition by place and date and checked against the
FIS podium (it is in its `warnings`). `load_json.py` takes it like an Olympedia
result (`FULL_LISTS`) and gives an athlete whose nation the organiser printed wrong
('CECON, Andrea JPN') the nation of the FIS lists. Two lists are not loaded: the
Zakopane PDF of 1997 is a picture, and the "Zusatzwettkampf" of Klingenthal on
13 March 1999 is no competition of the FIS calendar.

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
`fis_nk_fisdb.py` also saves the ranking of each individual race from the
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
