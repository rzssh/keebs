#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any


ROOT_FILES = ("keymap.toml", "layers.toml", "behaviors.toml", "profiles.json")
ROW_COUNTS = {"core30": [10, 10, 6, 4], "core34": [10, 10, 10, 4]}
MOD_ALIASES = {"LSHIFT": "LSHFT", "RSHIFT": "RSHFT"}
MODS = {"LGUI", "LALT", "LCTRL", "LSHFT", "RSHFT", "RCTRL", "RALT", "RGUI"} | set(MOD_ALIASES)
KEYS = {
    "SPACE", "RET", "ESC", "TAB", "CAPS", "BSPC", "DEL", "INS",
    "PSCRN", "PAUSE_BREAK", "PG_UP", "PG_DN", "UP", "DOWN", "LEFT", "RIGHT", "HOME", "END",
    "C_PREV", "C_PP", "C_NEXT", "C_MUTE", "POWER", "SLEEP",
    "COMMA", "DOT", "SEMI", "SQT", "MINUS", "EQUAL", "FSLH", "BSLH",
    "LBKT", "RBKT", "GRAVE",
} | MODS | {chr(value) for value in range(ord("A"), ord("Z") + 1)} | {
    f"N{value}" for value in range(10)
} | {f"F{value}" for value in range(1, 25)}
SHIFTED = {
    "AMPS": "N7", "AT": "N2", "CARET": "N6", "COLON": "SEMI",
    "DLLR": "N4", "DQT": "SQT", "EXCL": "N1", "GT": "DOT",
    "HASH": "N3", "LBRC": "LBKT", "LPAR": "N9", "LT": "COMMA",
    "PIPE": "BSLH", "PLUS": "EQUAL", "PRCNT": "N5", "QMARK": "FSLH",
    "RBRC": "RBKT", "RPAR": "N0", "STAR": "N8", "TILDE": "GRAVE",
    "UNDER": "MINUS",
}
QMK_KEYS = {
    "SPACE": "KC_SPC", "RET": "KC_ENT", "ESC": "KC_ESC", "TAB": "KC_TAB",
    "CAPS": "KC_CAPS", "BSPC": "KC_BSPC", "DEL": "KC_DEL", "INS": "KC_INS",
    "PSCRN": "KC_PSCR", "PAUSE_BREAK": "KC_PAUS",
    "PG_UP": "KC_PGUP", "PG_DN": "KC_PGDN", "UP": "KC_UP", "DOWN": "KC_DOWN",
    "LEFT": "KC_LEFT", "RIGHT": "KC_RGHT", "HOME": "KC_HOME", "END": "KC_END",
    "C_PREV": "KC_MPRV", "C_PP": "KC_MPLY", "C_NEXT": "KC_MNXT", "C_MUTE": "KC_MUTE",
    "POWER": "KC_PWR", "SLEEP": "KC_SLEP", "COMMA": "KC_COMM", "DOT": "KC_DOT",
    "SEMI": "KC_SCLN", "SQT": "KC_QUOT", "MINUS": "KC_MINS", "EQUAL": "KC_EQL",
    "FSLH": "KC_SLSH", "BSLH": "KC_BSLS", "LBKT": "KC_LBRC", "RBKT": "KC_RBRC",
    "GRAVE": "KC_GRV", "LGUI": "KC_LGUI", "LALT": "KC_LALT", "LCTRL": "KC_LCTL",
    "LSHFT": "KC_LSFT", "RSHFT": "KC_RSFT", "RCTRL": "KC_RCTL", "RALT": "KC_RALT",
    "RGUI": "KC_RGUI",
}
QMK_MODS = {
    "LGUI": "G", "LALT": "A", "LCTRL": "C", "LSHFT": "S",
    "RGUI": "G", "RALT": "A", "RCTRL": "C", "RSHFT": "S",
}
QMK_ONESHOT_MODS = {
    "LGUI": "MOD_LGUI", "LALT": "MOD_LALT", "LCTRL": "MOD_LCTL", "LSHFT": "MOD_LSFT",
    "RGUI": "MOD_RGUI", "RALT": "MOD_RALT", "RCTRL": "MOD_RCTL", "RSHFT": "MOD_RSFT",
}
ZMK_MODS = {
    "LGUI": "LG", "LALT": "LA", "LCTRL": "LC", "LSHFT": "LS",
    "RGUI": "RG", "RALT": "RA", "RCTRL": "RC", "RSHFT": "RS",
}
MOUSE_ZMK = {
    "MOVE_UP": "&mmv MOVE_UP", "MOVE_DOWN": "&mmv MOVE_DOWN",
    "MOVE_LEFT": "&mmv MOVE_LEFT", "MOVE_RIGHT": "&mmv MOVE_RIGHT",
    "SCRL_UP": "&msc SCRL_UP", "SCRL_DOWN": "&msc SCRL_DOWN",
    "SCRL_LEFT": "&msc SCRL_LEFT", "SCRL_RIGHT": "&msc SCRL_RIGHT",
    "LCLK": "&mkp LCLK", "RCLK": "&mkp RCLK", "MCLK": "&mkp MCLK",
    "MB4": "&mkp MB4", "MB5": "&mkp MB5",
}
MOUSE_QMK = {
    "MOVE_UP": "MS_UP", "MOVE_DOWN": "MS_DOWN", "MOVE_LEFT": "MS_LEFT",
    "MOVE_RIGHT": "MS_RGHT", "SCRL_UP": "MS_WHLU", "SCRL_DOWN": "MS_WHLD",
    "SCRL_LEFT": "MS_WHLL", "SCRL_RIGHT": "MS_WHLR", "LCLK": "MS_BTN1",
    "RCLK": "MS_BTN2", "MCLK": "MS_BTN3", "MB4": "MS_BTN4", "MB5": "MS_BTN5",
}
RGB_ZMK = {
    "hue_decrease": "RGB_HUD", "hue_increase": "RGB_HUI",
    "effect_reverse": "RGB_EFR", "effect_forward": "RGB_EFF",
    "brightness_decrease": "RGB_BRD", "brightness_increase": "RGB_BRI",
    "toggle": "RGB_TOG", "speed_decrease": "RGB_SPD", "speed_increase": "RGB_SPI",
    "saturation_decrease": "RGB_SAD", "saturation_increase": "RGB_SAI",
}
ZMK_KEYS = {"SLEEP": "C_SLEEP", "POWER": "C_POWER", "PSCRN": "PSCRN", "PAUSE_BREAK": "PAUSE_BREAK"}


def mdi(name: str) -> str:
    return f"$$mdi:{name}$$"


DISPLAY = {
    "SPACE": mdi("keyboard-space"), "RET": mdi("keyboard-return"), "ESC": mdi("keyboard-esc"),
    "TAB": mdi("keyboard-tab"), "BSPC": mdi("backspace"), "DEL": mdi("backspace-reverse"),
    "PG_UP": mdi("arrow-collapse-up"), "PG_DN": mdi("arrow-collapse-down"), "UP": mdi("arrow-up"),
    "DOWN": mdi("arrow-down"), "LEFT": mdi("arrow-left"), "RIGHT": mdi("arrow-right"),
    "HOME": mdi("arrow-collapse-left"), "END": mdi("arrow-collapse-right"),
    "C_PREV": mdi("skip-previous"), "C_PP": mdi("play-pause"), "C_NEXT": mdi("skip-next"),
    "C_MUTE": mdi("volume-mute"), "POWER": mdi("power"), "SLEEP": mdi("moon-waning-crescent"),
    "COMMA": ",", "DOT": ".", "SEMI": ";", "SQT": "'", "MINUS": "-", "EQUAL": "=",
    "FSLH": "/", "BSLH": "\\", "LBKT": "[", "RBKT": "]", "GRAVE": "`",
    "AMPS": "&", "AT": "@", "CARET": "^", "COLON": ":", "DLLR": "$", "DQT": '"',
    "EXCL": "!", "GT": ">", "HASH": "#", "LBRC": "{", "LPAR": "(", "LT": "<",
    "PIPE": "|", "PLUS": "+", "PRCNT": "%", "QMARK": "?", "RBRC": "}", "RPAR": ")",
    "STAR": "*", "TILDE": "~", "UNDER": "_", "CAPS": "Caps", "PSCRN": "PrtSc", "PAUSE_BREAK": "Pause", "LGUI": "❖", "RGUI": "❖",
    "LALT": "⌥", "RALT": "⌥", "LCTRL": "⌃", "RCTRL": "⌃", "LSHFT": mdi("arrow-up-bold"),
    "RSHFT": mdi("arrow-up-bold"),
}
DRAW_SHORTCUTS = {
    ("C", "LCTRL"): mdi("content-copy"),
    ("F5", "LGUI"): mdi("microphone-off"),
    ("F6", "LGUI"): mdi("volume-mute"),
    ("G", "LSHFT"): "G",
    ("O", "LGUI"): "Space ←",
    ("S", "LALT", "LGUI"): "STT",
    ("U", "LGUI"): "Space →",
    ("V", "LCTRL"): "⌃V",
    ("X", "LCTRL"): mdi("content-cut"),
    ("Z", "LCTRL"): mdi("undo"),
    ("Z", "LCTRL", "LSHFT"): mdi("redo"),
}
OS_DISPLAY = {
    "home": mdi("arrow-collapse-left"),
    "end": mdi("arrow-collapse-right"),
    "delete_word_left": mdi("backspace-outline"),
    "delete_word_right": mdi("backspace-reverse-outline"),
    "undo": mdi("undo"),
    "redo": mdi("redo"),
    "lock": mdi("lock"),
    "shutdown": mdi("power"),
    "sleep": mdi("moon-waning-crescent"),
    "cut": mdi("content-cut"),
    "copy": mdi("content-copy"),
    "paste": mdi("content-paste"),
    "select_all": mdi("select-all"),
    "screenshot_full": {"t": mdi("monitor-screenshot"), "s": "Scr"},
    "screenshot_area": {"t": mdi("crop"), "s": "Scr"},
}
MOUSE_DISPLAY = {
    "MOVE_UP": "Mouse ↑", "MOVE_DOWN": "Mouse ↓", "MOVE_LEFT": "Mouse ←", "MOVE_RIGHT": "Mouse →",
    "SCRL_UP": "Scroll ↑", "SCRL_DOWN": "Scroll ↓", "SCRL_LEFT": "Scroll ←", "SCRL_RIGHT": "Scroll →",
    "LCLK": "LMB", "RCLK": "RMB", "MCLK": "MMB", "MB4": "MB4", "MB5": "MB5",
}
RGB_DISPLAY = {
    "hue_decrease": "RGB HUD", "hue_increase": "RGB HUI", "effect_reverse": "RGB EFR",
    "effect_forward": "RGB EFF", "brightness_decrease": "RGB BRD", "brightness_increase": "RGB BRI",
    "toggle": "RGB TOG", "speed_decrease": "RGB SPD", "speed_increase": "RGB SPI",
    "saturation_decrease": "RGB SAD", "saturation_increase": "RGB SAI",
}


class KeymapError(ValueError):
    pass


def fail(message: str) -> None:
    raise KeymapError(message)


