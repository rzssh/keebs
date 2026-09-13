#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$REPO_ROOT/config"
WORKSPACE_BASE="${ZMK_WORKSPACE_BASE:-$REPO_ROOT/.cache/zmk-workspaces}"
ZEPHYR_SDK_VERSION=0.17.0

find_sdk() {
    local sdk version
    if [[ -n "${ZEPHYR_SDK_INSTALL_DIR:-}" && -d "$ZEPHYR_SDK_INSTALL_DIR" ]]; then
        sdk="$ZEPHYR_SDK_INSTALL_DIR"
    else
        local search_dirs=("$HOME/.local" "$HOME" "/opt" "/usr/local")
        for dir in "${search_dirs[@]}"; do
            if [[ -d "$dir/zephyr-sdk-$ZEPHYR_SDK_VERSION" ]]; then
                sdk="$dir/zephyr-sdk-$ZEPHYR_SDK_VERSION"
                break
            fi
        done
    fi
    if [[ -z "${sdk:-}" ]]; then
        echo "Error: Zephyr SDK $ZEPHYR_SDK_VERSION not found. Install it or set ZEPHYR_SDK_INSTALL_DIR." >&2
        exit 1
    fi
    version="$(tr -d '[:space:]' < "$sdk/sdk_version" 2>/dev/null || true)"
    if [[ "$version" != "$ZEPHYR_SDK_VERSION" ]]; then
        echo "Error: Zephyr SDK $ZEPHYR_SDK_VERSION required; found ${version:-unknown} at $sdk." >&2
        exit 1
    fi
    echo "$sdk"
}

SDK="$(find_sdk)"
export ZEPHYR_SDK_INSTALL_DIR="$SDK"
export ZEPHYR_TOOLCHAIN_VARIANT=zephyr

hosttools="$(find "$SDK/hosttools" -type d -name bin 2>/dev/null | head -1)"
[[ -n "$hosttools" ]] && export PATH="$hosttools:$PATH"

find_keyboard_dir() {
    if [[ -d "$CONFIG_DIR/keyboards/$1" ]]; then
        echo "$CONFIG_DIR/keyboards/$1"
    else
        echo "No keyboard config found for '$1'" >&2
        exit 1
    fi
}

find_manifest() {
    if [[ -f "$KB_DIR/$KEYBOARD.west.yml" ]]; then
        echo "$KEYBOARD.west.yml"
    elif [[ -f "$CONFIG_DIR/default.west.yml" ]]; then
        echo "default.west.yml"
    else
        echo "No west manifest found for '$KEYBOARD'" >&2
        exit 1
    fi
}

uses_nrf52_ble_board() {
    local yml="$KB_DIR/keyboard.yml"
    local board="nice_nano/nrf52840/zmk"

    if [[ -f "$yml" ]]; then
        board="$(python3 -c "
import yaml
with open('$yml') as f:
    d = yaml.safe_load(f) or {}
print(d.get('board', 'nice_nano/nrf52840/zmk'))
")"
    fi

    case "$board" in
        *nrf52*|xiao_ble|glove80)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

get_board_shield() {
    local yml="$KB_DIR/keyboard.yml"
    if [[ -f "$yml" ]]; then
        python3 -c "
import yaml
with open('$yml') as f:
    d = yaml.safe_load(f)
board = d.get('board', 'nice_nano/nrf52840/zmk')
prefix = d.get('shield_prefix', '$KEYBOARD')
suffixes = d.get('split_suffixes', '_left _right')
print(f'{board}|{prefix}|{suffixes}')
"
    else
        echo "nice_nano/nrf52840/zmk|$KEYBOARD|_left _right"
    fi
}

