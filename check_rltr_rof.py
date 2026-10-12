"""Check zero-data distribution by year for RLTR and ROF."""
from fis_parser.parser import parse_pdf
import glob, os, re

def year_from_path(f):
    parts = f.replace('\\', '/').split('/')
    return next((p for p in parts if re.match(r'^20\d{2}$', p)), '?')

for pattern_suffix, label in [('*RLTR.pdf', 'RLTR'), ('*ROF.pdf', 'ROF'), ('*ROFM.pdf', 'ROFM')]:
    files = sorted(
        glob.glob(f'fis_nk_pdfs/**/{pattern_suffix}', recursive=True) +
        glob.glob(f'fis_nk_coc_pdfs/**/{pattern_suffix}', recursive=True)
    )
    if not files:
        continue
    zero_by_year = {}
    total_by_year = {}
    for f in files:
        year = year_from_path(f)
        total_by_year[year] = total_by_year.get(year, 0) + 1
        doc = parse_pdf(f)
        if len(doc.jump_rounds) == 0 and len(getattr(doc, 'xc_results', [])) == 0:
            zero_by_year[year] = zero_by_year.get(year, 0) + 1

    print(f'\n=== {label} ===')
    print(f'{"Year":6s}  {"Total":>6}  {"Zero":>6}  {"Pct":>6}')
    for y in sorted(total_by_year):
        t = total_by_year[y]
        z = zero_by_year.get(y, 0)
        pct = z * 100 // t if t else 0
        flag = ' <--' if z > 0 else ''
        print(f'  {y}  {t:6d}  {z:6d}  {pct:5d}%{flag}')
    total = sum(total_by_year.values())
    zero = sum(zero_by_year.values())
    print(f'  TOTAL: {total} files, {zero} zero ({zero*100//total if total else 0}%)')
