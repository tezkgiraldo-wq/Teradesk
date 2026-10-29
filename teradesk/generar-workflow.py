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
wf["name"] = "TeraDesk - compilar Windows x64"  # y macOS (dmg)
wf["on"] = {"workflow_dispatch": None}
# sin esto el GITHUB_TOKEN del fork no puede crear la release (403 en "Publish Release")
wf.insert(list(wf.keys()).index("on") + 1, "permissions", {"contents": "write"})

QUEDAN = ["validate-update-metadata-keys", "generate-bridge",
          "build-RustDeskTempTopMostWindow", "build-for-windows-flutter", "build-for-macOS"]
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

# ---------------------------------------------------------------- macOS (.dmg)
# Mismo server/llave/marca. En Mac APP_NAME tiene que coincidir con /Applications/<APP_NAME>.app
# y con el ejecutable de dentro, asi que tambien cambia PRODUCT_NAME y todas las rutas RustDesk.app.
MARCA_MAC = {
    "name": "TeraDesk - nombre e iconos propios (Mac)",
    "shell": "bash",
    "run": (
        "set -e\n"
        "F=libs/hbb_common/src/config.rs\n"
        "sed -i '' 's|RwLock::new(\"RustDesk\".to_owned())|RwLock::new(\"TeraDesk\".to_owned())|' $F\n"
        "grep -q 'RwLock::new(\"TeraDesk\".to_owned())' $F || { echo 'NO SE CAMBIO APP_NAME'; exit 1; }\n"
        "cp teradesk/marca/icon.png res/icon.png\n"
        "cp teradesk/marca/icon.ico flutter/assets/icon.ico\n"
        "cp teradesk/marca/icon.png flutter/assets/icon.png\n"
        "cp teradesk/marca/logo.png teradesk/marca/logo_light.png teradesk/marca/logo_dark.png flutter/assets/\n"
        "D=flutter/lib/common.dart\n"
        "sed -i '' 's|if (bind.mainGetBuildinOption(key: \"hide-powered-by-me\") == .Y.) {|if (true) {|' $D\n"
        "grep -q 'if (true) {' $D || { echo 'NO SE OCULTO powered_by'; exit 1; }\n"
        "X=flutter/macos/Runner/Configs/AppInfo.xcconfig\n"
        "sed -i '' -e 's|^PRODUCT_NAME = .*|PRODUCT_NAME = TeraDesk|' "
        "-e 's|^PRODUCT_BUNDLE_IDENTIFIER = .*|PRODUCT_BUNDLE_IDENTIFIER = com.teranet.teradesk|' $X\n"
        "P=flutter/macos/Runner/Info.plist\n"
        "sed -i '' -e 's|<string>com.carriez.rustdesk</string>|<string>com.teranet.teradesk</string>|' "
        "-e 's|<string>rustdesk</string>|<string>teradesk</string>|' $P\n"
        "sed -i '' 's|RustDesk.app|TeraDesk.app|g' build.py flutter/macos/Runner.xcodeproj/project.pbxproj\n"
        "cp teradesk/marca/AppIcon.icns flutter/macos/Runner/AppIcon.icns\n"
        "cp teradesk/marca/mac-icon.png res/mac-icon.png\n"
        "grep -n 'PRODUCT_NAME\\|BUNDLE_IDENTIFIER' $X\n"
        "grep -c 'TeraDesk.app' build.py\n"
    ),
}
mac = wf["jobs"]["build-for-macOS"]["steps"]
j = next(k for k, s in enumerate(mac) if s.get("name") == "Checkout source code")
mac.insert(j + 1, dict(PASO, name="TeraDesk - server y llave propios (Mac)",
                       run=PASO["run"].replace("sed -i -E ", "sed -i '' -E ")))
mac.insert(j + 2, MARCA_MAC)
for s in mac:
    for campo in ("run",):
        if campo in s and not s.get("name", "").startswith("TeraDesk"):
            s[campo] = (s[campo].replace("RustDesk.app", "TeraDesk.app")
                        .replace("Contents/MacOS/RustDesk", "Contents/MacOS/TeraDesk")
                        .replace("rustdesk-${{ env.VERSION }}", "TeraDesk-${{ env.VERSION }}")
                        .replace('"rustdesk-${VERSION}', '"TeraDesk-${VERSION}'))
    if s.get("name") == "Publish DMG package":
        s["with"]["files"] = "TeraDesk*-${{ matrix.job.arch }}.dmg\n"
    if s.get("name") == "Upload unsigned macOS app":
        s["with"]["path"] = "TeraDesk-${{ env.VERSION }}-${{ matrix.job.arch }}.dmg"

