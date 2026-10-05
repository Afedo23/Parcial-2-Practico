# Checklist de entrega (para el estudiante, antes de las 23:00)

- [ ] Completar nombre y carné en `README.md` y `docs/RESOLUCION.md`.
- [ ] `cp .env.example .env` y ejecutar `bash scripts/verificar.sh` (o los comandos del README) en su equipo con Docker; **pegar la salida real** en `docs/evidencias/pruebas_docker_postgres.txt` y en `RESOLUCION.md` §8 (fecha, commit, resultado).
- [ ] Completar `docs/prompts/registro-prompts.md` con SUS prompts reales (mínimo 5 y 2 iteraciones) y revisar que todo lo documentado coincide con lo que realmente hizo.
- [ ] `git init`, `git add .`, commit; crear repo `parcial-catalogo-servicios-<carnet>` en GitHub y subir `main`.
- [ ] Agregar colaborador **`maldanap-usac`** (Settings → Collaborators). Si es privado, verificar la invitación enviada.
- [ ] `git tag parcial-v2.0 && git push origin parcial-v2.0`; anotar el SHA (`git rev-parse HEAD`) y entregar: URL, nombre, carné, rama y SHA.
- [ ] Confirmar que `.env` NO está en el repositorio y que `data/CatalogoServicios.xlsx` sí.
- [ ] Entender el código: puede preguntarse cualquier decisión (ver `RESOLUCION.md`).
