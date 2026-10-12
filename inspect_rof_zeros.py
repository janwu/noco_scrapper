"""Inspect sample zero-result ROF files from different years."""
from fis_parser.parser import parse_pdf
import glob, os, pdfplumber

# Get one zero-result file from each era bucket
samples = {
    '2009': None, '2012': None, '2015': None, '2018': None, '2022': None,
}

files = sorted(
    glob.glob('fis_nk_pdfs/**/*ROF.pdf', recursive=True) +
    glob.glob('fis_nk_coc_pdfs/**/*ROF.pdf', recursive=True)
)

import re
def year_from_path(f):
    parts = f.replace('\\', '/').split('/')
    return next((p for p in parts if re.match(r'^20\d{2}$', p)), '?')

for f in files:
    y = year_from_path(f)
    if y in samples and samples[y] is None:
        doc = parse_pdf(f)
        cr = getattr(doc, 'combined_results', [])
        if len(cr) == 0:
            samples[y] = f

for year, f in sorted(samples.items()):
    if f is None:
        print(f'\n=== {year}: no zero sample found ===')
        continue
    print(f'\n=== {year}: {os.path.basename(f)[:60]} ===')
    doc = parse_pdf(f)
    print(f'  era={doc.format_era} combined_results={len(getattr(doc,"combined_results",[]))} errors={doc.parse_errors[:1]}')
    with pdfplumber.open(f) as pdf:
        txt = pdf.pages[0].extract_text() or ''
        print('  ' + txt[:600].replace('\n', ' | '))
