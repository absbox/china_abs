# china-abs task runner (just)

# Show available recipes
default:
    @just --list

# Enter the root nix shell (includes `just` itself)
shell:
    nix-shell shell.nix

# Enter a component's dev shell: `just shell-in maker`
shell-in component:
    @cd {{component}} && nix-shell shell.nix

# Compile-check every Python component
check:
    @for d in reader china_model maker absbox.cloud; do \
        echo "== $$d =="; \
        (cd $$d && python -m py_compile $$(find . -name '*.py' -not -path './__pycache__/*' -not -path '*/.venv/*') 2>&1 || true); \
    done

# Run the reader ETL pipeline
reader:
    cd reader && python main.py

# Run the maker API (uvicorn, hot reload)
maker:
    cd maker && uv run uvicorn app.main:app --reload --port 8000

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
