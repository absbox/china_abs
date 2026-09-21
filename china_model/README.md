# china_model

The shared Peewee data model and database access layer for the `china-abs`
monorepo. It is the **single source of truth** for the schema — `absbox.cloud`,
`docToCloud` and `toMarkdown` all depend on it instead of keeping their own
copies of `model.py`.

## Design

- The schema lives in `src/china_model/models.py`.
- Everything is bound to a `peewee.DatabaseProxy`, so **importing the package
  has no side effects** — nothing connects and no env vars are read until the
  host application calls `configure()`.
- `QiniuStorage` (`qiniu_storage`) and `Mineru` (`mineru`) are modelled here so
  the ETL projects do not hand-write SQL.

## Setup

Requires Python 3.13+ (a `shell.nix` is provided for NixOS; it exports the
native `libstdc++`/`zlib` libraries the wheels need).

```bash
nix-shell          # optional, on NixOS
uv sync            # from the repo root: installs this package + all members
```

The repo-root `.env` (git-ignored; see [`.env.example`](../.env.example))
or exported variables supply:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_HOST` | `localhost` | PostgreSQL host (`DATABASE_URL` is accepted as a legacy fallback when it has no scheme) |
| `DATABASE_PORT` | `5432` | PostgreSQL port |
| `DATABASE_NAME` | `deal-library` | Database name |
| `DATABASE_USER` | `doadmin` | Database user |
| `DATABASE_PASSWORD` | – | Database password |

## Usage

```python
import china_model

# no connection yet
assert not china_model.is_configured()

# bind once, at application startup
china_model.configure()                       # from DATABASE_* env vars
# china_model.configure("postgresql://doadmin:pw@localhost:5432/deal-library")

from china_model import Deal, Bond, QiniuStorage, Mineru

Deal.select().count()
QiniuStorage.select(QiniuStorage.key, QiniuStorage.hash).tuples()
```

Upserts use the unique index on `key`:

```python
from china_model import QiniuStorage, Mineru

(QiniuStorage.insert(bucket="deal-docs", key="x.pdf", ts=0, hash="h", md5="m")
    .on_conflict(conflict_target=[QiniuStorage.key],
                 update={QiniuStorage.hash: "h2"})
    .execute())

(Mineru.insert(key="x.pdf", markdown="# doc", model="inspector")
    .on_conflict(conflict_target=[Mineru.key],
                 update={Mineru.markdown: "# doc"})
    .execute())
```

`model.py` is kept as a backwards-compatible shim for existing
`from model import ...` imports; new code should import `china_model`.

## Project structure

```
china_model/
├── pyproject.toml          # hatchling + src layout, workspace member
├── shell.nix               # NixOS dev shell
├── model.py                # compatibility shim -> china_model
└── src/china_model/
    ├── __init__.py         # re-exports the models and helpers
    ├── db.py               # DatabaseProxy + configure()
    └── models.py           # the schema
```
