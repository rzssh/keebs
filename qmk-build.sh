#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
QMK_HOME="${QMK_HOME:-$REPO_ROOT/.qmk/qmk_firmware}"
QMK_REF="${QMK_REF:-c26449e64f18940c0a57e459eeae465b26502b64}"
QMK_REPO="${QMK_REPO:-https://github.com/qmk/qmk_firmware.git}"
QMK_VENV="${QMK_VENV:-$REPO_ROOT/.qmk/.venv}"
KEYBOARD="${QMK_KEYBOARD:-yetis}"
KEYMAP="${QMK_KEYMAP:-razen}"
KEYBOARD_ROOT="${QMK_KEYBOARD_ROOT:-${KEYBOARD%%/*}}"
OUTPUT_KEYBOARD="${QMK_OUTPUT_KEYBOARD:-$KEYBOARD_ROOT}"
QMK_CONVERT_TO="${QMK_CONVERT_TO:-${CONVERT_TO:-none}}"
KEYBOARD_SRC="$REPO_ROOT/qmk/keyboards/$KEYBOARD_ROOT"
KEYMAP_SRC="$REPO_ROOT/qmk/keyboards/$KEYBOARD/keymaps/$KEYMAP"
KEYMAP_PROFILE="${KEYMAP_PROFILE:-}"
if [[ -z "$KEYMAP_PROFILE" ]]; then
    echo "KEYMAP_PROFILE is required. Use 'just qmk <target>'." >&2
    exit 1
fi
case "${KEYMAP_OS:-${OPERATING_SYSTEM:-1}}" in
    1|linux) KEYMAP_OS=linux ;;
    2|macos) KEYMAP_OS=macos ;;
    3|windows) KEYMAP_OS=windows ;;
    *) echo "Unknown KEYMAP_OS: ${KEYMAP_OS:-${OPERATING_SYSTEM:-}}" >&2; exit 1 ;;
esac
GENERATED_KEYMAP_DIR="$REPO_ROOT/.cache/keymap/$KEYMAP_OS/qmk/$KEYMAP_PROFILE"
ARTIFACT_DIR="$REPO_ROOT/build/qmk/$OUTPUT_KEYBOARD"

if [[ "$KEYBOARD" == "crkbd/rev1" && "$OUTPUT_KEYBOARD" != "cygnus" ]]; then
    echo "No QMK Corne target in this repo. Set QMK_OUTPUT_KEYBOARD=cygnus for Cygnus wiring." >&2
    exit 1
fi

usage() {
    cat <<EOF
Usage: $0 [setup|build|flash|clean|distclean]

Environment overrides:
  QMK_HOME      QMK checkout path (default: $REPO_ROOT/.qmk/qmk_firmware)
  QMK_REF       QMK git ref (default: $QMK_REF)
  QMK_KEYBOARD  Keyboard target (default: $KEYBOARD)
  QMK_KEYMAP    Keymap target (default: $KEYMAP)
  QMK_CONVERT_TO Controller converter (default: $QMK_CONVERT_TO, use none for AVR)
EOF
}

clone_or_update_qmk() {
    if [[ ! -d "$QMK_HOME/.git" ]]; then
        mkdir -p "$(dirname "$QMK_HOME")"
        git clone "$QMK_REPO" "$QMK_HOME"
    fi

    git -C "$QMK_HOME" remote set-url origin "$QMK_REPO"
    if ! git -C "$QMK_HOME" cat-file -e "$QMK_REF^{commit}" 2>/dev/null; then
        git -C "$QMK_HOME" fetch --tags origin
        git -C "$QMK_HOME" fetch origin "$QMK_REF"
    fi
    git -C "$QMK_HOME" checkout "$QMK_REF"
    git -C "$QMK_HOME" submodule update --init --recursive
}

ensure_qmk_cli() {
    if [[ -x "$QMK_VENV/bin/qmk" ]]; then
        export PATH="$QMK_VENV/bin:$PATH"
        return
    fi

    if command -v qmk >/dev/null 2>&1; then
        return
    fi

    python3 -m venv "$QMK_VENV"
    "$QMK_VENV/bin/python" -m pip install -q --upgrade pip
    "$QMK_VENV/bin/python" -m pip install -q qmk
    export PATH="$QMK_VENV/bin:$PATH"
}

