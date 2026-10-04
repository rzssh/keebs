import json
from pathlib import Path

import keymap


model = keymap.load_sources(Path(__file__).resolve().parents[1])
expected = {
    "ferris_not_equal": (["L_RING_TOP", "L_MIDDLE_TOP"], ["EXCL", "EQUAL"]),
    "ferris_less_equal": (["L_MIDDLE_TOP", "L_INDEX_TOP"], ["LT", "EQUAL"]),
    "ferris_fat_arrow": (["R_INDEX_TOP", "R_MIDDLE_TOP"], ["EQUAL", "GT"]),
    "ferris_dot_brace": (["L_RING_HOME", "L_MIDDLE_HOME"], ["DOT", "LBRC"]),
    "ferris_greater_equal": (["L_MIDDLE_HOME", "L_INDEX_HOME"], ["GT", "EQUAL"]),
    "ferris_thin_arrow": (["R_INDEX_BOTTOM", "R_MIDDLE_BOTTOM"], ["MINUS", "GT"]),
    "ferris_template_interpolation": (["R_MIDDLE_TOP", "R_RING_TOP"], ["DLLR", "LBRC"]),
    "ferris_rust_attribute": (["R_MIDDLE_BOTTOM", "R_RING_BOTTOM"], ["HASH", "LBKT"]),
    "ferris_optional_chain": (["L_RING_BOTTOM", "L_MIDDLE_BOTTOM"], ["QMARK", "DOT"]),
    "ferris_relative_path": (["L_MIDDLE_BOTTOM", "L_INDEX_BOTTOM"], ["DOT", "FSLH"]),
}
for backend in ("qmk", "zmk"):
    trial = keymap.compile_profile(model, "dartyl_34", backend, "linux")
    compact = keymap.compile_profile(model, "luna_30", "zmk", "linux")
    combos = {combo["name"]: combo for combo in trial["combos"] if combo["name"].startswith("ferris_")}
    assert set(combos) == set(expected)
    assert not any(combo["name"].startswith("ferris_") for combo in compact["combos"])
    sym = trial["layers"]["Sym"][:30]
    assert sym[:10] == ["CARET", "LBKT", "LBRC", "LPAR", "LT", "GT", "RPAR", "RBRC", "RBKT", "TILDE"]
    assert sym[10:16] == ["MINUS", "STAR", "UNDER", "EQUAL", "AT", "HASH"]
    assert sym[20:] == ["PLUS", "COLON", "SEMI", "FSLH", "PRCNT", "DLLR", "BSLH", "AMPS", "PIPE", "GRAVE"]
    assert [cell["use"] for cell in sym[16:20]] == ["osm_shift", "osm_ctrl", "osm_alt", "osm_gui"]
    punctuation = set(keymap.SHIFTED) | {"COMMA", "DOT", "SEMI", "SQT", "MINUS", "EQUAL", "FSLH", "BSLH", "LBKT", "RBKT", "GRAVE"}
    assert punctuation - {cell for cell in sym if isinstance(cell, str)} == {"DOT", "COMMA", "SQT", "DQT", "QMARK", "EXCL"}
    num = trial["layers"]["Num"][:30]
    assert num[6:9] == ["N7", "N8", "N9"]
    assert num[16:20] == ["N1", "N2", "N3", "N0"]
    assert num[26:29] == ["N4", "N5", "N6"]
    assert num[14] == "UNDER"
    assert num[20:24] == ["COMMA", "DOT", "MINUS", "PLUS"]
    assert [cell["use"] for cell in num[10:14]] == ["osm_gui", "osm_alt", "osm_ctrl", "osm_shift"]
    assert sorted(cell for cell in num if isinstance(cell, str) and cell.startswith("N")) == [f"N{digit}" for digit in range(10)]
    interpolation = combos["ferris_template_interpolation"]
    for name in ("backspace", "delete"):
        utility = next(combo for combo in trial["combos"] if combo["name"] == name)
        assert "Sym" in utility["layers"]
        assert set(interpolation["positions"]) < set(utility["positions"])
        assert interpolation["term_ms"] == utility["term_ms"]
    drawing_ir = keymap.draw_ir(model, trial)
    drawing = json.loads(keymap.render_draw(model, drawing_ir))
    for name, label in (("ferris_template_interpolation", "${"), ("ferris_rust_attribute", "#["), ("ferris_optional_chain", "?."), ("ferris_relative_path", "./")):
        positions = [drawing_ir["slots"].index(position) for position in combos[name]["positions"]]
        assert any(combo["p"] == positions and combo["k"] == label for combo in drawing["combos"])
    source = keymap.render_qmk(model, trial) if backend == "qmk" else keymap.render_zmk(model, trial)
    for name, (positions, keys) in expected.items():
        combo = combos[name]
        assert combo["positions"] == positions and combo["layers"] == ["Sym"]
        assert combo["term_ms"] == 40 and combo["prior_idle_ms"] == 0
        if name in {"ferris_optional_chain", "ferris_relative_path"}:
            assert not any(other["name"] != name and "Sym" in other["layers"] and set(other["positions"]) == set(positions) for other in trial["combos"])
        assert [step["key"] for step in keymap.behavior(model, combo["action"]["use"])["steps"]] == keys
        assert (name.upper() if backend == "qmk" else name) in source
print("Sym/Num: firmware outputs, combos, digits and core30 isolation passed")
