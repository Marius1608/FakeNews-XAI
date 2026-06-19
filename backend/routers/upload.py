import logging

from fastapi import APIRouter, UploadFile, File, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(tags=["upload"])

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
SUPPORTED_EXTENSIONS = ("txt", "pdf", "docx", "doc")


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict:
    """Extract text from an uploaded file (.txt, .pdf, .docx)."""
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content = await file.read()

    # Validare dimensiune — peste 5MB se respinge inainte de parsare
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File too large. Maximum allowed size is 5MB.",
        )

    # Validare extensie — tipuri nesuportate respinse inainte de parsare
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Supported formats: PDF, DOCX, TXT.",
        )

    # Parsarea efectiva — orice eroare (fisier corupt/criptat) devine HTTP 400
    try:
        if ext == "txt":
            text = content.decode("utf-8", errors="replace")

        elif ext == "pdf":
            from PyPDF2 import PdfReader
            import io
            reader = PdfReader(io.BytesIO(content))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)

        else:  # docx / doc
            from docx import Document
            import io
            doc = Document(io.BytesIO(content))
            text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"/upload: failed to parse '{filename}' (.{ext}): {e}")
        raise HTTPException(
            status_code=400,
            detail="File could not be parsed. Ensure it is a valid unencrypted PDF or DOCX.",
        )

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from the file")

    return {
        "text": text.strip(),
        "filename": filename,
        "file_type": ext,
        "char_count": len(text.strip()),
    }
