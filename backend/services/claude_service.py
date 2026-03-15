import base64
import re
from datetime import date

import anthropic

from config import ANTHROPIC_API_KEY, BACKEND_URL

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

## Ejercicios en R

### Ejercicio 1: {titulo}

{descripcion del ejercicio}

```r
# Tu código aquí

```

### Ejercicio 2: {titulo}

{descripcion del ejercicio}

```r
# Tu código aquí

```

### Ejercicio 3: {titulo}

{descripcion del ejercicio}

```r
# Tu código aquí

```

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
10. No inventes contenido que no este en el PDF (excepto los ejercicios de R)
11. No incluyas encabezados de pagina, pies de pagina, ni numeros de pagina del PDF
12. No envuelvas tu respuesta en bloques de codigo
13. SIEMPRE incluye una seccion final "## Ejercicios en R" con exactamente 3 ejercicios practicos de programacion en R relacionados con el contenido de la leccion
14. Los ejercicios deben ser progresivos: el primero basico, el segundo intermedio, el tercero avanzado
15. Cada ejercicio debe incluir un bloque de codigo R con comentarios guia y espacio para que el estudiante escriba su codigo"""


EXERCISES_SYSTEM_PROMPT = """Eres un asistente que genera ejercicios adaptativos de programacion en R.

Se te proporcionara el contenido de una leccion en formato .qmd que incluye 3 ejercicios originales.

Tu tarea es generar 3 NUEVOS ejercicios de practica en R que:
1. Se basen en los temas de los ejercicios originales
2. Sean complementarios (no repetitivos)
3. Aumenten progresivamente en dificultad
4. Incluyan pistas y comentarios guia en el codigo

Tu respuesta debe ser UNICAMENTE el contenido Markdown de los 3 ejercicios, sin explicaciones adicionales, sin bloques de codigo envolventes.

Formato exacto:

## Ejercicios de Práctica Adicionales

### Ejercicio 4: {titulo}

{descripcion del ejercicio con contexto}

```r
# Pista: {pista para resolver el ejercicio}
# Tu código aquí

```

### Ejercicio 5: {titulo}

{descripcion del ejercicio con contexto}

```r
# Pista: {pista para resolver el ejercicio}
# Tu código aquí

```

### Ejercicio 6: {titulo}

{descripcion del ejercicio con contexto}

```r
# Pista: {pista para resolver el ejercicio}
# Tu código aquí

```"""


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


STUDENT_EXERCISES_PROMPT = """Eres un tutor de programacion en R. Un estudiante acaba de completar ejercicios de una leccion y necesita mas practica.

Se te proporcionara:
1. El contenido de la leccion
2. Las respuestas del estudiante a los 3 ejercicios originales

Analiza las respuestas del estudiante para identificar:
- Conceptos que domina bien
- Areas donde necesita mas practica
- Errores comunes en su codigo

Genera 3 ejercicios adaptativos en HTML que se enfoquen en las areas donde el estudiante necesita mejorar.

Tu respuesta debe ser UNICAMENTE HTML (sin markdown), con este formato exacto:

<div class="ejercicio-adaptativo">
<h4>Ejercicio 4: {titulo}</h4>
<p>{descripcion que explique por que este ejercicio es relevante basado en las respuestas del estudiante}</p>
<pre><code class="language-r"># {comentario guia}
# Tu codigo aqui
</code></pre>
</div>

<div class="ejercicio-adaptativo">
<h4>Ejercicio 5: {titulo}</h4>
<p>{descripcion}</p>
<pre><code class="language-r"># {comentario guia}
# Tu codigo aqui
</code></pre>
</div>

<div class="ejercicio-adaptativo">
<h4>Ejercicio 6: {titulo}</h4>
<p>{descripcion}</p>
<pre><code class="language-r"># {comentario guia}
# Tu codigo aqui
</code></pre>
</div>

