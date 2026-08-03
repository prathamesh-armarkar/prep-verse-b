"""PDF extraction with PyMuPDF as the primary parser and pdfplumber fallback."""


class DocumentParsingError(ValueError):
    """Includes the document type so the API can produce a precise error."""

    def __init__(self, document_type, detail):
        self.document_type = document_type
        self.detail = str(detail)
        super().__init__(self.detail)


def extract_pdf_text(file_path):
    primary_error = None
    try:
        import fitz
        with fitz.open(file_path) as document:
            text = "\n".join(page.get_text("text") for page in document)
        if text.strip():
            return text.strip()
        primary_error = "The PDF does not contain extractable text."
    except Exception as exc:
        primary_error = str(exc)
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as document:
            text = "\n".join(page.extract_text() or "" for page in document.pages)
        if text.strip():
            return text.strip()
    except Exception as exc:
        detail = f"PyMuPDF: {primary_error}; pdfplumber: {exc}"
        raise DocumentParsingError("PDF", detail) from exc
    raise DocumentParsingError("PDF", primary_error or "No extractable text was found in the PDF.")