link_keymap() {
    if [[ ! -d "$KEYMAP_SRC" ]]; then
        echo "Missing keymap source: $KEYMAP_SRC" >&2
        exit 1
    fi

    local dest="$QMK_HOME/keyboards/$KEYBOARD/keymaps/$KEYMAP"
    mkdir -p "$(dirname "$dest")"
    rm -rf "$dest"
    mkdir -p "$dest"
    cp -a "$KEYMAP_SRC/." "$dest/"
    cp "$GENERATED_KEYMAP_DIR/keymap.c" "$dest/keymap.c"

    local user_dest="$QMK_HOME/users/razen"
    rm -rf "$user_dest"
    mkdir -p "$user_dest"
    cp -a "$REPO_ROOT/qmk/users/razen/." "$user_dest/"
    cp "$GENERATED_KEYMAP_DIR/razen_config.h" "$user_dest/razen_config.h"
}

link_keyboard_definition() {
    if [[ ! -f "$KEYBOARD_SRC/info.json" && ! -f "$KEYBOARD_SRC/keyboard.json" ]]; then
        return
    fi

    local dest="$QMK_HOME/keyboards/$KEYBOARD_ROOT"
    rm -rf "$dest"
    mkdir -p "$dest"
    cp -a "$KEYBOARD_SRC/." "$dest/"
}

patch_keyboard_for_rp2040() {
    if [[ "$KEYBOARD" != "yetis" || "$QMK_CONVERT_TO" != "rp2040_ce" ]]; then
        return
    fi

    python3 - "$QMK_HOME/keyboards/yetis/keyboard.json" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text())
data["pin_compatible"] = "elite_c"
data["bootloader"] = "rp2040"
data.setdefault("features", {})["rgblight"] = True
data.setdefault("ws2812", {})["driver"] = "vendor"
path.write_text(json.dumps(data, indent=4) + "\n")
PY
    if [[ -f "$QMK_HOME/keyboards/yetis/rules.mk" ]]; then
        python3 - "$QMK_HOME/keyboards/yetis/rules.mk" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = [line for line in path.read_text().splitlines() if not line.startswith("PIN_COMPATIBLE")]
path.write_text("\n".join(lines).rstrip() + "\n")
PY
    fi
}

