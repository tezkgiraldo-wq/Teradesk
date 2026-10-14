#!/usr/bin/env python3
"""Genera .github/workflows/teradesk.yml a partir de flutter-build.yml (upstream).

TeraDesk = RustDesk apuntando al server propio de TeraNeT. No se toca ningun
archivo de upstream: este script copia su workflow, deja solo lo que hace falta
para Windows x64 y le mete un paso que cambia el server y la llave por defecto.
Cuando RustDesk cambie su workflow: traer upstream y volver a correr esto.
    python3 teradesk/generar-workflow.py
"""
import re, sys, pathlib
from ruamel.yaml import YAML

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SRC = RAIZ / ".github/workflows/flutter-build.yml"
DST = RAIZ / ".github/workflows/teradesk.yml"
CONF = (RAIZ / "teradesk/teradesk.conf").read_text()
SERVER = re.search(r'^SERVER=(.+)$', CONF, re.M).group(1).strip()
KEY = re.search(r'^KEY=(.+)$', CONF, re.M).group(1).strip()

txt = SRC.read_text()
# los inputs del workflow_call pasan a ser constantes
txt = txt.replace("${{ inputs.upload-artifact }}", "true")
txt = txt.replace("!inputs.upload-artifact", "false")
txt = txt.replace("inputs.upload-artifact", "true")
txt = txt.replace("${{ inputs.upload-tag }}", "teradesk")
txt = txt.replace("${{ inputs.publish-update-metadata }}", "false")
txt = txt.replace("inputs.publish-update-metadata", "false")
txt = txt.replace("inputs.upload-tag", "'teradesk'")
assert "inputs." not in txt, "quedo una referencia a inputs.* sin traducir"

y = YAML(); y.preserve_quotes = True; y.width = 4096
wf = y.load(txt)
wf["name"] = "TeraDesk - compilar Windows x64"
wf["on"] = {"workflow_dispatch": None}

QUEDAN = ["validate-update-metadata-keys", "generate-bridge",
          "build-RustDeskTempTopMostWindow", "build-for-windows-flutter"]
for j in list(wf["jobs"]):
    if j not in QUEDAN:
        del wf["jobs"][j]

def solo_x64(job):
    m = job["strategy"]["matrix"]["job"]
    keep = [e for e in m if e.get("platform") == "x64" or e.get("arch") == "x86_64"]
    assert keep, "no encontre la variante x64"
    m.clear(); m.extend(keep)

solo_x64(wf["jobs"]["build-RustDeskTempTopMostWindow"])
solo_x64(wf["jobs"]["build-for-windows-flutter"])

PASO = {
    "name": "TeraDesk - server y llave propios",
    "shell": "bash",
    "run": (
        "set -e\n"
        "F=libs/hbb_common/src/config.rs\n"
        f"sed -i -E 's|^pub const RENDEZVOUS_SERVERS: &\\[&str\\] = &\\[.*\\];|pub const RENDEZVOUS_SERVERS: \\&[\\&str] = \\&[\"{SERVER}\"];|' $F\n"
        f"sed -i -E 's|^pub const RS_PUB_KEY: &str = \".*\";|pub const RS_PUB_KEY: \\&str = \"{KEY}\";|' $F\n"
        "grep -n 'RENDEZVOUS_SERVERS\\|RS_PUB_KEY' $F\n"
        f"grep -q '\"{SERVER}\"' $F && grep -q '\"{KEY}\"' $F || {{ echo 'NO SE APLICO EL PARCHE'; exit 1; }}\n"
    ),
}
pasos = wf["jobs"]["build-for-windows-flutter"]["steps"]
i = next(k for k, s in enumerate(pasos) if s.get("name") == "Checkout source code")
pasos.insert(i + 1, PASO)

with open(DST, "w") as f:
    f.write("# GENERADO por teradesk/generar-workflow.py - no editar a mano\n")
    y.dump(wf, f)
print("ok ->", DST)
