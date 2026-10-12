"""Inspect failing RLTR files - show word coordinates."""
from fis_parser.parser import parse_pdf
import glob, pdfplumber, os, re

def year_from_path(f):
    parts = f.replace('\\', '/').split('/')
    return next((p for p in parts if re.match(r'^20\d{2}$', p)), '?')

files = sorted(
    glob.glob('fis_nk_pdfs/**/*RLTR.pdf', recursive=True) +
    glob.glob('fis_nk_coc_pdfs/**/*RLTR.pdf', recursive=True)
)

# Get zero files from years 2012 and 2019
zero_12 = zero_19 = None
for f in files:
    y = year_from_path(f)
    doc = parse_pdf(f)
    if len(doc.jump_rounds) == 0:
        if y == '2012' and zero_12 is None:
            zero_12 = f
        if y == '2019' and zero_19 is None:
            zero_19 = f
    if zero_12 and zero_19:
        break

for label, f in [('2012', zero_12), ('2019', zero_19)]:
    if not f:
        continue
    print(f'\n=== {label}: {os.path.basename(f)[:65]} ===')
    doc = parse_pdf(f)
    print(f'  jump_rounds={len(doc.jump_rounds)} era={doc.format_era}')
    with pdfplumber.open(f) as pdf:
        words = pdf.pages[0].extract_words()
        # Show first 50 words with position
        print('  First 30 words:')
        for w in words[:30]:
            print(f'    x0={w["x0"]:6.1f}  x1={w["x1"]:5.1f}  top={w["top"]:6.1f}  text={w["text"]!r}')
        # Show full text
        print('  Page text (first 1000 chars):')
        txt = pdf.pages[0].extract_text() or ''
        print('  ' + txt[:1000].replace('\n', ' | '))
