import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
layers = tomllib.loads((ROOT / "keymap/layers.toml").read_text())["layers"]
config = tomllib.loads((ROOT / "keymap/keymap.toml").read_text())
behaviors = tomllib.loads((ROOT / "keymap/behaviors.toml").read_text())
nav = {"layer": "Nav", "mode": "momentary"}
sym = {"layer": "Sym", "mode": "sticky"}
for name in ("Graphium", "Vestnik"):
    thumbs = layers[name]["core34"]["rows"][-1]
    assert thumbs[0] == nav and thumbs[3] == sym
assert layers["Nav"]["core34"]["rows"][-1][3] == sym
assert layers["Sym"]["core34"]["rows"][-1][0] == nav
assert layers["Num"]["core34"]["rows"][-1] == ["trans"] * 4
assert any(set(rule["if_layers"]) == {"Nav", "Sym"} and rule["then_layer"] == "Num" for rule in config["conditional_layers"])
assert not {"num_from_nav", "num_from_sym"}.intersection(behaviors["behaviors"])
for positions in (("R_INDEX_HOME", "R_MIDDLE_HOME"), ("R_MIDDLE_HOME", "R_RING_HOME"), ("R_RING_HOME", "R_PINKY_HOME")):
    assert not any("Num" in combo["layers"] and "core34" in combo.get("variants", ["core30", "core34"]) and set(combo["positions"]) == set(positions) for combo in behaviors["combos"])
    assert any("Num" in combo["layers"] and combo.get("variants") == ["core30"] and set(combo["positions"]) == set(positions) for combo in behaviors["combos"])
print("Native Num: transparent thumbs, Nav/Sym tri-layer, sticky Sym, no Num lock or digit-pair combos")
