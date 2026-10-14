#!/usr/bin/env python3
"""
FIS Nordic Combined World Cup - result PDFs into fis_nk_pdfs/.

    python fis_nk_scraper.py --seasons 2027
    python fis_nk_scraper.py --from-season 2018 --dry-run

The scraping itself is in fis_nk_pdf_scraper.py (shared with the Continental Cup).
"""
from fis_nk_pdf_scraper import main

if __name__ == "__main__":
    main(circuit="WC")
