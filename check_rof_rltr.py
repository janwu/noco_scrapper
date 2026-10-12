"""Check zero-data by year for ROF and RLTR using correct fields."""
from fis_parser.parser import parse_pdf
import glob, os, re

def year_from_path(f):
    parts = f.replace('\\', '/').split('/')
    return next((p for p in parts if re.match(r'^20\d{2}$', p)), '?')

# ROF: data goes to combined_results
print('=== ROF (checking combined_results) ===')
files = sorted(
    glob.glob('fis_nk_pdfs/**/*ROF.pdf', recursive=True) +
    glob.glob('fis_nk_pdfs/**/*ROFM.pdf', recursive=True) +
    glob.glob('fis_nk_coc_pdfs/**/*ROF.pdf', recursive=True)
)
zero_by_year = {}
total_by_year = {}
sample_zeros = []
for f in files:
    year = year_from_path(f)
    total_by_year[year] = total_by_year.get(year, 0) + 1
    doc = parse_pdf(f)
    cr = getattr(doc, 'combined_results', [])
    if len(cr) == 0:
        zero_by_year[year] = zero_by_year.get(year, 0) + 1
        if len(sample_zeros) < 3:
            sample_zeros.append(os.path.basename(f))

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
print('Sample zero files:', sample_zeros[:3])

# RLTR: data goes to jump_rounds; sample some zero files
print('\n=== RLTR zero sample (first 5) ===')
files2 = sorted(
    glob.glob('fis_nk_pdfs/**/*RLTR.pdf', recursive=True) +
    glob.glob('fis_nk_coc_pdfs/**/*RLTR.pdf', recursive=True)
)
zero_samples = []
for f in files2:
    doc = parse_pdf(f)
    if len(doc.jump_rounds) == 0 and len(zero_samples) < 5:
        zero_samples.append(f)

for f in zero_samples:
    import pdfplumber
    print(f'\n  {os.path.basename(f)[:65]}')
    with pdfplumber.open(f) as pdf:
        print('  ' + (pdf.pages[0].extract_text() or '')[:400].replace('\n', ' | '))