get_custom_build_entries() {
    local action="$1"
    local yml="$KB_DIR/keyboard.yml"
    [[ -f "$yml" ]] || return 0

    ACTION="$action" KEYBOARD="$KEYBOARD" YML="$yml" python3 - <<'PY'
import os
import yaml

with open(os.environ["YML"]) as f:
    data = yaml.safe_load(f) or {}

builds = data.get("builds")
if not builds:
    raise SystemExit

action = os.environ["ACTION"]
aliases = {
    "lh": "left",
    "rh": "right",
}
action = aliases.get(action, action)

if action == "both":
    keys = data.get("default_builds") or list(builds)
elif action in builds:
    keys = [action]
else:
    raise SystemExit

default_board = data.get("board", "nice_nano/nrf52840/zmk")

for key in keys:
    entry = builds[key]
    if isinstance(entry, str):
        entry = {"shield": entry}

    board = entry.get("board", default_board)
    shield = entry.get("shield", "")
    label = entry.get("label") or (shield.split()[0] if shield else board.replace("/", "_"))
    snippets = entry.get("snippets", "")
    if isinstance(snippets, list):
        snippets = " ".join(snippets)

    cmake_args = entry.get("cmake_args", "")
    if isinstance(cmake_args, list):
        cmake_args = " ".join(cmake_args)

    print(f"{board}|{shield}|{label}|{snippets}|{cmake_args}")
PY
}

