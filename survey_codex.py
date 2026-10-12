import glob, re, collections, os

codex_files = collections.defaultdict(list)
for f in glob.glob('output/**/*.json', recursive=True):
    fname = os.path.basename(f)
    m = re.match(r'(\d+)_', fname)
    if m:
        codex_files[m.group(1)].append(fname)

print('Unique codex values in filenames:', len(codex_files))
print('Files per codex stats:')
counts = collections.Counter(len(v) for v in codex_files.values())
for k in sorted(counts):
    print(f'  {k} files: {counts[k]} competitions')

big = max(codex_files, key=lambda k: len(codex_files[k]))
print(f'\nBiggest codex {big}: {len(codex_files[big])} files')
for fname in sorted(codex_files[big]):
    print('  ', fname[:70])
