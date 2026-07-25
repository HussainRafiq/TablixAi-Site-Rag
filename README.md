# Tablix Web RAG

Browserless research API for AI apps — site-scoped search, page extraction, BM25 retrieval, and OpenRouter answer synthesis.

Built for **Linux servers** (Docker, systemd, or bare metal). Also runs locally on macOS/Windows for development.

Pipeline:

1. **Search** — DuckDuckGo (`ddgs`), optional `site:` allowlist
2. **Extract** — HTTP fetch + Trafilatura (LLM-ready text)
3. **Retrieve** — BM25 over chunks
4. **Synthesize** — OpenRouter chat model with citations

## Linux quick start (recommended: Docker)

```bash
git clone <your-repo-url> tablix-web-rag
cd tablix-web-rag
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY=sk-or-v1-...

docker compose up -d --build
curl -s http://127.0.0.1:8000/health
```

Service listens on `0.0.0.0:8000`. Docs: `http://<server-ip>:8000/docs`

### OpenRouter key

Required only when `"synthesize": true` (default).

1. Create a key at https://openrouter.ai/keys
2. Set in `.env`:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-4o-mini
HOST=0.0.0.0
PORT=8000
WORKERS=2
```

Use `"synthesize": false` to return ranked sources without a key.

## Linux bare metal

Requires Python 3.10+ (`python3`, `python3-venv`, build tools for `lxml` on some distros).

```bash
# Debian/Ubuntu
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-dev build-essential \
  libxml2-dev libxslt1-dev zlib1g-dev curl

cd /opt
sudo git clone <your-repo-url> tablix-web-rag
cd tablix-web-rag
cp .env.example .env
# set OPENROUTER_API_KEY in .env

chmod +x scripts/run.sh
./scripts/run.sh
```

Dev reload:

```bash
RELOAD=1 ./scripts/run.sh
```

### systemd

```bash
sudo mkdir -p /opt/tablix-web-rag
sudo rsync -a ./ /opt/tablix-web-rag/
cd /opt/tablix-web-rag
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# edit .env

sudo cp deploy/tablix-web-rag.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tablix-web-rag
sudo systemctl status tablix-web-rag
```

## API

### `POST /research`

| Field | Type | Description |
|-------|------|-------------|
| `query` | string | Research question |
| `sites` | string[] | Domains and/or full URLs to restrict research to |
| `max_results` | int | Max pages (1–20, default 6) |
| `synthesize` | bool | Cited answer via OpenRouter (default true) |
| `include_raw` | bool | Include full extracted page text (default false) |
| `search_web` | bool | Run site-scoped web search (default true) |

Restrict to domains:

```bash
curl -s -X POST http://127.0.0.1:8000/research \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do async context managers work?",
    "sites": ["docs.python.org"],
    "max_results": 5
  }'
```

Specific endpoints only:

```bash
curl -s -X POST http://127.0.0.1:8000/research \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Summarize installation steps",
    "sites": [
      "https://fastapi.tiangolo.com/tutorial/",
      "https://fastapi.tiangolo.com/deployment/"
    ],
    "search_web": false
  }'
```

Retrieval only (no OpenRouter):

```bash
curl -s -X POST http://127.0.0.1:8000/research \
  -H "Content-Type: application/json" \
  -d '{
    "query": "vector databases comparison",
    "sites": ["pinecone.io", "weaviate.io", "qdrant.tech"],
    "synthesize": false,
    "include_raw": true
  }'
```

### `GET /health`

Reports process health and whether `OPENROUTER_API_KEY` is configured.

## Behavior notes

- If `sites` contains **only full URLs**, those pages are fetched and web search is skipped.
- If `sites` contains **domains**, search uses `site:domain` filters and drops off-allowlist results.
- Empty `sites` = open web search (still browserless).
- Answers cite sources as `[n]` matching `citations` / `sources`.

## Reverse proxy (optional)

Nginx example:

```nginx
server {
    listen 80;
    server_name research.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```