# Firma con el certificado AUTOFIRMADO de TeraNeT (no es de Apple: no quita el aviso de la primera vez).
# Sin firma, en Mac M (arm64) la app sale "danada" y no abre; firmada en el Mac con "-" abre, pero cada
# version nueva cambia de identidad y Mac pierde los permisos (pantalla negra). Con un certificado FIJO
# la identidad es siempre la misma y los permisos de Grabacion/Accesibilidad sobreviven al actualizar.
# Secrets con nombre propio a proposito: MACOS_P12_BASE64 activaria la firma+notarizacion de upstream.
# El certificado vive en el server: /etc/lab/teradesk-firma-mac/ (si se pierde, los permisos de todos
# los Mac clientes se caen en la siguiente actualizacion).
# Dos pasos: el certificado se IMPORTA al principio (si los secrets estan mal pegados, falla en 1 minuto y
# no tras 25 de compilacion) y se FIRMA antes del dmg. El keychain vive en $RUNNER_TEMP durante el job.
# Los secrets se limpian de espacios/saltos de linea (error tipico al pegarlos en GitHub). El log muestra
# longitud y huella para comparar con el server, nunca los valores:
#   wc -c < /etc/lab/teradesk-firma-mac/firma.p12.b64      -> 3488
#   sha256sum /etc/lab/teradesk-firma-mac/firma.p12        -> empieza por 71d79ab17fa4226d
FIRMA_MAC_IMPORTAR = {
    "name": "TeraDesk - importar certificado de firma (Mac)",
    "if": "env.UPLOAD_ARTIFACT == 'true'",
    "shell": "bash",
    "env": {"P12": "${{ secrets.TERADESK_MAC_P12 }}", "P12_PASS": "${{ secrets.TERADESK_MAC_P12_PASS }}"},
    "run": (
        "set -euo pipefail\n"
        "[ -n \"$P12\" ] || { echo '::error::falta el secret TERADESK_MAC_P12'; exit 1; }\n"
        "P12=$(printf '%s' \"$P12\" | tr -d ' \\r\\n\\t')\n"
        "P12_PASS=$(printf '%s' \"$P12_PASS\" | tr -d ' \\r\\n\\t')\n"
        "echo \"TERADESK_MAC_P12: ${#P12} caracteres (deben ser 3488)\"\n"
        "echo \"TERADESK_MAC_P12_PASS: ${#P12_PASS} caracteres (deben ser 32)\"\n"
        "printf '%s' \"$P12\" | base64 --decode > \"$RUNNER_TEMP/firma.p12\"\n"
        "echo \"huella del p12: $(shasum -a 256 \"$RUNNER_TEMP/firma.p12\" | cut -c1-16) (debe ser 71d79ab17fa4226d)\"\n"
        "KC=\"$RUNNER_TEMP/teradesk.keychain-db\"; KCPASS=$(openssl rand -hex 16)\n"
        "security create-keychain -p \"$KCPASS\" \"$KC\"\n"
        "security set-keychain-settings -lut 21600 \"$KC\"\n"
        "security unlock-keychain -p \"$KCPASS\" \"$KC\"\n"
        "security import \"$RUNNER_TEMP/firma.p12\" -k \"$KC\" -P \"$P12_PASS\" -T /usr/bin/codesign\n"
        "rm -f \"$RUNNER_TEMP/firma.p12\"\n"
        "security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k \"$KCPASS\" \"$KC\" >/dev/null\n"
        "security list-keychains -d user -s \"$KC\" $(security list-keychains -d user | tr -d '\"')\n"
        "security find-identity -p codesigning \"$KC\"\n"
        "# por huella SHA-1: el certificado es autofirmado y no sale como 'valido' en find-identity -v\n"
        "ID=$(security find-certificate -c 'TeraNeT Computadores' -Z \"$KC\" | awk '/SHA-1 hash/{print $3}')\n"
        "[ -n \"$ID\" ] || { echo '::error::no se encontro el certificado en el keychain'; exit 1; }\n"
        "echo \"TERADESK_FIRMA_ID=$ID\" >> \"$GITHUB_ENV\"\n"
    ),
}
FIRMA_MAC = {
    "name": "TeraDesk - firmar con certificado propio (Mac)",
    "if": "env.UPLOAD_ARTIFACT == 'true'",
    "shell": "bash",
    "run": (
        "set -euo pipefail\n"
        "[ -n \"${TERADESK_FIRMA_ID:-}\" ] || { echo '::error::no se importo el certificado'; exit 1; }\n"
        "APP=./flutter/build/macos/Build/Products/Release/TeraDesk.app\n"
        "bash ./.github/scripts/sign-macos-app.sh \"$APP\" \"$TERADESK_FIRMA_ID\" ./flutter/macos/Runner/Release.entitlements\n"
        "codesign -dvv \"$APP\" 2>&1 | grep -E 'Identifier|Authority|TeamIdentifier'\n"
        "echo 'Requisito designado (lo que Mac usa para amarrar los permisos):'\n"
        "codesign -d -r- \"$APP\"\n"
        "codesign -d -r- \"$APP\" 2>&1 | grep -q 'certificate' || { echo '::error::la firma no quedo amarrada al certificado'; exit 1; }\n"
    ),
}
k = next(i for i, s in enumerate(mac) if s.get("name") == "TeraDesk - nombre e iconos propios (Mac)")
mac.insert(k + 1, FIRMA_MAC_IMPORTAR)
k = next(i for i, s in enumerate(mac) if s.get("name") == "create unsigned dmg")
mac.insert(k, FIRMA_MAC)

