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
# sin esto el GITHUB_TOKEN del fork no puede crear la release (403 en "Publish Release")
wf.insert(list(wf.keys()).index("on") + 1, "permissions", {"contents": "write"})

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
MARCA = {
    "name": "TeraDesk - nombre e iconos propios",
    "shell": "bash",
    "run": (
        "set -e\n"
        # APP_NAME manda en: carpeta de config, servicio, carpeta de instalacion, TeraDesk.exe
        # al instalar, tuberias IPC y protocolo teradesk://. Asi convive con un RustDesk oficial.
        "F=libs/hbb_common/src/config.rs\n"
        "sed -i 's|RwLock::new(\"RustDesk\".to_owned())|RwLock::new(\"TeraDesk\".to_owned())|' $F\n"
        "grep -q 'RwLock::new(\"TeraDesk\".to_owned())' $F || { echo 'NO SE CAMBIO APP_NAME'; exit 1; }\n"
        "cp teradesk/marca/icon.ico res/icon.ico\n"
        "cp teradesk/marca/tray-icon.ico res/tray-icon.ico\n"
        "cp teradesk/marca/icon.png res/icon.png\n"
        "cp teradesk/marca/icon.ico flutter/windows/runner/resources/app_icon.ico\n"
        "cp teradesk/marca/icon.ico flutter/assets/icon.ico\n"
        "cp teradesk/marca/icon.png flutter/assets/icon.png\n"
        "cp teradesk/marca/logo.png teradesk/marca/logo_light.png teradesk/marca/logo_dark.png flutter/assets/\n"
        # Sin \"Con tecnologia de RustDesk\": es un enlace a rustdesk.com y un cliente acabaria bajando el oficial.
        "D=flutter/lib/common.dart\n"
        "sed -i 's|if (bind.mainGetBuildinOption(key: \"hide-powered-by-me\") == .Y.) {|if (true) {|' $D\n"
        "grep -q 'if (true) {' $D || { echo 'NO SE OCULTO powered_by'; exit 1; }\n"
        "R=flutter/windows/runner/Runner.rc\n"
        "sed -i -E 's|(VALUE \"ProductName\", )\"RustDesk\"|\\1\"TeraDesk\"|; "
        "s|(VALUE \"FileDescription\", )\"[^\"]*\"|\\1\"TeraDesk - Soporte remoto TeraNeT\"|' $R\n"
        "grep -n 'ProductName\\|FileDescription' $R\n"
    ),
}

pasos = wf["jobs"]["build-for-windows-flutter"]["steps"]
i = next(k for k, s in enumerate(pasos) if s.get("name") == "Checkout source code")
pasos.insert(i + 1, PASO)
pasos.insert(i + 2, MARCA)

# El MSI de RustDesk exige <app-name>.exe en la carpeta y comparte UpgradeCode con el
# oficial si no se reconstruye entero: instalarlo podria reemplazar un RustDesk oficial.
# Por ahora solo se publica el .exe.
for nombre in ("Build msi", "Build pre-built MSI template", "Upload unsigned msi template"):
    pasos[:] = [s for s in pasos if s.get("name") != nombre]

# El autoextraible saca los archivos a una carpeta con el nombre del .exe: con
# TeraDesk.exe no se mezcla con la de un RustDesk portable.
se = next(s for s in pasos if s.get("name") == "Build self-extracted executable")
viejo = "python3 ./generate.py -f ../../rustdesk/ -o . -e ../../rustdesk/rustdesk.exe"
assert viejo in se["run"], "cambio el paso del autoextraible"
se["run"] = se["run"].replace(viejo, "mv ../../rustdesk/rustdesk.exe ../../rustdesk/TeraDesk.exe\n"
                              "python3 ./generate.py -f ../../rustdesk/ -o . -e ../../rustdesk/TeraDesk.exe")
se["run"] = se["run"].replace("./SignOutput/rustdesk-${{ env.VERSION }}", "./SignOutput/TeraDesk-${{ env.VERSION }}")
assert "TeraDesk-${{ env.VERSION }}" in se["run"]

pub = next(s for s in pasos if s.get("name") == "Publish Release")
pub["with"]["files"] = "./SignOutput/TeraDesk-*.exe\n"

with open(DST, "w") as f:
    f.write("# GENERADO por teradesk/generar-workflow.py - no editar a mano\n")
    y.dump(wf, f)
print("ok ->", DST)
