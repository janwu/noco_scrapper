"""Find which JSON files produce garbage athlete names."""
import glob, json, os, re, collections

suspect = re.compile(r'\d{2}:\d{2}|\d+\.\d+\s*$|^\s*\d+\s+\w|\s+\d{2}\s+\d+\s+\d+')

era_counts = collections.Counter()
era_files  = collections.defaultdict(list)

for f in sorted(glob.glob('output/**/*.json', recursive=True)):
    with open(f) as fh:
        d = json.load(fh)
    era  = d.get('format_era', '?')
    dt   = d.get('doc_type', '?')
    bad  = []
    for r in d.get('combined_results', []) + d.get('jump_rounds', []):
        name = r.get('name', '') or ''
        if suspect.search(name) or len(name) > 45 or (name and name[0].isdigit()):
            bad.append(name)
    if bad:
        key = f'{dt}-era{era}'
        era_counts[key] += len(bad)
        era_files[key].append((os.path.basename(f), bad[:2]))

print('Garbage rows by doc_type+era:')
for k, n in sorted(era_counts.items(), key=lambda x: -x[1]):
    print(f'  {k:<20} {n:>5} bad rows,  {len(era_files[k])} files')
    for fname, samples in era_files[k][:2]:
        print(f'      {fname[:60]}')
        for s in samples:
            print(f'        > {repr(s[:80])}')
