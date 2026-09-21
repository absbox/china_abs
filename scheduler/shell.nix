{
  pkgs ? import <nixpkgs> { config = { allowUnfree = true; }; },
}:

let
  libs = [
    pkgs.stdenv.cc.cc.lib # libstdc++, libgcc_s
    pkgs.zlib
    pkgs.openssl
    pkgs.libffi
  ];
in
pkgs.mkShell {
  buildInputs = [
    pkgs.uv
    pkgs.python313
    pkgs.just
  ] ++ libs;

  shellHook = ''
    export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath libs}:$LD_LIBRARY_PATH
    # Load the repo-root .env (one env file for the whole monorepo).
    ENV_FILE="${toString ./..}/.env"
    if [ -f "$ENV_FILE" ]; then
      set -a
      while IFS= read -r line; do export "$line"; done < <(grep -vE '^[[:space:]]*(#|$)' "$ENV_FILE")
      set +a
    fi
    echo "scheduler dev shell"
    echo "  uv sync                # install dependencies"
    echo "  python main.py --list  # list registered jobs"
    echo "  python main.py         # start the APScheduler"
  '';
}
