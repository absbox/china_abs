{ pkgs ? import <nixpkgs> { config = { allowUnfree = true; }; } }:

pkgs.mkShell {
  buildInputs = [
    pkgs.python312

    # PostgreSQL client only (psql, pg_dump, libpq) - remote server not required
    pkgs.libpq

    # MongoDB server + tools, used as the local/internal JSON storage backend
    pkgs.mongodb
  ];
}