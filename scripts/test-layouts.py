import argparse
import ctypes as c
import ctypes.util
from pathlib import Path

import keymap


def check_firmware():
    model = keymap.load_sources(Path(__file__).resolve().parents[1])
    assert not {"sqt_dqt", "combo_minus_under"} & model["behaviors"]["behaviors"].keys()
    for name, profile in model["profiles"]["profiles"].items():
        for backend in ("zmk", "qmk"):
            if backend not in profile:
                continue
            for os_name in ("linux", "macos", "windows"):
                ir = keymap.compile_profile(model, name, backend, os_name)
                plane = keymap.symbol_plane(model, ir)
                minus_combos = [combo for combo in ir["combos"] if combo["name"] == "graphium_minus_under"]
                if ir["variant"] == "core34":
                    assert len(minus_combos) == 1
                    combo = minus_combos[0]
                    assert combo["positions"] == ["R_MIDDLE_BOTTOM", "R_RING_BOTTOM"]
                    assert combo["layers"] == ["Graphium"]
                    assert combo["term_ms"] == 40 and combo["prior_idle_ms"] == 0
                    assert combo["action"] == "MINUS"
                    assert keymap.zmk_action(model, ir, combo["action"]) == ("&symbol_minus" if plane else "&kp MINUS")
                    assert keymap.qmk_action(model, ir, combo["action"], {}) == ("RALT(KC_MINS)" if plane else "KC_MINS")
                    assert keymap.label_action(model, ir, combo["action"]) == {"t": "-", "s": "_"}
                    quote = ir["layers"]["Graphium"][ir["slots"].index("R_INNER_TOP")]
                    assert quote == "SQT"
                    assert keymap.zmk_action(model, ir, quote) == ("&symbol_sqt" if plane else "&kp SQT")
                    assert keymap.qmk_action(model, ir, quote, {}) == ("RALT(KC_QUOT)" if plane else "KC_QUOT")
                    assert keymap.label_action(model, ir, quote) == {"t": "'", "s": '"'}
                    assert not any(other["name"] != combo["name"] and "Graphium" in other["layers"] and set(other["positions"]) == set(combo["positions"]) for other in ir["combos"])
                    for slot, behavior_name, tap, shifted in (
                        ("R_MIDDLE_BOTTOM", "dot_colon", "DOT", "COLON"),
                        ("R_RING_BOTTOM", "comma_semi", "COMMA", "SEMI"),
                        ("R_PINKY_BOTTOM", "qmark_excl", "QMARK", "EXCL"),
                    ):
                        cell = ir["layers"]["Graphium"][ir["slots"].index(slot)]
                        assert cell == {"use": behavior_name}
                        morph = keymap.behavior(model, behavior_name)
                        assert morph == {"recipe": "shift_morph", "tap": tap, "shifted": shifted}
                        assert keymap.label_action(model, ir, cell) == {"t": keymap.label_key(model, tap), "s": keymap.label_key(model, shifted)}
                else:
                    assert not minus_combos
                assert keymap.zmk_action(model, ir, "LBKT") == ("&symbol_lbkt" if plane else "&kp LBKT")
                assert keymap.qmk_output_key(model, ir, "AT") == ("RALT(S(KC_2))" if plane else "S(KC_2)")
                assert keymap.zmk_action(model, ir, "Х") == "&kp LBKT"
                assert keymap.qmk_output_key(model, ir, "Х") == "KC_LBRC"
                assert keymap.zmk_action(model, ir, {"key": "N2", "mods": ["LCTRL"]}) == "&kp LC(N2)"
                assert keymap.qmk_action(model, ir, {"key": "N2", "mods": ["LCTRL"]}, {}) == "C(KC_2)"
                for index, normal, shortcut in keymap.shortcut_cells(model, ir):
                    source = ir["layers"]["Graphium"][index]
                    assert shortcut == (keymap.cell_tap(source) or source)
                    if isinstance(normal, dict) and normal.get("hand") == "right" and normal["tap"] == "Е":
                        assert normal["hold"] == ("LALT" if plane else "RALT")
                for alias, token in keymap.SYMBOL_ALIASES.items():
                    if plane:
                        assert keymap.zmk_action(model, ir, alias) == keymap.zmk_action(model, ir, token)
                        assert keymap.qmk_output_key(model, ir, alias) == keymap.qmk_output_key(model, ir, token)
    print("Firmware symbols, shortcut positions, Cyrillic aliases and OS isolation passed")