patch_klor_keyboard() {
    if [[ "$KEYBOARD_ROOT" != "klor" ]]; then
        return
    fi

    python3 - "$QMK_HOME/keyboards/klor/rules.mk" "$QMK_HOME/keyboards/klor/config.h" "$QMK_HOME/keyboards/klor/klor.c" "$QMK_HOME/keyboards/klor/halconf.h" <<'PY'
import sys
from pathlib import Path

rules_path = Path(sys.argv[1])
config_path = Path(sys.argv[2])
klor_c_path = Path(sys.argv[3])
halconf_path = Path(sys.argv[4])

rules = rules_path.read_text()
rules = rules.replace("OLED_DRIVER = SSD1306", "OLED_DRIVER = ssd1306")
rules = rules.replace("HAPTIC_DRIVER = DRV2605L", "HAPTIC_DRIVER = drv2605l")
rules = rules.replace("RGB_MATRIX_DRIVER = WS2812", "RGB_MATRIX_DRIVER = ws2812")
if "I2C_DRIVER_REQUIRED = yes" not in rules:
    rules = rules.rstrip() + "\n\nI2C_DRIVER_REQUIRED = yes\n"
rules_path.write_text(rules)

config = config_path.read_text()
config = config.replace('#include "config_common.h"\n', "")
config = config.replace("#define RGB_DI_PIN D3", "#define WS2812_DI_PIN D3")
config = config.replace("#define I2C1_SCL_PIN GP3\n", "")
config = config.replace("#define I2C1_SDA_PIN GP2\n", "")
config = config.replace("#define I2C_DRIVER I2CD1\n", "")
config = config.replace("#define ENCODERS_PAD_A       { F5 }\n", "")
config = config.replace("#define ENCODERS_PAD_B       { F4 }\n", "")
config = config.replace("#define ENCODERS_PAD_A_RIGHT { F4 }\n", "")
config = config.replace("#define ENCODERS_PAD_B_RIGHT { F5 }\n", "")
config = config.replace('#    define OLED_FONT_H  "./lib/glcdfont.c"\n', "")
if "#define I2C1_SCL_PIN D0" not in config:
    config = config.replace(
        "#pragma once\n",
        "#pragma once\n\n#define I2C_DRIVER I2CD1\n#define I2C1_SCL_PIN D0\n#define I2C1_SDA_PIN D1\n\n",
        1,
    )
if "#    define RGB_MATRIX_DEFAULT_ON true" not in config:
    config = config.replace(
        "#    define RGB_MATRIX_SPLIT { 21, 21 }\n",
        "#    define RGB_MATRIX_SPLIT { 21, 21 }\n#    define RGB_MATRIX_STARTUP_MODE RGB_MATRIX_BREATHING\n#    define RGB_MATRIX_DEFAULT_ON true\n",
        1,
    )
config_path.write_text(config)

klor_c = klor_c_path.read_text()
old_oled = """oled_rotation_t oled_init_kb(oled_rotation_t rotation) {
    return OLED_ROTATION_180;
}
"""
new_oled = """#ifdef OLED_ENABLE
oled_rotation_t oled_init_kb(oled_rotation_t rotation) {
    return rotation;
}
#endif
"""
wrapped_old_oled = """#ifdef OLED_ENABLE
oled_rotation_t oled_init_kb(oled_rotation_t rotation) {
    return OLED_ROTATION_180;
}
#endif
"""
double_wrapped_new_oled = """#ifdef OLED_ENABLE
#ifdef OLED_ENABLE
oled_rotation_t oled_init_kb(oled_rotation_t rotation) {
    return rotation;
}
#endif
#endif
"""
if double_wrapped_new_oled in klor_c:
    klor_c = klor_c.replace(double_wrapped_new_oled, new_oled)
if wrapped_old_oled in klor_c:
    klor_c = klor_c.replace(wrapped_old_oled, new_oled)
elif old_oled in klor_c and new_oled not in klor_c:
    klor_c = klor_c.replace(old_oled, new_oled)
klor_c_path.write_text(klor_c)

halconf_path.write_text("""// Copyright 2022 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

#define HAL_USE_I2C TRUE

#include_next <halconf.h>
""")
PY
}

