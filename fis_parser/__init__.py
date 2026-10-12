"""
FIS Nordic Combined PDF Parser.

Usage:
    from fis_parser import parse_pdf
    doc = parse_pdf("path/to/results.pdf")
"""
from fis_parser.parser import parse_pdf

__all__ = ['parse_pdf']
