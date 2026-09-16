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
    if [ -f .env ]; then set -a; . ./.env; set +a; fi
    echo "absbox.cloud dev shell"
    echo "  uv sync                                  # install dependencies"
    echo "  PYTHONPATH=. python index.py             # site on :8001"
    echo "  PYTHONPATH=. python webApi.py            # JSON API"
    echo "  gunicorn -c gunicorn_conf.py index:app"
    echo "note: the private 'cnc' package is optional (Chinese numeral parsing)."
  '';
}
