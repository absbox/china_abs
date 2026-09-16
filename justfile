# china-abs task runner (just)
#
# End-to-end document workflows built on the sub-projects:
#   docToCloud  -> scan / download / upload chinabond files
#   scheduler   -> deal init + allocation (jobs.digest)
#   toMarkdown  -> pdf -> markdown
#   digester    -> LLM extraction (digest.py)

py := justfile_directory() + "/.venv/bin/python"
today := `date +%Y-%m-%d`

# Show available recipes
default:
    @just --list

# Enter the root nix shell (includes `just` itself)
shell:
    nix-shell shell.nix

# Enter a component's dev shell: `just shell-in digester`
shell-in component:
    @cd {{component}} && nix-shell shell.nix

# ==========================================================================
# Requested workflows
# ==========================================================================

# 1) Scan chinabond and download new files from BEGIN to END (default today),
#    uploading them to Qiniu.  e.g. `just scan-download 2026-09-01`
scan-download begin end=today:
    cd docToCloud && {{py}} main.py sync --start {{begin}} --end {{end}}

# 1b) Preview only: list the files still missing from Qiniu in the window
scan-list begin end=today:
    cd docToCloud && {{py}} main.py list --outstanding --start {{begin}} --end {{end}}

# 2) Run deal init for documents that arrived since SINCE (default today)
deal-init since=today:
    cd scheduler && {{py}} -c "from jobs.digest import allocate_to_location_by_date; allocate_to_location_by_date('{{since}}')"

# 3) Allocate newly uploaded files to existing deals since SINCE
allocate since=today:
    cd scheduler && {{py}} -c "from jobs.digest import process_new; process_new('{{since}}')"

# 4) Convert PDFs to markdown by Qiniu key(s), then inspect the folder.
#    e.g. `just convert "农盈利信远弘2025年第二期不良资产支持证券发行说明书.pdf"`
convert +names:
    cd toMarkdown && for n in {{names}}; do {{py}} main.py download "$n"; done
    cd toMarkdown && {{py}} main.py inspect

# 4b) Convert ALL outstanding PDFs that have no markdown yet
convert-all:
    cd toMarkdown && {{py}} main.py download-all
    cd toMarkdown && {{py}} main.py inspect

# 4c) List PDFs still missing markdown
convert-list:
    cd toMarkdown && {{py}} main.py list

# 5) Digest a list of markdown reports/files with a single question.
#    e.g. `just digest PRICING_ANN "a.pdf" "b.pdf"`
digest question +names:
    cd digester && uv run python digest.py --question "{{question}}" {{names}}

# ==========================================================================
# Component helpers
# ==========================================================================

# Compile-check every Python component
check:
    @for d in reader china_model digester absbox.cloud docToCloud toMarkdown scheduler; do \
        echo "== $$d =="; \
        (cd $$d && python -m py_compile $$(find . -name '*.py' -not -path './__pycache__/*' -not -path '*/.venv/*' -not -path '*/.devenv/*') 2>&1 || true); \
    done

# Run the reader ETL pipeline
reader:
    cd reader && python main.py

# Run the digester API (uvicorn, hot reload)
digester:
    cd digester && uv run uvicorn app.main:app --reload --port 8000

# Run the absbox.cloud site (port 8001)
web:
    cd absbox.cloud && PYTHONPATH=. python index.py

# Run the absbox.cloud JSON API (port 8001)
api:
    cd absbox.cloud && PYTHONPATH=. python webApi.py

# Upload absbox.cloud (current dev branch code) to the dev folder via scp
upload-web-dev:
    @test "$(git rev-parse --abbrev-ref HEAD)" = "dev" || { echo "Error: must be on dev branch"; exit 1; }
    scp -r absbox.cloud alight:/home/xiaoyu/repo/absbox.cloud-dev

# Upload absbox.cloud (current dev branch code) to the production folder via scp
upload-web:
    @test "$(git rev-parse --abbrev-ref HEAD)" = "master" || { echo "Error: must be on master branch"; exit 1; }
    scp -r absbox.cloud alight:/home/xiaoyu/repo/absbox.cloud
