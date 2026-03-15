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

{descripcion del ejercicio en un solo parrafo}

```r
# Tu código aquí

```

### Ejercicio 2: {titulo}

{descripcion del ejercicio en un solo parrafo}

```r
# Tu código aquí

```

### Ejercicio 3: {titulo}

{descripcion del ejercicio en un solo parrafo}

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
15. Cada ejercicio debe tener UNA descripcion breve en un solo parrafo seguida de UN SOLO bloque de codigo R con comentarios guia
16. NO uses sub-encabezados dentro de los ejercicios, NO uses texto en negritas como sub-pasos. Cada ejercicio es: titulo (###), un parrafo descriptivo, y un bloque de codigo R"""


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


VERIFY_EXERCISE_PROMPT = """Eres un tutor de programacion en R. Un estudiante ha enviado su codigo para un ejercicio de practica.

Se te proporcionara:
1. La descripcion del ejercicio
2. El codigo del estudiante

Evalua el codigo y proporciona retroalimentacion constructiva en HTML.

Tu respuesta debe ser UNICAMENTE HTML con este formato:

<div class="feedback-content {status}">
<p class="feedback-status">{icono} {Estado}</p>
<p>{Retroalimentacion especifica sobre el codigo}</p>
<p class="feedback-hint">{Sugerencia para mejorar, si aplica}</p>
</div>

Donde {status} es una de estas clases CSS: "correcto", "parcial", "incorrecto"
Donde {icono} es: correcto, parcial, incorrecto

Reglas:
1. Responde SOLO con HTML, sin markdown
2. Se constructivo y motivador en tu retroalimentacion
3. Si el codigo esta vacio o dice "(sin respuesta)", indica amablemente que debe escribir una respuesta
4. Senala errores especificos y como corregirlos
5. Si esta correcto, felicita y sugiere mejoras opcionales
6. Evalua si el codigo resuelve correctamente lo que pide el ejercicio
7. Verifica la sintaxis de R y el uso correcto de funciones"""


def _get_interactive_html() -> str:
    """Return the interactive exercises HTML/JS block to append to .qmd files.

    Uses JavaScript to find exercise headings on the rendered page and inject
    a textarea + "Verificar" button after each one. At the bottom, a single
    "Generar Ejercicios Adaptativos" button sends all answers to the backend.
    """
    return f'''

<style>
.exercise-interactive {{
  margin: 1.5rem 0 2.5rem 0;
  padding: 1.25rem;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #f9fafb;
}}
.exercise-interactive label {{
  display: block;
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: #374151;
  font-size: 0.9rem;
}}
.exercise-interactive textarea {{
  width: 100%;
  min-height: 140px;
  padding: 0.75rem;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 0.85rem;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #1e1e1e;
  color: #d4d4d4;
  line-height: 1.5;
  resize: vertical;
  box-sizing: border-box;
}}
.exercise-interactive textarea:focus {{
  outline: none;
  border-color: #7c3aed;
  box-shadow: 0 0 0 3px rgba(124,58,237,0.1);
}}
.verify-btn {{
  display: inline-block;
  margin: 0.75rem 0.5rem 0.5rem 0;
  padding: 0.5rem 1.5rem;
  background: #059669;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}}
.verify-btn:hover {{ background: #047857; }}
.verify-btn:disabled {{ background: #6ee7b7; cursor: not-allowed; }}
.verify-spinner {{
  display: none;
  margin-left: 0.5rem;
  color: #059669;
  font-size: 0.85rem;
}}
.exercise-feedback {{
  margin-top: 0.75rem;
}}
.exercise-feedback .feedback-content {{
  padding: 1rem;
  border-radius: 8px;
  border-left: 4px solid #d1d5db;
  background: white;
}}
.exercise-feedback .feedback-content.correcto {{
  border-left-color: #059669;
  background: #f0fdf4;
}}
.exercise-feedback .feedback-content.parcial {{
  border-left-color: #d97706;
  background: #fffbeb;
}}
.exercise-feedback .feedback-content.incorrecto {{
  border-left-color: #dc2626;
  background: #fef2f2;
}}
.exercise-feedback .feedback-status {{
  font-weight: 600;
  margin-bottom: 0.5rem;
}}
.exercise-feedback .feedback-hint {{
  color: #6b7280;
  font-style: italic;
  margin-top: 0.5rem;
}}
#generate-section {{
  text-align: center;
  margin: 3rem 0 1rem 0;
  padding: 2rem 1.5rem;
  border-top: 2px solid #e5e7eb;
}}
#generate-btn {{
  display: inline-block;
  padding: 0.75rem 2rem;
  background: #7c3aed;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}}
#generate-btn:hover {{ background: #6d28d9; }}
#generate-btn:disabled {{ background: #a78bfa; cursor: not-allowed; }}
#spinner-adaptive {{
  display: none;
  color: #7c3aed;
  margin: 1rem 0;
}}
#adaptive-results {{ margin-top: 2rem; text-align: left; }}
#adaptive-results .ejercicio-adaptativo {{
  margin: 1.5rem 0;
  padding: 1.25rem;
  border-left: 4px solid #7c3aed;
  background: #faf5ff;
  border-radius: 0 8px 8px 0;
}}
#adaptive-results h4 {{ color: #6d28d9; margin-bottom: 0.5rem; }}
#adaptive-results pre {{ background: #1e1e1e; padding: 1rem; border-radius: 6px; overflow-x: auto; }}
#adaptive-results code {{ color: #d4d4d4; font-size: 0.85rem; }}
</style>

<div id="generate-section">
  <p style="color: #6b7280; margin-bottom: 1rem;">Completa y verifica los ejercicios de arriba, luego genera ejercicios adaptativos basados en tus respuestas.</p>
  <button id="generate-btn" onclick="generateAdaptive()">Generar Ejercicios Adaptativos</button>
  <p id="spinner-adaptive">Analizando tus respuestas y generando ejercicios personalizados...</p>
</div>

<div id="adaptive-results"></div>

<script>
const BACKEND_URL = "{BACKEND_URL}";

document.addEventListener("DOMContentLoaded", function() {{
  const allH3 = document.querySelectorAll("h3");

  allH3.forEach(function(h3) {{
    const match = h3.textContent.trim().match(/^Ejercicio\\s+(\\d+)/);
    if (!match) return;

    const num = parseInt(match[1]);

    /* Quarto may wrap each heading in a <section>. Use that if available. */
    const section = h3.closest("section");
    const container = section || h3.parentElement;

    /* Gather the description text for this exercise */
    const description = container.textContent.trim().substring(0, 2000);

    /* Build the interactive block */
    const block = document.createElement("div");
    block.className = "exercise-interactive";
    block.setAttribute("data-exercise-num", num);
    block.setAttribute("data-description", description);
    block.innerHTML =
      '<label for="answer-' + num + '">Tu respuesta al Ejercicio ' + num + ':</label>' +
      '<textarea id="answer-' + num + '" placeholder="# Escribe tu codigo R aqui..."></textarea>' +
      '<div>' +
        '<button class="verify-btn" id="verify-btn-' + num + '" onclick="verifyExercise(' + num + ')">Verificar Ejercicio ' + num + '</button>' +
        '<span class="verify-spinner" id="spinner-' + num + '">Verificando...</span>' +
      '</div>' +
      '<div class="exercise-feedback" id="feedback-' + num + '"></div>';

    container.appendChild(block);
  }});
}});

async function verifyExercise(num) {{
  var btn = document.getElementById("verify-btn-" + num);
  var spinner = document.getElementById("spinner-" + num);
  var feedback = document.getElementById("feedback-" + num);
  var code = document.getElementById("answer-" + num).value;
  var block = document.querySelector('[data-exercise-num="' + num + '"]');
  var description = block ? block.getAttribute("data-description") : "";

  btn.disabled = true;
  btn.textContent = "Verificando...";
  spinner.style.display = "inline";
  feedback.innerHTML = "";

  try {{
    var resp = await fetch(BACKEND_URL + "/api/verify-exercise", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{
        exercise_description: description,
        student_code: code
      }})
    }});
    var data = await resp.json();
    if (data.error) {{
      feedback.innerHTML = '<div class="feedback-content incorrecto"><p style="color:#dc2626">Error: ' + data.error + '</p></div>';
    }} else {{
      feedback.innerHTML = data.feedback_html;
    }}
  }} catch (err) {{
    feedback.innerHTML = '<div class="feedback-content incorrecto"><p style="color:#dc2626">Error de conexion. Verifica que el servidor este activo.</p></div>';
  }}

  btn.disabled = false;
  btn.textContent = "Verificar Ejercicio " + num;
  spinner.style.display = "none";
}}

async function generateAdaptive() {{
  var btn = document.getElementById("generate-btn");
  var spinner = document.getElementById("spinner-adaptive");
  var results = document.getElementById("adaptive-results");

  var answers = [];
  for (var i = 1; i <= 3; i++) {{
    var ta = document.getElementById("answer-" + i);
    answers.push(ta ? ta.value : "");
  }}

  btn.disabled = true;
  btn.textContent = "Generando...";
  spinner.style.display = "block";
  results.innerHTML = "";

  try {{
    var resp = await fetch(BACKEND_URL + "/api/student-exercises", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{
        lesson_content: document.body.innerText.substring(0, 5000),
        student_answers: answers
      }})
    }});
    var data = await resp.json();
    if (data.error) {{
      results.innerHTML = '<p style="color:#dc2626">Error: ' + data.error + '</p>';
    }} else {{
      results.innerHTML = data.exercises_html;
    }}
  }} catch (err) {{
    results.innerHTML = '<p style="color:#dc2626">Error de conexion. Verifica que el servidor este activo.</p>';
  }}

  btn.disabled = false;
  btn.textContent = "Generar Ejercicios Adaptativos";
  spinner.style.display = "none";
}}
</script>
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


def verify_exercise(exercise_description: str, student_code: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=VERIFY_EXERCISE_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Descripcion del ejercicio:\n{exercise_description}\n\n"
                    f"Codigo del estudiante:\n```r\n{student_code or '(sin respuesta)'}\n```"
                ),
            }
        ],
    )

    return message.content[0].text.strip()