Reglas:
1. Responde SOLO con HTML, sin markdown
2. Los ejercicios deben ser adaptativos: si el estudiante comete errores, enfocate en esas areas
3. Si el estudiante no escribio codigo, genera ejercicios basicos del tema
4. Incluye retroalimentacion breve sobre lo que observas en sus respuestas
5. Los ejercicios deben ser progresivos en dificultad"""


def _get_interactive_html() -> str:
    """Return the interactive exercises HTML/JS block to append to .qmd files."""
    return f'''

## Practica Interactiva

Escribe tu codigo R para cada ejercicio y luego genera ejercicios adaptativos basados en tus respuestas.

```{{=html}}
<style>
.exercise-input {{ margin: 1.5rem 0; padding: 1rem; border: 1px solid #e5e7eb; border-radius: 8px; background: #f9fafb; }}
.exercise-input label {{ display: block; font-weight: 600; margin-bottom: 0.5rem; color: #374151; }}
.exercise-input textarea {{ width: 100%; min-height: 120px; padding: 0.75rem; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.85rem; border: 1px solid #d1d5db; border-radius: 6px; background: #1e1e1e; color: #d4d4d4; line-height: 1.5; resize: vertical; }}
.exercise-input textarea:focus {{ outline: none; border-color: #7c3aed; box-shadow: 0 0 0 3px rgba(124,58,237,0.1); }}
#generate-btn {{ display: block; margin: 1.5rem auto; padding: 0.75rem 2rem; background: #7c3aed; color: white; border: none; border-radius: 8px; font-size: 1rem; font-weight: 500; cursor: pointer; transition: background 0.2s; }}
#generate-btn:hover {{ background: #6d28d9; }}
#generate-btn:disabled {{ background: #a78bfa; cursor: not-allowed; }}
#adaptive-results {{ margin-top: 2rem; }}
#adaptive-results .ejercicio-adaptativo {{ margin: 1.5rem 0; padding: 1.25rem; border-left: 4px solid #7c3aed; background: #faf5ff; border-radius: 0 8px 8px 0; }}
#adaptive-results h4 {{ color: #6d28d9; margin-bottom: 0.5rem; }}
#adaptive-results pre {{ background: #1e1e1e; padding: 1rem; border-radius: 6px; overflow-x: auto; }}
#adaptive-results code {{ color: #d4d4d4; font-size: 0.85rem; }}
#spinner-msg {{ text-align: center; color: #7c3aed; display: none; margin: 1rem 0; }}
</style>

<div class="exercise-input">
  <label>Tu respuesta al Ejercicio 1:</label>
  <textarea id="answer-1" placeholder="# Escribe tu codigo R aqui..."></textarea>
</div>

<div class="exercise-input">
  <label>Tu respuesta al Ejercicio 2:</label>
  <textarea id="answer-2" placeholder="# Escribe tu codigo R aqui..."></textarea>
</div>

<div class="exercise-input">
  <label>Tu respuesta al Ejercicio 3:</label>
  <textarea id="answer-3" placeholder="# Escribe tu codigo R aqui..."></textarea>
</div>

<button id="generate-btn" onclick="generateAdaptive()">Generar 3 Ejercicios de Practica</button>
<p id="spinner-msg">Analizando tus respuestas y generando ejercicios...</p>

<div id="adaptive-results"></div>

<script>
const BACKEND_URL = "{BACKEND_URL}";

async function generateAdaptive() {{
  const btn = document.getElementById("generate-btn");
  const spinner = document.getElementById("spinner-msg");
  const results = document.getElementById("adaptive-results");
  const answers = [
    document.getElementById("answer-1").value,
    document.getElementById("answer-2").value,
    document.getElementById("answer-3").value
  ];

  btn.disabled = true;
  btn.textContent = "Generando...";
  spinner.style.display = "block";
  results.innerHTML = "";

  try {{
    const resp = await fetch(BACKEND_URL + "/api/student-exercises", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{
        lesson_content: document.body.innerText.substring(0, 5000),
        student_answers: answers
      }})
    }});
    const data = await resp.json();
    if (data.error) {{
      results.innerHTML = "<p style=\\"color:#b91c1c\\">Error: " + data.error + "</p>";
    }} else {{
      results.innerHTML = data.exercises_html;
    }}
  }} catch (err) {{
    results.innerHTML = "<p style=\\"color:#b91c1c\\">Error de conexion. Verifica que el servidor este activo.</p>";
  }}

  btn.disabled = false;
  btn.textContent = "Generar 3 Ejercicios de Practica";
  spinner.style.display = "none";
}}
</script>
```
'''


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

    # Append interactive exercises section
    content += _get_interactive_html()

    return content


def generate_exercises(qmd_content: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=EXERCISES_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Aquí está el contenido de la lección. Genera 3 ejercicios adicionales de práctica en R basados en el contenido y los ejercicios existentes:\n\n{qmd_content}",
            }
        ],
    )

    content = message.content[0].text.strip()

    # Strip accidental code block wrappers
    content = re.sub(r"^```(?:qmd|markdown|yaml)?\s*\n", "", content)
    content = re.sub(r"\n```\s*$", "", content)

    return content


def generate_student_exercises(lesson_content: str, student_answers: list[str]) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    answers_text = ""
    for i, answer in enumerate(student_answers, 1):
        answers_text += f"\n### Respuesta del estudiante al Ejercicio {i}:\n```r\n{answer or '(sin respuesta)'}\n```\n"

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=STUDENT_EXERCISES_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Contenido de la leccion:\n{lesson_content}\n\nRespuestas del estudiante:\n{answers_text}",
            }
        ],
    )

    return message.content[0].text.strip()
