{ pkgs, lib, config, inputs, ... }:

{
  # FastAPI + MongoDB "digester" service (NPL securitization report tooling).
  #
  #   devenv shell   # enter dev environment (installs deps via `uv sync`)
  #   devenv up      # run MongoDB + API with hot reload
  #   seed <u> <p>   # pre-seed a login user into MongoDB
  #   devenv test    # validate the environment
  #
  # Package manager is `uv` (pyproject.toml / uv.lock). Pin Python 3.13 to
  # match `.python-version`.

  packages = [
    pkgs.git
    pkgs.jq
    pkgs.mongosh
    pkgs.nodejs
  ];

  env = {
    # The app connects to the local devenv MongoDB (see services.mongodb).
    MONGODB_URI = "mongodb://localhost:27017";
    JWT_ALGORITHM = "HS256";
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES = "60";
    # Dev-only value; the app defaults to "change-me-in-production" otherwise.
    JWT_SECRET_KEY = "dev-only-secret-change-me";
    # Keep all MongoDB data inside the project at ./db instead of the default
    # .devenv/state/mongodb. The service's start script uses $MONGODBDATA as
    # mongod's --dbpath (i.e. storage.dbPath), so force-override it.
    MONGODBDATA = lib.mkForce "${config.devenv.root}/db";
  };

  # The repo-root `.env` is the single env file for the whole monorepo. It is
  # loaded into the dev shell below (see `enterShell`); the app also self-loads
  # it via python-dotenv at import time. `devenv` env values above take
  # precedence over both.

  languages.python = {
    enable = true;
    package = pkgs.python313;
    uv = {
      enable = true;
      sync.enable = true;
    };
  };

  # The API reads/writes MongoDB, so run it locally in the dev environment.
  services.mongodb.enable = true;
  # Bind to all interfaces (not just loopback) so MongoDB is reachable from
  # other machines. NOTE: still runs --noauth, so the port is open to anyone
  # who can reach this host.
  services.mongodb.additionalArgs = [ "--noauth" "--bind_ip" "0.0.0.0" ];

  # `.env` and `opencode.json` reference a Postgres database `deal-library`
  # (DigitalOcean managed, host localhost). When you want a local copy
  # instead, uncomment this (it will bind :5432):
  # services.postgres = {
  #   enable = true;
  #   initialDatabases = [{ name = "deal-library"; }];
  # };

  scripts = {
    seed.exec = ''
      if [ $# -ne 2 ]; then
        echo "usage: seed <username> <password>"
        exit 1
      fi
      uv run seed_user.py "$1" "$2"
    '';
  };

  processes.api = {
    # Start after the MongoDB service is ready, then probe /health.
    exec = "uv run uvicorn app.main:app --reload --port 8000";
    after = [ "devenv:processes:mongodb@started" ];
    ready.http.get = {
      port = 8000;
      path = "/health";
    };
  };

  enterShell = ''
    # Load the repo-root .env (one env file for the whole monorepo).
    ENV_FILE="${config.devenv.root}/../.env"
    if [ -f "$ENV_FILE" ]; then
      set -a
      while IFS= read -r line; do export "$line"; done < <(grep -vE '^[[:space:]]*(#|$)' "$ENV_FILE")
      set +a
    fi

    echo "digester dev environment ready"
    echo "  devenv up        # start MongoDB + API (http://127.0.0.1:8000)"
    echo "  seed <u> <p>     # pre-seed a login user into MongoDB"
    echo "  uv run <cmd>     # run commands inside the project venv"
  '';

  enterTest = ''
    uv run python -c "import fastapi, motor, jose, orjson, passlib, dotenv; print('dependencies ok')"
  '';
}