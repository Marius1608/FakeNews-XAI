from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter(tags=["upload"])


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict:
    """Extract text from an uploaded file (.txt, .pdf, .docx)."""
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content = await file.read()

    if ext == "txt":
        text = content.decode("utf-8", errors="replace")

    elif ext == "pdf":
        from PyPDF2 import PdfReader
        import io
        reader = PdfReader(io.BytesIO(content))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)

    elif ext in ("docx", "doc"):
        from docx import Document
        import io
        doc = Document(io.BytesIO(content))
        text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{ext}. Use .txt, .pdf, or .docx",
        )

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from the file")

    return {
        "text": text.strip(),
        "filename": filename,
        "file_type": ext,
        "char_count": len(text.strip()),
    }
