#!/usr/bin/env bash
# P12: los datos persisten al reiniciar contenedores SIN eliminar volúmenes. Código de salida 0 = éxito.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up --build -d
reintentar() { for i in $(seq 1 30); do "$@" && return 0; sleep 3; done; return 1; }
reintentar docker compose exec -T app python -m catalogo.cli persistencia crear
echo ">> Reiniciando contenedores (sin 'down -v')..."
docker compose restart
reintentar docker compose exec -T app python -m catalogo.cli persistencia verificar
echo "P12 OK: el marcador sobrevivió al reinicio."
