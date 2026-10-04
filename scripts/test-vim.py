import json
import subprocess
import tempfile
from pathlib import Path

import keymap


repo = Path(__file__).resolve().parents[1]
model = keymap.load_sources(repo)
model["root"]["features"]["vim_combos"]["core34"] = True
expected = {
    "vim_save": (["L_RING_TOP", "L_INDEX_HOME"], [{"key": "COLON"}, {"key": "W"}, {"key": "RET"}]),
    "vim_save_quit": (["L_INDEX_TOP", "L_RING_HOME"], [{"key": "COLON"}, {"key": "W"}, {"key": "Q"}, {"key": "RET"}]),
    "vim_vertical_split": (["R_INDEX_TOP", "R_RING_HOME"], [{"key": "W", "mods": ["LCTRL"]}, {"key": "V"}]),
    "vim_horizontal_split": (["R_INDEX_HOME", "R_RING_TOP"], [{"key": "W", "mods": ["LCTRL"]}, {"key": "S"}]),
}
for backend in ("qmk", "zmk"):
    ir = keymap.compile_profile(model, "dartyl_34", backend, "linux")
    assert ir["layer_index"]["Vestnik"] < ir["layer_index"]["Vim"] < ir["layer_index"]["Nav"]
    assert set(ir["layers"]["Vim"]) == {"trans"}
    combos = {combo["name"]: combo for combo in ir["combos"]}
    for name, (positions, steps) in expected.items():
        combo = combos[name]
        assert combo["positions"] == positions and combo["layers"] == ["Vim"]
        assert combo["term_ms"] == 40 and combo["prior_idle_ms"] == 0
        assert keymap.behavior(model, combo["action"]["use"])["steps"] == steps
        assert not any(other["name"] != name and "Vim" in other["layers"] and set(other["positions"]) == set(positions) for other in combos.values())
        assert len({position.split("_")[0] for position in positions}) == 1
        assert len({position.split("_")[1] for position in positions}) == len(positions)
        assert {position.split("_")[-1] for position in positions} == {"TOP", "HOME"}
        for other in combos.values():
            if set(other["layers"]) & set(model["root"]["alpha_layers"]):
                assert not set(positions).issubset(other["positions"])
                assert not set(other["positions"]).issubset(positions)
    assert set(combos["vim_save"]["positions"]).isdisjoint(combos["vim_save_quit"]["positions"])
    for left, right in (("vim_save", "vim_horizontal_split"), ("vim_save_quit", "vim_vertical_split")):
        assert {position[2:] for position in combos[left]["positions"]} == {position[2:] for position in combos[right]["positions"]}
    for name in ("escape", "tab", "enter", "backspace", "delete"):
        assert "Vim" in combos[name]["layers"]
    source = keymap.render_qmk(model, ir) if backend == "qmk" else keymap.render_zmk(model, ir)
    if backend == "zmk":
        assert "managed-layers = <LAYER_Vim>;" in source
        assert "off-delay-ms = <0>;" in source
        assert "normal { code = <1>; layers = <LAYER_Vim>; };" in source
        for name, code in (("insert", 2), ("visual", 3), ("legacy", 4), ("cmdline", 5), ("raw", 6), ("legacy_silent", 7)):
            assert f"{name} {{ code = <{code}>; }};" in source
    else:
        assert "#define RAZEN_VIM_COMBOS_ENABLE" in keymap.render_qmk_config(model, ir)
        assert "L_VIM" in source
    drawing_ir = keymap.draw_ir(model, ir)
    assert "Vim" not in drawing_ir["layers"] and "Vim" not in drawing_ir["layer_index"]
    assert not any(combo["name"] in expected for combo in drawing_ir["combos"])
    drawing = json.loads(keymap.render_draw(model, drawing_ir))
    assert "Vim" not in drawing["layers"]
    assert all("Vim" not in combo["l"] for combo in drawing["combos"])
    assert all("mdi:" not in keymap.behavior(model, name)["label"] for name in expected)
    compact = keymap.compile_profile(model, "luna_30", "zmk", "linux")
    assert "Vim" not in compact["layers"]
    assert not any(combo["name"] in expected for combo in compact["combos"])
    model["root"]["features"]["vim_combos"]["core34"] = False
    disabled = keymap.compile_profile(model, "dartyl_34", backend, "linux")
    assert "Vim" not in disabled["layers"]
    assert not any(combo["name"] in expected or "Vim" in combo["layers"] for combo in disabled["combos"])
    model["root"]["features"]["vim_combos"]["core34"] = True

source = (repo / "qmk/users/razen/razen.c").read_text()
led = "bool led_update_user(" + source.split("bool led_update_user(", 1)[1].split("\n}\n", 1)[0] + "\n}\n"
combo = "bool combo_should_trigger(" + source.split("bool combo_should_trigger(", 1)[1].split("\n}\n", 1)[0] + "\n}\n"
program = """
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#define RAZEN_VIM_COMBOS_ENABLE
#define L_VIM 2
#define COMBO_TERM 40
typedef struct { uint8_t compose, kana, scroll_lock; } led_t;
typedef struct { uint8_t state; } combo_t;
typedef struct { struct { bool pressed; } event; } keyrecord_t;
typedef struct { uint32_t layers; uint16_t idle_ms; } razen_combo_t;
static uint32_t layer_state;
static uint32_t default_layer_state = 1;
static bool adaptives_enabled = true;
static uint16_t current_keypress_idle = 100;
static const razen_combo_t razen_combos[] = {{1 << L_VIM, 0}, {7, 0}};
static const uint8_t razen_combo_count = 2;
static void clear_history(void) {}
static void layer_on(uint8_t layer) { layer_state |= 1 << layer; }
static void layer_off(uint8_t layer) { layer_state &= ~(1 << layer); }
static uint8_t get_highest_layer(uint32_t state) {
    uint8_t layer = 0;
    while (state >>= 1) { layer++; }
    return layer;
}
""" + led + combo + """
int main(void) {
    combo_t combo = {0};
    keyrecord_t record = {.event.pressed = true};
    for (uint8_t base = 0; base < 2; base++) {
        default_layer_state = 1 << base;
        for (uint8_t code = 0; code < 8; code++) {
            led_update_user((led_t){1, 0, 0});
            assert(combo_should_trigger(0, &combo, 0, &record));
            led_update_user((led_t){code & 1, (code >> 1) & 1, (code >> 2) & 1});
            assert(combo_should_trigger(0, &combo, 0, &record) == (code == 1));
            assert(combo_should_trigger(1, &combo, 0, &record));
            for (uint8_t outer = 3; outer < 8; outer++) {
                layer_on(outer);
                assert(!combo_should_trigger(0, &combo, 0, &record));
                layer_off(outer);
            }
        }
    }
}
"""
with tempfile.TemporaryDirectory(prefix="vim-combos-") as directory:
    directory = Path(directory)
    test = directory / "test.c"
    binary = directory / "test"
    test.write_text(program)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Werror", str(test), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("Vim: Normal-only recognition, mode exits, layer precedence, utility preservation and firmware parity passed")