patch_cygnus_keyboard() {
    if [[ "$KEYBOARD" != "crkbd/rev1" || "$OUTPUT_KEYBOARD" != "cygnus" ]]; then
        return
    fi

    python3 - "$QMK_HOME/keyboards/crkbd/rev1/keyboard.json" "$QMK_HOME/keyboards/crkbd/info.json" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
parent_path = Path(sys.argv[2])
data = json.loads(path.read_text())

cygnus_layouts = {
    "LAYOUT_split_3x5_3": {
        "layout": [
            {"matrix": [0, 0], "x": 0, "y": 0.3},
            {"matrix": [0, 1], "x": 1, "y": 0.1},
            {"matrix": [0, 2], "x": 2, "y": 0},
            {"matrix": [0, 3], "x": 3, "y": 0.1},
            {"matrix": [0, 4], "x": 4, "y": 0.2},
            {"matrix": [4, 4], "x": 8, "y": 0.2},
            {"matrix": [4, 3], "x": 9, "y": 0.1},
            {"matrix": [4, 2], "x": 10, "y": 0},
            {"matrix": [4, 1], "x": 11, "y": 0.1},
            {"matrix": [4, 0], "x": 12, "y": 0.3},

            {"matrix": [1, 0], "x": 0, "y": 1.3},
            {"matrix": [1, 1], "x": 1, "y": 1.1},
            {"matrix": [1, 2], "x": 2, "y": 1},
            {"matrix": [1, 3], "x": 3, "y": 1.1},
            {"matrix": [1, 4], "x": 4, "y": 1.2},
            {"matrix": [5, 4], "x": 8, "y": 1.2},
            {"matrix": [5, 3], "x": 9, "y": 1.1},
            {"matrix": [5, 2], "x": 10, "y": 1},
            {"matrix": [5, 1], "x": 11, "y": 1.1},
            {"matrix": [5, 0], "x": 12, "y": 1.3},

            {"matrix": [2, 0], "x": 0, "y": 2.3},
            {"matrix": [2, 1], "x": 1, "y": 2.1},
            {"matrix": [2, 2], "x": 2, "y": 2},
            {"matrix": [2, 3], "x": 3, "y": 2.1},
            {"matrix": [2, 4], "x": 4, "y": 2.2},
            {"matrix": [6, 4], "x": 8, "y": 2.2},
            {"matrix": [6, 3], "x": 9, "y": 2.1},
            {"matrix": [6, 2], "x": 10, "y": 2},
            {"matrix": [6, 1], "x": 11, "y": 2.1},
            {"matrix": [6, 0], "x": 12, "y": 2.3},

            {"matrix": [3, 2], "x": 3, "y": 3.7},
            {"matrix": [3, 3], "x": 4, "y": 3.7},
            {"matrix": [3, 4], "x": 5, "y": 3.2, "h": 1.5},
            {"matrix": [7, 4], "x": 7, "y": 3.2, "h": 1.5},
            {"matrix": [7, 3], "x": 8, "y": 3.7},
            {"matrix": [7, 2], "x": 9, "y": 3.7},
        ]
    }
}

parent = json.loads(parent_path.read_text())
parent.setdefault("features", {})["rgblight"] = False
parent["features"]["rgb_matrix"] = False
parent["layout_aliases"] = {"LAYOUT": "LAYOUT_split_3x5_3"}
parent["community_layouts"] = ["split_3x5_3"]
parent["layouts"] = cygnus_layouts
parent.pop("rgblight", None)
parent.pop("rgb_matrix", None)
parent_path.write_text(json.dumps(parent, indent=4) + "\n")

data["keyboard_name"] = "Cygnus"
data["processor"] = "RP2040"
data["board"] = "GENERIC_RP_RP2040"
data["bootloader"] = "rp2040"
data.pop("development_board", None)
data["matrix_pins"] = {
    "cols": ["GP29", "GP28", "GP27", "GP26", "GP15"],
    "rows": ["GP4", "GP5", "GP6", "GP7"],
}
data["diode_direction"] = "COL2ROW"
data["bootmagic"] = {"matrix": [0, 0]}

data.setdefault("features", {})["rgblight"] = False
data["features"]["rgb_matrix"] = False
data.pop("rgblight", None)
data.pop("rgb_matrix", None)
data.pop("ws2812", None)

data.setdefault("split", {})["serial"] = {"pin": "GP3"}
data["split"]["bootmagic"] = {"matrix": [4, 0]}

data["layouts"] = cygnus_layouts

path.write_text(json.dumps(data, indent=4) + "\n")
PY
}

patch_qmk_python_compat() {
    local math_py="$QMK_HOME/lib/python/qmk/math.py"
    if [[ ! -f "$math_py" ]]; then
        return
    fi

    python3 - "$math_py" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
old = """def _eval(node):
    if isinstance(node, ast.Num):  # <number>
        return node.n
"""
new = """def _eval(node):
    if isinstance(node, ast.Constant):  # <number>
        return node.value
    elif isinstance(node, ast.Num):  # <number>
        return node.n
"""
if old in text and new not in text:
    path.write_text(text.replace(old, new))
PY
}

generate_keymap() {
    if [[ -z "$KEYMAP_PROFILE" ]]; then
        echo "No generator configured for $KEYBOARD:$KEYMAP" >&2
        exit 1
    fi
    "$REPO_ROOT/scripts/generate" qmk --profile "$KEYMAP_PROFILE" --os "$KEYMAP_OS"
}

container_runtime() {
    if [[ -n "${QMK_RUNTIME:-}" ]]; then
        command -v "$QMK_RUNTIME" >/dev/null 2>&1 && echo "$QMK_RUNTIME" && return
    fi
    if command -v podman >/dev/null 2>&1; then
        echo podman
    elif command -v docker >/dev/null 2>&1; then
        echo docker
    fi
}