pub = next(s for s in pasos if s.get("name") == "Publish Release")
pub["with"]["files"] = "./SignOutput/TeraDesk-*.exe\n"

with open(DST, "w") as f:
    f.write("# GENERADO por teradesk/generar-workflow.py - no editar a mano\n")
    y.dump(wf, f)
print("ok ->", DST)
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
wf["name"] = "TeraDesk - compilar Windows x64"  # y macOS (dmg)
wf["on"] = {"workflow_dispatch": None}
# sin esto el GITHUB_TOKEN del fork no puede crear la release (403 en "Publish Release")
wf.insert(list(wf.keys()).index("on") + 1, "permissions", {"contents": "write"})

QUEDAN = ["validate-update-metadata-keys", "generate-bridge",
          "build-RustDeskTempTopMostWindow", "build-for-windows-flutter", "build-for-macOS"]
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

# ---------------------------------------------------------------- macOS (.dmg)
# Mismo server/llave/marca. En Mac APP_NAME tiene que coincidir con /Applications/<APP_NAME>.app
# y con el ejecutable de dentro, asi que tambien cambia PRODUCT_NAME y todas las rutas RustDesk.app.
MARCA_MAC = {
    "name": "TeraDesk - nombre e iconos propios (Mac)",
    "shell": "bash",
    "run": (
        "set -e\n"
        "F=libs/hbb_common/src/config.rs\n"
        "sed -i '' 's|RwLock::new(\"RustDesk\".to_owned())|RwLock::new(\"TeraDesk\".to_owned())|' $F\n"
        "grep -q 'RwLock::new(\"TeraDesk\".to_owned())' $F || { echo 'NO SE CAMBIO APP_NAME'; exit 1; }\n"
        "cp teradesk/marca/icon.png res/icon.png\n"
        "cp teradesk/marca/icon.ico flutter/assets/icon.ico\n"
        "cp teradesk/marca/icon.png flutter/assets/icon.png\n"
        "cp teradesk/marca/logo.png teradesk/marca/logo_light.png teradesk/marca/logo_dark.png flutter/assets/\n"
        "D=flutter/lib/common.dart\n"
        "sed -i '' 's|if (bind.mainGetBuildinOption(key: \"hide-powered-by-me\") == .Y.) {|if (true) {|' $D\n"
        "grep -q 'if (true) {' $D || { echo 'NO SE OCULTO powered_by'; exit 1; }\n"
        "X=flutter/macos/Runner/Configs/AppInfo.xcconfig\n"
        "sed -i '' -e 's|^PRODUCT_NAME = .*|PRODUCT_NAME = TeraDesk|' "
        "-e 's|^PRODUCT_BUNDLE_IDENTIFIER = .*|PRODUCT_BUNDLE_IDENTIFIER = com.teranet.teradesk|' $X\n"
        "P=flutter/macos/Runner/Info.plist\n"
        "sed -i '' -e 's|<string>com.carriez.rustdesk</string>|<string>com.teranet.teradesk</string>|' "
        "-e 's|<string>rustdesk</string>|<string>teradesk</string>|' $P\n"
        "sed -i '' 's|RustDesk.app|TeraDesk.app|g' build.py flutter/macos/Runner.xcodeproj/project.pbxproj\n"
        "cp teradesk/marca/AppIcon.icns flutter/macos/Runner/AppIcon.icns\n"
        "cp teradesk/marca/mac-icon.png res/mac-icon.png\n"
        "grep -n 'PRODUCT_NAME\\|BUNDLE_IDENTIFIER' $X\n"
        "grep -c 'TeraDesk.app' build.py\n"
    ),
}
mac = wf["jobs"]["build-for-macOS"]["steps"]
j = next(k for k, s in enumerate(mac) if s.get("name") == "Checkout source code")
mac.insert(j + 1, dict(PASO, name="TeraDesk - server y llave propios (Mac)",
                       run=PASO["run"].replace("sed -i -E ", "sed -i '' -E ")))