usage() {
    echo "Usage: $0 <keyboard> [left|right|both|clean|setup|reset]"
    echo ""
    echo "Keyboards:"
    for d in "$CONFIG_DIR"/keyboards/*/; do
        [[ -d "$d" ]] && echo "  $(basename "$d")"
    done
    echo ""
    echo "Examples:"
    echo "  $0 cradio          # build both halves"
    echo "  $0 cradio left     # left hand only"
    echo "  $0 cradio setup    # init west workspace"
    echo "  $0 cradio clean    # remove build artifacts"
    echo "  $0 cradio reset    # build settings_reset firmware"
    echo "  CLEAN=1 $0 cradio  # full rebuild"
    echo "  EXTRA_CONF_PATH=... EXTRA_KEYMAP_PATH=... $0 <keyboard> both"
    exit 1
}

[[ $# -lt 1 ]] && usage

KEYBOARD="$1"
ACTION="${2:-both}"
OUTPUT_KEYBOARD="${ZMK_OUTPUT_KEYBOARD:-$KEYBOARD}"
KB_DIR="$(find_keyboard_dir "$KEYBOARD")"
case "$KEYBOARD" in
    adept|charybdis_nano|flake|glove80|piantor_pro) DEFAULT_WORKSPACE_GROUP="$KEYBOARD" ;;
    *) DEFAULT_WORKSPACE_GROUP=main ;;
esac
WORKSPACE_GROUP="${ZMK_WORKSPACE_GROUP:-$DEFAULT_WORKSPACE_GROUP}"
WORKSPACE="$WORKSPACE_BASE/$WORKSPACE_GROUP"

KEYMAP_PROFILE="${KEYMAP_PROFILE:-}"
KEYMAP_OS="${KEYMAP_OS:-linux}"
if [[ -n "${EXTRA_KEYMAP_PATH:-}" ]]; then
    DEFAULT_KEYMAP_PATH="$EXTRA_KEYMAP_PATH"
elif [[ -n "$KEYMAP_PROFILE" ]]; then
    "$REPO_ROOT/scripts/generate" zmk --profile "$KEYMAP_PROFILE" --os "$KEYMAP_OS" >/dev/null
    DEFAULT_KEYMAP_PATH="$REPO_ROOT/.cache/keymap/$KEYMAP_OS/zmk/$KEYMAP_PROFILE/keymap.keymap"
else
    DEFAULT_KEYMAP_PATH="$KB_DIR/$KEYBOARD.keymap"
fi
[[ ! -f "$DEFAULT_KEYMAP_PATH" ]] && echo "No $KEYBOARD.keymap found" && exit 1
DEFAULT_KEYMAP_PATH="$(realpath "$DEFAULT_KEYMAP_PATH")"

sync_workspace_config() {
    rm -rf "$WORKSPACE/config"
    mkdir -p "$WORKSPACE/config"

    local kb_conf="$KB_DIR/$KEYBOARD.conf"
    local extra_conf="${EXTRA_CONF_PATH:-}"
    local keymap_source="${EXTRA_KEYMAP_PATH:-$DEFAULT_KEYMAP_PATH}"

    [[ -f "$keymap_source" ]] || {
        echo "No keymap found at '$keymap_source'" >&2
        exit 1
    }
    keymap_source="$(realpath "$keymap_source")"

    [[ -f "$CONFIG_DIR/default.west.yml" ]] && ln -sf "$CONFIG_DIR/default.west.yml" "$WORKSPACE/config/"

    for f in "$KB_DIR"/*; do
        [[ -e "$f" && "$(basename "$f")" != "shields" && "$(basename "$f")" != "$KEYBOARD.conf" ]] && ln -sf "$f" "$WORKSPACE/config/"
    done

    ln -sf "$keymap_source" "$WORKSPACE/config/$KEYBOARD.keymap"
    if [[ "$KEYBOARD" == "charybdis_nano" ]]; then
        ln -sf "$keymap_source" "$WORKSPACE/config/charybdis_dongle.keymap"
    fi

    if [[ -f "$kb_conf" ]]; then
        {
            [[ -f "$CONFIG_DIR/default.conf" ]] && cat "$CONFIG_DIR/default.conf"
            uses_nrf52_ble_board && [[ -f "$CONFIG_DIR/nrf52_ble.conf" ]] && cat "$CONFIG_DIR/nrf52_ble.conf"
            cat "$kb_conf"
            [[ -n "$extra_conf" && -f "$extra_conf" ]] && cat "$extra_conf"
        } > "$WORKSPACE/config/$KEYBOARD.conf"
    elif [[ -f "$CONFIG_DIR/default.conf" ]]; then
        if [[ -n "$extra_conf" && -f "$extra_conf" ]]; then
            {
                cat "$CONFIG_DIR/default.conf"
                uses_nrf52_ble_board && [[ -f "$CONFIG_DIR/nrf52_ble.conf" ]] && cat "$CONFIG_DIR/nrf52_ble.conf"
                cat "$extra_conf"
            } > "$WORKSPACE/config/$KEYBOARD.conf"
        else
            if uses_nrf52_ble_board && [[ -f "$CONFIG_DIR/nrf52_ble.conf" ]]; then
                {
                    cat "$CONFIG_DIR/default.conf"
                    cat "$CONFIG_DIR/nrf52_ble.conf"
                } > "$WORKSPACE/config/$KEYBOARD.conf"
            else
                ln -sf "$CONFIG_DIR/default.conf" "$WORKSPACE/config/$KEYBOARD.conf"
                ln -sf "$CONFIG_DIR/default.conf" "$WORKSPACE/config/default.conf"
            fi
        fi
    fi

    local config_prefix="$KEYBOARD"
    if [[ -f "$KB_DIR/keyboard.yml" ]]; then
        config_prefix="$(python3 -c "
import yaml
with open('$KB_DIR/keyboard.yml') as f:
    d = yaml.safe_load(f) or {}
print(d.get('config_prefix', '$KEYBOARD'))
")"
    fi
    if [[ "$config_prefix" != "$KEYBOARD" ]]; then
        ln -sf "$WORKSPACE/config/$KEYBOARD.conf" "$WORKSPACE/config/$config_prefix.conf"
    fi

    if [[ -d "$KB_DIR/shields" ]]; then
        mkdir -p "$WORKSPACE/config/boards"
        ln -sf "$KB_DIR/shields" "$WORKSPACE/config/boards/shields"
    fi
}

apply_patches() {
    "$REPO_ROOT/scripts/apply-zmk-patches" "$WORKSPACE"
    if [[ -d "$KB_DIR/shields" ]]; then
        for patch in "$KB_DIR"/shields/*/*.patch; do
            [[ -f "$patch" ]] || continue
            if git -C "$WORKSPACE/zephyr" apply --reverse --check "$patch" 2>/dev/null; then
                continue
            fi
            git -C "$WORKSPACE/zephyr" apply --check "$patch"
            git -C "$WORKSPACE/zephyr" apply "$patch"
        done
    fi
}

