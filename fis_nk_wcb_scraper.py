#!/usr/bin/env python3
"""
FIS World Cup B (Nordic Combined, 2000/01 - 2007/08) - result PDFs from weltcup-b.org
====================================================================================
The World Cup B was the second league before it was renamed Continental Cup in
2008/09.  FIS has no PDFs of it; the former coordinator of the series keeps them
at www.weltcup-b.org, under Weltcup-B/<season>/Ergebnisse (results, jump and
cross-country lists, training) and Weltcup-B/<season>/Gesamt (standings).

Step 1, download:  every PDF of those folders into fis_nk_wcb_pdfs/_raw/<season>/,
                   named as on the site.
Step 2, file:      python fis_nk_wcb_scraper.py --file
                   reads codex, date, venue and discipline from each result PDF and
                   copies it to the layout of the other circuits:
                   fis_nk_wcb_pdfs/2005/20041218_20041219_LAKE_PLACID_USA/M/
                       4170_20041218_Gundersen_K90_15.0_Km_WCB_M_M_2005NK4170ROF.pdf

    python fis_nk_wcb_scraper.py                  # download (skips what is there)
    python fis_nk_wcb_scraper.py --file           # file the downloaded PDFs
    python fis_nk_wcb_scraper.py --fis-results    # the ranking of each competition from the FIS database
    python fis_nk_wcb_scraper.py --dry-run        # list what would be downloaded
"""
import argparse
import io
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

BASE = "https://www.weltcup-b.org/"
# the pages listing the results and standings of every season
INDEX_PAGES = ["WeltcupA/WC96_01.htm", "WeltcupA/WC01_09.htm"] + [
    f"Weltcup-B/20{a:02d}_{a + 1:02d}/wc-ergebnisse-content{a:02d}_{a + 1:02d}.htm" for a in range(0, 8)]
SEASONS = [f"{a:04d}_{(a + 1) % 100:02d}" for a in range(2000, 2008)]          # 2000_01 .. 2007_08
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FIS-NK-Scraper/3.0)"}
OUTPUT = Path("fis_nk_wcb_pdfs")
DELAY = 1.0


def pdf_links(session: requests.Session) -> list:
    """All PDFs under Weltcup-B/<season>/Ergebnisse and /Gesamt linked from the index pages."""
    found = {}
    for page in INDEX_PAGES:
        url = urljoin(BASE, page)
        try:
            r = session.get(url, headers=HEADERS, timeout=30)
        except requests.RequestException as e:
            print(f"  FAIL {url}: {e}")
            continue
        time.sleep(DELAY)
        if r.status_code != 200:
            continue
        soup = BeautifulSoup(r.content.decode("latin-1", "replace"), "html.parser")
        for a in soup.find_all("a", href=True):
            target = urljoin(url, a["href"])
            path = unquote(urlparse(target).path)
            m = re.search(r"/Weltcup-B/(\d{4}_\d{2})/(Ergebnisse|Gesamt)/[^/]+\.pdf$", path, re.I)
            if m and m.group(1) in SEASONS:
                found[target] = (m.group(1), m.group(2))
    return sorted((u, s, kind) for u, (s, kind) in found.items())


def download(dry_run: bool) -> None:
    session = requests.Session()
    links = pdf_links(session)
    print(f"{len(links)} PDFs linked for {SEASONS[0]} - {SEASONS[-1]}")
    counts = {"downloaded": 0, "existed": 0, "failed": 0}
    for url, season, kind in links:
        dest = OUTPUT / "_raw" / season / kind / unquote(url.rsplit("/", 1)[-1])
        if dest.exists():
            counts["existed"] += 1
            continue
        if dry_run:
            print("  would download", dest)
            continue
        try:
            r = session.get(url, headers=HEADERS, timeout=60)
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                raise ValueError("not a PDF")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            counts["downloaded"] += 1
        except (requests.RequestException, ValueError) as e:
            print(f"  FAIL {url}: {e}")
            counts["failed"] += 1
        time.sleep(DELAY)
    print(counts)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--file", action="store_true", help="file the downloaded PDFs (step 2)")
    parser.add_argument("--fis-results", action="store_true",
                        help="store the ranking of every competition from the FIS database (step 3)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.fis_results:
        from fis_nk_wcb_fisdb import fetch_all
        fetch_all(OUTPUT)
    elif args.file:
        from fis_nk_wcb_files import file_all
        file_all(OUTPUT, dry_run=args.dry_run)
    else:
        download(args.dry_run)


if __name__ == "__main__":
    main()
