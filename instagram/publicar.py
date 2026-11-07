"""Publica no Instagram os posts da fila (fila.json) cujo horário já chegou.

Roda no GitHub Actions (ou no PC) só com a biblioteca padrão do Python.
Publica no máximo 1 post por execução: o workflow grava a fila logo depois,
assim um post nunca sai duas vezes.

Variáveis de ambiente:
  IG_ACCESS_TOKEN  token da conta (segredo do repositório)
  IG_USER_ID       id da conta profissional do Instagram
  MEDIA_BASE_URL   endereço público onde ficam as imagens (GitHub Pages)
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ig_api import IG, IGError  # noqa: E402

AQUI = Path(__file__).parent
FILA = AQUI / "fila.json"
BRASILIA = timezone(timedelta(hours=-3))  # Goiânia/Brasília, sem horário de verão


def agora():
    return datetime.now(BRASILIA).strftime("%Y-%m-%dT%H:%M")


def url_no_ar(url):
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    base = os.environ.get("MEDIA_BASE_URL", "").rstrip("/")
    if not token or not base:
        sys.exit("Faltam IG_ACCESS_TOKEN ou MEDIA_BASE_URL.")

    fila = json.loads(FILA.read_text(encoding="utf-8"))
    pendentes = sorted((p for p in fila if p["status"] == "agendado" and p["quando"] <= agora()),
                       key=lambda p: p["quando"])
    if not pendentes:
        print(f"{agora()} · nada para publicar agora.")
        return

    post = pendentes[0]
    urls = [f"{base}/instagram/midia/{arq}" for arq in post["arquivos"]]
    fora = [u for u in urls if not url_no_ar(u)]
    if fora:
        post["erro"] = "Imagens ainda não estão no ar (o site está sendo atualizado). Tento de novo na próxima rodada."
        FILA.write_text(json.dumps(fila, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(post["erro"], fora)
        return

    ig = IG(token, os.environ.get("IG_USER_ID") or "me")
    print(f"Publicando post {post['id']} ({post['tipo']}, {len(urls)} mídia(s)) agendado para {post['quando']}…")
    try:
        if ig.user_id == "me":
            ig.profile()
        container = ig.create_container(post["tipo"], urls, post.get("legenda") or "")
        media_id, link = ig.publish(container)
        post.update(status="publicado", erro=None, ig_media_id=media_id, link=link, publicado_em=agora())
        print("Publicado:", link or media_id)
    except IGError as e:
        post.update(status="erro", erro=str(e))
        print("ERRO:", e)
    FILA.write_text(json.dumps(fila, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if post["status"] == "erro":
        sys.exit(1)  # o GitHub avisa por e-mail quando a execução falha


if __name__ == "__main__":
    main()