run_qmk_make() {
    local target="$1"
    local mode="${2:-build}"
    local make_args=("$target")
    if [[ -n "$QMK_CONVERT_TO" && "$QMK_CONVERT_TO" != "none" ]]; then
        make_args+=("CONVERT_TO=$QMK_CONVERT_TO")
    fi
    if [[ "$KEYBOARD" == "crkbd/rev1" && "$OUTPUT_KEYBOARD" == "cygnus" ]]; then
        make_args+=("RAZEN_CYGNUS_QMK=yes")
    fi
    if [[ -n "${QMK_MAKE_ARGS:-}" ]]; then
        read -ra extra_make_args <<< "$QMK_MAKE_ARGS"
        make_args+=("${extra_make_args[@]}")
    fi

    local runtime
    runtime="$(container_runtime)"
    local use_container=0

    if [[ -n "$runtime" && -n "${QMK_RUNTIME:-}" ]]; then
        use_container=1
    elif [[ -n "$runtime" ]] && python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 14) else 1)
PY
    then
        use_container=1
    fi

    if [[ "$use_container" -eq 0 ]] && command -v avr-gcc >/dev/null 2>&1; then
        ensure_qmk_cli
        if make -C "$QMK_HOME" "${make_args[@]}"; then
            return
        fi

        if [[ -n "$runtime" ]]; then
            echo "Local QMK build failed, retrying in $runtime..." >&2
        else
            return 1
        fi
    fi

    if [[ -z "$runtime" ]]; then
        echo "Missing avr-gcc and no Docker/Podman runtime was found." >&2
        echo "Install QMK's AVR toolchain or install Docker/Podman." >&2
        exit 1
    fi

    local uid_arg=()
    [[ "$runtime" == "docker" ]] && uid_arg=(--user "$(id -u):$(id -g)")

    local device_args=()
    if [[ "$mode" == "flash" ]]; then
        device_args=(--privileged -v /dev:/dev)
    fi

    mkdir -p "$QMK_HOME/.build/userspace"
    "$runtime" run --rm \
        "${device_args[@]}" \
        "${uid_arg[@]}" \
        -w /qmk_firmware \
        -v "$QMK_HOME:/qmk_firmware:z" \
        -e QMK_USERSPACE=/qmk_firmware/.build/userspace \
        ghcr.io/qmk/qmk_cli \
        make "${make_args[@]}"
}

build_keymap() {
    clone_or_update_qmk
    patch_qmk_python_compat
    link_keyboard_definition
    patch_keyboard_for_rp2040
    patch_klor_keyboard
    patch_cygnus_keyboard
    generate_keymap
    link_keymap

    mkdir -p "$ARTIFACT_DIR"
    local stamp
    stamp="$(mktemp)"
    touch "$stamp"
    local artifact_base
    artifact_base="${KEYBOARD//\//_}"

    run_qmk_make "$KEYBOARD:$KEYMAP"

    mapfile -t artifacts < <(
        find "$QMK_HOME" -maxdepth 1 -type f -newer "$stamp" \
            \( -name "${artifact_base}*.hex" -o -name "${artifact_base}*.bin" -o -name "${artifact_base}*.uf2" \) | sort
    )
    rm -f "$stamp"

    if ((${#artifacts[@]} == 0)); then
        echo "Build finished, but no firmware artifact was found in $QMK_HOME." >&2
        exit 1
    fi

    for artifact in "${artifacts[@]}"; do
        cp "$artifact" "$ARTIFACT_DIR/"
        echo "-> build/qmk/$OUTPUT_KEYBOARD/$(basename "$artifact")"
    done
}

flash_keymap() {
    clone_or_update_qmk
    patch_qmk_python_compat
    link_keyboard_definition
    patch_keyboard_for_rp2040
    patch_klor_keyboard
    patch_cygnus_keyboard
    generate_keymap
    link_keymap
    run_qmk_make "$KEYBOARD:$KEYMAP:flash" flash
}

action="${1:-build}"
case "$action" in
    setup) clone_or_update_qmk; patch_qmk_python_compat; ensure_qmk_cli; link_keyboard_definition; patch_keyboard_for_rp2040; patch_klor_keyboard; patch_cygnus_keyboard; generate_keymap; link_keymap ;;
    build) build_keymap ;;
    flash) flash_keymap ;;
    clean)
        rm -rf "$ARTIFACT_DIR" "$QMK_HOME/.build"
        ;;
    distclean)
        rm -rf "$REPO_ROOT/.qmk" "$ARTIFACT_DIR"
        ;;
    -h|--help|help) usage ;;
    *) usage; exit 1 ;;
esac
