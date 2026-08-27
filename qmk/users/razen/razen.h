#pragma once

#include QMK_KEYBOARD_H

enum razen_tap_kind {
    RAZEN_TAP_KEY,
    RAZEN_TAP_MORPH,
    RAZEN_TAP_MAGIC,
    RAZEN_TAP_ONESHOT_MOD,
    RAZEN_TAP_ONESHOT_LAYER,
    RAZEN_TAP_SMART_SHIFT,
};

enum razen_hold_kind {
    RAZEN_HOLD_KEY,
    RAZEN_HOLD_LAYER,
};

typedef struct {
    uint16_t trigger;
    uint16_t tap;
    uint16_t shifted;
} razen_morph_t;

typedef struct {
    uint16_t trigger;
    uint8_t layer;
    uint16_t keycode;
} razen_macro_t;

typedef struct {
    uint16_t trigger;
    uint16_t keys[4];
    uint8_t length;
} razen_sequence_t;

typedef struct {
    uint8_t layer;
    uint16_t input;
    uint16_t after[6];
    uint8_t after_len;
    uint16_t emit[6];
    uint8_t emit_len;
    uint16_t timeout_ms;
    bool strict_modifiers;
} razen_adaptive_rule_t;

typedef struct {
    uint16_t after;
    uint16_t emit;
} razen_adaptive_repeat_rule_t;

typedef struct {
    uint32_t layers;
    uint16_t term_ms;
    uint16_t idle_ms;
} razen_combo_t;

typedef struct {
    uint8_t tap_kind;
    uint16_t tap;
    uint8_t hold_kind;
    uint16_t hold;
    uint16_t term_ms;
    bool hold_on_interrupt;
    bool held;
} razen_tap_dance_t;

typedef struct {
    uint16_t keycode;
    uint8_t layer;
} razen_oneshot_layer_t;

typedef struct {
    uint16_t trigger;
    uint8_t parent_layer;
    uint8_t child_layer;
    uint16_t parent_position;
    uint16_t child_position;
    bool parent_pressed;
    bool child_pressed;
} razen_layer_chord_t;

extern const razen_morph_t razen_morphs[];
extern const uint8_t razen_morph_count;
extern const razen_macro_t razen_macros[];
extern const uint8_t razen_macro_count;
extern const razen_sequence_t razen_sequences[];
extern const uint8_t razen_sequence_count;
extern const razen_adaptive_rule_t razen_adaptive_rules[];
extern const uint8_t razen_adaptive_rule_count;
extern const uint16_t razen_adaptive_repeat_keycode;
extern const uint16_t razen_adaptive_repeat_marker;
extern const uint16_t razen_adaptive_repeat_timeout;
extern const bool razen_adaptive_repeat_strict_modifiers;
extern const razen_adaptive_repeat_rule_t razen_adaptive_repeat_rules[];
extern const uint8_t razen_adaptive_repeat_rule_count;
extern const razen_combo_t razen_combos[];
extern const uint8_t razen_combo_count;
extern const uint16_t razen_magic_keycode;
extern const uint16_t razen_magic_hold_keycode;
#ifdef RAZEN_SMART_LAYER_ENABLE
extern const uint16_t razen_smart_layer_keycode;
extern const uint8_t razen_smart_layer;
extern const uint16_t razen_smart_layer_positions[];
extern const uint8_t razen_smart_layer_position_count;
#endif
extern razen_tap_dance_t razen_tap_dance_data[];
extern tap_dance_action_t tap_dance_actions[];
extern const uint16_t razen_home_row_keys[];
extern const uint8_t razen_home_row_key_count;
extern const uint16_t razen_balanced_keys[];
extern const uint8_t razen_balanced_key_count;
extern const uint16_t razen_hold_preferred_keys[];
extern const uint8_t razen_hold_preferred_key_count;
extern const razen_oneshot_layer_t razen_oneshot_layers[];
extern const uint8_t razen_oneshot_layer_count;
#ifdef RAZEN_LAYER_CHORD_ENABLE
extern razen_layer_chord_t razen_layer_chords[];
extern const uint8_t razen_layer_chord_count;
#endif

void razen_tap_dance_finished(tap_dance_state_t *state, void *user_data);
void razen_tap_dance_reset(tap_dance_state_t *state, void *user_data);

#define RAZEN_TAP_DANCE(data) { .fn = {NULL, razen_tap_dance_finished, razen_tap_dance_reset, NULL}, .user_data = (void *)(data) }