setup_workspace() {
    echo "Setting up $WORKSPACE_GROUP west workspace at $WORKSPACE ..."
    sync_workspace_config
    cd "$WORKSPACE"
    if [[ ! -d .west ]]; then
        west init -l config/ --mf "$(find_manifest)"
    fi
    while IFS= read -r project_path; do
        mkdir -p "$(dirname "$project_path")"
    done < <(west list -f '{abspath}')
    west update --narrow
    apply_patches
    if [[ ! -x "$WORKSPACE/.venv/bin/west" ]] || [[ "$(head -n 1 "$WORKSPACE/.venv/bin/west")" != "#!$WORKSPACE/.venv/bin/python3" ]]; then
        rm -rf "$WORKSPACE/.venv"
        python3 -m venv "$WORKSPACE/.venv"
        "$WORKSPACE/.venv/bin/pip" install -q -r "$WORKSPACE/zephyr/scripts/requirements.txt"
        "$WORKSPACE/.venv/bin/pip" install -q -U protobuf
        "$WORKSPACE/.venv/bin/pip" install -q --ignore-installed west
    fi
    echo "Done. Workspace ready at $WORKSPACE"
}

if [[ "$ACTION" == "setup" ]]; then
    setup_workspace
    exit 0
fi

if [[ ! -d "$WORKSPACE/.west" ]]; then
    echo "Workspace not initialized. Run: $0 $KEYBOARD setup"
    exit 1
fi

reset_conf="$KB_DIR/$KEYBOARD.reset.conf"
if [[ "$ACTION" == "reset" && ! -f "$reset_conf" ]]; then
    IFS='|' read -r board _ _ <<< "$(get_board_shield)"
    export ZEPHYR_BASE="$WORKSPACE/zephyr"
    export CMAKE_PREFIX_PATH="$WORKSPACE/zephyr/share/zephyr-package/cmake"
    [[ -d "$WORKSPACE/.venv" ]] && source "$WORKSPACE/.venv/bin/activate"
    cd "$WORKSPACE"
    cmake -E remove_directory "build/$OUTPUT_KEYBOARD/settings_reset"
    west build -d "build/$OUTPUT_KEYBOARD/settings_reset" -s zmk/app -b "$board" -- -DSHIELD=settings_reset
    out="$REPO_ROOT/build/$OUTPUT_KEYBOARD"
    mkdir -p "$out"
    cp "build/$OUTPUT_KEYBOARD/settings_reset/zephyr/zmk.uf2" "$out/settings_reset.uf2"
    echo "→ build/$OUTPUT_KEYBOARD/settings_reset.uf2"
    echo "Flash this to BOTH halves to clear bonds."
    exit 0
fi

"$REPO_ROOT/scripts/generate" check

if [[ "$ACTION" == "reset" && -f "$reset_conf" && -z "${EXTRA_CONF_PATH:-}" ]]; then
    export EXTRA_CONF_PATH="$reset_conf"
fi

sync_workspace_config

export ZEPHYR_BASE="$WORKSPACE/zephyr"
export CMAKE_PREFIX_PATH="$WORKSPACE/zephyr/share/zephyr-package/cmake"
[[ -d "$WORKSPACE/.venv" ]] && source "$WORKSPACE/.venv/bin/activate"
cd "$WORKSPACE"

missing_projects=()
while IFS='|' read -r project project_path; do
    [[ -d "$project_path" ]] || missing_projects+=("$project")
