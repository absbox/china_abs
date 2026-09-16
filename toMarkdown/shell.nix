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
    echo "toMarkdown dev shell"
    echo "  uv sync                 # install dependencies"
    echo "  python main.py list"
    echo "  python main.py download-all"
    echo "  python main.py inspect"
  '';
}
