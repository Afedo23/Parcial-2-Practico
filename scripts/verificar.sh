#!/usr/bin/env bash
# Harness: rutina única de verificación para el asistente y el catedrático. Falla (exit != 0) ante cualquier control incumplido.
#   ./scripts/verificar.sh
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Falta .env: cp .env.example .env"; exit 5; }
echo "== 1/6 Configuración de compose válida"; docker compose config -q
echo "== 2/6 Construcción y arranque";        docker compose up --build -d
echo "== 3/6 Pruebas automatizadas (P01-P12 lógicos, BD catalogo_test)"; docker compose --profile test run --rm tests
echo "== 4/6 Importación del Excel original (2 veces: la segunda no debe crear ni actualizar)"
docker compose exec -T app python -m catalogo.cli importar
docker compose exec -T app python -m catalogo.cli importar | tee /tmp/segunda_importacion.txt
grep -q "creados=0 actualizados=0" /tmp/segunda_importacion.txt || { echo "FALLO: la reimportación no fue idempotente"; exit 1; }
echo "== 5/6 Cuentas y datos de demostración"; docker compose exec -T app python -m catalogo.cli datos-demo
echo "== 6/6 Persistencia (P12)";               bash scripts/p12_persistencia.sh
echo "TODO OK"
