import pdfplumber, glob, os

patterns = ['*4148*RLLL*', '*4144*RLLL*', '*4139*RLLL*', '*4142*RLLL*', '*4176*2025*RLLL*', '*4182*RLLL*']
for p in patterns:
    matches = glob.glob('fis_nk_pdfs/**/' + p, recursive=True)
    if matches:
        f = matches[0]
        print('=== ' + os.path.basename(f)[:70] + ' ===')
        with pdfplumber.open(f) as pdf:
            print(pdf.pages[0].extract_text()[:2000])
        print()
