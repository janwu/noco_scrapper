"""
run_parser.py — batch parse all FIS Nordic Combined PDFs.

Usage:
    python run_parser.py [options]

Options:
    --input-dirs DIR [DIR ...]   Directories to scan (default: fis_nk_pdfs fis_nk_coc_pdfs)
    --output-dir DIR             Output directory for JSON files (default: output)
    --workers N                  Parallel worker processes (default: 4)
    --overwrite                  Re-parse files even if JSON already exists
    --doc-type TYPE              Only parse files of this type (ROF, RL, RLT, RLLL, RLTR, PCR)
    --limit N                    Stop after N files (useful for testing)
    --errors-only                Print only files that produced parse errors
    --log-file FILE              Write log to file in addition to stdout
"""

import argparse
import dataclasses
import json
import logging
import multiprocessing
import os
import re
import shutil
import sys
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(log_file: Optional[str] = None) -> logging.Logger:
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-8s %(message)s',
        datefmt='%H:%M:%S',
        handlers=handlers,
    )
    return logging.getLogger('run_parser')


# ---------------------------------------------------------------------------
# JSON serialisation
# ---------------------------------------------------------------------------

def _to_serialisable(obj):
    """Recursively convert dataclasses / nested structures to dicts."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_serialisable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_serialisable(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_serialisable(v) for k, v in obj.items()}
    return obj


def _message_kind(message: str) -> str:
    """'ranked rows: parsed 50, PDF statistics say 49' → 'ranked rows: parsed N, PDF statistics say N'."""
    kind = re.sub(r"'[^']*'|\"[^\"]*\"", '…', message.splitlines()[0])
    return re.sub(r'\d+', 'N', kind)[:100]


def save_json(doc, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = _to_serialisable(doc)
    with open(output_path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Worker function (runs in subprocess)
# ---------------------------------------------------------------------------

def _parse_one(args: Tuple[str, str, bool]) -> dict:
    """
    Parse a single PDF.  Returns a result dict with keys:
        pdf, json_out, doc_type, errors, skipped, elapsed_ms
    """
    pdf_path, json_out, overwrite = args

    result = {
        'pdf': pdf_path,
        'json_out': json_out,
        'doc_type': None,
        'errors': [],
        'warnings': [],
        'skipped': False,
        'elapsed_ms': 0,
    }

    if not overwrite and Path(json_out).exists():
        result['skipped'] = True
        return result

    t0 = datetime.now()
    try:
        from fis_parser.parser import parse_pdf
        doc = parse_pdf(pdf_path)
        result['doc_type'] = doc.doc_type
        result['errors'] = doc.parse_errors
        result['warnings'] = doc.warnings
        save_json(doc, Path(json_out))
    except Exception as exc:
        result['errors'] = [f"FATAL: {exc}", traceback.format_exc()]

    result['elapsed_ms'] = int((datetime.now() - t0).total_seconds() * 1000)
    return result


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_pdfs(directories: List[str], doc_type_filter: Optional[str] = None) -> List[Path]:
    pdfs = []
    for d in directories:
        base = Path(d)
        if not base.exists():
            continue
        for pdf in sorted(base.rglob('*.pdf')):
            if '_raw' in pdf.parts:
                continue                    # downloads not yet filed (fis_nk_wcb_pdfs/_raw)
            if doc_type_filter:
                from fis_parser.detector import detect_doc_type_from_filename
                if detect_doc_type_from_filename(str(pdf)) != doc_type_filter:
                    continue
            pdfs.append(pdf)
    return pdfs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_json_path(pdf: Path, input_dirs: List[str], output_dir: Path) -> Path:
    """
    Mirror the directory structure under output_dir.
    e.g. fis_nk_pdfs/2023/NC2301_ROF.pdf  →  output/fis_nk_pdfs/2023/NC2301_ROF.json
    """
    for d in input_dirs:
        try:
            rel = pdf.relative_to(d)
            return output_dir / d / rel.with_suffix('.json')
        except ValueError:
            continue
    # Fallback: flat output
    return output_dir / pdf.with_suffix('.json').name


def main() -> int:
    parser = argparse.ArgumentParser(description='Batch parse FIS Nordic Combined PDFs')
    parser.add_argument('--input-dirs', nargs='+',
                        default=['fis_nk_pdfs', 'fis_nk_coc_pdfs', 'fis_nk_wcb_pdfs'],
                        help='Directories containing PDFs')
    parser.add_argument('--output-dir', default='output',
                        help='Output directory for JSON files')
    parser.add_argument('--workers', type=int, default=4,
                        help='Parallel worker processes')
    parser.add_argument('--overwrite', action='store_true',
                        help='Re-parse files even if JSON exists')
    parser.add_argument('--doc-type',
                        choices=['ROF', 'RL', 'RL1', 'RLT', 'RLLL', 'RLTR', 'PCR'],
                        help='Only parse files of this type')
    parser.add_argument('--limit', type=int, default=0,
                        help='Stop after N files (0 = no limit)')
    parser.add_argument('--errors-only', action='store_true',
                        help='Print only files that produced parse errors')
    parser.add_argument('--log-file', default=None,
                        help='Also write log to this file')
    args = parser.parse_args()

    log = setup_logging(args.log_file)
    output_dir = Path(args.output_dir)

    # Discover PDFs
    pdfs = find_pdfs(args.input_dirs, args.doc_type)
    if not pdfs:
        log.error("No PDFs found in: %s", args.input_dirs)
        return 1

    if args.limit:
        pdfs = pdfs[:args.limit]

    log.info("Found %d PDFs to process", len(pdfs))

    # Build work list
    work = []
    for pdf in pdfs:
        json_out = str(build_json_path(pdf, args.input_dirs, output_dir))
        work.append((str(pdf), json_out, args.overwrite))

    # Rankings from the FIS database (fis_nk_fisdb.py) go to output/ as they are
    copied = 0
    for d in args.input_dirs:
        base = Path(d)
        for src in sorted(base.rglob('*FDB.json')) if base.exists() else []:
            if '_raw' in src.parts:
                continue
            dest = build_json_path(src, args.input_dirs, output_dir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            copied += 1
    if copied:
        log.info("Copied %d rankings from the FIS database", copied)

    # Process
    total = len(work)
    done = 0
    errors = 0
    skipped = 0

    workers = min(args.workers, total)
    if workers <= 1:
        results = [_parse_one(item) for item in work]
    else:
        with multiprocessing.Pool(processes=workers) as pool:
            results = pool.map(_parse_one, work)

    for r in results:
        done += 1
        if r['skipped']:
            skipped += 1
            if not args.errors_only:
                log.debug("SKIP  %s", r['pdf'])
            continue

        if r['errors']:
            errors += 1
            log.warning("ERROR [%s] %s  (%dms)  errors=%s",
                        r.get('doc_type', '?'),
                        Path(r['pdf']).name,
                        r['elapsed_ms'],
                        r['errors'])
        else:
            if not args.errors_only:
                log.info("OK    [%s] %s  (%dms)",
                         r.get('doc_type', '?'),
                         Path(r['pdf']).name,
                         r['elapsed_ms'])

    log.info("─" * 60)
    log.info("Processed %d files: %d OK, %d errors, %d skipped",
             total, total - errors - skipped, errors, skipped)

    # Which checks failed how often (one count per file, numbers and names blanked)
    for label, key in (("Errors", 'errors'), ("Warnings", 'warnings')):
        kinds = Counter()
        for r in results:
            kinds.update({_message_kind(m) for m in r[key]})
        if kinds:
            log.info("%s by kind (files):", label)
            for kind, n in kinds.most_common():
                log.info("  %5d  %s", n, kind)

    return 0 if errors == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
