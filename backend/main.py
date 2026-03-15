import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from services import claude_service, github_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Generador de Lecciones")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

MAX_PDF_SIZE = 32 * 1024 * 1024  # 32 MB


@app.get("/", response_class=HTMLResponse)
async def upload_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


@app.post("/upload", response_class=HTMLResponse)
async def handle_upload(request: Request, file: UploadFile):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "error": "Por favor sube un archivo PDF."},
        )

    pdf_bytes = await file.read()

    if len(pdf_bytes) == 0:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "error": "El archivo está vacío."},
        )

    if len(pdf_bytes) > MAX_PDF_SIZE:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "error": "El archivo excede el límite de 32 MB."},
        )

    try:
        lesson_number = await github_service.get_next_lesson_number()
        logger.info("Siguiente número de lección: %d", lesson_number)

        qmd_content = await asyncio.to_thread(
            claude_service.generate_lesson_qmd, pdf_bytes, lesson_number
        )
        logger.info("Lección generada exitosamente")

    except Exception as e:
        logger.exception("Error al generar la lección")
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "error": f"Error al generar la lección: {e}"},
        )

    return templates.TemplateResponse(
        "edit.html",
        {
            "request": request,
            "qmd_content": qmd_content,
            "lesson_number": lesson_number,
            "filename": f"leccion-{lesson_number:02d}.qmd",
        },
    )


@app.post("/publish", response_class=HTMLResponse)
async def publish_lesson(request: Request):
    form = await request.form()
    qmd_content = form.get("qmd_content", "")
    lesson_number = int(form.get("lesson_number", 0))

    if not qmd_content or lesson_number == 0:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "error": "Datos inválidos. Intenta de nuevo."},
        )

    try:
        file_url = await github_service.push_lesson_file(lesson_number, qmd_content)
        logger.info("Lección publicada: %s", file_url)
    except Exception as e:
        logger.exception("Error al publicar la lección")
        return templates.TemplateResponse(
            "edit.html",
            {
                "request": request,
                "qmd_content": qmd_content,
                "lesson_number": lesson_number,
                "filename": f"leccion-{lesson_number:02d}.qmd",
                "error": f"Error al publicar: {e}",
            },
        )

    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "success": f"Lección {lesson_number:02d} publicada exitosamente.",
            "file_url": file_url,
        },
    )
