from fis_parser.parser import parse_pdf
import glob

patterns = ['*4148*RLLL*', '*4144*RLLL*', '*4139*RLLL*', '*4142*RLLL*', '*4176*2025*RLLL*', '*4182*RLLL*']
for p in patterns:
    matches = glob.glob('fis_nk_pdfs/**/' + p, recursive=True)
    if not matches:
        continue
    f = matches[0]
    doc = parse_pdf(f)
    n = len(doc.xc_results)
    first = doc.xc_results[0] if n else None
    print(f"{f.split('/')[-1][:55]:56s}  results={n:3d}  errors={len(doc.parse_errors)}")
    if first:
        print(f"  rank={first.rank} bib={first.bib} name={first.name} nation={first.nation} time={first.total_time}")
    if doc.parse_errors:
        for e in doc.parse_errors:
            print(f"  ERR: {e}")
