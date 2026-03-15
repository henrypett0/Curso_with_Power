import base64
import re

import httpx

from config import GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO

BASE_URL = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}


async def get_next_lesson_number() -> int:
    async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=30.0) as client:
        resp = await client.get(f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/lecciones")

    if resp.status_code == 404:
        return 1

    resp.raise_for_status()
    files = resp.json()

    numbers = []
    for f in files:
        match = re.match(r"leccion-(\d+)\.qmd", f["name"])
        if match:
            numbers.append(int(match.group(1)))

    return max(numbers) + 1 if numbers else 1


async def push_lesson_file(lesson_number: int, qmd_content: str) -> str:
    filename = f"leccion-{lesson_number:02d}.qmd"
    path = f"lecciones/{filename}"
    content_b64 = base64.b64encode(qmd_content.encode("utf-8")).decode("utf-8")

    # Extract title from YAML frontmatter for commit message
    title_match = re.search(r'^title:\s*"(.+)"', qmd_content, re.MULTILINE)
    title = title_match.group(1) if title_match else filename

    payload = {
        "message": f"Agregar {title}",
        "content": content_b64,
        "branch": "main",
    }

    async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=30.0) as client:
        resp = await client.put(f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}", json=payload)

    if resp.status_code == 422:
        raise ValueError(f"El archivo {filename} ya existe en el repositorio")

    resp.raise_for_status()
    return resp.json()["content"]["html_url"]
