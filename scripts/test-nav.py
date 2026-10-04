import json
from pathlib import Path

import keymap


model = keymap.load_sources(Path(__file__).resolve().parents[1])
expected = {
    "nav_workspace_previous": (["L_RING_TOP", "L_MIDDLE_TOP"], {"key": "TAB", "mods": ["LGUI"]}),
    "nav_volume_down": (["R_INDEX_BOTTOM", "R_MIDDLE_BOTTOM"], {"key": "F11", "mods": ["LGUI"]}),
    "nav_volume_up": (["R_MIDDLE_BOTTOM", "R_RING_BOTTOM"], {"key": "F12", "mods": ["LGUI"]}),
    "nav_output_mute": (["R_INDEX_BOTTOM", "R_MIDDLE_BOTTOM", "R_RING_BOTTOM"], {"use": "nav_mute"}),
    "nav_zoom_out": (["L_RING_BOTTOM", "L_MIDDLE_BOTTOM"], {"key": "MINUS", "mods": ["LCTRL"]}),
    "nav_zoom_in": (["L_MIDDLE_BOTTOM", "L_INDEX_BOTTOM"], {"key": "PLUS", "mods": ["LCTRL"]}),
    "nav_zoom_reset": (["L_RING_BOTTOM", "L_MIDDLE_BOTTOM", "L_INDEX_BOTTOM"], {"key": "N0", "mods": ["LCTRL"]}),
    "nav_home": (["R_INDEX_HOME", "R_MIDDLE_HOME"], {"os": "home"}),
    "nav_end": (["R_MIDDLE_HOME", "R_RING_HOME"], {"os": "end"}),
}
for backend in ("qmk", "zmk"):
    ir = keymap.compile_profile(model, "dartyl_34", backend, "linux")
    combos = {combo["name"]: combo for combo in ir["combos"] if combo["name"].startswith("nav_") and not combo["name"].endswith("_chord")}
    assert set(combos) == set(expected)
    compact = keymap.compile_profile(model, "luna_30", "zmk", "linux")
    assert not any(combo["name"] in expected for combo in compact["combos"])
    drawing = json.loads(keymap.render_draw(model, keymap.draw_ir(model, ir)))
    legends = [combo for combo in drawing.get("combos", []) if isinstance(combo["k"], dict) and combo["k"].get("type") == "modifier-legend"]
    assert len(legends) == 1
    compact_drawing = json.loads(keymap.render_draw(model, keymap.draw_ir(model, compact)))
    assert not any(isinstance(combo["k"], dict) and combo["k"].get("type") == "modifier-legend" for combo in compact_drawing.get("combos", []))
    nav = ir["layers"]["Nav"]
    assert nav[0] == {"use": "nav_overview_opacity"}
    assert nav[ir["slots"].index("R_THUMB_A")] == {"use": "nav_pointer"}
    assert nav[6] == {"key": "P", "mods": ["LGUI"], "draw": "nav_files"}
    assert nav[8] == {"key": "F", "mods": ["LGUI"], "draw": "nav_window"}
    assert [nav[index] for index in (5, 7, 15, 16, 17, 18)] == [{"use": "nav_page_up"}, "UP", {"use": "nav_page_down"}, "LEFT", "DOWN", "RIGHT"]
    assert [cell["use"] for cell in nav[10:14]] == ["osm_gui", "osm_alt", "osm_ctrl", "osm_shift"]
    assert not any(isinstance(cell, dict) and cell.get("use") == "caps_word_lock" for cell in nav)
    assert {f"F{index}" for index in range(1, 13)}.issubset(cell for cell in ir["layers"]["Fn"] if isinstance(cell, str))
    for index, key in {1: "PG_UP", 2: "PG_DN", 6: "P", 8: "F", 9: "F1", 14: "R", 19: "F2", 25: "F3", 26: "F7", 27: "F8", 28: "F9", 29: "F4"}.items():
        cell = nav[index]
        assert cell["key"] == key and cell["mods"] == ["LGUI"]
        rendered = keymap.qmk_action(model, ir, cell, {}) if backend == "qmk" else keymap.zmk_action(model, ir, cell)
        assert rendered == (f"G({keymap.qmk_key(model, key)})" if backend == "qmk" else f"&kp LG({keymap.zmk_key(model, key)})")
    for name, (positions, action) in expected.items():
        combo = combos[name]
        assert combo["positions"] == positions and combo["action"] == action
        assert combo["layers"] == ["Nav"] and combo["term_ms"] == 40 and combo["prior_idle_ms"] == 0
    morphs = {
        "nav_mute": (("F6", ["LGUI"]), ("F5", ["LGUI"])),
        "nav_pointer": (("F13", []), ("F14", [])),
        "nav_overview_opacity": (("F16", []), ("F10", ["LGUI", "LCTRL"])),
    }
    source = keymap.render_qmk(model, ir) if backend == "qmk" else keymap.render_zmk(model, ir)
    for name, outputs in morphs.items():
        morph = keymap.behavior(model, name)
        assert morph["recipe"] == "shift_morph"
        for branch, (key, mods) in zip(("tap", "shifted"), outputs):
            action = morph[branch]
            action = {"key": action} if isinstance(action, str) else action
            assert keymap.resolved_key(model, action["key"]) == key and action.get("mods", []) == mods
        if backend == "qmk":
            shifted = keymap.qmk_basic(model, ir, morph["shifted"])
            assert f"MOD_MASK_SHIFT, {keymap.custom_name('MORPH', name)}, {shifted}, ~0, 0" in source
        else:
            assert f"ZMK_MOD_MORPH({name}, bindings = <{keymap.zmk_action(model, ir, morph['tap'])}>, <{keymap.zmk_action(model, ir, morph['shifted'])}>; mods = <(MOD_LSFT|MOD_RSFT)>;)" in source
        legend = keymap.label_action(model, ir, {"use": name})
        assert legend["t"].startswith("$$mdi:") and legend["s"].startswith("$$mdi:")
    for name, key, direction in (("nav_page_up", "PG_UP", "UP"), ("nav_page_down", "PG_DN", "DOWN")):
        morph = keymap.behavior(model, name)
        assert morph == {"recipe": "shift_morph", "tap": key, "shifted": {"mouse": f"SCRL_{direction}", "draw": f"nav_scroll_{direction.lower()}"}}
        if backend == "qmk":
            assert f"MOD_MASK_SHIFT, {keymap.custom_name('MORPH', name)}, {keymap.MOUSE_QMK[f'SCRL_{direction}']}, ~0, 0" in source
        else:
            assert f"ZMK_MOD_MORPH({name}, bindings = <&kp {keymap.zmk_key(model, key)}>, <&msc SCRL_{direction}>; mods = <(MOD_LSFT|MOD_RSFT)>;)" in source
        legend = keymap.label_action(model, ir, {"use": name})
        assert legend["t"].startswith("$$mdi:") and legend["s"] == f"$$mdi:mouse-move-{direction.lower()}$$" and "h" not in legend
    for name, mods in (("tab_previous", ["LCTRL", "LSHIFT"]), ("tab_next", ["LCTRL"])):
        assert keymap.behavior(model, name)["steps"] == [{"key": "TAB", "mods": mods}]
    pointer = keymap.label_action(model, ir, {"use": "nav_pointer"})
    assert pointer["t"] == "$$mdi:cursor-default-click$$" and pointer["s"] == "$$mdi:cursor-default-outline$$"
    assert pointer["left"] == "$$mdi:arrow-split-vertical$$" and pointer["type"] == "nav-group"
    assert pointer["right"] == "$$mdi:mouse-right-click-outline$$" and "h" not in pointer
    for index in (3, 4):
        assert keymap.label_action(model, ir, nav[index])["right"] == "$$mdi:robot-outline$$"
    for index in (0, 1, 2, 3, 4, 6, 8, 9, 14, 19, 25, 26, 27, 28, 29):
        legend = keymap.label_action(model, ir, nav[index])
        assert (legend["t"] if isinstance(legend, dict) else legend).startswith("$$mdi:")
    window = keymap.label_action(model, ir, nav[8])
    assert window["left"] == "$$mdi:window-restore$$" and window["right"] == "$$mdi:align-horizontal-center$$"
    assert keymap.label_action(model, ir, nav[29])["right"] == "$$mdi:alphabet-cyrillic$$"
    for index in (6, 8, 9, 19, 25, 29):
        legend = keymap.label_action(model, ir, nav[index])
        assert all(legend[field].startswith("$$mdi:") for field in ("t", "s", "left", "right"))
        assert "h" not in legend and legend["type"] == "nav-group"
    assert all(not {"tl", "tr", "bl", "br"}.intersection(label) for label in drawing["layers"]["Nav"] if isinstance(label, dict))
    assert legends[0]["k"] == {"t": "$$mdi:gesture-tap$$", "s": "$$mdi:apple-keyboard-shift$$", "left": "$$mdi:apple-keyboard-control$$", "right": "$$mdi:apple-keyboard-option$$", "type": "modifier-legend"}
    assert legends[0]["l"] == ["Nav"] and legends[0]["d"] is False
    assert legends[0]["w"] == legends[0]["h"] == 52
    utility = {"escape", "tab", "backspace", "delete", "enter"}
    utility_chords = {frozenset(combo["positions"]) for combo in ir["combos"] if combo["name"] in utility and "Nav" in combo["layers"]}
    assert len(utility_chords) == 5
    enter = next(combo for combo in ir["combos"] if combo["name"] == "enter")
    assert enter["term_ms"] == combos["nav_home"]["term_ms"] == combos["nav_end"]["term_ms"]
    assert set(combos["nav_home"]["positions"]) < set(enter["positions"])
    assert set(combos["nav_end"]["positions"]) < set(enter["positions"])
    for combo in combos.values():
        assert len({position.split("_")[0] for position in combo["positions"]}) == 1
        assert len({position.split("_")[1] for position in combo["positions"]}) == len(combo["positions"])
        assert frozenset(combo["positions"]) not in utility_chords
        if len(combo["positions"]) == 3:
            assert combo["draw"]["align"] == "bottom" and combo["draw"]["offset"] == 0.1
        else:
            assert "align" not in combo.get("draw", {})
    mute = next(combo for combo in drawing["combos"] if combo["p"] == [26, 27, 28])
    assert mute["h"] == 38 and mute["k"]["s"] == "$$mdi:microphone-off$$"
    for name in expected:
        assert (name.upper() if backend == "qmk" else name) in source
    assert {"escape", "tab", "backspace", "delete", "enter"}.issubset(combo["name"] for combo in ir["combos"] if "Nav" in combo["layers"])
print("Nav: firmware parity, grouped icons, same-hand combos and utility collision checks passed")
