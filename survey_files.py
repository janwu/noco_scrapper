import glob, json, collections, re, os

gender_cnt = collections.Counter()
cat_cnt = collections.Counter()
codex_docs = collections.defaultdict(set)
season_cnt = collections.Counter()
discipline_cnt = collections.Counter()

for f in glob.glob('output/**/*.json', recursive=True):
    fname = os.path.basename(f)
    m_codex = re.match(r'(\d+)_', fname)
    codex = m_codex.group(1) if m_codex else None
    m_gender = re.search(r'_(M|W)_(M|W)_', fname)
    gender = m_gender.group(1) if m_gender else None
    m_cat = re.search(r'_(WC|COC)_', fname)
    cat = m_cat.group(1) if m_cat else None
    m_season = re.search(r'_(\d{4})NK', fname)
    season = m_season.group(1) if m_season else None
    m_dt = re.search(r'(ROF|RL1?|RLLL|RLT|RLTR|PCR)\.json$', fname)
    dt = m_dt.group(1) if m_dt else None

    # Extract discipline from filename path
    m_disc = re.search(r'_(Gundersen|Mass_Start|Individual|Team|Sprint|Super_Sprint)_', fname, re.IGNORECASE)
    disc = m_disc.group(1) if m_disc else 'Unknown'

    gender_cnt[gender] += 1
    cat_cnt[cat] += 1
    if codex:
        codex_docs[codex].add(dt)
    if season:
        season_cnt[season] += 1
    discipline_cnt[disc] += 1

print('Gender values:', dict(sorted(gender_cnt.items(), key=lambda x: str(x[0]))))
print('Category values:', dict(sorted(cat_cnt.items(), key=lambda x: str(x[0]))))
print('Unique codex values:', len(codex_docs))
print('Seasons:', sorted(season_cnt.keys()))
print('Disciplines:', dict(sorted(discipline_cnt.items())))

# Multi-doc codex examples
multi = [(k, v) for k, v in codex_docs.items() if len(v) >= 4][:5]
print('\nSample multi-doc codex:')
for k, v in multi:
    print(f'  codex {k}: {sorted(v)}')

# Distribution of docs per codex
dist = collections.Counter(len(v) for v in codex_docs.values())
print('\nDocs per codex distribution:', dict(sorted(dist.items())))