done < <(west list -f '{name}|{abspath}')
if ((${#missing_projects[@]})); then
    echo "Workspace is missing manifest projects: ${missing_projects[*]}" >&2
    echo "Run: $0 $KEYBOARD setup" >&2
    exit 1
fi

apply_patches

revision_mismatches=()
while IFS='|' read -r project revision project_path; do
    [[ -d "$project_path/.git" ]] || continue
    if [[ "$revision" =~ ^[0-9a-f]{40}$ ]]; then
        expected="$revision"
    else
        expected="$(git -C "$project_path" rev-parse refs/heads/manifest-rev 2>/dev/null || true)"
    fi
    actual="$(git -C "$project_path" rev-parse HEAD)"
    if [[ -z "$expected" || "$actual" != "$expected" ]]; then
        revision_mismatches+=("$project")
    fi
done < <(west list -f '{name}|{revision}|{abspath}')
if ((${#revision_mismatches[@]})); then
    echo "Updating stale workspace projects: ${revision_mismatches[*]}"
    west update --narrow
    apply_patches
fi

build_entry() {
    local board=$1 shield=${2:-} label=${3:-} entry_snippets=${4:-} entry_cmake_args=${5:-}
    if [[ -z "$label" ]]; then
        if [[ -n "$shield" ]]; then
            read -ra _shield_parts <<< "$shield"
            label="${_shield_parts[0]}"
        else
            label="${board//\//_}"
        fi
    fi

    if [[ "${CLEAN:-}" == "1" || ( "$ACTION" == "reset" && -n "${EXTRA_CONF_PATH:-}" ) ]]; then
        rm -rf "build/$OUTPUT_KEYBOARD/$label"
    fi

    local keymap_file="$DEFAULT_KEYMAP_PATH"
    [[ -f "$KB_DIR/$label.keymap" ]] && keymap_file="$(realpath "$KB_DIR/$label.keymap")"
    local cmake_args=("-DZMK_CONFIG=$WORKSPACE/config" "-DKEYMAP_FILE=$keymap_file" "-DZMK_EXTRA_MODULES=$CONFIG_DIR/modules/layer-chord")
    local snippet_args=()
    if [[ -n "$shield" ]]; then
        cmake_args+=("-DSHIELD=$shield")
    fi
    local snippets="${EXTRA_SNIPPETS:-}"
    if [[ -n "$entry_snippets" ]]; then
        snippets="${snippets:+$snippets }$entry_snippets"
    fi
    if [[ -n "$snippets" ]]; then
        read -ra _snippets <<< "$snippets"
        for snippet in "${_snippets[@]}"; do
            snippet_args+=("-S" "$snippet")
        done
    fi
    if [[ -n "$entry_cmake_args" ]]; then
        read -ra _extra_cmake <<< "$entry_cmake_args"
        cmake_args+=("${_extra_cmake[@]}")
    fi
    west build -d "build/$OUTPUT_KEYBOARD/$label" -s zmk/app -b "$board" "${snippet_args[@]}" -- "${cmake_args[@]}"

    local out="$REPO_ROOT/build/$OUTPUT_KEYBOARD"
    mkdir -p "$out"
    cp "build/$OUTPUT_KEYBOARD/$label/zephyr/zmk.uf2" "$out/${label}.uf2"
    echo "→ build/$OUTPUT_KEYBOARD/${label}.uf2"
}

if custom_entries="$(get_custom_build_entries "$ACTION")" && [[ -n "$custom_entries" ]]; then
    while IFS='|' read -r entry_board entry_shield entry_label entry_snippets entry_cmake_args; do
        [[ -n "$entry_board" ]] || continue
        build_entry "$entry_board" "$entry_shield" "$entry_label" "$entry_snippets" "$entry_cmake_args"
    done <<< "$custom_entries"
    exit 0
fi

IFS='|' read -r board shield_prefix suffixes <<< "$(get_board_shield)"
read -ra suffix_arr <<< "$suffixes"

case "$ACTION" in
    left|lh)
        if [[ -n "$shield_prefix" ]]; then
            build_entry "$board" "${shield_prefix}${suffix_arr[0]}"
        else
            build_entry "${board}${suffix_arr[0]}" ""
        fi ;;
    right|rh)
        if [[ -n "$shield_prefix" ]]; then
            build_entry "$board" "${shield_prefix}${suffix_arr[1]}"
        else
            build_entry "${board}${suffix_arr[1]}" ""
        fi ;;
    both)
        for sfx in "${suffix_arr[@]}"; do
            if [[ -n "$shield_prefix" ]]; then
                build_entry "$board" "${shield_prefix}${sfx}"
            else
                build_entry "${board}${sfx}" ""
            fi
        done
        ;;
    reset)
        cmake -E remove_directory "build/$OUTPUT_KEYBOARD/settings_reset"
        west build -d "build/$OUTPUT_KEYBOARD/settings_reset" -s zmk/app -b "$board" -- -DSHIELD=settings_reset
        out="$REPO_ROOT/build/$OUTPUT_KEYBOARD"
        mkdir -p "$out"
        cp "build/$OUTPUT_KEYBOARD/settings_reset/zephyr/zmk.uf2" "$out/settings_reset.uf2"
        echo "→ build/$OUTPUT_KEYBOARD/settings_reset.uf2"
        echo "Flash this to BOTH halves to clear bonds."
        ;;
    clean)
        rm -rf "build/$OUTPUT_KEYBOARD" "$REPO_ROOT/build/$OUTPUT_KEYBOARD"
        echo "Cleaned."
        ;;
    *) usage ;;
esac
