# TeraDesk

RustDesk apuntando al servidor propio de TeraNeT (LXC 103 del lab `tera`).

- `teradesk.conf` — servidor y llave publica que van incrustados en la app.
- `generar-workflow.py` — genera `.github/workflows/teradesk.yml` a partir de
  `flutter-build.yml` de RustDesk: solo Windows x64 + un paso que cambia
  `RENDEZVOUS_SERVERS` y `RS_PUB_KEY` en `libs/hbb_common/src/config.rs`.
  No se toca ningun archivo de RustDesk, para que traer sus updates no choque.

Compilar: pestaña **Actions** → *TeraDesk - compilar Windows x64* → **Run workflow**.
El instalador sale en la release `teradesk` del repo.

Al traer cambios de RustDesk: sincronizar el fork y volver a correr
`python3 teradesk/generar-workflow.py` (requiere `ruamel.yaml`).