mac.insert(j + 2, MARCA_MAC)
for s in mac:
    for campo in ("run",):
        if campo in s and not s.get("name", "").startswith("TeraDesk"):
            s[campo] = (s[campo].replace("RustDesk.app", "TeraDesk.app")
                        .replace("Contents/MacOS/RustDesk", "Contents/MacOS/TeraDesk")
                        .replace("rustdesk-${{ env.VERSION }}", "TeraDesk-${{ env.VERSION }}")
                        .replace('"rustdesk-${VERSION}', '"TeraDesk-${VERSION}'))
    if s.get("name") == "Publish DMG package":
        s["with"]["files"] = "TeraDesk*-${{ matrix.job.arch }}.dmg\n"
    if s.get("name") == "Upload unsigned macOS app":
        s["with"]["path"] = "TeraDesk-${{ env.VERSION }}-${{ matrix.job.arch }}.dmg"

# Firma con el certificado AUTOFIRMADO de TeraNeT (no es de Apple: no quita el aviso de la primera vez).
# Sin firma, en Mac M (arm64) la app sale "danada" y no abre; firmada en el Mac con "-" abre, pero cada
# version nueva cambia de identidad y Mac pierde los permisos (pantalla negra). Con un certificado FIJO
# la identidad es siempre la misma y los permisos de Grabacion/Accesibilidad sobreviven al actualizar.
# Secrets con nombre propio a proposito: MACOS_P12_BASE64 activaria la firma+notarizacion de upstream.
# El certificado vive en el server: /etc/lab/teradesk-firma-mac/ (si se pierde, los permisos de todos
# los Mac clientes se caen en la siguiente actualizacion).
FIRMA_MAC = {
    "name": "TeraDesk - firmar con certificado propio (Mac)",
    "if": "env.UPLOAD_ARTIFACT == 'true'",
    "shell": "bash",
    "env": {"P12": "${{ secrets.TERADESK_MAC_P12 }}", "P12_PASS": "${{ secrets.TERADESK_MAC_P12_PASS }}"},
    "run": (
        "set -euo pipefail\n"
        "[ -n \"$P12\" ] || { echo '::error::falta el secret TERADESK_MAC_P12'; exit 1; }\n"
        "KC=\"$RUNNER_TEMP/teradesk.keychain-db\"; KCPASS=$(openssl rand -hex 16)\n"
        "echo \"$P12\" | base64 --decode > \"$RUNNER_TEMP/firma.p12\"\n"
        "security create-keychain -p \"$KCPASS\" \"$KC\"\n"
        "security set-keychain-settings -lut 21600 \"$KC\"\n"
        "security unlock-keychain -p \"$KCPASS\" \"$KC\"\n"
        "security import \"$RUNNER_TEMP/firma.p12\" -k \"$KC\" -P \"$P12_PASS\" -T /usr/bin/codesign\n"
        "rm -f \"$RUNNER_TEMP/firma.p12\"\n"
        "security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k \"$KCPASS\" \"$KC\" >/dev/null\n"
        "security list-keychains -d user -s \"$KC\" $(security list-keychains -d user | tr -d '\"')\n"
        "security find-identity -p codesigning \"$KC\"\n"
        "# por huella SHA-1: el certificado es autofirmado y no sale como 'valido' en find-identity -v\n"
        "ID=$(security find-certificate -c 'TeraNeT Computadores' -Z \"$KC\" | awk '/SHA-1 hash/{print $3}')\n"
        "[ -n \"$ID\" ] || { echo '::error::no se encontro el certificado en el keychain'; exit 1; }\n"
        "APP=./flutter/build/macos/Build/Products/Release/TeraDesk.app\n"
        "bash ./.github/scripts/sign-macos-app.sh \"$APP\" \"$ID\" ./flutter/macos/Runner/Release.entitlements\n"
        "codesign -dvv \"$APP\" 2>&1 | grep -E 'Identifier|Authority|TeamIdentifier'\n"
        "echo 'Requisito designado (lo que Mac usa para amarrar los permisos):'\n"
        "codesign -d -r- \"$APP\"\n"
        "codesign -d -r- \"$APP\" 2>&1 | grep -q 'certificate' || { echo '::error::la firma no quedo amarrada al certificado'; exit 1; }\n"
    ),
}
k = next(i for i, s in enumerate(mac) if s.get("name") == "create unsigned dmg")
mac.insert(k, FIRMA_MAC)

pub = next(s for s in pasos if s.get("name") == "Publish Release")
pub["with"]["files"] = "./SignOutput/TeraDesk-*.exe\n"

with open(DST, "w") as f:
    f.write("# GENERADO por teradesk/generar-workflow.py - no editar a mano\n")
    y.dump(wf, f)
print("ok ->", DST)