def ident(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    if not result:
        fail(f"invalid identifier {value!r}")
    return result


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def expand_modifier_chords(model: dict[str, Any]) -> None:
    source = model["behaviors"]
    behaviors = source.setdefault("behaviors", {})
    combos = source.setdefault("combos", [])
    behavior_names = set(behaviors)
    combo_names = {combo.get("name") for combo in combos if isinstance(combo, dict)}
    for family in source.get("modifier_chords", []):
        if not isinstance(family, dict) or not isinstance(family.get("name"), str) or not family["name"]:
            fail("modifier chord family needs a name")
        modifiers = family.get("modifiers")
        if not isinstance(modifiers, list) or not 1 <= len(modifiers) <= 4:
            fail(f"modifier chord family {family['name']}: needs one through four modifiers")
        fields = ("name", "behavior", "position")
        if any(not isinstance(item, dict) or any(not isinstance(item.get(field), str) or not item[field] for field in fields) for item in modifiers):
            fail(f"modifier chord family {family['name']}: invalid modifier")
        for field in fields:
            values = [item[field] for item in modifiers]
            if len(values) != len(set(values)):
                fail(f"modifier chord family {family['name']}: duplicate modifier {field}")
        for count in range(1, len(modifiers) + 1):
            for selected in itertools.combinations(modifiers, count):
                name = f"{family['name']}_{'_'.join(item['name'] for item in selected)}_chord"
                if name in behavior_names or name in combo_names:
                    fail(f"modifier chord family {family['name']}: generated name {name!r} already exists")
                behavior_names.add(name)
                combo_names.add(name)
                behaviors[name] = {
                    "recipe": "layer_sticky_mod",
                    "targets": ["zmk"],
                    "layer": family["layer"],
                    "modifier_behaviors": [item["behavior"] for item in selected],
                    "layer_position": family["layer_position"],
                    "modifier_positions": [item["position"] for item in selected],
                }
                combo = {
                    "name": name,
                    "positions": [family["layer_position"], *(item["position"] for item in selected)],
                    "layers": family["layers"],
                    "action": {"use": name},
                    "term_ms": family["term_ms"],
                    "prior_idle_ms": family.get("prior_idle_ms", 0),
                    "slow_release": True,
                    "draw": False,
                }
                if "variants" in family:
                    combo["variants"] = family["variants"]
                combos.append(combo)


def load_sources(repo: Path) -> dict[str, Any]:
    base = repo / "keymap"
    missing = [name for name in ROOT_FILES if not (base / name).is_file()]
    if missing:
        fail(f"missing source files: {', '.join(missing)}")
    with (base / "keymap.toml").open("rb") as source:
        root = tomllib.load(source)
    with (base / "layers.toml").open("rb") as source:
        layers = tomllib.load(source)
    with (base / "behaviors.toml").open("rb") as source:
        behaviors = tomllib.load(source)
    profiles = json.loads((base / "profiles.json").read_text())
    model = {"root": root, "layers": layers, "behaviors": behaviors, "profiles": profiles}
    expand_modifier_chords(model)
    validate(model)
    return model


def flattened(variant: dict[str, Any]) -> list[Any]:
    if "bindings" in variant:
        return variant["bindings"]
    return [cell for row in variant.get("rows", []) for cell in row]


def profile_slots(model: dict[str, Any], profile: dict[str, Any], backend: str) -> list[str]:
    slots = profile.get(f"{backend}_slots")
    if slots is not None:
        return slots
    topology = profile.get("position_set")
    if topology is None:
        fail(f"profile has no {backend} slots or position_set")
    try:
        return model["profiles"]["topologies"][topology]
    except KeyError:
        fail(f"unknown topology {topology!r}")


def key_alias(model: dict[str, Any], token: str) -> dict[str, Any] | None:
    value = model["behaviors"].get("keys", {}).get(token)
    return value if isinstance(value, dict) else None


def valid_key(model: dict[str, Any], token: str) -> bool:
    return token in KEYS or token in SHIFTED or key_alias(model, token) is not None


def validate_action(model: dict[str, Any], value: Any, context: str) -> None:
    if isinstance(value, str):
        if value not in {"none", "trans"} and not valid_key(model, value):
            fail(f"{context}: unknown key {value!r}")
        return
    if not isinstance(value, dict):
        fail(f"{context}: action must be a string or table")
    if "tap" in value or "hold" in value:
        if "tap" not in value or "hold" not in value:
            fail(f"{context}: tap-hold requires tap and hold")
        validate_action(model, value["tap"], f"{context}.tap")
        hold = value["hold"]
        if isinstance(hold, str):
            if not valid_key(model, hold):
                fail(f"{context}: unknown hold key {hold!r}")
        else:
            validate_action(model, hold, f"{context}.hold")
        timing = value.get("timing")
        if timing and timing not in model["behaviors"].get("timings", {}):
            fail(f"{context}: unknown timing {timing!r}")
        if "hand" in value and value["hand"] not in {"left", "right"}:
            fail(f"{context}: hand must be left or right")
        if "adaptive" in value and value["adaptive"] not in model["behaviors"].get("adaptives", {}):
            fail(f"{context}: unknown adaptive set {value['adaptive']!r}")
        return
    kinds = [name for name in ("use", "key", "os", "layer", "mouse", "light", "rgb", "platform") if name in value]
    if len(kinds) != 1:
        fail(f"{context}: action needs exactly one action kind")
    kind = kinds[0]
    if kind == "use":
        if value["use"] not in model["behaviors"].get("behaviors", {}):
            fail(f"{context}: unknown behavior {value['use']!r}")
    elif kind == "key":
        if not valid_key(model, value["key"]):
            fail(f"{context}: unknown key {value['key']!r}")
        unknown = set(value.get("mods", [])) - MODS
        if unknown:
            fail(f"{context}: unknown modifiers {sorted(unknown)}")
    elif kind == "os":
        for os_name, os_actions in model["root"].get("operating_systems", {}).items():
            if value["os"] not in os_actions:
                fail(f"{context}: OS action {value['os']!r} missing for {os_name}")
    elif kind == "layer":
        if value["layer"] not in model["root"]["layers"]:
            fail(f"{context}: unknown layer {value['layer']!r}")
        if value.get("mode", "momentary") not in {"momentary", "toggle", "sticky", "move"}:
            fail(f"{context}: invalid layer mode")
    elif kind == "mouse" and value["mouse"] not in MOUSE_ZMK:
        fail(f"{context}: unknown mouse action {value['mouse']!r}")
    elif kind == "light" and value["light"] not in {"toggle", "decrease", "increase"}:
        fail(f"{context}: unknown light action {value['light']!r}")
    elif kind == "rgb" and value["rgb"] not in RGB_ZMK:
        fail(f"{context}: unknown RGB action {value['rgb']!r}")


def validate(model: dict[str, Any]) -> None:
    root = model["root"]
    layer_source = model["layers"].get("layers", {})
    behavior_source = model["behaviors"]
    profile_source = model["profiles"]
    if root.get("version") != 1 or profile_source.get("version") != 1:
        fail("source version must be 1")
    if root.get("layer_source") != "layers.toml" or root.get("behavior_source") != "behaviors.toml" or root.get("profile_source") != "profiles.json":
        fail("keymap.toml source entry points changed")
    if root.get("default_os") not in root.get("operating_systems", {}):
        fail("default_os is not declared")
    declared_layers = root.get("layers", [])
    if not declared_layers or any(not isinstance(name, str) or not name for name in declared_layers):
        fail("layer order must contain non-empty names")
    if len(declared_layers) != len(set(declared_layers)):
        fail("layer order contains duplicates")
    layer_identifiers = [qmk_layer(name) for name in declared_layers]
    if len(layer_identifiers) != len(set(layer_identifiers)):
        fail("layer names produce duplicate QMK identifiers")
    if root.get("default_layer") != declared_layers[0]:
        fail("default_layer must be first in layer order")
    disabled_layers = root.get("disabled_layers", [])
    if len(disabled_layers) != len(set(disabled_layers)) or not set(disabled_layers).issubset(declared_layers):
        fail("disabled_layers must uniquely reference declared layers")
    if root["default_layer"] in disabled_layers:
        fail("default_layer cannot be disabled")
    alpha_layers = root.get("alpha_layers", [])
    if len(alpha_layers) != len(set(alpha_layers)) or not set(alpha_layers).issubset(declared_layers):
        fail("alpha_layers must uniquely reference declared layers")
    hidden_layers = root.get("draw_hidden_layers", [])
    if len(hidden_layers) != len(set(hidden_layers)) or not set(hidden_layers).issubset(declared_layers):
        fail("draw_hidden_layers must uniquely reference declared layers")
    if set(layer_source) != set(declared_layers):
        fail("layers.toml must define every declared layer exactly once")
    for name, variants in layer_source.items():
        if name == "Magic":
            if set(variants) != {"glove80_80"} or len(flattened(variants["glove80_80"])) != 80:
                fail("Magic must define exactly glove80_80 with 80 bindings")
            for index, cell in enumerate(flattened(variants["glove80_80"])):
                validate_action(model, cell, f"Magic.glove80_80[{index}]")
            continue
        if set(variants) != set(ROW_COUNTS):
            fail(f"{name} must define full core30 and core34 matrices")
        for variant_name, row_counts in ROW_COUNTS.items():
            rows = variants[variant_name].get("rows")
            if not isinstance(rows, list) or [len(row) for row in rows] != row_counts:
                fail(f"{name}.{variant_name} rows must be {row_counts}")
            for index, cell in enumerate(flattened(variants[variant_name])):
                validate_action(model, cell, f"{name}.{variant_name}[{index}]")
            adaptive_names = {cell["adaptive"] for cell in flattened(variants[variant_name]) if isinstance(cell, dict) and cell.get("adaptive")}
            if len(adaptive_names) > 1:
                fail(f"{name}.{variant_name} uses multiple adaptive sets")
            if adaptive_names and name not in alpha_layers:
                fail(f"{name}.{variant_name} uses adaptives outside alpha_layers")
    behaviors = behavior_source.get("behaviors", {})
    behavior_identifiers = [ident(name) for name in behaviors]
    if len(behavior_identifiers) != len(set(behavior_identifiers)):
        fail("behavior names produce duplicate identifiers")
    allowed_recipes = {"shift_morph", "sequence", "repeat_magic", "adaptive_repeat", "tap_hold", "leader", "macro", "layer_action", "layer_chord", "layer_sticky_mod", "smart_layer", "sticky_key", "platform"}
    for name, behavior in behaviors.items():
        if behavior.get("recipe") not in allowed_recipes:
            fail(f"behavior {name}: unknown recipe {behavior.get('recipe')!r}")
        for target in behavior.get("targets", []):
            if target not in {"zmk", "qmk"}:
                fail(f"behavior {name}: unknown target {target!r}")
        if "draw_on" in behavior and behavior["draw_on"] not in declared_layers:
            fail(f"behavior {name}: unknown draw layer")
        if behavior["recipe"] == "shift_morph":
            validate_action(model, behavior["tap"], f"behavior {name}.tap")
            validate_action(model, behavior["shifted"], f"behavior {name}.shifted")
        if behavior["recipe"] == "sequence":
            keys = behavior.get("keys")
            steps = behavior.get("steps")
            if (keys is None) == (steps is None):
                fail(f"behavior {name}: sequence needs exactly one of keys or steps")
            if keys is not None:
                if not isinstance(keys, list) or not 1 <= len(keys) <= 4:
                    fail(f"behavior {name}: keys must contain one through four keys")
                for token in keys:
                    if not isinstance(token, str) or not valid_key(model, token):
                        fail(f"behavior {name}: invalid key {token!r}")
            else:
                if not isinstance(steps, list) or not 1 <= len(steps) <= 4:
                    fail(f"behavior {name}: steps must contain one through four actions")
                for index, step in enumerate(steps):
                    validate_action(model, step, f"behavior {name}.steps[{index}]")
                    if not isinstance(step, dict) or not ({"key", "os"} & set(step)):
                        fail(f"behavior {name}: sequence steps must be key or OS actions")
            if not isinstance(behavior.get("label"), str) or not behavior["label"]:
                fail(f"behavior {name}: label must be a non-empty string")
        if behavior["recipe"] == "tap_hold":
            validate_action(model, behavior["tap"], f"behavior {name}.tap")
            validate_action(model, behavior["hold"], f"behavior {name}.hold")
            if behavior.get("timing") not in behavior_source.get("timings", {}):
                fail(f"behavior {name}: unknown timing")
        if behavior["recipe"] == "macro":
            for index, step in enumerate(behavior.get("steps", [])):
                validate_action(model, step, f"behavior {name}.steps[{index}]")
        if behavior["recipe"] == "layer_action":
            if behavior.get("layer") not in declared_layers:
                fail(f"behavior {name}: unknown layer")
            if behavior.get("mode") not in {"momentary", "toggle", "sticky", "move"}:
                fail(f"behavior {name}: invalid layer mode")
        if behavior["recipe"] == "layer_chord":
            layers = [behavior.get("parent_layer"), behavior.get("child_layer")]
            if len(set(layers)) != 2 or not set(layers).issubset(declared_layers):
                fail(f"behavior {name}: layer_chord needs two unique layers")
            if declared_layers.index(layers[1]) <= declared_layers.index(layers[0]):
                fail(f"behavior {name}: child layer must be above parent layer")
            if "tap" in behavior:
                if not isinstance(behavior["tap"], str) or not valid_key(model, behavior["tap"]):
                    fail(f"behavior {name}: invalid layer_chord tap")
                if behavior.get("timing") not in behavior_source.get("timings", {}):
                    fail(f"behavior {name}: unknown timing")
        if behavior["recipe"] == "layer_sticky_mod":
            modifier_behaviors = behavior.get("modifier_behaviors", [])
            modifier_positions = behavior.get("modifier_positions", [])
            if behavior.get("targets") != ["zmk"]:
                fail(f"behavior {name}: layer_sticky_mod must be ZMK-only")
            if behavior.get("layer") not in declared_layers:
                fail(f"behavior {name}: unknown layer")
            if not 1 <= len(modifier_behaviors) <= 4 or len(modifier_behaviors) != len(modifier_positions):
                fail(f"behavior {name}: modifier behaviors and positions must have matching lengths")
            if len(modifier_behaviors) != len(set(modifier_behaviors)):
                fail(f"behavior {name}: modifier behaviors must be unique")
            if any(behaviors.get(modifier, {}).get("recipe") != "sticky_key" for modifier in modifier_behaviors):
                fail(f"behavior {name}: modifier_behaviors must reference sticky keys")
        if behavior["recipe"] == "smart_layer":
            if "zmk" in behavior.get("targets", ["zmk", "qmk"]):
                fail(f"behavior {name}: smart_layer is QMK-only")
            if behavior.get("layer") not in declared_layers:
                fail(f"behavior {name}: unknown layer")
            if behavior["layer"] not in behavior.get("keep_layers", []):
                fail(f"behavior {name}: keep_layers must include smart layer")
            if not set(behavior.get("keep_layers", [])).issubset(declared_layers):
                fail(f"behavior {name}: unknown keep layer")
            positions = behavior.get("keep_positions", [])
            if not isinstance(positions, list) or len(positions) != len(set(positions)):
                fail(f"behavior {name}: keep_positions must be unique")
        if behavior["recipe"] == "sticky_key" and resolved_key(model, behavior.get("key", "")) not in MODS:
            fail(f"behavior {name}: key must be a modifier")
        if behavior["recipe"] == "sticky_key" and behavior.get("timing") not in behavior_source.get("timings", {}):
            fail(f"behavior {name}: unknown timing")
        if behavior["recipe"] == "repeat_magic":
            if behavior.get("timing") not in behavior_source.get("timings", {}):
                fail(f"behavior {name}: unknown timing")
            if resolved_key(model, behavior.get("hold", "")) not in MODS:
                fail(f"behavior {name}: hold must be a modifier")
            if behavior.get("fallback") != "sticky_shift" or behavior.get("shifted") != "caps_word":
                fail(f"behavior {name}: unsupported fallback or shifted action")
            if behavior.get("repeat_timeout_ms", 0) <= 0:
                fail(f"behavior {name}: repeat timeout must be positive")
        if behavior["recipe"] == "adaptive_repeat":
            if not valid_key(model, behavior.get("marker", "")):
                fail(f"behavior {name}: invalid marker")
            if behavior.get("timeout_ms", 0) <= 0 or not isinstance(behavior.get("strict_modifiers"), bool):
                fail(f"behavior {name}: invalid adaptive settings")
            rules = behavior.get("rules", [])
            if not rules or any(not valid_key(model, rule.get("after", "")) or not valid_key(model, rule.get("emit", "")) for rule in rules):
                fail(f"behavior {name}: invalid adaptive repeat rules")
    if not isinstance(behavior_source.get("timings", {}).get("home_row", {}).get("opposite_hand_hold"), bool):
        fail("home_row.opposite_hand_hold must be a boolean")
    if not isinstance(behavior_source.get("timings", {}).get("home_row", {}).get("hold_while_undecided", False), bool):
        fail("home_row.hold_while_undecided must be a boolean")
    conditional_layers = root.get("conditional_layers", [])
    if not isinstance(conditional_layers, list):
        fail("conditional_layers must be a list")
    seen_conditional_layers: set[str] = set()
    for index, conditional in enumerate(conditional_layers):
        if_layers = conditional.get("if_layers", [])
        then_layer = conditional.get("then_layer")
        if not isinstance(if_layers, list) or len(if_layers) != 2 or len(set(if_layers)) != 2:
            fail(f"conditional layer {index}: if_layers must contain two unique layers")
        if not set(if_layers).issubset(declared_layers) or then_layer not in declared_layers:
            fail(f"conditional layer {index}: unknown layer")
        variants = conditional.get("variants", [])
        if len(variants) != len(set(variants)) or not set(variants).issubset(ROW_COUNTS):
            fail(f"conditional layer {index}: invalid variants")
        if then_layer in if_layers or declared_layers.index(then_layer) <= max(declared_layers.index(layer) for layer in if_layers):
            fail(f"conditional layer {index}: then_layer must be above if_layers")
        if then_layer in seen_conditional_layers:
            fail(f"conditional layer {index}: duplicate then_layer")
        seen_conditional_layers.add(then_layer)
    for name, adaptive in behavior_source.get("adaptives", {}).items():
        if not isinstance(adaptive.get("enabled"), bool) or not isinstance(adaptive.get("swaps_enabled", False), bool):
            fail(f"adaptive {name}: enabled flags must be booleans")
        if adaptive.get("timeout_ms", 0) <= 0:
            fail(f"adaptive {name}: timeout must be positive")
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for rule in adaptive.get("rules", []):
            after = rule.get("after", [])
            if not 1 <= len(after) <= 6:
                fail(f"adaptive {name}: suffix length must be 1 through 6")
            if not 1 <= len(rule.get("emit", [])) <= 6:
                fail(f"adaptive {name}: output length must be 1 through 6")
            for token in [rule.get("input"), *after, *rule.get("emit", [])]:
                if not isinstance(token, str) or not valid_key(model, token):
                    fail(f"adaptive {name}: invalid key {token!r}")
            signature = (rule["input"], tuple(after))
            if signature in seen:
                fail(f"adaptive {name}: duplicate rule {signature}")
            seen.add(signature)
        variant_swaps = adaptive.get("variant_swaps", {})
        if not set(variant_swaps).issubset(ROW_COUNTS):
            fail(f"adaptive {name}: invalid swap variants")
        for swap in [*adaptive.get("swaps", []), *(swap for swaps in variant_swaps.values() for swap in swaps)]:
            if len(swap) != 3 or any(not valid_key(model, token) for token in swap):
                fail(f"adaptive {name}: invalid swap {swap!r}")
            if swap[1] == swap[2]:
                fail(f"adaptive {name}: swap maps a key to itself")
        if adaptive["enabled"] and not any(
            isinstance(cell, dict) and cell.get("adaptive") == name
            for variants in layer_source.values()
            for variant in variants.values()
            for cell in flattened(variant)
        ):
            fail(f"adaptive {name}: enabled but unused")
    topologies = profile_source.get("topologies", {})
    if not topologies:
        fail("profiles.json has no topologies")
    for name, slots in topologies.items():
        if not isinstance(slots, list) or len(slots) != len(set(slots)):
            fail(f"topology {name}: slots must be a unique list")
    if len(topologies.get("core_30", [])) != 30 or len(topologies.get("core_34", [])) != 34:
        fail("core topologies must contain 30 and 34 slots")
    core30 = set(topologies["core_30"])
    core34 = set(topologies["core_34"])
    if core34 - core30 != {"L_INNER_TOP", "R_INNER_TOP", "L_PINKY_BOTTOM", "R_PINKY_BOTTOM"} or core30 - core34:
        fail("core_30 must omit only inner tops and pinky bottoms from core_34")
    for name, item in behaviors.items():
        if item["recipe"] == "smart_layer" and not set(item.get("keep_positions", [])).issubset(core34):
            fail(f"behavior {name}: keep position outside core34")
        if item["recipe"] == "layer_chord":
            positions = {item.get("parent_position"), item.get("child_position")}
            if len(positions) != 2 or not positions.issubset(core34):
                fail(f"behavior {name}: layer_chord needs two unique core positions")
        if item["recipe"] == "layer_sticky_mod":
            modifier_positions = item.get("modifier_positions", [])
            positions = {item.get("layer_position"), *modifier_positions}
            if len(positions) != len(modifier_positions) + 1 or not positions.issubset(core34):
                fail(f"behavior {name}: layer_sticky_mod needs unique core positions")
    profiles = profile_source.get("profiles", {})
    if not profiles:
        fail("profiles.json has no profiles")
    targets = profile_source.get("targets", {})
    if not isinstance(targets, dict) or not targets:
        fail("profiles.json has no targets")
    target_aliases: dict[str, str] = {}
    for target_name, target in targets.items():
        if not isinstance(target, dict) or re.fullmatch(r"[a-z0-9][a-z0-9_-]*", target_name) is None:
            fail(f"invalid target {target_name!r}")
        profile_name = target.get("profile")
        zmk_keyboard = target.get("zmk_keyboard")
        if profile_name is None and not isinstance(zmk_keyboard, str):
            fail(f"target {target_name}: needs profile or zmk_keyboard")
        if profile_name is not None and profile_name not in profiles:
            fail(f"target {target_name}: unknown profile {profile_name!r}")
        available = {backend for backend in ("zmk", "qmk") if profile_name and backend in profiles[profile_name]}
        if zmk_keyboard:
            available.add("zmk")
        backends = target.get("backends", list(available))
        defaults = target.get("default_backends", backends)
        if not isinstance(backends, list) or len(backends) != len(set(backends)) or not set(backends).issubset(available):
            fail(f"target {target_name}: invalid backends")
        if not isinstance(defaults, list) or len(defaults) != len(set(defaults)) or not set(defaults).issubset(backends):
            fail(f"target {target_name}: invalid default backends")
        draw_profiles = target.get("draw_profiles", [profile_name] if profile_name else [])
        if not isinstance(draw_profiles, list) or not draw_profiles or not set(draw_profiles).issubset(profiles):
            if profile_name or draw_profiles:
                fail(f"target {target_name}: invalid drawing profiles")
        if not isinstance(target.get("all", True), bool):
            fail(f"target {target_name}: all must be boolean")
        aliases = target.get("aliases", [])
        if not isinstance(aliases, list) or any(not isinstance(alias, str) or not alias for alias in aliases):
            fail(f"target {target_name}: invalid aliases")
        for alias in [target_name, *aliases]:
            normalized = alias.replace("-", "_")
            owner = target_aliases.setdefault(normalized, target_name)
            if owner != target_name:
                fail(f"target alias {alias!r} belongs to both {owner} and {target_name}")
    for name, profile in profiles.items():
        if profile.get("physical_keys", 0) < 30:
            fail(f"profile {name}: fewer than 30 physical keys")
        if profile.get("binding_positions", 0) < profile["physical_keys"]:
            fail(f"profile {name}: fewer bindings than physical keys")
        board_only = profile.get("board_only_positions", [])
        if profile["binding_positions"] - profile["physical_keys"] != len(board_only):
            fail(f"profile {name}: board-only positions do not explain binding count")
        if profile.get("alpha_capacity") not in {30, 34, 38}:
            fail(f"profile {name}: unsupported alpha capacity")
        zmk = profile.get("zmk")
        if zmk is not None:
            if not isinstance(zmk, dict):
                fail(f"profile {name}: zmk target must be an object")
            physical_layout = zmk.get("physical_layout")
            if physical_layout is not None and (not isinstance(physical_layout, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", physical_layout) is None):
                fail(f"profile {name}: invalid ZMK physical layout")
            physical_layout_include = zmk.get("physical_layout_include")
            if physical_layout_include is not None and (not isinstance(physical_layout_include, str) or not physical_layout_include or any(character in physical_layout_include for character in "<>\r\n")):
                fail(f"profile {name}: invalid ZMK physical layout include")
            if physical_layout_include and not physical_layout:
                fail(f"profile {name}: ZMK physical layout include needs a layout")
            transform = zmk.get("transform")
            if transform is not None:
                valid_transform = isinstance(transform, list) and len(transform) == profile["binding_positions"]
                valid_transform = valid_transform and all(isinstance(coordinate, list) and len(coordinate) == 2 and all(type(value) is int and value >= 0 for value in coordinate) for coordinate in transform)
                if not valid_transform or len({tuple(coordinate) for coordinate in transform}) != len(transform):
                    fail(f"profile {name}: ZMK transform must uniquely match binding positions")
        if "layers" in profile:
            unknown = set(profile["layers"]) - set(declared_layers)
            if unknown:
                fail(f"profile {name}: unknown layers {sorted(unknown)}")
        for backend in ("zmk", "qmk"):
            if backend not in profile:
                continue
            slots = profile_slots(model, profile, backend)
            if len(slots) != profile["binding_positions"] or len(slots) != len(set(slots)):
                fail(f"profile {name}: {backend} slots must be unique and match binding_positions")
            expected = core30 if profile["alpha_capacity"] == 30 else core34
            if not expected.issubset(slots):
                fail(f"profile {name}: {backend} slots do not cover its alpha core")
            if backend == "qmk" and not set(board_only).issubset(slots):
                fail(f"profile {name}: qmk slots omit board-only positions")
        for layer_name, overlay in profile.get("overlays", {}).items():
            if layer_name not in declared_layers:
                fail(f"profile {name}: overlay names unknown layer {layer_name}")
            for position, cell in overlay.items():
                if not any(position in profile_slots(model, profile, backend) for backend in ("zmk", "qmk") if backend in profile):
                    fail(f"profile {name}: overlay position {position} does not exist")
                validate_action(model, cell, f"profile {name}.{layer_name}.{position}")
        for position, cell in profile.get("defaults", {}).items():
            if not any(position in profile_slots(model, profile, backend) for backend in ("zmk", "qmk") if backend in profile):
                fail(f"profile {name}: default position {position} does not exist")
            validate_action(model, cell, f"profile {name}.defaults.{position}")
    combo_names: set[str] = set()
    combo_identifiers: set[str] = set()
    for index, combo in enumerate(behavior_source.get("combos", [])):
        if not isinstance(combo, dict):
            fail(f"combo {index}: must be an object")
        name = combo.get("name")
        positions = combo.get("positions")
        if not isinstance(name, str) or not name or not isinstance(positions, list) or len(positions) < 2:
            fail(f"combo {index}: needs name and at least two positions")
        if name in combo_names:
            fail(f"combo {name}: duplicate name")
        combo_names.add(name)
        identifier = ident(name)
        if identifier in combo_identifiers:
            fail(f"combo {name}: duplicate generated identifier")
        combo_identifiers.add(identifier)
        if len(positions) != len(set(positions)):
            fail(f"combo {name}: positions must be unique")
        for timing_name in ("term_ms", "prior_idle_ms"):
            if timing_name not in combo:
                continue
            timing_value = combo[timing_name]
            if type(timing_value) is not int or timing_value < (1 if timing_name == "term_ms" else 0):
                fail(f"combo {name}: invalid {timing_name}")
        if "slow_release" in combo and not isinstance(combo["slow_release"], bool):
            fail(f"combo {name}: slow_release must be a boolean")
        variants = combo.get("variants", [])
        if len(variants) != len(set(variants)) or not set(variants).issubset(ROW_COUNTS):
            fail(f"combo {combo['name']}: invalid variants")
        if not set(combo.get("layers", [])).issubset(declared_layers):
            fail(f"combo {combo['name']}: unknown layer")
        if not set(combo["positions"]).issubset(core34):
            fail(f"combo {combo['name']}: position outside core34")
        for variant in variants:
            topology = core30 if variant == "core30" else core34
            if not set(combo["positions"]).issubset(topology):
                fail(f"combo {combo['name']}: position outside {variant}")
        validate_action(model, combo["action"], f"combo {combo['name']}")
        drawing = combo.get("draw", {})
        if drawing is False:
            continue
        if not isinstance(drawing, dict):
            fail(f"combo {combo['name']}: draw must be an object or false")
        if "action" in drawing:
            validate_action(model, drawing["action"], f"combo {combo['name']}.draw")
        if "type" in drawing and (not isinstance(drawing["type"], str) or re.fullmatch(r"[a-z][a-z0-9-]*", drawing["type"]) is None):
            fail(f"combo {combo['name']}: invalid draw type")
        draw_layers = drawing.get("layers", combo["layers"])
        if not draw_layers or len(draw_layers) != len(set(draw_layers)) or not set(draw_layers).issubset(combo["layers"]):
            fail(f"combo {combo['name']}: invalid draw layers")
    for index, leader in enumerate(behavior_source.get("leader", [])):
        if not 1 <= len(leader.get("sequence", [])) <= 5:
            fail(f"leader {index}: sequence length must be 1 through 5")
        for token in leader["sequence"]:
            if not valid_key(model, token):
                fail(f"leader {index}: unknown key {token!r}")
        validate_action(model, leader["action"], f"leader {index}")


def active_layers(model: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    disabled = set(model["root"].get("disabled_layers", []))
    if "layers" in profile:
        return [name for name in profile["layers"] if name not in disabled]
    excluded = {"Magic", "Game", "GameExtra", *disabled}
    if profile["alpha_capacity"] >= 34:
        excluded.add("Vestnik2")
    return [name for name in model["root"]["layers"] if name not in excluded]


def behavior_layer_refs(model: dict[str, Any], item: dict[str, Any]) -> set[str]:
    refs = {item[key] for key in ("layer", "parent_layer", "child_layer") if key in item}
    for value in [*item.get("steps", []), item.get("tap"), item.get("hold")]:
        if isinstance(value, dict):
            if "layer" in value:
                refs.add(value["layer"])
            if "use" in value:
                refs.update(behavior_layer_refs(model, behavior(model, value["use"])))
    return refs


def action_layer_refs(model: dict[str, Any], value: Any) -> set[str]:
    if not isinstance(value, dict):
        return set()
    if "layer" in value:
        return {value["layer"]}
    if "use" in value:
        return behavior_layer_refs(model, behavior(model, value["use"]))
    return set()


def compile_profile(model: dict[str, Any], profile_name: str, backend: str, os_name: str) -> dict[str, Any]:
    profiles = model["profiles"]["profiles"]
    if profile_name not in profiles:
        fail(f"unknown profile {profile_name!r}")
    profile = profiles[profile_name]
    if backend not in profile:
        fail(f"profile {profile_name!r} has no {backend} target")
    if os_name not in model["root"]["operating_systems"]:
        fail(f"unknown operating system {os_name!r}")
    slots = list(profile_slots(model, profile, backend))
    layers = active_layers(model, profile)
    variant = "core30" if profile["alpha_capacity"] == 30 else "core34"
    core_name = "core_30" if variant == "core30" else "core_34"
    core_slots = model["profiles"]["topologies"][core_name]
    compiled_layers: dict[str, list[Any]] = {}
    for layer_name in layers:
        variants = model["layers"]["layers"][layer_name]
        direct_name = f"{profile_name}_80"
        if layer_name == "Magic":
            direct = variants.get(direct_name) or variants.get(profile_name)
            if direct is None:
                fail(f"profile {profile_name}: Magic has no direct matrix")
            cells = list(flattened(direct))
            if len(cells) != len(slots):
                fail(f"profile {profile_name}: Magic binding count mismatch")
            compiled_layers[layer_name] = cells
            continue
        values = dict(zip(core_slots, flattened(variants[variant])))
        defaults = profile.get("defaults", {})
        overlay = profile.get("overlays", {}).get(layer_name, {})
        cells = [overlay.get(slot, values.get(slot, defaults.get(slot, "none"))) for slot in slots]
        compiled_layers[layer_name] = [cell if action_layer_refs(model, cell).issubset(layers) else "none" for cell in cells]
    layer_index = {name: index for index, name in enumerate(layers)}
    combos = []
    slot_index = {slot: index for index, slot in enumerate(slots)}
    for combo in model["behaviors"].get("combos", []):
        if combo.get("variants") and variant not in combo["variants"]:
            continue
        if not set(combo["layers"]).intersection(layers):
            continue
        if not set(combo["positions"]).issubset(slot_index):
            continue
        if not action_layer_refs(model, combo["action"]).issubset(layers):
            continue
        if isinstance(combo["action"], dict) and "use" in combo["action"] and not behavior_available(behavior(model, combo["action"]["use"]), backend):
            continue
        item = dict(combo)
        item.update(profile.get("combo_overrides", {}).get(combo["name"], {}))
        item["indices"] = [slot_index[position] for position in combo["positions"]]
        item["layers"] = [layer for layer in combo["layers"] if layer in layers]
        combos.append(item)
    conditional_layers = [
        conditional
        for conditional in model["root"].get("conditional_layers", [])
        if (not conditional.get("variants") or variant in conditional["variants"])
        and set(conditional["if_layers"] + [conditional["then_layer"]]).issubset(layers)
    ]
    return {
        "version": 1,
        "profile_name": profile_name,
        "backend": backend,
        "os": os_name,
        "profile": profile,
        "slots": slots,
        "variant": variant,
        "layers": compiled_layers,
        "layer_index": layer_index,
        "conditional_layers": conditional_layers,
        "combos": combos,
        "source_hash": source_hash(model),
    }


def source_hash(model: dict[str, Any]) -> str:
    return hashlib.sha256(stable_json(model).encode()).hexdigest()


def resolved_key(model: dict[str, Any], token: str) -> str:
    alias = key_alias(model, token)
    return MOD_ALIASES.get(alias["key"] if alias else token, alias["key"] if alias else token)


def with_mods(expression: str, mods: list[str], wrappers: dict[str, str]) -> str:
    for mod in reversed(mods):
        expression = f"{wrappers[MOD_ALIASES.get(mod, mod)]}({expression})"
    return expression


def zmk_key(model: dict[str, Any], token: str) -> str:
    token = resolved_key(model, token)
    if token in SHIFTED:
        return f"LS({SHIFTED[token]})"
    return ZMK_KEYS.get(token, token)


def qmk_key(model: dict[str, Any], token: str) -> str:
    token = resolved_key(model, token)
    if token in SHIFTED:
        return f"S({qmk_key(model, SHIFTED[token])})"
    if len(token) == 1 and "A" <= token <= "Z":
        return f"KC_{token}"
    if re.fullmatch(r"N[0-9]", token):
        return f"KC_{token[1]}"
    if re.fullmatch(r"F(?:[1-9]|1[0-9]|2[0-4])", token):
        return f"KC_{token}"
    try:
        return QMK_KEYS[token]
    except KeyError:
        fail(f"no QMK keycode for {token!r}")


def resolve_os(model: dict[str, Any], os_name: str, action: str) -> Any:
    return model["root"]["operating_systems"][os_name][action]


def behavior(model: dict[str, Any], name: str) -> dict[str, Any]:
    return model["behaviors"]["behaviors"][name]


def behavior_available(value: dict[str, Any], backend: str) -> bool:
    return backend in value.get("targets", ["zmk", "qmk"])


def smart_layer_behavior(model: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    matches = [(name, item) for name, item in model["behaviors"]["behaviors"].items() if item["recipe"] == "smart_layer"]
    if len(matches) > 1:
        fail("only one smart layer is supported")
    return matches[0] if matches else None


def smart_layer_indices(model: dict[str, Any], ir: dict[str, Any], name: str, item: dict[str, Any]) -> list[int]:
    indices = {
        index
        for index, cell in enumerate(ir["layers"][item["layer"]])
        if not (isinstance(cell, str) and cell in {"none", "trans"})
    }
    slot_indices = {slot: index for index, slot in enumerate(ir["slots"])}
    indices.update(slot_indices[position] for position in item.get("keep_positions", []) if position in slot_indices)
    for combo in ir["combos"]:
        if isinstance(combo["action"], dict) and combo["action"].get("use") == name:
            indices.update(combo["indices"])
    return sorted(indices)


def is_layer_tap_hold(value: dict[str, Any]) -> bool:
    return value.get("recipe") == "tap_hold" and all(isinstance(value.get(action), dict) and "layer" in value[action] for action in ("hold", "tap"))


def is_key_layer_tap_hold(value: dict[str, Any]) -> bool:
    return value.get("recipe") == "tap_hold" and isinstance(value.get("tap"), str) and isinstance(value.get("hold"), dict) and "layer" in value["hold"]


def is_sticky_key_layer_tap_hold(model: dict[str, Any], value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    tap = value.get("tap")
    return value.get("recipe") == "tap_hold" and isinstance(tap, dict) and "use" in tap and behavior(model, tap["use"]).get("recipe") == "sticky_key" and isinstance(value.get("hold"), dict) and "layer" in value["hold"]


def is_shift_morph_layer_tap_hold(model: dict[str, Any], value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    tap = value.get("tap")
    return value.get("recipe") == "tap_hold" and isinstance(tap, dict) and "use" in tap and behavior(model, tap["use"]).get("recipe") == "shift_morph" and isinstance(value.get("hold"), dict) and "layer" in value["hold"]


def is_key_key_tap_hold(value: dict[str, Any]) -> bool:
    return value.get("recipe") == "tap_hold" and isinstance(value.get("tap"), str) and isinstance(value.get("hold"), dict) and "key" in value["hold"]


def zmk_layer_action(layer: str, mode: str) -> str:
    return {
        "momentary": f"&mo LAYER_{layer}",
        "toggle": f"&tog LAYER_{layer}",
        "sticky": f"&sl LAYER_{layer}",
        "move": f"&to LAYER_{layer}",
    }[mode]


def adaptive_rules(model: dict[str, Any], name: str, variant: str) -> list[dict[str, Any]]:
    config = model["behaviors"].get("adaptives", {}).get(name, {})
    if not config.get("enabled"):
        return []
    rules = [dict(rule) for rule in config.get("rules", [])]
    if config.get("swaps_enabled"):
        swaps = [*config.get("swaps", []), *config.get("variant_swaps", {}).get(variant, [])]
        for prior, left, right in swaps:
            rules.append({"input": right, "after": [prior], "emit": [left]})
            rules.append({"input": left, "after": [prior], "emit": [right]})
    for rule in rules:
        rule.setdefault("timeout_ms", config["timeout_ms"])
        rule.setdefault("strict_modifiers", config.get("strict_modifiers", True))
    return sorted(rules, key=lambda item: (-len(item["after"]), item["input"], item["after"]))


def adaptive_inputs(model: dict[str, Any], name: str, variant: str) -> set[str]:
    return {rule["input"] for rule in adaptive_rules(model, name, variant)}


def cell_tap(value: Any) -> str | None:
    if isinstance(value, str) and value not in {"none", "trans"}:
        return value
    if isinstance(value, dict) and isinstance(value.get("tap"), str):
        return value["tap"]
    return None


def adaptive_layers(ir: dict[str, Any], name: str) -> list[str]:
    return [
        layer_name
        for layer_name, cells in ir["layers"].items()
        if any(isinstance(cell, dict) and cell.get("adaptive") == name for cell in cells)
    ]


def zmk_action(model: dict[str, Any], ir: dict[str, Any], value: Any, adaptive_name: str | None = None) -> str:
    if isinstance(value, str):
        if value == "none":
            return "&none"
        if value == "trans":
            return "&trans"
        if adaptive_name and resolved_key(model, value) in {resolved_key(model, item) for item in adaptive_inputs(model, adaptive_name, ir["variant"])}:
            return f"&adaptive_{ident(adaptive_name).lower()}_{ident(resolved_key(model, value)).lower()}"
        return f"&kp {zmk_key(model, value)}"
    if "tap" in value:
        tap = value["tap"]
        hold = value["hold"]
        adaptive = value.get("adaptive", adaptive_name)
        if adaptive and resolved_key(model, tap) in {resolved_key(model, item) for item in adaptive_inputs(model, adaptive, ir["variant"])}:
            base = f"adaptive_{ident(adaptive).lower()}_{ident(resolved_key(model, tap)).lower()}"
            if value.get("hand"):
                return f"&{base}_{'hml' if value['hand'] == 'left' else 'hmr'} {zmk_key(model, hold)} 0"
            return f"&{base}"
        if value.get("hand"):
            return f"&{'hml' if value['hand'] == 'left' else 'hmr'} {zmk_key(model, hold)} {zmk_key(model, tap)}"
        if isinstance(hold, str):
            return f"&fnum {zmk_key(model, hold)} {zmk_key(model, tap)}"
        if "layer" in hold and hold.get("mode", "momentary") == "momentary":
            timing = value.get("timing", "thumb")
            name = {"layer_thumb": "layer_thumb", "thumb_tap_preferred": "thumb_tp"}.get(timing, "thumb_ht")
            return f"&{name} LAYER_{hold['layer']} {zmk_key(model, tap)}"
        fail(f"cannot render ZMK tap-hold {value!r}")
    if "use" in value:
        name = value["use"]
        item = behavior(model, name)
        if not behavior_available(item, "zmk"):
            return "&none"
        recipe = item["recipe"]
        if recipe in {"shift_morph", "sequence", "macro", "layer_sticky_mod", "leader"}:
            return f"&{name}"
        if recipe == "layer_action":
            return zmk_layer_action(item["layer"], item["mode"])
        if recipe == "layer_chord":
            if "tap" in item:
                return f"&{name} 0 {zmk_key(model, item['tap'])}"
            return f"&{name}"
        if recipe == "sticky_key":
            key = zmk_key(model, item["key"])
            return f"&{name} {key} {key}"
        if recipe == "repeat_magic":
            return f"&{name} {zmk_key(model, item['hold'])} 0"
        if recipe == "adaptive_repeat":
            return f"&{name}"
        if recipe == "tap_hold":
            if is_layer_tap_hold(item):
                return f"&{name} LAYER_{item['hold']['layer']} LAYER_{item['tap']['layer']}"
            if is_sticky_key_layer_tap_hold(model, item):
                modifier = resolved_key(model, behavior(model, item["tap"]["use"])["key"])
                return f"&{name} LAYER_{item['hold']['layer']} {'0' if modifier in {'LSHFT', 'RSHFT'} else zmk_key(model, modifier)}"
            if is_shift_morph_layer_tap_hold(model, item):
                return f"&{name} LAYER_{item['hold']['layer']} 0"
            if is_key_layer_tap_hold(item):
                return f"&{name} LAYER_{item['hold']['layer']} {zmk_key(model, item['tap'])}"
            if is_key_key_tap_hold(item):
                hold = with_mods(zmk_key(model, item["hold"]["key"]), item["hold"].get("mods", []), ZMK_MODS)
                return f"&{name} {hold} {zmk_key(model, item['tap'])}"
            if name == "glove_magic":
                return f"&{name} LAYER_{item['hold']['layer']} 0"
            return f"&{name}"
        if recipe == "platform":
            action = item["action"]
            if action == "bootloader":
                return "&bootloader"
            if action == "reset":
                return "&sys_reset"
            if action == "soft_off":
                return "&soft_off"
            if action == "output_toggle":
                return "&out OUT_TOG"
            if action == "bt_clear":
                return "&bt BT_CLR"
            if action == "bt_clear_all":
                return "&bt BT_CLR_ALL"
            if action == "caps_word":
                return "&caps_word"
            if action == "key_repeat":
                return "&key_repeat"
            if action == "bt_select":
                return f"&{name}"
        fail(f"cannot render ZMK behavior {name!r}")
    if "key" in value:
        return f"&kp {with_mods(zmk_key(model, value['key']), value.get('mods', []), ZMK_MODS)}"
    if "os" in value:
        return zmk_action(model, ir, resolve_os(model, ir["os"], value["os"]))
    if "layer" in value:
        return zmk_layer_action(value["layer"], value.get("mode", "momentary"))
    if "mouse" in value:
        return MOUSE_ZMK[value["mouse"]]
    if "light" in value:
        lighting = ir["profile"].get("capabilities", {}).get("lighting")
        if lighting != "backlight":
            return "&none"
        return {"toggle": "&bl BL_TOG", "decrease": "&bl BL_DEC", "increase": "&bl BL_INC"}[value["light"]]
    if "rgb" in value:
        return f"&rgb_ug {RGB_ZMK[value['rgb']]}"
    if "platform" in value:
        return {"output_usb": "&out OUT_USB"}.get(value["platform"], "&none")
    fail(f"cannot render ZMK action {value!r}")


def render_zmk_behaviors(model: dict[str, Any], ir: dict[str, Any]) -> list[str]:
    timings = model["behaviors"]["timings"]
    h = timings["home_row"] | ir["profile"].get("timing_overrides", {}).get("home_row", {})
    left_positions = [index for index, slot in enumerate(ir["slots"]) if slot.startswith("L_") and "THUMB" not in slot]
    right_positions = [index for index, slot in enumerate(ir["slots"]) if slot.startswith("R_") and "THUMB" not in slot]
    thumbs = [index for index, slot in enumerate(ir["slots"]) if "THUMB" in slot]
    slot_indices = {slot: index for index, slot in enumerate(ir["slots"])}
    left_trigger = f'; hold-trigger-key-positions = <{" ".join(map(str, right_positions + thumbs))}>; hold-trigger-on-release' if h["opposite_hand_hold"] else ""
    right_trigger = f'; hold-trigger-key-positions = <{" ".join(map(str, left_positions + thumbs))}>; hold-trigger-on-release' if h["opposite_hand_hold"] else ""
    immediate_hold = "; hold-while-undecided" if h.get("hold_while_undecided", False) else ""
    lines = [
        f'ZMK_HOLD_TAP(hml, bindings = <&kp>, <&kp>; flavor = "{h["flavor"]}"; tapping-term-ms = <{h["tapping_term_ms"]}>; quick-tap-ms = <{h["quick_tap_ms"]}>; require-prior-idle-ms = <{h["prior_idle_ms"]}>{left_trigger}{immediate_hold};)',
        f'ZMK_HOLD_TAP(hmr, bindings = <&kp>, <&kp>; flavor = "{h["flavor"]}"; tapping-term-ms = <{h["tapping_term_ms"]}>; quick-tap-ms = <{h["quick_tap_ms"]}>; require-prior-idle-ms = <{h["prior_idle_ms"]}>{right_trigger}{immediate_hold};)',
    ]
    if any(is_sticky_key_layer_tap_hold(model, item) and resolved_key(model, behavior(model, item["tap"]["use"])["key"]) in {"LSHFT", "RSHFT"} for item in model["behaviors"]["behaviors"].values()):
        lines.append("ZMK_MOD_MORPH(smart_shift, bindings = <&sk LSHFT>, <&caps_word>; mods = <(MOD_LSFT|MOD_RSFT)>;)")
    layer_chords = []
    layer_sticky_mods = []
    for name, timing_name in (("thumb_ht", "thumb"), ("layer_thumb", "layer_thumb"), ("thumb_tp", "thumb_tap_preferred")):
        timing = timings[timing_name]
        immediate_hold = "; hold-while-undecided" if timing_name == "layer_thumb" else ""
        lines.append(f'ZMK_HOLD_TAP({name}, bindings = <&mo>, <&kp>; flavor = "{timing["flavor"]}"; tapping-term-ms = <{timing["tapping_term_ms"]}>; quick-tap-ms = <{timing["quick_tap_ms"]}>{immediate_hold};)')
    fnum = timings["function_number"]
    lines.append(f'ZMK_HOLD_TAP(fnum, bindings = <&kp>, <&kp>; flavor = "{fnum["flavor"]}"; tapping-term-ms = <{fnum["tapping_term_ms"]}>;)')
    for name, item in model["behaviors"]["behaviors"].items():
        if not behavior_available(item, "zmk") or not behavior_layer_refs(model, item).issubset(ir["layers"]):
            continue
        recipe = item["recipe"]
        if recipe == "shift_morph":
            lines.append(f"ZMK_MOD_MORPH({name}, bindings = <{zmk_action(model, ir, item['tap'])}>, <{zmk_action(model, ir, item['shifted'])}>; mods = <(MOD_LSFT|MOD_RSFT)>;)")
        elif recipe == "sticky_key":
            timing = timings[item["timing"]]
            lines.append(f'ZMK_HOLD_TAP({name}, bindings = <&kp>, <&sk>; flavor = "{timing["flavor"]}"; tapping-term-ms = <{timing["tapping_term_ms"]}>; hold-while-undecided; hold-while-undecided-linger;)')
        elif recipe == "sequence":
            timing = timings["sequence"]
            bindings = ", ".join(
                f"<&kp {zmk_key(model, token)}>" for token in item["keys"]
            ) if "keys" in item else ", ".join(f"<{zmk_action(model, ir, step)}>" for step in item["steps"])
            lines.append(f"ZMK_MACRO({name}, wait-ms = <{timing['wait_ms']}>; tap-ms = <{timing['tap_ms']}>; bindings = {bindings};)")
        elif recipe == "macro":
            bindings = ", ".join(f"<{zmk_action(model, ir, step)}>" for step in item["steps"])
            lines.append(f"ZMK_MACRO({name}, bindings = {bindings};)")
        elif recipe == "layer_sticky_mod":
            layer_sticky_mods.append((name, item))
        elif recipe == "layer_chord":
            chord_name = f"{name}_hold" if "tap" in item else name
            layer_chords.append((chord_name, item))
            if "tap" in item:
                timing = timings[item["timing"]]
                lines.append(f'ZMK_HOLD_TAP({name}, bindings = <&{chord_name}>, <&kp>; flavor = "{timing["flavor"]}"; tapping-term-ms = <{timing["tapping_term_ms"]}>; quick-tap-ms = <{timing["quick_tap_ms"]}>; hold-while-undecided;)')
        elif recipe == "adaptive_repeat":
            marker = zmk_key(model, item["marker"])
            lines.append(f"ZMK_MACRO({name}_default, bindings = <&alpha_repeat>, <&kp {marker}>;)")
            triggers = []
            for index, rule in enumerate(item["rules"]):
                macro = f"{name}_r{index}"
                lines.append(f"ZMK_MACRO({macro}, bindings = <&kp {zmk_key(model, rule['emit'])}>, <&kp {marker}>;)")
                strict = " strict-modifiers;" if item["strict_modifiers"] else ""
                triggers.append(f"r{index} {{ trigger-keys = <{zmk_key(model, rule['after'])}>; bindings = <&{macro}>; max-prior-idle-ms = <{item['timeout_ms']}>;{strict} }};")
            lines.append(f"ZMK_ADAPTIVE_KEY({name}, bindings = <&{name}_default>; dead-keys = <{marker}>; {' '.join(triggers)})")
        elif recipe == "platform" and item["action"] == "bt_select":
            lines.append(f"ZMK_MACRO({name}, bindings = <&out OUT_BLE>, <&bt BT_SEL {item['value']}>;)")
        elif is_layer_tap_hold(item):
            if item["hold"]["layer"] not in ir["layer_index"] or item["tap"]["layer"] not in ir["layer_index"]:
                continue
            timing = timings[item["timing"]]
            hold_binding = {"momentary": "&mo"}.get(item["hold"].get("mode", "momentary"))
            tap_binding = {"sticky": "&sl", "toggle": "&tog"}.get(item["tap"].get("mode", "momentary"))
            if hold_binding is None or tap_binding is None:
                fail(f"unsupported layer tap-hold {name!r}")
            quick_tap = f'; quick-tap-ms = <{timing["quick_tap_ms"]}>' if "quick_tap_ms" in timing else ""
            lines.append(f'ZMK_HOLD_TAP({name}, bindings = <{hold_binding}>, <{tap_binding}>; flavor = "{timing["flavor"]}"; tapping-term-ms = <{timing["tapping_term_ms"]}>{quick_tap};)')
        elif is_sticky_key_layer_tap_hold(model, item):
            timing = timings[item["timing"]]
            if item["hold"].get("mode", "momentary") != "momentary":
                fail(f"unsupported sticky-key layer tap-hold {name!r}")
            modifier = resolved_key(model, behavior(model, item["tap"]["use"])["key"])
            tap_binding = "&smart_shift" if modifier in {"LSHFT", "RSHFT"} else "&sk"
            quick_tap = f'; quick-tap-ms = <{timing["quick_tap_ms"]}>' if "quick_tap_ms" in timing else ""
            lines.append(f'ZMK_HOLD_TAP({name}, bindings = <&mo>, <{tap_binding}>; flavor = "{timing["flavor"]}"; tapping-term-ms = <{timing["tapping_term_ms"]}>{quick_tap};)')
        elif is_shift_morph_layer_tap_hold(model, item):
            timing = timings[item["timing"]]
            if item["hold"].get("mode", "momentary") != "momentary":
                fail(f"unsupported shift-morph layer tap-hold {name!r}")
            quick_tap = f'; quick-tap-ms = <{timing["quick_tap_ms"]}>' if "quick_tap_ms" in timing else ""
            lines.append(f'ZMK_HOLD_TAP({name}, bindings = <&mo>, <&{item["tap"]["use"]}>; flavor = "{timing["flavor"]}"; tapping-term-ms = <{timing["tapping_term_ms"]}>{quick_tap};)')
        elif is_key_layer_tap_hold(item):
            timing = timings[item["timing"]]
            if item["hold"].get("mode", "momentary") != "momentary":
                fail(f"unsupported key layer tap-hold {name!r}")
            quick_tap = f'; quick-tap-ms = <{timing["quick_tap_ms"]}>' if "quick_tap_ms" in timing else ""
            lines.append(f'ZMK_HOLD_TAP({name}, bindings = <&mo>, <&kp>; flavor = "{timing["flavor"]}"; tapping-term-ms = <{timing["tapping_term_ms"]}>{quick_tap};)')
        elif is_key_key_tap_hold(item):
            timing = timings[item["timing"]]
            quick_tap = f'; quick-tap-ms = <{timing["quick_tap_ms"]}>' if "quick_tap_ms" in timing else ""
            lines.append(f'ZMK_HOLD_TAP({name}, bindings = <&kp>, <&kp>; flavor = "{timing["flavor"]}"; tapping-term-ms = <{timing["tapping_term_ms"]}>{quick_tap};)')
        elif recipe == "tap_hold" and name == "glove_magic" and name in {cell.get("use") for cells in ir["layers"].values() for cell in cells if isinstance(cell, dict)}:
            timing = timings[item["timing"]]
            lines.append("ZMK_MACRO(rgb_status, bindings = <&rgb_ug RGB_STATUS>;)")
            lines.append(f'ZMK_HOLD_TAP({name}, bindings = <&mo>, <&rgb_status>; flavor = "{timing["flavor"]}"; tapping-term-ms = <{timing["tapping_term_ms"]}>; quick-tap-ms = <{timing["quick_tap_ms"]}>;)')
    if layer_chords or layer_sticky_mods:
        lines.extend(["", "/ {", "    behaviors {"])
        for name, item in layer_chords:
            lines.extend([
                f"        {name}: {name} {{",
                '            compatible = "zmk,behavior-layer-chord";',
                "            #binding-cells = <0>;",
                f'            parent-layer = <LAYER_{item["parent_layer"]}>;',
                f'            child-layer = <LAYER_{item["child_layer"]}>;',
                f'            parent-position = <{slot_indices[item["parent_position"]]}>;',
                f'            child-position = <{slot_indices[item["child_position"]]}>;',
                "        };",
            ])
        for name, item in layer_sticky_mods:
            bindings = [
                f"<&sk {zmk_key(model, behavior(model, modifier_behavior)['key'])}>"
                for modifier_behavior in item["modifier_behaviors"]
            ]
            positions = " ".join(str(slot_indices[position]) for position in item["modifier_positions"])
            lines.extend([
                f"        {name}: {name} {{",
                '            compatible = "zmk,behavior-layer-mod-chord";',
                "            #binding-cells = <0>;",
                f'            layer = <LAYER_{item["layer"]}>;',
                f'            layer-position = <{slot_indices[item["layer_position"]]}>;',
                f'            modifier-positions = <{positions}>;',
                f'            bindings = {", ".join(bindings)};',
                "        };",
            ])
        lines.extend(["    };", "};", ""])
    magic = behavior(model, "thumb_magic")
    repeat_keys = " ".join(chr(value) for value in range(ord("A"), ord("Z") + 1))
    lines.extend([
        '/ { behaviors { alpha_repeat: alpha_repeat { compatible = "zmk,behavior-alpha-repeat"; #binding-cells = <0>; }; }; };',
        f"ZMK_ADAPTIVE_KEY(thumb_magic_adaptive, bindings = <&sk LSHFT>; repeat {{ trigger-keys = <{repeat_keys}>; bindings = <&alpha_repeat>; max-prior-idle-ms = <{magic['repeat_timeout_ms']}>; strict-modifiers; }};)",
        "ZMK_MOD_MORPH(thumb_magic_tap, bindings = <&thumb_magic_adaptive>, <&caps_word>; mods = <(MOD_LSFT|MOD_RSFT)>;)",
        f'ZMK_HOLD_TAP(thumb_magic, bindings = <&kp>, <&thumb_magic_tap>; flavor = "{timings[magic["timing"]]["flavor"]}"; tapping-term-ms = <{timings[magic["timing"]]["tapping_term_ms"]}>; quick-tap-ms = <{timings[magic["timing"]]["quick_tap_ms"]}>;)',
    ])
    for adaptive_name in model["behaviors"].get("adaptives", {}):
        if not adaptive_layers(ir, adaptive_name):
            continue
        rules = adaptive_rules(model, adaptive_name, ir["variant"])
        by_input: dict[str, list[dict[str, Any]]] = {}
        for rule in rules:
            by_input.setdefault(rule["input"], []).append(rule)
        for input_key, input_rules in sorted(by_input.items()):
            base = f"adaptive_{ident(adaptive_name).lower()}_{ident(resolved_key(model, input_key)).lower()}"
            body = [f"ZMK_ADAPTIVE_KEY({base}, bindings = <&kp {zmk_key(model, input_key)}>;"]
            for index, rule in enumerate(input_rules):
                after = [zmk_key(model, token) for token in rule["after"]]
                emit = " ".join(zmk_action(model, ir, token) for token in rule["emit"])
                properties = [f"trigger-keys = <{after[-1]}>;"]
                if len(after) > 1:
                    properties.append(f"prior-keys = <{' '.join(after[:-1])}>;")
                properties.append(f"max-prior-idle-ms = <{rule['timeout_ms']}>;")
                properties.append(f"bindings = <{emit}>;")
                if rule["strict_modifiers"]:
                    properties.append("strict-modifiers;")
                body.append(f"r{index} {{ {' '.join(properties)} }};")
            body.append(")")
            lines.append(" ".join(body))
            used_cells = [
                cell
                for layer_name in adaptive_layers(ir, adaptive_name)
                for cell in ir["layers"][layer_name]
                if cell_tap(cell) is not None and resolved_key(model, cell_tap(cell)) == resolved_key(model, input_key)
            ]
            for hand in sorted({cell.get("hand") for cell in used_cells if isinstance(cell, dict) and cell.get("hand")}):
                side = "hml" if hand == "left" else "hmr"
                positions = right_positions + thumbs if hand == "left" else left_positions + thumbs
                trigger = f'; hold-trigger-key-positions = <{" ".join(map(str, positions))}>; hold-trigger-on-release' if h["opposite_hand_hold"] else ""
                lines.append(f'ZMK_HOLD_TAP({base}_{side}, bindings = <&kp>, <&{base}>; flavor = "{h["flavor"]}"; tapping-term-ms = <{h["tapping_term_ms"]}>; quick-tap-ms = <{h["quick_tap_ms"]}>; require-prior-idle-ms = <{h["prior_idle_ms"]}>{trigger};)')
    return lines


def render_zmk_leader(model: dict[str, Any], ir: dict[str, Any]) -> str:
    if not model["behaviors"].get("leader"):
        return ""
    children = []
    for index, item in enumerate(model["behaviors"].get("leader", [])):
        action = zmk_action(model, ir, item["action"])
        sequence = " ".join(zmk_key(model, token) for token in item["sequence"])
        children.append(f"s{index} {{ sequence = <{sequence}>; bindings = <{action}>; }};")
    return f'/ {{ behaviors {{ leader: leader {{ compatible = "zmk,behavior-leader-key"; #binding-cells = <0>; {" ".join(children)} }}; }}; }};'


def render_zmk(model: dict[str, Any], ir: dict[str, Any]) -> str:
    zmk = ir["profile"]["zmk"]
    move = model["behaviors"]["timings"]["mouse_move"]
    scroll = model["behaviors"]["timings"]["mouse_scroll"]
    includes = [
        "#include <behaviors.dtsi>",
        "#include <dt-bindings/zmk/keys.h>",
        "#include <dt-bindings/zmk/bt.h>",
        "#include <dt-bindings/zmk/outputs.h>",
        f"#define ZMK_POINTING_DEFAULT_MOVE_VAL {move['value']}",
        f"#define ZMK_POINTING_DEFAULT_SCRL_VAL {scroll['value']}",
        "#include <dt-bindings/zmk/mouse.h>",
        "#include <zmk-helpers/helper.h>",
    ]
    if zmk.get("physical_layout_include"):
        includes.append(f'#include <{zmk["physical_layout_include"]}>')
    if zmk.get("transform"):
        includes.append("#include <dt-bindings/zmk/matrix_transform.h>")
    if any("rgb" in cell for cells in ir["layers"].values() for cell in cells if isinstance(cell, dict)):
        includes.append("#include <dt-bindings/zmk/rgb.h>")
    if ir["profile"].get("capabilities", {}).get("lighting") == "backlight":
        includes.append("#include <dt-bindings/zmk/backlight.h>")
    lines = includes + [""]
    if zmk.get("physical_layout"):
        lines.extend([
            "/ {",
            "    chosen {",
            f'        zmk,physical-layout = &{zmk["physical_layout"]};',
            "    };",
            "};",
            "",
        ])
    if zmk.get("transform"):
        coordinates = [f"RC({row},{column})" for row, column in zmk["transform"]]
        lines.extend(["&default_transform {", "    map = <"])
        for index in range(0, len(coordinates), 12):
            lines.append("        " + " ".join(coordinates[index:index + 12]))
        lines.extend(["    >;", "};", ""])
    for name, index in ir["layer_index"].items():
        lines.append(f"#define LAYER_{name} {index}")
    lines.append("")
    if ir["conditional_layers"]:
        lines.extend(["/ {", "    conditional_layers {", '        compatible = "zmk,conditional-layers";'])
        for conditional in ir["conditional_layers"]:
            name = ident(conditional["then_layer"]).lower()
            if_layers = " ".join(f"LAYER_{layer}" for layer in conditional["if_layers"])
            lines.append(f"        conditional_{name} {{ if-layers = <{if_layers}>; then-layer = <LAYER_{conditional['then_layer']}>; }};")
        lines.extend(["    };", "};", ""])
    lines.extend(render_zmk_behaviors(model, ir))
    lines.extend([
        "",
        render_zmk_leader(model, ir),
        "",
        "/ {",
        "    behaviors {",
        "        behavior_caps_word { continue-list = <UNDERSCORE MINUS BACKSPACE DELETE N1 N2 N3 N4 N5 N6 N7 N8 N9 N0>; };",
        "    };",
        "};",
        "",
    ])
    sticky_mod = model["behaviors"]["timings"]["sticky_mod"]
    sticky_layer = model["behaviors"]["timings"]["sticky_layer"]
    lines.extend([
        f"&mmv {{ trigger-period-ms = <{move['interval_ms']}>; time-to-max-speed-ms = <{move['time_to_max_ms']}>; delay-ms = <{move['delay_ms']}>; }};",
        f"&msc {{ trigger-period-ms = <{scroll['interval_ms']}>; time-to-max-speed-ms = <{scroll['time_to_max_ms']}>; delay-ms = <{scroll['delay_ms']}>; }};",
        f"&sk {{ release-after-ms = <{sticky_mod['release_after_ms']}>; quick-release; ignore-modifiers; }};",
        f"&sl {{ release-after-ms = <{sticky_layer['release_after_ms']}>; ignore-modifiers; }};",
        "",
        "/ {",
        "    combos {",
        '        compatible = "zmk,combos";',
    ])
    combo_default = model["behaviors"]["timings"]["combo"]
    for combo in ir["combos"]:
        layers = " ".join(f"LAYER_{layer}" for layer in combo["layers"])
        positions = " ".join(map(str, combo["indices"]))
        action = zmk_action(model, ir, combo["action"])
        term = combo.get("term_ms", combo_default["term_ms"])
        idle = combo.get("prior_idle_ms", combo_default["prior_idle_ms"])
        node = ident(combo["name"]).lower()
        slow_release = " slow-release;" if combo.get("slow_release") else ""
        lines.append(f"        {node} {{ timeout-ms = <{term}>; require-prior-idle-ms = <{idle}>; key-positions = <{positions}>; layers = <{layers}>; bindings = <{action}>;{slow_release} }};")
    lines.extend(["    };", "", "    keymap {", '        compatible = "zmk,keymap";'])
    sensor_bindings = ir["profile"].get("capabilities", {}).get("sensor_bindings", [])
    for layer_name, cells in ir["layers"].items():
        lines.append(f"        layer_{ident(layer_name)} {{")
        lines.append(f'            display-name = "{layer_name}";')
        lines.append("            bindings = <")
        layer_adaptives = [name for name in model["behaviors"].get("adaptives", {}) if layer_name in adaptive_layers(ir, name)]
        adaptive_name = layer_adaptives[0] if layer_adaptives else None
        rendered = [zmk_action(model, ir, cell, adaptive_name) for cell in cells]
        for index in range(0, len(rendered), 10):
            lines.append("                " + "  ".join(rendered[index:index + 10]))
        lines.append("            >;")
        for sensor in sensor_bindings:
            lines.append(f"            sensor-bindings = <&inc_dec_kp {sensor[0]} {sensor[1]}>;")
        lines.append("        };")
    lines.extend(["    };", "};", ""])
    return "\n".join(lines)


def qmk_layer(name: str) -> str:
    return f"L_{ident(name).upper()}"


def custom_name(prefix: str, name: str) -> str:
    return f"RK_{prefix}_{ident(name).upper()}"


def qmk_layer_action(layer: str, mode: str) -> str:
    return {
        "momentary": f"MO({qmk_layer(layer)})",
        "toggle": f"TG({qmk_layer(layer)})",
        "sticky": f"OSL({qmk_layer(layer)})",
        "move": f"TO({qmk_layer(layer)})",
    }[mode]


def qmk_mod_tap(mod: str, tap: str) -> str:
    wrapper = {
        "LGUI": "LGUI_T",
        "LALT": "LALT_T",
        "LCTRL": "LCTL_T",
        "LSHFT": "LSFT_T",
        "RSHFT": "RSFT_T",
        "RCTRL": "RCTL_T",
        "RALT": "RALT_T",
        "RGUI": "RGUI_T",
    }[mod]
    return f"{wrapper}({tap})"


def qmk_native_tap_hold_spec(model: dict[str, Any], value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and "use" in value:
        name = value["use"]
        item = behavior(model, name)
        if item["recipe"] == "repeat_magic":
            return {
                "keycode": qmk_mod_tap(resolved_key(model, item["hold"]), "KC_NO"),
                "timing": item["timing"],
                "magic": True,
            }
        if is_key_layer_tap_hold(item):
            if item["hold"].get("mode", "momentary") != "momentary":
                fail(f"unsupported QMK key layer tap-hold {name!r}")
            return {
                "keycode": f"LT({qmk_layer(item['hold']['layer'])}, {qmk_key(model, item['tap'])})",
                "timing": item["timing"],
            }
        if is_layer_tap_hold(item):
            if item["hold"].get("mode", "momentary") != "momentary" or item["tap"].get("mode") != "sticky":
                fail(f"unsupported QMK layer tap-hold {name!r}")
            return {
                "keycode": f"LT({qmk_layer(item['hold']['layer'])}, KC_NO)",
                "timing": item["timing"],
                "oneshot_layer": item["tap"]["layer"],
            }
    if isinstance(value, dict) and "tap" in value and not value.get("hand"):
        hold = value["hold"]
        if isinstance(hold, dict) and "layer" in hold and hold.get("mode", "momentary") == "momentary":
            return {
                "keycode": f"LT({qmk_layer(hold['layer'])}, {qmk_key(model, value['tap'])})",
                "timing": value.get("timing", "thumb"),
            }
    return None


def tap_dance_spec(model: dict[str, Any], value: Any) -> dict[str, Any] | None:
    timings = model["behaviors"]["timings"]
    if isinstance(value, dict) and "use" in value:
        item = behavior(model, value["use"])
        if item["recipe"] == "tap_hold":
            value = item
        elif item["recipe"] == "sticky_key":
            key = resolved_key(model, item["key"])
            return {
                "name": f"sticky_{key}",
                "tap_kind": "RAZEN_TAP_ONESHOT_MOD",
                "tap": QMK_ONESHOT_MODS[key],
                "hold_kind": "RAZEN_HOLD_KEY",
                "hold": qmk_key(model, key),
                "timing": item["timing"],
                "hold_on_interrupt": True,
            }
    if is_sticky_key_layer_tap_hold(model, value):
        modifier = resolved_key(model, behavior(model, value["tap"]["use"])["key"])
        return {
            "name": f"{value['hold']['layer']}_{modifier}",
            "tap_kind": "RAZEN_TAP_SMART_SHIFT" if modifier in {"LSHFT", "RSHFT"} else "RAZEN_TAP_ONESHOT_MOD",
            "tap": QMK_ONESHOT_MODS[modifier],
            "hold_kind": "RAZEN_HOLD_LAYER",
            "hold": qmk_layer(value["hold"]["layer"]),
            "timing": value["timing"],
        }
    if is_shift_morph_layer_tap_hold(model, value):
        tap = value["tap"]["use"]
        return {
            "name": f"{value['hold']['layer']}_{tap}",
            "tap_kind": "RAZEN_TAP_MORPH",
            "tap": custom_name("MORPH", tap),
            "hold_kind": "RAZEN_HOLD_LAYER",
            "hold": qmk_layer(value["hold"]["layer"]),
            "timing": value["timing"],
        }
    if isinstance(value, dict) and "tap" in value and not value.get("hand"):
        hold = value["hold"]
        if isinstance(hold, str):
            hold_key = qmk_key(model, hold)
        elif isinstance(hold, dict) and "key" in hold:
            hold_key = with_mods(qmk_key(model, hold["key"]), hold.get("mods", []), QMK_MODS)
        else:
            return None
        timing_name = value.get("timing", "function_number")
        timing = timings[timing_name]
        return {"name": f"{hold_key}_{value['tap']}", "tap_kind": "RAZEN_TAP_KEY", "tap": qmk_key(model, value["tap"]), "hold_kind": "RAZEN_HOLD_KEY", "hold": hold_key, "timing": timing_name, "hold_on_interrupt": timing.get("flavor") != "tap-preferred"}
    return None


def collect_tap_dances(model: dict[str, Any], ir: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    specs: dict[str, dict[str, Any]] = {}
    keys: dict[str, str] = {}
    actions = [cell for cells in ir["layers"].values() for cell in cells]
    actions.extend(combo["action"] for combo in ir["combos"])
    for action in actions:
        spec = tap_dance_spec(model, action)
        if spec is None:
            continue
        signature = stable_json(spec)
        if signature not in keys:
            base = f"TD_{ident(spec['name']).upper()}"
            name = base
            suffix = 2
            while name in specs:
                name = f"{base}_{suffix}"
                suffix += 1
            keys[signature] = name
            specs[name] = spec
    return specs, keys


def collect_native_tap_holds(model: dict[str, Any], ir: dict[str, Any]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    actions = [cell for cells in ir["layers"].values() for cell in cells]
    actions.extend(combo["action"] for combo in ir["combos"])
    for action in actions:
        spec = qmk_native_tap_hold_spec(model, action)
        if spec is None:
            continue
        keycode = spec["keycode"]
        if keycode in result and result[keycode] != spec:
            fail(f"QMK tap-hold keycode collision for {keycode}")
        result[keycode] = spec
    return list(result.values())


def qmk_action(model: dict[str, Any], ir: dict[str, Any], value: Any, td_keys: dict[str, str]) -> str:
    native = qmk_native_tap_hold_spec(model, value)
    if native is not None:
        return native["keycode"]
    spec = tap_dance_spec(model, value)
    if spec is not None:
        return f"TD({td_keys[stable_json(spec)]})"
    if isinstance(value, str):
        if value == "none":
            return "KC_NO"
        if value == "trans":
            return "KC_TRNS"
        return qmk_key(model, value)
    if "tap" in value:
        if value.get("hand"):
            mod = resolved_key(model, value["hold"])
            return qmk_mod_tap(mod, qmk_key(model, value["tap"]))
        hold = value["hold"]
        if isinstance(hold, dict) and "layer" in hold and hold.get("mode", "momentary") == "momentary":
            return f"LT({qmk_layer(hold['layer'])}, {qmk_key(model, value['tap'])})"
        fail(f"cannot render QMK tap-hold {value!r}")
    if "use" in value:
        name = value["use"]
        item = behavior(model, name)
        if not behavior_available(item, "qmk"):
            return "KC_NO"
        recipe = item["recipe"]
        if recipe == "shift_morph":
            return custom_name("MORPH", name)
        if recipe == "sequence":
            return custom_name("SEQUENCE", name)
        if recipe == "macro":
            return custom_name("MACRO", name)
        if recipe == "adaptive_repeat":
            return custom_name("ADAPTIVE_REPEAT", name)
        if recipe == "layer_action":
            return qmk_layer_action(item["layer"], item["mode"])
        if recipe == "layer_chord":
            return custom_name("LAYER_CHORD", name)
        if recipe == "smart_layer":
            return custom_name("SMART_LAYER", name)
        if recipe == "sticky_key":
            return f"OSM({QMK_ONESHOT_MODS[resolved_key(model, item['key'])]})"
        if recipe == "leader":
            return "QK_LEAD"
        if recipe == "platform":
            return {
                "bootloader": "QK_BOOT", "reset": "QK_RBT", "caps_word": "CW_TOGG",
                "key_repeat": "QK_REP",
            }.get(item["action"], "KC_NO")
        fail(f"cannot render QMK behavior {name!r}")
    if "key" in value:
        return with_mods(qmk_key(model, value["key"]), value.get("mods", []), QMK_MODS)
    if "os" in value:
        return qmk_action(model, ir, resolve_os(model, ir["os"], value["os"]), td_keys)
    if "layer" in value:
        return qmk_layer_action(value["layer"], value.get("mode", "momentary"))
    if "mouse" in value:
        return MOUSE_QMK[value["mouse"]]
    if "light" in value:
        return {"toggle": "RGB_TOG", "decrease": "RGB_VAD", "increase": "RGB_VAI"}[value["light"]]
    if "rgb" in value or "platform" in value:
        return "KC_NO"
    fail(f"cannot render QMK action {value!r}")


def qmk_basic(model: dict[str, Any], ir: dict[str, Any], value: Any) -> str:
    if isinstance(value, str):
        return qmk_key(model, value)
    if isinstance(value, dict) and "key" in value:
        return with_mods(qmk_key(model, value["key"]), value.get("mods", []), QMK_MODS)
    if isinstance(value, dict) and "os" in value:
        return qmk_basic(model, ir, resolve_os(model, ir["os"], value["os"]))
    fail(f"expected basic QMK action, got {value!r}")


def qmk_custom_ids(model: dict[str, Any], ir: dict[str, Any]) -> list[str]:
    result = []
    for name, item in model["behaviors"]["behaviors"].items():
        if not behavior_available(item, "qmk") or not behavior_layer_refs(model, item).issubset(ir["layers"]):
            continue
        if item["recipe"] == "shift_morph":
            result.append(custom_name("MORPH", name))
        elif item["recipe"] == "sequence":
            result.append(custom_name("SEQUENCE", name))
        elif item["recipe"] == "macro":
            result.append(custom_name("MACRO", name))
        elif item["recipe"] == "adaptive_repeat":
            result.append(custom_name("ADAPTIVE_REPEAT", name))
        elif item["recipe"] == "smart_layer":
            result.append(custom_name("SMART_LAYER", name))
        elif item["recipe"] == "layer_chord":
            result.append(custom_name("LAYER_CHORD", name))
    return result


def qmk_leader_statement(model: dict[str, Any], ir: dict[str, Any], value: Any) -> str:
    if isinstance(value, str):
        return f"tap_code16({qmk_key(model, value)});"
    if "key" in value:
        return f"tap_code16({with_mods(qmk_key(model, value['key']), value.get('mods', []), QMK_MODS)});"
    if "use" in value:
        item = behavior(model, value["use"])
        if not behavior_available(item, "qmk"):
            return ""
        if item["recipe"] == "layer_action":
            return f"layer_move({qmk_layer(item['layer'])});"
        if item["recipe"] == "sequence":
            values = [qmk_key(model, token) for token in item["keys"]] if "keys" in item else [qmk_basic(model, ir, step) for step in item["steps"]]
            return " ".join(f"tap_code16_delay({value}, RAZEN_SEQUENCE_DELAY);" for value in values)
        if item["recipe"] == "macro":
            statements = []
            for step in item["steps"]:
                if "layer" in step and step.get("mode") == "move":
                    statements.append(f"layer_move({qmk_layer(step['layer'])});")
                else:
                    statements.append(qmk_leader_statement(model, ir, step))
            return " ".join(statements)
        if item["recipe"] == "platform":
            return {"bootloader": "reset_keyboard();", "reset": "soft_reset_keyboard();"}.get(item["action"], "")
    if "platform" in value:
        return ""
    return ""


def render_qmk(model: dict[str, Any], ir: dict[str, Any]) -> str:
    specs, td_keys = collect_tap_dances(model, ir)
    native_tap_holds = collect_native_tap_holds(model, ir)
    custom_ids = qmk_custom_ids(model, ir)
    position_ids = [f"P_{ident(slot).upper()}" for slot in ir["slots"]]
    layout = ir["profile"]["qmk"]["layout"]
    lines = ["#include QMK_KEYBOARD_H", '#include "razen.h"', "", "enum generated_keycodes {"]
    for index, name in enumerate(custom_ids + position_ids):
        lines.append(f"    {name}{' = SAFE_RANGE' if index == 0 else ''},")
    magic = behavior(model, "thumb_magic")
    magic_spec = qmk_native_tap_hold_spec(model, {"use": "thumb_magic"})
    smart = smart_layer_behavior(model)
    adaptive_repeats = [
        (name, item)
        for name, item in model["behaviors"]["behaviors"].items()
        if item["recipe"] == "adaptive_repeat" and behavior_available(item, "qmk") and behavior_layer_refs(model, item).issubset(ir["layers"])
    ]
    if len(adaptive_repeats) != 1:
        fail("QMK needs exactly one adaptive_repeat behavior")
    adaptive_repeat_name, adaptive_repeat = adaptive_repeats[0]
    layer_chords = [
        (name, item)
        for name, item in model["behaviors"]["behaviors"].items()
        if item["recipe"] == "layer_chord" and behavior_available(item, "qmk") and behavior_layer_refs(model, item).issubset(ir["layers"])
    ]
    lines.extend([
        "};",
        "",
        f"const uint16_t razen_magic_keycode = {magic_spec['keycode']};",
        f"const uint16_t razen_magic_hold_keycode = {qmk_key(model, magic['hold'])};",
        f"const uint16_t razen_adaptive_repeat_keycode = {custom_name('ADAPTIVE_REPEAT', adaptive_repeat_name)};",
        f"const uint16_t razen_adaptive_repeat_marker = {qmk_key(model, adaptive_repeat['marker'])};",
        f"const uint16_t razen_adaptive_repeat_timeout = {adaptive_repeat['timeout_ms']};",
        f"const bool razen_adaptive_repeat_strict_modifiers = {'true' if adaptive_repeat['strict_modifiers'] else 'false'};",
        "const razen_adaptive_repeat_rule_t razen_adaptive_repeat_rules[] = {",
        *(f"    {{{qmk_key(model, rule['after'])}, {qmk_key(model, rule['emit'])}}}," for rule in adaptive_repeat["rules"]),
        "};",
        "const uint8_t razen_adaptive_repeat_rule_count = sizeof(razen_adaptive_repeat_rules) / sizeof(razen_adaptive_repeat_rules[0]);",
        "",
    ])
    if smart is not None and behavior_available(smart[1], "qmk"):
        smart_name, smart_item = smart
        smart_positions = [position_ids[index] for index in smart_layer_indices(model, ir, smart_name, smart_item)]
        lines.extend([
            f"const uint16_t razen_smart_layer_keycode = {custom_name('SMART_LAYER', smart_name)};",
            f"const uint8_t razen_smart_layer = {qmk_layer(smart_item['layer'])};",
            f"const uint16_t razen_smart_layer_positions[] = {{{', '.join(smart_positions)}}};",
            "const uint8_t razen_smart_layer_position_count = sizeof(razen_smart_layer_positions) / sizeof(razen_smart_layer_positions[0]);",
            "",
        ])
    if layer_chords:
        slot_positions = dict(zip(ir["slots"], position_ids))
        lines.append("razen_layer_chord_t razen_layer_chords[] = {")
        for name, item in layer_chords:
            tap = qmk_key(model, item["tap"]) if "tap" in item else "KC_NO"
            term = model["behaviors"]["timings"][item["timing"]]["tapping_term_ms"] if "tap" in item else 0
            lines.append(
                f"    {{{custom_name('LAYER_CHORD', name)}, {qmk_layer(item['parent_layer'])}, "
                f"{qmk_layer(item['child_layer'])}, {slot_positions[item['parent_position']]}, "
                f"{slot_positions[item['child_position']]}, {tap}, {term}, 0, false, false, false}},"
            )
        lines.extend([
            "};",
            "const uint8_t razen_layer_chord_count = sizeof(razen_layer_chords) / sizeof(razen_layer_chords[0]);",
            "",
        ])
    lines.append("enum generated_tap_dances {")
    for name in specs or ("TD_UNUSED",):
        lines.append(f"    {name},")
    lines.extend(["};", "", "const razen_morph_t razen_morphs[] = {"])
    for name, item in model["behaviors"]["behaviors"].items():
        if item["recipe"] == "shift_morph" and behavior_available(item, "qmk"):
            lines.append(f"    {{{custom_name('MORPH', name)}, {qmk_basic(model, ir, item['tap'])}, {qmk_basic(model, ir, item['shifted'])}}},")
    lines.extend(["};", "const uint8_t razen_morph_count = sizeof(razen_morphs) / sizeof(razen_morphs[0]);", "", "const razen_macro_t razen_macros[] = {"])
    for name, item in model["behaviors"]["behaviors"].items():
        if item["recipe"] != "macro" or not behavior_available(item, "qmk") or not behavior_layer_refs(model, item).issubset(ir["layers"]):
            continue
        layer_step = next((step for step in item["steps"] if "layer" in step), None)
        key_step = next((step for step in item["steps"] if "key" in step), None)
        if layer_step is None or key_step is None:
            fail(f"QMK macro {name} must contain one layer and one key step")
        lines.append(f"    {{{custom_name('MACRO', name)}, {qmk_layer(layer_step['layer'])}, {qmk_basic(model, ir, key_step)}}},")
    lines.extend(["};", "const uint8_t razen_macro_count = sizeof(razen_macros) / sizeof(razen_macros[0]);", "", "const razen_sequence_t razen_sequences[] = {"])
    for name, item in model["behaviors"]["behaviors"].items():
        if item["recipe"] == "sequence" and behavior_available(item, "qmk"):
            values = [qmk_key(model, token) for token in item["keys"]] if "keys" in item else [qmk_basic(model, ir, step) for step in item["steps"]]
            lines.append(f"    {{{custom_name('SEQUENCE', name)}, {{{', '.join(values)}}}, {len(values)}}},")
    lines.extend(["};", "const uint8_t razen_sequence_count = sizeof(razen_sequences) / sizeof(razen_sequences[0]);", "", "const razen_adaptive_rule_t razen_adaptive_rules[] = {"])
    adaptive_count = 0
    for adaptive_name in model["behaviors"].get("adaptives", {}):
        for matching_layer in adaptive_layers(ir, adaptive_name):
            for rule in adaptive_rules(model, adaptive_name, ir["variant"]):
                after = [qmk_key(model, token) for token in rule["after"]]
                emit = [qmk_key(model, token) for token in rule["emit"]]
                lines.append(f"    {{{qmk_layer(matching_layer)}, {qmk_key(model, rule['input'])}, {{{', '.join(after)}}}, {len(after)}, {{{', '.join(emit)}}}, {len(emit)}, {rule['timeout_ms']}, {'true' if rule['strict_modifiers'] else 'false'}}},")
                adaptive_count += 1
    lines.extend(["};", f"const uint8_t razen_adaptive_rule_count = {adaptive_count};", "", "razen_tap_dance_t razen_tap_dance_data[] = {"])
    for name, spec in specs.items():
        timing = model["behaviors"]["timings"][spec["timing"]]
        lines.append(f"    [{name}] = {{{spec['tap_kind']}, {spec['tap']}, {spec['hold_kind']}, {spec['hold']}, {timing['tapping_term_ms']}, {'true' if spec.get('hold_on_interrupt', timing.get('flavor') != 'tap-preferred') else 'false'}, false}},")
    if not specs:
        lines.append("    [TD_UNUSED] = {0},")
    lines.extend(["};", "", "tap_dance_action_t tap_dance_actions[] = {"])
    for name in specs:
        lines.append(f"    [{name}] = RAZEN_TAP_DANCE(&razen_tap_dance_data[{name}]),")
    if not specs:
        lines.append("    [TD_UNUSED] = {.fn = {NULL, NULL, NULL, NULL}, .user_data = NULL},")
    lines.extend(["};", "", "const uint16_t razen_home_row_keys[] = {"])
    home_keys = []
    for cells in ir["layers"].values():
        for cell in cells:
            if isinstance(cell, dict) and cell.get("hand"):
                keycode = qmk_action(model, ir, cell, td_keys)
                if keycode not in home_keys:
                    home_keys.append(keycode)
    lines.append("    " + ", ".join(home_keys))
    balanced_keys = []
    hold_preferred_keys = []
    for spec in native_tap_holds:
        flavor = model["behaviors"]["timings"][spec["timing"]]["flavor"]
        if flavor == "balanced" and spec["keycode"] not in balanced_keys:
            balanced_keys.append(spec["keycode"])
        if flavor == "hold-preferred" and spec["keycode"] not in hold_preferred_keys:
            hold_preferred_keys.append(spec["keycode"])
    lines.extend([
        "};",
        "const uint8_t razen_home_row_key_count = sizeof(razen_home_row_keys) / sizeof(razen_home_row_keys[0]);",
        "",
        "const uint16_t razen_balanced_keys[] = {",
        "    " + ", ".join(balanced_keys),
        "};",
        "const uint8_t razen_balanced_key_count = sizeof(razen_balanced_keys) / sizeof(razen_balanced_keys[0]);",
        "",
        "const uint16_t razen_hold_preferred_keys[] = {",
        "    " + ", ".join(hold_preferred_keys),
        "};",
        "const uint8_t razen_hold_preferred_key_count = sizeof(razen_hold_preferred_keys) / sizeof(razen_hold_preferred_keys[0]);",
        "",
        "const razen_oneshot_layer_t razen_oneshot_layers[] = {",
    ])
    for spec in native_tap_holds:
        if "oneshot_layer" in spec:
            lines.append(f"    {{{spec['keycode']}, {qmk_layer(spec['oneshot_layer'])}}},")
    lines.extend([
        "};",
        "const uint8_t razen_oneshot_layer_count = sizeof(razen_oneshot_layers) / sizeof(razen_oneshot_layers[0]);",
        "",
        "const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {",
    ])
    for layer_name, cells in ir["layers"].items():
        lines.append(f"    [{qmk_layer(layer_name)}] = {layout}(")
        rendered = [qmk_action(model, ir, cell, td_keys) for cell in cells]
        for index in range(0, len(rendered), 10):
            comma = "," if index + 10 < len(rendered) else ""
            lines.append("        " + ", ".join(rendered[index:index + 10]) + comma)
        lines.append("    ),")
    lines.append(f"    [L_COMBO_REF] = {layout}(")
    for index in range(0, len(position_ids), 10):
        comma = "," if index + 10 < len(position_ids) else ""
        lines.append("        " + ", ".join(position_ids[index:index + 10]) + comma)
    lines.extend(["    ),", "};", "", f"const char chordal_hold_layout[MATRIX_ROWS][MATRIX_COLS] PROGMEM = {layout}("])
    hands = ["'*'" if "THUMB" in slot else "'L'" if slot.startswith("L_") else "'R'" if slot.startswith("R_") else "'*'" for slot in ir["slots"]]
    for index in range(0, len(hands), 12):
        comma = "," if index + 12 < len(hands) else ""
        lines.append("    " + ", ".join(hands[index:index + 12]) + comma)
    lines.extend([");", "", "uint8_t combo_ref_from_layer(uint8_t layer) {", "    (void)layer;", "    return L_COMBO_REF;", "}", "", "enum generated_combos {"])
    for combo in ir["combos"]:
        lines.append(f"    CB_{ident(combo['name']).upper()},")
    lines.extend(["};", ""])
    for combo in ir["combos"]:
        positions = ", ".join(position_ids[index] for index in combo["indices"])
        lines.append(f"const uint16_t PROGMEM combo_{ident(combo['name']).lower()}[] = {{{positions}, COMBO_END}};")
    lines.extend(["", "combo_t key_combos[] = {"])
    for combo in ir["combos"]:
        action = qmk_action(model, ir, combo["action"], td_keys)
        lines.append(f"    [CB_{ident(combo['name']).upper()}] = COMBO(combo_{ident(combo['name']).lower()}, {action}),")
    lines.extend(["};", "", "const razen_combo_t razen_combos[] = {"])
    combo_timing = model["behaviors"]["timings"]["combo"]
    for combo in ir["combos"]:
        mask = " | ".join(f"(1UL << {qmk_layer(layer)})" for layer in combo["layers"])
        lines.append(f"    {{{mask}, {combo.get('term_ms', combo_timing['term_ms'])}, {combo.get('prior_idle_ms', combo_timing['prior_idle_ms'])}}},")
    lines.extend(["};", "const uint8_t razen_combo_count = sizeof(razen_combos) / sizeof(razen_combos[0]);", ""])
    if ir["conditional_layers"] or layer_chords:
        lines.append("layer_state_t layer_state_set_user(layer_state_t state) {")
        if layer_chords:
            lines.extend([
                "    for (uint8_t index = 0; index < razen_layer_chord_count; index++) {",
                "        if (razen_layer_chords[index].parent_pressed) state |= 1UL << razen_layer_chords[index].parent_layer;",
                "        if (razen_layer_chords[index].child_pressed) state |= 1UL << razen_layer_chords[index].child_layer;",
                "    }",
            ])
        for conditional in ir["conditional_layers"]:
            first, second = conditional["if_layers"]
            lines.append(f"    state = update_tri_layer_state(state, {qmk_layer(first)}, {qmk_layer(second)}, {qmk_layer(conditional['then_layer'])});")
        lines.extend(["    return state;", "}", ""])
    if model["behaviors"].get("leader"):
        lines.append("void leader_end_user(void) {")
        leader_count = 0
        for item in model["behaviors"]["leader"]:
            sequence = ", ".join(qmk_key(model, token) for token in item["sequence"])
            condition = f"leader_sequence_{['one', 'two', 'three', 'four', 'five'][len(item['sequence']) - 1]}_key{'s' if len(item['sequence']) > 1 else ''}({sequence})"
            statement = qmk_leader_statement(model, ir, item["action"])
            if not statement:
                continue
            lines.append(f"    {'if' if leader_count == 0 else 'else if'} ({condition}) {{ {statement} }}")
            leader_count += 1
        lines.extend(["}", ""])
    return "\n".join(lines)


def render_qmk_config(model: dict[str, Any], ir: dict[str, Any]) -> str:
    timing = model["behaviors"]["timings"]
    magic = behavior(model, "thumb_magic")
    move = timing["mouse_move"]
    scroll = timing["mouse_scroll"]
    move_max_speed = max(1, round(move["value"] * move["interval_ms"] / 1000))
    move_time_to_max = max(1, round(move["time_to_max_ms"] / move["interval_ms"]))
    scroll_interval = max(1, round(1000 / scroll["value"]))
    lines = [
        "#pragma once",
        "",
        "#ifndef __ASSEMBLER__",
        "enum razen_layers {",
        *(f"    {qmk_layer(name)}," for name in ir["layers"]),
        "    L_COMBO_REF,",
        "};",
        "#endif",
        "",
        f"#define RAZEN_LAYER_NAMES {{{', '.join(json.dumps(name) for name in ir['layers'])}}}",
        *(
            ["#define RAZEN_SMART_LAYER_ENABLE"]
            if (smart := smart_layer_behavior(model)) is not None and behavior_available(smart[1], "qmk")
            else []
        ),
        *(
            ["#define RAZEN_LAYER_CHORD_ENABLE", "#define COMBO_PROCESS_KEY_RELEASE", "#define COMBO_PROCESS_KEY_REPRESS"]
            if any(item["recipe"] == "layer_chord" and behavior_available(item, "qmk") for item in model["behaviors"]["behaviors"].values())
            else []
        ),
        f"#define RAZEN_HOME_ROW_TAPPING_TERM {timing['home_row']['tapping_term_ms']}",
        f"#define RAZEN_HOME_ROW_QUICK_TAP_TERM {timing['home_row']['quick_tap_ms']}",
        f"#define RAZEN_MAGIC_TAPPING_TERM {timing[magic['timing']]['tapping_term_ms']}",
        f"#define RAZEN_MAGIC_QUICK_TAP_TERM {timing[magic['timing']]['quick_tap_ms']}",
        f"#define RAZEN_MAGIC_REPEAT_TIMEOUT {magic['repeat_timeout_ms']}",
        *(
            ["#define CHORDAL_HOLD"]
            if timing["home_row"]["opposite_hand_hold"]
            else []
        ),
        f"#define RAZEN_SEQUENCE_DELAY {timing['sequence']['tap_ms']}",
        f"#define TAPPING_TERM {timing['thumb']['tapping_term_ms']}",
        "#define TAPPING_TERM_PER_KEY",
        f"#define QUICK_TAP_TERM {timing['thumb']['quick_tap_ms']}",
        "#define QUICK_TAP_TERM_PER_KEY",
        f"#define FLOW_TAP_TERM {timing['home_row']['prior_idle_ms']}",
        "#define PERMISSIVE_HOLD_PER_KEY",
        "#define HOLD_ON_OTHER_KEY_PRESS_PER_KEY",
        f"#define ONESHOT_TIMEOUT {timing['sticky_mod']['release_after_ms']}",
        "#define ONESHOT_TAP_TOGGLE 0",
        f"#define COMBO_TERM {timing['combo']['term_ms']}",
        "#define COMBO_TERM_PER_COMBO",
        "#define COMBO_SHOULD_TRIGGER",
        *([
            "#define LEADER_PER_KEY_TIMING",
            f"#define LEADER_TIMEOUT {timing['leader']['timeout_ms']}",
        ] if model["behaviors"].get("leader") else []),
        f"#define MOUSEKEY_DELAY {move['delay_ms']}",
        f"#define MOUSEKEY_INTERVAL {move['interval_ms']}",
        "#define MOUSEKEY_MOVE_DELTA 1",
        f"#define MOUSEKEY_MAX_SPEED {move_max_speed}",
        f"#define MOUSEKEY_TIME_TO_MAX {move_time_to_max}",
        f"#define MOUSEKEY_WHEEL_DELAY {scroll['delay_ms']}",
        f"#define MOUSEKEY_WHEEL_INTERVAL {scroll_interval}",
        "#define MOUSEKEY_WHEEL_MAX_SPEED 1",
        "#define MOUSEKEY_WHEEL_TIME_TO_MAX 0",
        "",
    ]
    return "\n".join(lines)


def label_key(model: dict[str, Any], token: str) -> str:
    alias = key_alias(model, token)
    if alias:
        return alias.get("label", token)
    if re.fullmatch(r"N[0-9]", token):
        return token[1:]
    return DISPLAY.get(token, token)


def label_action(model: dict[str, Any], ir: dict[str, Any], value: Any) -> Any:
    if isinstance(value, str):
        if value == "none":
            return ""
        if value == "trans":
            return {"t": "▽", "type": "trans"}
        return label_key(model, value)
    if "tap" in value:
        hold = value["hold"]
        hold_label = label_key(model, hold) if isinstance(hold, str) else hold.get("layer", "Hold")
        return {"t": label_action(model, ir, value["tap"]), "h": hold_label}
    if "use" in value:
        name = value["use"]
        item = behavior(model, name)
        if item["recipe"] == "shift_morph":
            tap = label_action(model, ir, item["tap"])
            shifted = label_action(model, ir, item["shifted"])
            return tap if tap == shifted else {"t": tap, "s": shifted}
        if item["recipe"] == "sequence":
            return item["label"]
        if item["recipe"] == "macro":
            return {"lang_en": "EN", "lang_ru": "RU", "lang_ua": "UA"}.get(name, name)
        if item["recipe"] == "layer_action":
            layer = item["layer"]
            return {
                "t": {"Graphite": "GRA", "Bunya": "BUN"}.get(layer, layer),
                "type": f"{ident(layer).lower()}-activator" if layer in {"Graphite", "Bunya", *model["root"].get("draw_hidden_layers", [])} else "layer-activator",
            }
        if item["recipe"] == "smart_layer":
            return {"t": item["layer"], "type": "layer-activator"}
        if item["recipe"] == "layer_chord":
            if "tap" in item:
                return {"t": label_key(model, item["tap"]), "h": item["child_layer"], "type": f"{ident(item['child_layer']).lower()}-activator"}
            return {"t": item["child_layer"], "type": "layer-activator"}
        if item["recipe"] == "layer_sticky_mod":
            modifier = behavior(model, item["modifier_behavior"])["key"]
            return {"t": label_key(model, modifier), "type": "mod"}
        if item["recipe"] == "sticky_key":
            return {"t": label_key(model, item["key"]), "type": "mod"}
        if item["recipe"] == "repeat_magic":
            return {"t": mdi("repeat"), "h": mdi("arrow-up-bold")}
        if item["recipe"] == "adaptive_repeat":
            return mdi("repeat")
        if is_sticky_key_layer_tap_hold(model, item) or is_shift_morph_layer_tap_hold(model, item):
            result = label_action(model, ir, item["tap"])
            result = dict(result) if isinstance(result, dict) else {"t": result}
            result.pop("type", None)
            if is_shift_morph_layer_tap_hold(model, item):
                result.pop("s", None)
            result["h"] = item["hold"]["layer"]
            return result
        if is_key_layer_tap_hold(item):
            return {"t": label_action(model, ir, item["tap"]), "h": item["hold"]["layer"]}
        if is_key_key_tap_hold(item):
            return {"t": label_action(model, ir, item["tap"]), "h": label_action(model, ir, item["hold"])}
        if is_layer_tap_hold(item):
            tap_layer = item["tap"]["layer"]
            hold_layer = item["hold"]["layer"]
            if tap_layer == hold_layer:
                return {"t": tap_layer, "type": "layer-activator"}
            result = {"t": tap_layer, "h": hold_layer}
            if tap_layer in model["root"].get("draw_hidden_layers", []):
                result["type"] = f"{ident(tap_layer).lower()}-activator"
            return result
        if name == "glove_magic":
            return {"t": "RGB", "h": "Magic"}
        if item["recipe"] == "leader":
            return mdi("star-four-points")
        if item["recipe"] == "platform":
            return {
                "bootloader": {"t": mdi("progress-download"), "s": "Boot"},
                "reset": {"t": mdi("restart"), "s": "Reset"},
                "soft_off": mdi("keyboard-off-outline"),
                "output_toggle": "OUT TOG",
                "bt_clear": "BT CLR",
                "bt_clear_all": "BT CLR ALL",
                "caps_word": "Caps Word",
                "key_repeat": mdi("repeat"),
                "bt_select": f"BT {item.get('value', '')}",
            }.get(item["action"], name)
    if "key" in value:
        mods = sorted(MOD_ALIASES.get(mod, mod) for mod in value.get("mods", []))
        shortcut = DRAW_SHORTCUTS.get((value["key"], *mods))
        if shortcut:
            return shortcut
        key = label_key(model, value["key"])
        return f"{''.join(label_key(model, mod) for mod in mods)}{key}" if mods else key
    if "os" in value:
        return OS_DISPLAY.get(value["os"], value["os"].replace("_", " ").title())
    if "layer" in value:
        return {"t": value["layer"], "type": "layer-activator"}
    if "mouse" in value:
        return MOUSE_DISPLAY[value["mouse"]]
    if "light" in value:
        return {"toggle": "Light", "decrease": "Light −", "increase": "Light +"}[value["light"]]
    if "rgb" in value:
        return RGB_DISPLAY[value["rgb"]]
    if "platform" in value:
        return value["platform"].replace("_", " ").title()
    return ""


def draw_ir(model: dict[str, Any], ir: dict[str, Any]) -> dict[str, Any]:
    result = dict(ir)
    profile = ir["profile"]
    slots = profile.get("qmk_draw_order") or [slot for slot in ir["slots"] if slot not in profile.get("board_only_positions", [])]
    indices = {slot: index for index, slot in enumerate(ir["slots"])}
    if len(slots) != profile["physical_keys"] or len(slots) != len(set(slots)) or not set(slots).issubset(indices):
        fail(f"profile {ir['profile_name']}: draw slots must uniquely match physical keys")
    result["slots"] = slots
    result["layers"] = {name: [cells[indices[slot]] for slot in slots] for name, cells in ir["layers"].items()}
    draw_slot_indices = {slot: index for index, slot in enumerate(slots)}
    result["combos"] = [
        {**combo, "indices": [draw_slot_indices[position] for position in combo["positions"]]}
        for combo in ir["combos"]
        if set(combo["positions"]).issubset(draw_slot_indices)
    ]
    if model["root"].get("draw_combo_reference_layer", False) and result["combos"]:
        result["combos"] = [{**combo, "layers": ["Combos"]} for combo in result["combos"]]
        result["layers"]["Combos"] = ["none"] * len(slots)
    return result


def held_layer(model: dict[str, Any], value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    item = behavior(model, value["use"]) if "use" in value else value
    hold = item.get("hold")
    if isinstance(hold, dict) and "layer" in hold:
        return hold["layer"]
    if "layer" in item and item.get("mode", "momentary") == "momentary":
        return item["layer"]
    return None


def render_draw(model: dict[str, Any], ir: dict[str, Any]) -> str:
    layers = {name: [label_action(model, ir, cell) for cell in cells] for name, cells in ir["layers"].items()}
    paired_layers = set()
    for item in model["behaviors"]["behaviors"].values():
        base = item.get("draw_on")
        alternate = item.get("layer")
        if alternate is None and is_layer_tap_hold(item):
            alternate = item["tap"]["layer"]
        if base not in layers or alternate not in layers:
            continue
        for index, cell in enumerate(ir["layers"][alternate]):
            if isinstance(cell, str) and cell in {"none", "trans"}:
                continue
            secondary = label_action(model, ir, cell)
            if isinstance(secondary, dict):
                if not layers[base][index]:
                    layers[base][index] = secondary
                    continue
                secondary = secondary.get("t") or secondary.get("s")
            current = layers[base][index]
            paired = dict(current) if isinstance(current, dict) else {"t": current}
            paired["s"] = secondary
            layers[base][index] = paired
        paired_layers.add(alternate)
    for layer in paired_layers:
        del layers[layer]
    for layer in model["root"].get("draw_hidden_layers", []):
        layers.pop(layer, None)
    for source, cells in ir["layers"].items():
        if source not in layers:
            continue
        for index, cell in enumerate(cells):
            if held_layer(model, cell) != "Num":
                continue
            current = layers[source][index]
            styled = dict(current) if isinstance(current, dict) else {"t": current}
            styled.setdefault("type", "num-activator")
            layers[source][index] = styled
    held = {name: set() for name in model["root"]["alpha_layers"] if name in layers}
    changed = True
    while changed:
        changed = False
        for source, cells in ir["layers"].items():
            if source not in held:
                continue
            for index, cell in enumerate(cells):
                target = held_layer(model, cell)
                if target not in layers:
                    continue
                indices = held[source] | {index}
                before = len(held.get(target, set()))
                held.setdefault(target, set()).update(indices)
                changed |= len(held[target]) != before
        for conditional in ir["conditional_layers"]:
            if not all(source in held for source in conditional["if_layers"]):
                continue
            target = conditional["then_layer"]
            indices = set().union(*(held[source] for source in conditional["if_layers"]))
            before = len(held.get(target, set()))
            held.setdefault(target, set()).update(indices)
            changed |= len(held[target]) != before
    for combo in ir["combos"]:
        action = combo["action"]
        item = behavior(model, action["use"]) if isinstance(action, dict) and "use" in action else None
        target = item["child_layer"] if item and item["recipe"] == "layer_chord" else held_layer(model, action)
        if target in layers:
            indices = combo["indices"]
            if item and item["recipe"] == "layer_sticky_mod":
                offset = combo["positions"].index(item["layer_position"])
                indices = [indices[offset]]
            held.setdefault(target, set()).update(indices)
    for layer, indices in held.items():
        for index in indices:
            layers[layer][index] = {"type": "held"}
    for conditional in ir["conditional_layers"]:
        sources = conditional["if_layers"]
        for source in sources:
            if source not in layers:
                continue
            opposite = set().union(*(held.get(other, set()) for other in sources if other != source)) - held.get(source, set())
            for index in opposite:
                layers[source][index] = {"type": "num-activator"}
    data: dict[str, Any] = {"layers": layers}
    combos = []
    for combo in ir["combos"]:
        drawing = combo.get("draw", {})
        if drawing is False:
            continue
        draw_layers = [layer for layer in drawing.get("layers", combo["layers"]) if layer in layers]
        if not draw_layers:
            continue
        key = label_action(model, ir, drawing.get("action", combo["action"]))
        if "type" in drawing:
            key = dict(key) if isinstance(key, dict) else {"t": key}
            key["type"] = drawing["type"]
        rendered = {"p": combo["indices"], "k": key, "l": draw_layers}
        if "align" in drawing:
            rendered["a"] = drawing["align"]
        if "offset" in drawing:
            rendered["o"] = drawing["offset"]
        combos.append(rendered)
    if combos:
        data["combos"] = combos
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def manifest(ir: dict[str, Any]) -> str:
    value = {key: ir[key] for key in ("version", "profile_name", "backend", "os", "slots", "variant", "layers", "layer_index", "conditional_layers", "combos", "source_hash")}
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def backend_output(model: dict[str, Any], ir: dict[str, Any], directory: Path) -> list[Path]:
    outputs = []
    if ir["backend"] == "zmk":
        path = directory / "keymap.keymap"
        write_output(path, render_zmk(model, ir))
        outputs.append(path)
    elif ir["backend"] == "qmk":
        path = directory / "keymap.c"
        config = directory / "razen_config.h"
        write_output(path, render_qmk(model, ir))
        write_output(config, render_qmk_config(model, ir))
        outputs.extend([path, config])
    elif ir["backend"] == "draw":
        path = directory / "keymap.yaml"
        write_output(path, render_draw(model, ir))
        outputs.append(path)
    else:
        fail(f"unknown backend {ir['backend']!r}")
    manifest_path = directory / "manifest.json"
    write_output(manifest_path, manifest(ir))
    outputs.append(manifest_path)
    return outputs


def render_svg(repo: Path, ir: dict[str, Any], yaml_path: Path, svg_path: Path) -> None:
    command = ["keymap", "-c", str(repo / "draw" / "config.yaml"), "draw", str(yaml_path), "-o", str(svg_path)]
    profile = ir["profile"]
    if profile.get("draw_notation"):
        command.extend(["-n", profile["draw_notation"]])
    elif profile.get("qmk_info"):
        command.extend(["-j", str(repo / profile["qmk_info"]), "-l", profile.get("qmk_draw_layout", profile.get("qmk", {}).get("layout", "LAYOUT"))])
    elif profile.get("zmk_transform"):
        command.extend(["-d", str(repo / profile["zmk_transform"])])
    elif profile.get("zmk_draw_keyboard"):
        command.extend(["-z", profile["zmk_draw_keyboard"]])
    elif profile.get("qmk"):
        command.extend(["-k", profile["qmk"]["keyboard"], "-l", profile.get("qmk_draw_layout", profile["qmk"]["layout"])])
    else:
        fail(f"profile {ir['profile_name']}: no draw geometry")
    subprocess.run(command, check=True)
    svg = svg_path.read_text()
    glyph_pattern = re.compile(r'<svg id="([^"]+)">\s*<svg[^>]* viewBox="([^"]+)"[^>]*>(.*?)</svg>\s*</svg>', re.S)
    glyphs = {match.group(1): (match.group(2), match.group(3)) for match in glyph_pattern.finditer(svg)}

    def inline_glyph(match: re.Match[str]) -> str:
        tag = match.group(0)
        reference = re.search(r'\bhref="#([^"]+)"', tag)
        if reference is None or reference.group(1) not in glyphs:
            return tag
        attributes = dict(re.findall(r'([\w-]+)="([^"]*)"', tag))
        rendered = " ".join(f'{name}="{attributes[name]}"' for name in ("x", "y", "height", "width", "class") if name in attributes)
        viewbox, body = glyphs[reference.group(1)]
        return f'<svg {rendered} viewBox="{viewbox}">{body}</svg>'

    def add_vestnik2_inner(match: re.Match[str]) -> str:
        outer = match.group(0)
        inner = outer.replace("vestnik2-activator", "vestnik2-inner").replace("/>", ' transform="scale(0.84)"/>')
        return f"{outer}\n{inner}"

    svg = re.sub(r"<use\b[^>]*/>", inline_glyph, svg)
    svg = re.sub(r'<rect\b[^>]*class="[^"]*\bvestnik2-activator\b[^"]*"[^>]*/>', add_vestnik2_inner, svg)
    svg_path.write_text(glyph_pattern.sub("", svg))


def generate_one(model: dict[str, Any], repo: Path, backend: str, profile: str, os_name: str, output: Path | None, svg: bool) -> list[Path]:
    profiles = model["profiles"]["profiles"]
    if profile not in profiles:
        fail(f"unknown profile {profile!r}")
    profile_data = profiles[profile]
    source_backend = "qmk" if backend == "draw" and profile_data.get("qmk_info") and "qmk" in profile_data else "zmk" if backend == "draw" and "zmk" in profile_data else "qmk" if backend == "draw" else backend
    ir = compile_profile(model, profile, source_backend, os_name)
    if backend == "draw":
        ir = draw_ir(model, ir)
    ir["backend"] = backend
    directory = output or repo / ".cache" / "keymap" / os_name / backend / profile
    outputs = backend_output(model, ir, directory)
    if backend == "draw" and svg:
        svg_path = directory / "keymap.svg" if output else repo / "draw" / "generated" / f"{profile}.svg"
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        render_svg(repo, ir, directory / "keymap.yaml", svg_path)
        outputs.append(svg_path)
    return outputs


def check_all(model: dict[str, Any], repo: Path, os_name: str) -> None:
    with tempfile.TemporaryDirectory(prefix="keymap-check-") as temporary:
        root = Path(temporary)
        first: dict[tuple[str, str], list[str]] = {}
        for profile_name, profile in model["profiles"]["profiles"].items():
            for backend in ("zmk", "qmk"):
                if backend not in profile:
                    continue
                out = root / "first" / backend / profile_name
                files = generate_one(model, repo, backend, profile_name, os_name, out, False)
                first[(backend, profile_name)] = [path.read_text() for path in files]
                second = root / "second" / backend / profile_name
                files2 = generate_one(model, repo, backend, profile_name, os_name, second, False)
                if first[(backend, profile_name)] != [path.read_text() for path in files2]:
                    fail(f"{backend}/{profile_name}: nondeterministic output")
            if "zmk" in profile or "qmk" in profile:
                generate_one(model, repo, "draw", profile_name, os_name, root / "draw" / profile_name, False)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("command", choices=["check", "all", "zmk", "qmk", "draw", "profiles"])
    result.add_argument("--repo", type=Path, default=Path.cwd())
    result.add_argument("--profile")
    result.add_argument("--os", dest="os_name")
    result.add_argument("--out", type=Path)
    result.add_argument("--no-svg", action="store_true")
    return result


def main() -> None:
    args = parser().parse_args()
    repo = args.repo.resolve()
    model = load_sources(repo)
    os_name = args.os_name or model["root"]["default_os"]
    if args.command == "profiles":
        for name, profile in model["profiles"]["profiles"].items():
            targets = ",".join(backend for backend in ("zmk", "qmk") if backend in profile)
            print(f"{name}\t{targets}")
        return
    if args.command == "check":
        for checked_os in ([args.os_name] if args.os_name else model["root"]["operating_systems"]):
            check_all(model, repo, checked_os)
        return
    if args.command in {"zmk", "qmk", "draw"}:
        if args.command == "draw" and not args.profile:
            if args.out:
                fail("draw --out requires --profile")
            for profile_name, profile in model["profiles"]["profiles"].items():
                if "zmk" not in profile and "qmk" not in profile:
                    continue
                for path in generate_one(model, repo, "draw", profile_name, os_name, args.out, not args.no_svg):
                    print(path)
            return
        if not args.profile:
            fail(f"{args.command} requires --profile")
        outputs = generate_one(model, repo, args.command, args.profile, os_name, args.out, not args.no_svg)
        for path in outputs:
            print(path)
        return
    for profile_name, profile in model["profiles"]["profiles"].items():
        for backend in ("zmk", "qmk"):
            if backend in profile:
                generate_one(model, repo, backend, profile_name, os_name, None, False)
        if "zmk" in profile or "qmk" in profile:
            generate_one(model, repo, "draw", profile_name, os_name, None, not args.no_svg)


if __name__ == "__main__":
    try:
        main()
    except (KeymapError, json.JSONDecodeError, tomllib.TOMLDecodeError, subprocess.CalledProcessError) as error:
        print(f"keymap: {error}", file=sys.stderr)
        raise SystemExit(1)
