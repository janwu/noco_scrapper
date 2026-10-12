"""Test ROF era detection fix on sample COC files."""
from fis_parser.parser import parse_pdf
import glob, os, re

def year_from_path(f):
    parts = f.replace('\\', '/').split('/')
    return next((p for p in parts if re.match(r'^20\d{2}$', p)), '?')

# Get one zero file per year
samples = {}
files = sorted(
    glob.glob('fis_nk_pdfs/**/*ROF.pdf', recursive=True) +
    glob.glob('fis_nk_coc_pdfs/**/*ROF.pdf', recursive=True)
)

# First pass: find zero files per year
zero_by_year = {}
for f in files:
    y = year_from_path(f)
    doc = parse_pdf(f)
    cr = getattr(doc, 'combined_results', [])
    n = len(cr)
    if n == 0 and y not in zero_by_year:
        zero_by_year[y] = (f, doc)

# Show before/after per year
print(f'{"Year":6s}  {"Era":5s}  {"Results":>8}  {"File":<55}')
print('-' * 80)
total_zero = 0
for y in sorted(zero_by_year):
    f, doc = zero_by_year[y]
    cr = getattr(doc, 'combined_results', [])
    print(f'  {y}  {doc.format_era:5s}  {len(cr):8d}  {os.path.basename(f)[:55]}')
    if len(cr) == 0:
        total_zero += 1

print(f'\nStill zero: {total_zero} / {len(zero_by_year)} sampled years')
