{ pkgs ? import <nixpkgs> { config = { allowUnfree = true; }; } }:

pkgs.mkShell {
  buildInputs = [
    pkgs.python312

    # PostgreSQL client only (psql, pg_dump, libpq) - remote server not required
    pkgs.libpq

    # MongoDB server + tools, used as the local/internal JSON storage backend
    pkgs.mongodb
  ];

  shellHook = ''
    # Load the repo-root .env (one env file for the whole monorepo).
    ENV_FILE="${toString ./..}/.env"
    if [ -f "$ENV_FILE" ]; then
      set -a
      while IFS= read -r line; do export "$line"; done < <(grep -vE '^[[:space:]]*(#|$)' "$ENV_FILE")
      set +a
    fi
  '';
}