def check_xkb(directory):
    x = c.CDLL(ctypes.util.find_library("xkbcommon") or "libxkbcommon.so.0")

    def api(name, result, *arguments):
        function = getattr(x, "xkb_" + name)
        function.restype = result
        function.argtypes = list(arguments)
        return function

    class Names(c.Structure):
        _fields_ = [(name, c.c_char_p) for name in ("rules", "model", "layout", "variant", "options")]

    context_new = api("context_new", c.c_void_p, c.c_int)
    append = api("context_include_path_append", c.c_int, c.c_void_p, c.c_char_p)
    keymap_new = api("keymap_new_from_names", c.c_void_p, c.c_void_p, c.POINTER(Names), c.c_int)
    key_by_name = api("keymap_key_by_name", c.c_uint, c.c_void_p, c.c_char_p)
    state_new = api("state_new", c.c_void_p, c.c_void_p)
    mod_index = api("keymap_mod_get_index", c.c_uint, c.c_void_p, c.c_char_p)
    update = api("state_update_mask", c.c_uint, c.c_void_p, *([c.c_uint] * 6))
    utf8 = api("state_key_get_utf8", c.c_int, c.c_void_p, c.c_uint, c.c_char_p, c.c_size_t)
    context = context_new(0)
    assert append(context, str(directory.resolve()).encode())
    names = Names(b"evdev", b"pc105", b"razen,razen,razen", b"us,ru,ua", b"grp:win_space_toggle")
    mapping = keymap_new(context, c.byref(names), 0)
    assert mapping, "Custom XKB layouts failed to compile"
    state = state_new(mapping)
    shift = 1 << mod_index(mapping, b"Shift")
    altgr = 1 << mod_index(mapping, b"Mod5")
    caps = 1 << mod_index(mapping, b"Lock")
    pairs = {
        "TLDE": "`~", "AE01": "1!", "AE02": "2@", "AE03": "3#", "AE04": "4$",
        "AE05": "5%", "AE06": "6^", "AE07": "7&", "AE08": "8*", "AE09": "9(",
        "AE10": "0)", "AE11": "-_", "AE12": "=+", "AD11": "[{", "AD12": "]}",
        "BKSL": "\\|", "AC10": ";:", "AC11": "'\"", "AB08": ",<", "AB09": ".>", "AB10": "/?",
    }

    def text(mapping, state, name):
        output = c.create_string_buffer(32)
        utf8(state, key_by_name(mapping, name.encode()), output, len(output))
        return output.value.decode()

    for group, (layout, variant) in enumerate(((b"us", b"basic"), (b"ru", b"winkeys"), (b"ua", b"unicode"))):
        stock_names = Names(b"evdev", b"pc105", layout, variant, b"")
        stock = keymap_new(context, c.byref(stock_names), 0)
        assert stock
        stock_state = state_new(stock)
        physical = ["TLDE", "BKSL"] + [f"{row}{index:02}" for row, count in (("AE", 12), ("AD", 12), ("AC", 11), ("AB", 10)) for index in range(1, count + 1)]
        for locked in (0, caps):
            for shifted in (0, shift):
                update(state, shifted, 0, locked, 0, 0, group)
                update(stock_state, shifted, 0, locked, 0, 0, 0)
                for name in physical:
                    assert text(mapping, state, name) == text(stock, stock_state, name), (layout, name, shifted, locked)
                update(state, altgr | shifted, 0, locked, 0, 0, group)
                for name, pair in pairs.items():
                    expected = pair[bool(shifted)]
                    assert text(mapping, state, name) == expected, (layout, name, shifted, locked, expected)
    print("XKB: all ASCII symbols and digits match; stock typing and Caps Lock preserved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--xkb", type=Path)
    arguments = parser.parse_args()
    check_firmware()
    if arguments.xkb:
        check_xkb(arguments.xkb)
