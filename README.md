# Crucial SSMA — site e publicações automáticas

- **Site:** `index.html`, `img/`, `fonts/`, publicado pelo GitHub Pages.
- **Instagram:** o GitHub roda `instagram/publicar.py` a cada 15 minutos e publica os posts de `instagram/fila.json` cujo horário (de Brasília) já chegou. Não precisa de computador ligado.

## Acompanhar

- Aba **Actions**, workflow **Publicar no Instagram**: cada execução mostra o que foi publicado. Se der erro, o GitHub envia um e-mail.
- `instagram/fila.json`: o `status` de cada post muda para `publicado` (com o `link`) ou `erro` (com a mensagem).
- Para publicar na hora: **Actions → Publicar no Instagram → Run workflow**.

## Adicionar um post

1. Coloque as imagens (JPEG) em `instagram/midia/`.
2. Acrescente um item em `instagram/fila.json`:

```json
{
  "id": 200,
  "tipo": "CAROUSEL",
  "quando": "2026-12-15T12:00",
  "status": "agendado",
  "arquivos": ["foto1.jpg", "foto2.jpg"],
  "legenda": "Texto do post…",
  "erro": null,
  "link": null
}
```

`tipo`: `IMAGE` (1 foto), `CAROUSEL` (2 a 10), `REELS` (MP4) ou `STORIES`.

## Segredos (Settings → Secrets and variables → Actions)

| Nome | Conteúdo |
|---|---|
| `IG_ACCESS_TOKEN` | token da conta do Instagram |
| `IG_USER_ID` | id da conta profissional |

Para trocar o token: gere um novo na Meta e atualize o segredo `IG_ACCESS_TOKEN`.
