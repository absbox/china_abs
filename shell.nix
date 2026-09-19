{
  pkgs ? import <nixpkgs> { config = { allowUnfree = true; }; },
}:

let
  # Native libraries required by the PyPI wheels (numpy/scipy/pandas/psycopg)
  # on NixOS.  They are exported via LD_LIBRARY_PATH in the shell hook.
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
    echo "china-abs monorepo dev shell"
    echo "  uv sync --all-packages   # install every workspace member"
    echo "  just --list              # component tasks"
    echo
    echo "per-component shells: cd <component> && just shell"
  '';
}
