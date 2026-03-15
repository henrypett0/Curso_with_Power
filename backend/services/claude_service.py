import base64
import re
from datetime import date

import anthropic

from config import ANTHROPIC_API_KEY

SYSTEM_PROMPT = """Eres un asistente que convierte documentos PDF en lecciones para un curso en formato Quarto (.qmd).

Tu respuesta debe ser UNICAMENTE el contenido del archivo .qmd, sin explicaciones adicionales, sin bloques de codigo envolventes (no uses ```qmd o ```markdown alrededor), solo el contenido directo del archivo.

El archivo debe seguir exactamente este formato:

---
title: "Lección {N}: {titulo extraido del contenido}"
description: "{resumen de una linea del contenido}"
date: "{fecha}"
---

## {Primera sección}

{contenido}

## {Segunda sección}

{contenido}

Reglas:
1. El YAML frontmatter debe tener exactamente tres campos: title, description, date
2. El title debe empezar con "Lección {N}: " seguido del titulo del tema
3. La description debe ser un resumen breve de una sola linea (maximo 100 caracteres)
4. La date debe ser la fecha proporcionada en formato YYYY-MM-DD
5. Usa encabezados ## para secciones principales y ### para subsecciones
6. Convierte tablas del PDF a tablas Markdown
7. Convierte codigo del PDF a bloques con el lenguaje apropiado (```python, ```r, etc.)
8. Convierte listas del PDF a listas Markdown (- para viñetas, 1. para numeradas)
9. Conserva el contenido en el idioma original del PDF
10. No inventes contenido que no este en el PDF
11. No incluyas encabezados de pagina, pies de pagina, ni numeros de pagina del PDF
12. No envuelvas tu respuesta en bloques de codigo"""


def generate_lesson_qmd(pdf_bytes: bytes, lesson_number: int) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    today = date.today().isoformat()

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"Convierte este PDF en una lección .qmd. El número de lección es {lesson_number}. La fecha de hoy es {today}.",
                    },
                ],
            }
        ],
    )

    content = message.content[0].text.strip()

    # Strip accidental code block wrappers
    content = re.sub(r"^```(?:qmd|markdown|yaml)?\s*\n", "", content)
    content = re.sub(r"\n```\s*$", "", content)

    if not content.startswith("---"):
        raise ValueError("La respuesta de Claude no contiene frontmatter YAML válido")

    return content
