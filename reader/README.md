# reader

A small async ETL pipeline that batch-processes markdown documents from a
(remote) PostgreSQL table, LLM-extracts structured metadata (title, summary,
key points, tags) via `instructor`, and idempotently upserts each result into
MongoDB keyed by the source record id.

**Stack** — asyncpg, motor, instructor + openai (AsyncOpenAI),
pydantic-settings; any OpenAI-compatible endpoint works (e.g. OpenAI or Ollama).

## Setup

Requires Python 3.13+.

```bash
nix-shell          # NixOS: Python + PostgreSQL client + MongoDB
pip install -r requirements.txt
```

Configuration is driven by environment variables (see `.env.example`) and read
by `config.py`.

## Usage

```bash
python main.py
```

## Task runner (`justfile`)

Run `just` from this folder:

```bash
just       # list recipes
just run   # run the ETL pipeline
just shell # enter the Nix dev shell
```

## Project structure

```
reader/
├── main.py       # async ETL entry point
├── config.py     # env-driven settings (pydantic-settings)
├── postgres.py   # asyncpg source client
├── mongo.py      # MongoDB sink
├── extractor.py  # instructor / OpenAI extraction
├── justfile
├── shell.nix
└── .env.example
```
