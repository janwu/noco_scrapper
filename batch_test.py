"""Full batch test across all PDF directories and document types."""
from fis_parser.parser import parse_pdf
import glob, os, sys
from collections import defaultdict

dirs = ['fis_nk_pdfs', 'fis_nk_coc_pdfs']
doc_types = ['ROF', 'RL', 'RLT', 'RLTR', 'RLLL', 'PCR']

total = 0
by_type = defaultdict(lambda: {'files': 0, 'errors': 0, 'zero': 0, 'error_files': []})

for d in dirs:
    files = sorted(glob.glob(f'{d}/**/*.pdf', recursive=True))
    for f in files:
        base = os.path.basename(f)
        doc_type = None
        for dt in doc_types:
            if base.upper().endswith(dt + '.PDF'):
                doc_type = dt
                break
        if doc_type is None:
            # Try to detect from filename suffix pattern
            for dt in doc_types:
                if dt in base.upper():
                    doc_type = dt
                    break
        if doc_type is None:
            doc_type = 'OTHER'

        total += 1
        key = f'{d.split("_")[1].upper()}_{doc_type}'
        by_type[key]['files'] += 1

        try:
            doc = parse_pdf(f)
            has_data = False
            if doc_type == 'RLLL':
                has_data = len(doc.xc_results) > 0
            else:
                has_data = len(doc.jump_rounds) > 0 or len(getattr(doc, 'combined_results', [])) > 0
            if doc.parse_errors:
                by_type[key]['errors'] += 1
                by_type[key]['error_files'].append((base, doc.parse_errors[0]))
            if not has_data:
                by_type[key]['zero'] += 1
        except Exception as e:
            by_type[key]['errors'] += 1
            by_type[key]['error_files'].append((base, str(e)))

print(f"\n{'Type':<20} {'Files':>6} {'Errors':>7} {'ZeroData':>9}")
print('-' * 46)
grand_files = grand_errors = grand_zero = 0
for key in sorted(by_type):
    s = by_type[key]
    print(f"{key:<20} {s['files']:>6} {s['errors']:>7} {s['zero']:>9}")
    grand_files += s['files']
    grand_errors += s['errors']
    grand_zero += s['zero']
print('-' * 46)
print(f"{'TOTAL':<20} {grand_files:>6} {grand_errors:>7} {grand_zero:>9}")

# Show first few error files per type
print()
for key in sorted(by_type):
    ef = by_type[key]['error_files']
    if ef:
        print(f"\n--- {key} errors (first 5) ---")
        for fname, err in ef[:5]:
            print(f"  {fname[:60]}: {str(err)[:80]}")
