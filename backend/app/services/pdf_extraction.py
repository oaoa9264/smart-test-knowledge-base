import io
import os
from typing import Any, Dict, List, Sequence

try:
    import pypdfium2 as pdfium
except ModuleNotFoundError:
    pdfium = None

try:
    from pypdf import PdfReader
except ModuleNotFoundError:
    PdfReader = None


MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 50


def validate_pdf_file(file: Any) -> Dict[str, Any]:
    if PdfReader is None:
        raise RuntimeError("pypdf is required for PDF validation")
    filename = str(getattr(file, "filename", "") or "").strip()
    if not filename.lower().endswith(".pdf"):
        raise ValueError("only .pdf files are supported")

    data = file.file.read()
    file.file.seek(0)

    if len(data) > MAX_PDF_SIZE_BYTES:
        raise ValueError("pdf file size must be <= 20MB")
    if not data.startswith(b"%PDF-"):
        raise ValueError("invalid pdf file")

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ValueError("invalid pdf file") from exc

    page_count = len(reader.pages)
    if page_count > MAX_PDF_PAGES:
        raise ValueError("pdf page count must be <= 50")

    return {
        "file_name": filename,
        "content": data,
        "file_size_bytes": len(data),
        "page_count": page_count,
    }


def extract_full_text(pdf_path: str) -> List[str]:
    if PdfReader is None:
        raise RuntimeError("pypdf is required for PDF text extraction")
    reader = PdfReader(pdf_path)
    pages: List[str] = []
    for page in reader.pages:
        pages.append(str(page.extract_text() or "").strip())
    return pages


def compute_page_stats(pages_text: Sequence[str]) -> List[Dict[str, Any]]:
    return [
        {
            "page_index": index,
            "text_length": len(str(text or "").strip()),
            "has_text": bool(str(text or "").strip()),
        }
        for index, text in enumerate(pages_text)
    ]


def select_vision_pages(stats: Sequence[Dict[str, Any]], pages_text: Sequence[str], max_pages: int = 10) -> List[int]:
    del pages_text
    if not stats:
        return []

    sparse_pages = sorted(stats, key=lambda item: (item.get("text_length", 0), item.get("page_index", 0)))
    selected: List[int] = []

    for item in sparse_pages:
        page_index = int(item.get("page_index", 0))
        if page_index not in selected:
            selected.append(page_index)
        if len(selected) >= max_pages:
            break

    for item in sorted(stats, key=lambda item: item.get("page_index", 0)):
        page_index = int(item.get("page_index", 0))
        if page_index not in selected:
            selected.append(page_index)
        if len(selected) >= max_pages:
            break

    return sorted(selected[:max_pages])


def render_pages(pdf_path: str, page_indexes: Sequence[int], output_dir: str, dpi: int = 150) -> List[str]:
    if not page_indexes:
        return []
    if pdfium is None:
        raise RuntimeError("pypdfium2 is required for PDF page rendering")

    os.makedirs(output_dir, exist_ok=True)
    document = pdfium.PdfDocument(pdf_path)
    rendered_paths: List[str] = []
    scale = float(dpi) / 72.0
    try:
        for page_index in page_indexes:
            page = document[int(page_index)]
            image = page.render(scale=scale).to_pil()
            output_path = os.path.join(output_dir, f"page_{int(page_index) + 1}.png")
            image.save(output_path)
            rendered_paths.append(output_path)
            page.close()
    finally:
        document.close()
    return rendered_paths
