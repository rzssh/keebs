import subprocess
import tempfile
from pathlib import Path


repo = Path(__file__).resolve().parents[1]
source = (repo / "qmk/users/razen/razen.c").read_text()
declarations = source.split("static uint16_t history[", 1)[1].split("static uint16_t suppressed_keycode", 1)[0]
functions = source.split("static void clear_history(void)", 1)[1].split("static void remember_repeat", 1)[0]
program = """
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "adaptive.h"

#define KC_NO 0
#define KC_A 4
#define KC_Z 29
#define KC_H 11
#define KC_P 19

typedef int razen_adaptive_rule_t;
static uint32_t repeat_timer;
static uint8_t repeat_mods;
static uint16_t last_keycode;
static uint8_t last_mods;
static uint32_t timer_read32(void) { return 1; }
static void set_last_keycode(uint16_t keycode) { last_keycode = keycode; }
static void set_last_mods(uint8_t mods) { last_mods = mods; }
""" + "static uint16_t history[" + declarations + "static void clear_history(void)" + functions + """
int main(void) {
    const razen_adaptive_rule_t swap = 0;
    const uint16_t trigger[] = {KC_P};
    append_history(KC_P, 0);
    append_history(KC_H, 0);
    active_swap = &swap;
    pop_history();
    assert(active_swap == NULL);
    assert(history_len == 1);
    assert(razen_suffix_matches(history, history_len, trigger, 1));
    assert(last_keycode == KC_P && last_mods == 0);
    assert(repeat_timer && repeat_mods == 0);
    pop_history();
    assert(history_len == 0 && active_swap == NULL);
    assert(!razen_suffix_matches(history, history_len, trigger, 1));
    assert(last_keycode == KC_NO && last_mods == 0);
    assert(repeat_timer == 0 && repeat_mods == 0);
    active_swap = &swap;
    pop_history();
    assert(history_len == 0 && active_swap == NULL);
    clear_history();
}
"""
with tempfile.TemporaryDirectory(prefix="adaptive-history-") as directory:
    directory = Path(directory)
    test = directory / "test.c"
    binary = directory / "test"
    test.write_text(program)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Werror", "-I", str(repo / "qmk/users/razen"), str(test), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("Adaptive history: Backspace clears swaps and rewinds trigger and repeat history")
