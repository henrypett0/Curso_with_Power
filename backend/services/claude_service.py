import base64
import re
from datetime import date

import anthropic

from config import ANTHROPIC_API_KEY, BACKEND_URL

SYSTEM_PROMPT = """Eres un asistente que convierte documentos PDF en lecciones para un curso en formato Quarto (.qmd) con bloques de codigo R interactivos usando quarto-webr.

Tu respuesta debe ser UNICAMENTE el contenido del archivo .qmd, sin explicaciones adicionales, sin bloques de codigo envolventes (no uses ```qmd o ```markdown alrededor), solo el contenido directo del archivo.

El archivo debe seguir exactamente este formato:

---
title: "Lección {N}: {titulo extraido del contenido}"
description: "{resumen de una linea del contenido}"
date: "{fecha}"
filters:
  - webr
---

## {Primera sección}

{contenido}

## {Segunda sección}

{contenido}

## Ejercicios en R

### Ejercicio 1: {titulo}

{descripcion del ejercicio en un solo parrafo}

```{webr-r}
# Comentarios guia para el estudiante
# Tu código aquí

```

### Ejercicio 2: {titulo}

{descripcion del ejercicio en un solo parrafo}

```{webr-r}
# Comentarios guia para el estudiante
# Tu código aquí

```

### Ejercicio 3: {titulo}

{descripcion del ejercicio en un solo parrafo}

```{webr-r}
# Comentarios guia para el estudiante
# Tu código aquí

```

Reglas:
1. El YAML frontmatter debe tener exactamente cuatro campos: title, description, date, filters
2. El campo filters SIEMPRE debe ser exactamente: filters:\\n  - webr
3. El title debe empezar con "Lección {N}: " seguido del titulo del tema
4. La description debe ser un resumen breve de una sola linea (maximo 100 caracteres)
5. La date debe ser la fecha proporcionada en formato YYYY-MM-DD
6. Usa encabezados ## para secciones principales y ### para subsecciones
7. Convierte tablas del PDF a tablas Markdown
8. Convierte codigo R del PDF a bloques interactivos ```{webr-r} para que el estudiante pueda ejecutarlos
9. Codigo en otros lenguajes (Python, SQL, etc.) usa bloques normales ```python, ```sql, etc.
10. Convierte listas del PDF a listas Markdown (- para viñetas, 1. para numeradas)
11. Conserva el contenido en el idioma original del PDF
12. No inventes contenido que no este en el PDF (excepto los ejercicios de R)
13. No incluyas encabezados de pagina, pies de pagina, ni numeros de pagina del PDF
14. No envuelvas tu respuesta en bloques de codigo
15. SIEMPRE incluye una seccion final "## Ejercicios en R" con exactamente 3 ejercicios practicos de programacion en R relacionados con el contenido de la leccion
16. Los ejercicios deben ser progresivos: el primero basico, el segundo intermedio, el tercero avanzado
17. Cada ejercicio debe tener UNA descripcion breve en un solo parrafo seguida de UN SOLO bloque ```{webr-r} con comentarios guia
18. NO uses sub-encabezados dentro de los ejercicios, NO uses texto en negritas como sub-pasos
19. TODOS los bloques de codigo R deben usar ```{webr-r} en lugar de ```r para ser interactivos
20. Si el contenido del PDF incluye ejemplos de codigo R, usalos como bloques ```{webr-r} con datos de ejemplo para que el estudiante pueda experimentar"""


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

    Since exercises use {webr-r} blocks (interactive R editors), the JS only
    injects a "Verificar" button after each exercise. It reads the student's
    code from the CodeMirror editor that webr creates. At the bottom, a
    "Generar Ejercicios Adaptativos" button sends all answers to the backend.
    """
    return f'''

<style>
.exercise-verify-block {{
  margin: 0.75rem 0 2rem 0;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
}}
.verify-btn {{
  display: inline-block;
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
  <p style="color: #6b7280; margin-bottom: 1rem;">Escribe y ejecuta tu codigo R en los editores interactivos de arriba. Luego verifica cada ejercicio o genera ejercicios adaptativos.</p>
  <button id="generate-btn" onclick="generateAdaptive()">Generar Ejercicios Adaptativos</button>
  <p id="spinner-adaptive">Analizando tus respuestas y generando ejercicios personalizados...</p>
</div>

<div id="adaptive-results"></div>

<script>
var BACKEND_URL = "{BACKEND_URL}";

/* Extract code from a CodeMirror 6 editor inside a container element */
function getCodeFromSection(container) {{
  /* Try CodeMirror 6 .cm-content (used by quarto-webr) */
  var cmContents = container.querySelectorAll(".cm-content");
  if (cmContents.length > 0) {{
    /* Return code from the last editor in this section (the exercise editor) */
    return cmContents[cmContents.length - 1].innerText || "";
  }}
  /* Fallback: try a regular code block */
  var codeEl = container.querySelector("code");
  return codeEl ? codeEl.textContent : "";
}}

function initVerifyButtons() {{
  var allH3 = document.querySelectorAll("h3");
  var exerciseFound = false;

  allH3.forEach(function(h3) {{
    var match = h3.textContent.trim().match(/^Ejercicio\\s+(\\d+)/);
    if (!match) return;
    exerciseFound = true;

    var num = parseInt(match[1]);
    var section = h3.closest("section");
    var container = section || h3.parentElement;

    /* Skip if we already injected a button here */
    if (container.querySelector(".exercise-verify-block")) return;

    var description = container.textContent.trim().substring(0, 2000);

    var block = document.createElement("div");
    block.className = "exercise-verify-block";
    block.setAttribute("data-exercise-num", num);
    block.setAttribute("data-description", description);
    block.innerHTML =
      '<button class="verify-btn" id="verify-btn-' + num + '" onclick="verifyExercise(' + num + ')">Verificar Ejercicio ' + num + '</button>' +
      '<span class="verify-spinner" id="spinner-' + num + '">Verificando...</span>' +
      '<div class="exercise-feedback" id="feedback-' + num + '"></div>';

    container.appendChild(block);
  }});

  return exerciseFound;
}}

/* Wait for webr CodeMirror editors to appear, then inject buttons */
(function waitForEditors() {{
  var attempts = 0;
  var maxAttempts = 30; /* 15 seconds max */

  function tryInit() {{
    attempts++;
    var hasEditors = document.querySelector(".cm-editor") !== null;
    var hasExercises = initVerifyButtons();

    if (!hasEditors && attempts < maxAttempts) {{
      setTimeout(tryInit, 500);
    }}
  }}

  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", function() {{ setTimeout(tryInit, 1000); }});
  }} else {{
    setTimeout(tryInit, 1000);
  }}
}})();

async function verifyExercise(num) {{
  var btn = document.getElementById("verify-btn-" + num);
  var spinner = document.getElementById("spinner-" + num);
  var feedback = document.getElementById("feedback-" + num);
  var block = document.querySelector('[data-exercise-num="' + num + '"]');
  var description = block ? block.getAttribute("data-description") : "";

  /* Get code from the webr editor in this exercise's section */
  var section = block.closest("section") || block.parentElement;
  var code = getCodeFromSection(section);

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

  /* Collect code from all exercise webr editors */
  var answers = [];
  for (var i = 1; i <= 3; i++) {{
    var block = document.querySelector('[data-exercise-num="' + i + '"]');
    if (block) {{
      var section = block.closest("section") || block.parentElement;
      answers.push(getCodeFromSection(section));
    }} else {{
      answers.push("");
    }}
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

    # Strip accidental code block wrappers (e.g. ```qmd\n...\n```)
    # Only strip trailing ``` if an opening wrapper was found and removed
    opening = re.match(r"^```(?:qmd|markdown|yaml)\s*\n", content)
    if opening:
        content = content[opening.end():]
        content = re.sub(r"\n```\s*$", "", content)

    if not content.startswith("---"):
        raise ValueError("La respuesta de Claude no contiene frontmatter YAML válido")

    # Ensure webr filter is in frontmatter
    if "filters:" not in content.split("---")[1]:
        # Insert filters before the closing ---
        parts = content.split("---", 2)
        parts[1] = parts[1].rstrip() + "\nfilters:\n  - webr\n"
        content = "---".join(parts)

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

    # Strip accidental code block wrappers (only if opening wrapper exists)
    opening = re.match(r"^```(?:qmd|markdown|yaml)\s*\n", content)
    if opening:
        content = content[opening.end():]
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
