"""
Central dispatch: detect document type and call the appropriate extractor.
"""
from pathlib import Path

from fis_parser.detector import detect_doc_type_from_filename
from fis_parser.models import ParsedDocument


def parse_pdf(filepath: str) -> ParsedDocument:
    """
    Parse a FIS Nordic Combined result PDF and return a ParsedDocument.

    Document type is inferred from the filename.  If detection fails the
    file is attempted with the ROF extractor as a last resort.
    """
    doc_type = detect_doc_type_from_filename(filepath)

    if doc_type == 'ROF':
        from fis_parser.extractors.rof import ROFExtractor
        return ROFExtractor(filepath).parse()

    if doc_type in ('RL', 'RL1', 'PCR'):
        from fis_parser.extractors.rl import RLExtractor
        return RLExtractor(filepath).parse(doc_type=doc_type)

    if doc_type == 'RLLL':
        from fis_parser.extractors.rlll import RLLLExtractor
        return RLLLExtractor(filepath).parse()

    if doc_type == 'RLT':
        from fis_parser.extractors.rlt import RLTExtractor
        return RLTExtractor(filepath).parse()

    if doc_type == 'RLTR':
        from fis_parser.extractors.rltr import RLTRExtractor
        return RLTRExtractor(filepath).parse()

    # Unknown / fallback — try ROF and record the ambiguity
    from fis_parser.extractors.rof import ROFExtractor
    doc = ROFExtractor(filepath).parse()
    doc.parse_errors.insert(0, f"Unknown doc_type '{doc_type}'; fell back to ROF extractor")
    return doc
