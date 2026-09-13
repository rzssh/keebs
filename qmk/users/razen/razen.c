#include "razen.h"
#include "adaptive.h"

#include "repeat_key.h"

static uint16_t history[6];
static uint8_t history_mods[6];
static uint8_t history_len;
static uint32_t history_timer;
static uint16_t suppressed_keycode = KC_NO;
static uint32_t last_keypress_timer;
static uint32_t current_keypress_idle = UINT32_MAX;
static uint32_t repeat_timer;
static uint8_t repeat_mods;

static bool shift_active(void) {
    return (get_mods() | get_oneshot_mods() | get_weak_mods()) & MOD_MASK_SHIFT;
}

static void tap_without_shift(uint16_t keycode) {
    uint8_t mods = get_mods();
    uint8_t oneshot = get_oneshot_mods();
    uint8_t weak = get_weak_mods();
    del_mods(MOD_MASK_SHIFT);
    del_weak_mods(MOD_MASK_SHIFT);
    set_oneshot_mods(oneshot & ~MOD_MASK_SHIFT);
    tap_code16(keycode);
    set_mods(mods);
    set_weak_mods(weak);
    set_oneshot_mods(oneshot & ~MOD_MASK_SHIFT);
}

static void tap_morph(uint16_t tap, uint16_t shifted) {
    if (shift_active()) {
        tap_without_shift(shifted);
    } else {
        tap_code16(tap);
    }
}

static void clear_history(void) {
    history_len = 0;
    history_timer = 0;
}

static void append_history(uint16_t keycode, uint8_t mods) {
    if (history_len == 6) {
        memmove(history, history + 1, sizeof(history[0]) * 5);
        memmove(history_mods, history_mods + 1, sizeof(history_mods[0]) * 5);
        history_len = 5;
    }
    history[history_len++] = keycode;
    history_mods[history_len - 1] = mods;
    history_timer = timer_read32();
}

static void pop_history(void) {
    if (history_len) {
        history_len--;
    }
    history_timer = timer_read32();
    for (uint8_t index = history_len; index > 0; index--) {
        if (history[index - 1] >= KC_A && history[index - 1] <= KC_Z) {
            set_last_keycode(history[index - 1]);
            set_last_mods(history_mods[index - 1]);
            repeat_mods = history_mods[index - 1];
            repeat_timer = history_timer;
            return;
        }
    }
    set_last_keycode(KC_NO);
    set_last_mods(0);
    repeat_mods = 0;
    repeat_timer = 0;
}

static void remember_repeat(uint16_t keycode, uint8_t mods) {
    set_last_keycode(keycode);
    set_last_mods(mods);
    repeat_mods = mods;
    repeat_timer = timer_read32();
}

static bool text_key(uint16_t keycode) {
    if ((keycode >= KC_A && keycode <= KC_Z) || (keycode >= KC_1 && keycode <= KC_0)) {
        return true;
    }
    switch (keycode) {
        case KC_SPC:
        case KC_COMM:
        case KC_DOT:
        case KC_SCLN:
        case KC_QUOT:
        case KC_MINS:
        case KC_EQL:
        case KC_SLSH:
        case KC_BSLS:
        case KC_LBRC:
        case KC_RBRC:
        case KC_GRV:
            return true;
    }
    return false;
}

static uint16_t tap_keycode(uint16_t keycode, keyrecord_t *record) {
    if (IS_QK_MOD_TAP(keycode) || IS_QK_LAYER_TAP(keycode)) {
        return record->tap.count ? get_tap_keycode(keycode) : KC_NO;
    }
    return keycode;
}

static bool history_matches(const razen_adaptive_rule_t *rule) {
    return razen_suffix_matches(history, history_len, rule->after, rule->after_len);
}

static bool process_adaptive(uint16_t keycode, keyrecord_t *record) {
    if (!record->event.pressed) {
        if (suppressed_keycode == keycode) {
            suppressed_keycode = KC_NO;
            return false;
        }
        return true;
    }

    uint16_t basic = tap_keycode(keycode, record);
    if (basic == KC_NO) {
        return true;
    }
    uint8_t mods = get_mods() | get_oneshot_mods() | get_weak_mods();
    if (basic == KC_BSPC) {
        if (mods) {
            clear_history();
        } else {
            pop_history();
        }
        return true;
    }

    uint8_t layer = get_highest_layer(layer_state | default_layer_state);
    for (uint8_t index = 0; index < razen_adaptive_rule_count; index++) {
        const razen_adaptive_rule_t *rule = &razen_adaptive_rules[index];
        if (rule->layer != layer || rule->input != basic || !history_timer || timer_elapsed32(history_timer) > rule->timeout_ms || (rule->strict_modifiers && mods) || !history_matches(rule)) {
            continue;
        }
        suppressed_keycode = keycode;
        uint16_t repeated = KC_NO;
        for (uint8_t output = 0; output < rule->emit_len; output++) {
            uint16_t emitted = rule->emit[output];
            tap_code16(emitted);
            if (emitted == KC_BSPC) {
                pop_history();
            } else {
                append_history(emitted, 0);
                repeated = emitted;
            }
        }
        if (repeated != KC_NO) {
            remember_repeat(repeated, 0);
        }
        return false;
    }

    if (text_key(basic) && (!mods || (basic >= KC_A && basic <= KC_Z && !(mods & ~MOD_MASK_SHIFT)))) {
        append_history(basic, mods & MOD_MASK_SHIFT);
    } else {
        clear_history();
    }
    return true;
}

static void repeat_magic(void) {
    if (shift_active()) {
        caps_word_on();
        return;
    }
    uint16_t repeated = get_last_keycode();
    if (repeated == KC_NO || !repeat_timer || timer_elapsed32(repeat_timer) > RAZEN_MAGIC_REPEAT_TIMEOUT ||
        (!(repeated >= KC_A && repeated <= KC_Z) && !repeat_mods)) {
        add_oneshot_mods(MOD_BIT(razen_magic_hold_keycode));
        return;
    }
    set_last_mods(repeat_mods);
    keyevent_t event = MAKE_KEYEVENT(0, 0, true);
    repeat_key_invoke(&event);
    event.pressed = false;
    repeat_key_invoke(&event);
    repeat_timer = timer_read32();
}

static void execute_tap(razen_tap_dance_t *data) {
    switch (data->tap_kind) {
        case RAZEN_TAP_KEY:
            tap_code16(data->tap);
            break;
        case RAZEN_TAP_MORPH:
            for (uint8_t index = 0; index < razen_morph_count; index++) {
                if (razen_morphs[index].trigger == data->tap) {
                    tap_morph(razen_morphs[index].tap, razen_morphs[index].shifted);
                    break;
                }
            }
            break;
        case RAZEN_TAP_MAGIC:
            repeat_magic();
            break;
        case RAZEN_TAP_ONESHOT_MOD:
            add_oneshot_mods(data->tap);
            break;
        case RAZEN_TAP_ONESHOT_LAYER:
            set_oneshot_layer(data->tap, ONESHOT_START);
            break;
        case RAZEN_TAP_SMART_SHIFT:
            if (shift_active()) {
                set_oneshot_mods(get_oneshot_mods() & ~MOD_MASK_SHIFT);
                caps_word_on();
            } else {
                add_oneshot_mods(MOD_BIT(KC_LSFT));
            }
            break;
    }
}

static void execute_hold(razen_tap_dance_t *data) {
    if (data->hold_kind == RAZEN_HOLD_KEY) {
        register_code16(data->hold);
    } else {
        layer_on(data->hold);
    }
    data->held = true;
}

static void release_hold(razen_tap_dance_t *data) {
    if (!data->held) {
        return;
    }
    if (data->hold_kind == RAZEN_HOLD_KEY) {
        unregister_code16(data->hold);
    } else {
        layer_off(data->hold);
    }
    data->held = false;
}

void razen_tap_dance_finished(tap_dance_state_t *state, void *user_data) {
    razen_tap_dance_t *data = user_data;
    if (!state->pressed) {
        return;
    }
    if (state->count == 1 && (!state->interrupted || data->hold_on_interrupt)) {
        execute_hold(data);
    } else {
        execute_tap(data);
    }
}

void razen_tap_dance_reset(tap_dance_state_t *state, void *user_data) {
    (void)state;
    release_hold(user_data);
}

static void process_tap_dance_release(uint16_t keycode, keyrecord_t *record) {
    if (!record->event.pressed && IS_QK_TAP_DANCE(keycode)) {
        tap_dance_action_t *action = &tap_dance_actions[QK_TAP_DANCE_GET_INDEX(keycode)];
        if (action->state.count && !action->state.finished) {
            execute_tap(action->user_data);
        }
    }
}

static bool custom_keycode(uint16_t keycode) {
#ifdef RAZEN_LAYER_STACK_ENABLE
    for (uint8_t index = 0; index < razen_layer_stack_count; index++) {
        if (razen_layer_stacks[index].parent_trigger == keycode ||
            razen_layer_stacks[index].child_trigger == keycode) {
            return true;
        }
    }
#endif
#ifdef RAZEN_LAYER_CHORD_ENABLE
    for (uint8_t index = 0; index < razen_layer_chord_count; index++) {
        if (razen_layer_chords[index].trigger == keycode) {
            return true;
        }
    }
#endif
#ifdef RAZEN_LAYER_MOD_CHORD_ENABLE
    for (uint8_t index = 0; index < razen_layer_mod_chord_count; index++) {
        if (razen_layer_mod_chords[index].trigger == keycode) {
            return true;
        }
    }
#endif
    for (uint8_t index = 0; index < razen_morph_count; index++) {
        if (razen_morphs[index].trigger == keycode) {
            return true;
        }
    }
    for (uint8_t index = 0; index < razen_macro_count; index++) {
        if (razen_macros[index].trigger == keycode) {
            return true;
        }
    }
    for (uint8_t index = 0; index < razen_sequence_count; index++) {
        if (razen_sequences[index].trigger == keycode) {
            return true;
        }
    }
    return false;
}

#ifdef RAZEN_LAYER_MOD_CHORD_ENABLE
static void press_layer_mod(razen_layer_mod_chord_t *chord, uint8_t index) {
    uint8_t mask = 1U << index;
    if (chord->modifiers_pressed & mask) {
        return;
    }
    uint8_t modifier = chord->modifiers[index];
    set_oneshot_mods(get_oneshot_mods() & ~modifier);
    register_mods(modifier);
    chord->modifiers_pressed |= mask;
    chord->modifiers_used &= ~mask;
    chord->timers[index] = timer_read();
}

static void release_layer_mod(razen_layer_mod_chord_t *chord, uint8_t index) {
    uint8_t mask = 1U << index;
    if (!(chord->modifiers_pressed & mask)) {
        return;
    }
    uint8_t modifier = chord->modifiers[index];
    unregister_mods(modifier);
    if (!(chord->modifiers_used & mask) && timer_elapsed(chord->timers[index]) < chord->tapping_term) {
        add_oneshot_mods(modifier);
    }
    chord->modifiers_pressed &= ~mask;
    chord->modifiers_used &= ~mask;
}

static razen_layer_mod_chord_t *active_layer_mod_session(uint8_t layer) {
    for (uint8_t index = 0; index < razen_layer_mod_chord_count; index++) {
        if (razen_layer_mod_chords[index].layer == layer && razen_layer_mod_chords[index].active) {
            return &razen_layer_mod_chords[index];
        }
    }
    return NULL;
}

static bool layer_control_position(uint16_t position) {
    for (uint8_t index = 0; index < razen_layer_mod_chord_count; index++) {
        if (razen_layer_mod_chords[index].layer_position == position) {
            return true;
        }
    }
#ifdef RAZEN_LAYER_CHORD_ENABLE
    for (uint8_t index = 0; index < razen_layer_chord_count; index++) {
        if (razen_layer_chords[index].parent_position == position ||
            razen_layer_chords[index].child_position == position) {
            return true;
        }
    }
#endif
#ifdef RAZEN_LAYER_STACK_ENABLE
    for (uint8_t index = 0; index < razen_layer_stack_count; index++) {
        if (razen_layer_stacks[index].parent_position == position ||
            razen_layer_stacks[index].child_position == position) {
            return true;
        }
    }
#endif
    return false;
}

static bool eager_layer_mod_candidate(const razen_layer_mod_chord_t *chord) {
    uint8_t layer = get_highest_layer(layer_state | default_layer_state);
    if (!(chord->activation_layers & (1UL << layer)) || !chord->layer_position_pressed ||
        (chord->modifier_positions_pressed & chord->trigger_modifiers) != chord->trigger_modifiers ||
        timer_elapsed32(chord->layer_timer) > chord->combo_term) {
        return false;
    }
    for (uint8_t index = 0; index < chord->modifier_count; index++) {
        if ((chord->trigger_modifiers & (1U << index)) &&
            timer_elapsed32(chord->modifier_timers[index]) > chord->combo_term) {
            return false;
        }
    }
    return true;
}

static razen_layer_mod_chord_t *best_eager_layer_mod_candidate(uint8_t layer) {
    razen_layer_mod_chord_t *best = NULL;
    uint8_t best_count = 0;
    for (uint8_t index = 0; index < razen_layer_mod_chord_count; index++) {
        razen_layer_mod_chord_t *chord = &razen_layer_mod_chords[index];
        uint8_t count = __builtin_popcount(chord->trigger_modifiers);
        if (chord->layer == layer && count > best_count && eager_layer_mod_candidate(chord)) {
            best = chord;
            best_count = count;
        }
    }
    return best;
}

static void start_layer_mod_session(razen_layer_mod_chord_t *chord, bool sticky_released) {
    chord->active = true;
    chord->layer_pressed = chord->layer_position_pressed;
    chord->modifiers_pressed = 0;
    chord->modifiers_used = 0;
    if (chord->layer_pressed) {
        layer_on(chord->layer);
    }
    for (uint8_t index = 0; index < chord->modifier_count; index++) {
        uint8_t mask = 1U << index;
        if (chord->modifier_positions_pressed & mask) {
            press_layer_mod(chord, index);
        } else if (sticky_released && (chord->trigger_modifiers & mask)) {
            add_oneshot_mods(chord->modifiers[index]);
        }
    }
    if (!chord->layer_pressed && !chord->modifiers_pressed) {
        chord->active = false;
    }
}
#endif

#if defined(RAZEN_LAYER_CHORD_ENABLE) || defined(RAZEN_LAYER_MOD_CHORD_ENABLE)
static void release_chord_position(uint16_t position) {
#ifdef RAZEN_LAYER_CHORD_ENABLE
    for (uint8_t index = 0; index < razen_layer_chord_count; index++) {
        razen_layer_chord_t *chord = &razen_layer_chords[index];
        if (position == chord->parent_position && chord->parent_pressed) {
            chord->parent_pressed = false;
            layer_off(chord->parent_layer);
        } else if (position == chord->child_position && chord->child_pressed) {
            chord->child_pressed = false;
            layer_off(chord->child_layer);
        }
    }
#endif
}
#endif

bool pre_process_record_user(uint16_t keycode, keyrecord_t *record) {
    bool continue_processing = true;
#if defined(RAZEN_LAYER_CHORD_ENABLE) || defined(RAZEN_LAYER_MOD_CHORD_ENABLE)
    uint16_t position = keymap_key_to_keycode(L_COMBO_REF, record->event.key);
#endif
#ifdef RAZEN_LAYER_CHORD_ENABLE
    if (!record->event.pressed) {
        release_chord_position(position);
    }
#endif
#ifdef RAZEN_LAYER_MOD_CHORD_ENABLE
    for (uint8_t index = 0; index < razen_layer_mod_chord_count; index++) {
        razen_layer_mod_chord_t *chord = &razen_layer_mod_chords[index];
        if (position == chord->layer_position) {
            chord->layer_position_pressed = record->event.pressed;
            if (record->event.pressed) {
                chord->layer_timer = timer_read32();
            }
        }
        for (uint8_t modifier = 0; modifier < chord->modifier_count; modifier++) {
            if (position == chord->modifier_positions[modifier]) {
                if (record->event.pressed) {
                    chord->modifier_positions_pressed |= 1U << modifier;
                    chord->modifier_timers[modifier] = timer_read32();
                } else {
                    chord->modifier_positions_pressed &= ~(1U << modifier);
                }
            }
        }
    }
    if (record->event.pressed) {
        for (uint8_t index = 0; index < razen_layer_mod_chord_count; index++) {
            razen_layer_mod_chord_t *chord = &razen_layer_mod_chords[index];
            if (!chord->layer_position_pressed || !chord->modifier_positions_pressed ||
                active_layer_mod_session(chord->layer) != NULL) {
                continue;
            }
            razen_layer_mod_chord_t *candidate = best_eager_layer_mod_candidate(chord->layer);
            if (candidate != NULL) {
                start_layer_mod_session(candidate, false);
            }
        }
    }
    for (uint8_t index = 0; index < razen_layer_mod_chord_count; index++) {
        razen_layer_mod_chord_t *chord = &razen_layer_mod_chords[index];
        if (!chord->active) {
            continue;
        }
        bool layer_position = position == chord->layer_position;
        int8_t modifier_index = -1;
        for (uint8_t modifier = 0; modifier < chord->modifier_count; modifier++) {
            if (position == chord->modifier_positions[modifier]) {
                modifier_index = modifier;
                break;
            }
        }
        bool managed_modifier =
            modifier_index >= 0 && (chord->modifiers_pressed & (1U << modifier_index));
        if (record->event.pressed) {
            if (layer_position) {
                if (!chord->layer_pressed) {
                    chord->layer_pressed = true;
                    layer_on(chord->layer);
                }
            } else if (modifier_index >= 0 && chord->layer_position_pressed) {
                press_layer_mod(chord, modifier_index);
                managed_modifier = chord->modifiers_pressed & (1U << modifier_index);
            } else if (!layer_control_position(position)) {
                chord->modifiers_used |= chord->modifiers_pressed;
            }
        } else {
            if (layer_position && chord->layer_pressed) {
                chord->layer_pressed = false;
                layer_off(chord->layer);
            } else if (managed_modifier) {
                release_layer_mod(chord, modifier_index);
            }
            if (!chord->layer_pressed && !chord->modifiers_pressed) {
                chord->active = false;
            }
        }
        if (managed_modifier && !(chord->trigger_modifiers & (1U << modifier_index))) {
            continue_processing = false;
        }
    }
#endif
    if (record->event.pressed) {
        current_keypress_idle = last_keypress_timer ? timer_elapsed32(last_keypress_timer) : UINT32_MAX;
        last_keypress_timer = timer_read32();
    }
    return continue_processing;
}

bool process_record_user(uint16_t keycode, keyrecord_t *record) {
    process_tap_dance_release(keycode, record);

#ifdef RAZEN_LAYER_STACK_ENABLE
    for (uint8_t index = 0; index < razen_layer_stack_count; index++) {
        razen_layer_stack_t *stack = &razen_layer_stacks[index];
        bool parent = stack->parent_trigger == keycode;
        if (!parent && stack->child_trigger != keycode) {
            continue;
        }
        if (record->event.pressed) {
            if (parent) {
                stack->parent_pressed = true;
                stack->child_latest = false;
                layer_on(stack->parent_layer);
            } else {
                stack->child_pressed = true;
                stack->child_latest = true;
                layer_on(stack->child_layer);
            }
            clear_history();
        } else if (parent) {
            stack->parent_pressed = false;
            if (stack->child_pressed) {
                stack->child_latest = true;
            }
            layer_off(stack->parent_layer);
        } else {
            stack->child_pressed = false;
            if (stack->parent_pressed) {
                stack->child_latest = false;
            }
            layer_off(stack->child_layer);
        }
        return false;
    }
#endif

#ifdef RAZEN_LAYER_CHORD_ENABLE
    if (record->event.pressed) {
        for (uint8_t index = 0; index < razen_layer_chord_count; index++) {
            razen_layer_chord_t *chord = &razen_layer_chords[index];
            if ((chord->parent_pressed || chord->child_pressed) && chord->trigger != keycode) {
                chord->interrupted = true;
            }
        }
    }
    for (uint8_t index = 0; index < razen_layer_chord_count; index++) {
        razen_layer_chord_t *chord = &razen_layer_chords[index];
        if (chord->trigger != keycode) {
            continue;
        }
        if (record->event.pressed) {
            chord->timer = timer_read();
            chord->interrupted = false;
            chord->parent_pressed = true;
            chord->child_pressed = true;
            layer_on(chord->parent_layer);
            layer_on(chord->child_layer);
            clear_history();
        } else {
            chord->parent_pressed = false;
            chord->child_pressed = false;
            layer_off(chord->child_layer);
            layer_off(chord->parent_layer);
        }
        return false;
    }
#endif

#ifdef RAZEN_LAYER_MOD_CHORD_ENABLE
    for (uint8_t index = 0; index < razen_layer_mod_chord_count; index++) {
        razen_layer_mod_chord_t *chord = &razen_layer_mod_chords[index];
        if (chord->trigger != keycode) {
            continue;
        }
        if (record->event.pressed && active_layer_mod_session(chord->layer) == NULL) {
            start_layer_mod_session(chord, true);
            clear_history();
        }
        return false;
    }
#endif

    if (keycode == razen_magic_keycode && record->tap.count) {
        if (record->event.pressed) {
            repeat_magic();
        }
        return false;
    }

    for (uint8_t index = 0; index < razen_oneshot_layer_count; index++) {
        if (razen_oneshot_layers[index].keycode != keycode || !record->tap.count) {
            continue;
        }
        if (record->event.pressed) {
            set_oneshot_layer(razen_oneshot_layers[index].layer, ONESHOT_START);
        } else {
            clear_oneshot_layer_state(ONESHOT_PRESSED);
        }
        return false;
    }

    if (!record->event.pressed) {
        return process_adaptive(keycode, record);
    }

    for (uint8_t index = 0; index < razen_morph_count; index++) {
        if (razen_morphs[index].trigger != keycode) {
            continue;
        }
        uint8_t mods = get_mods() | get_oneshot_mods() | get_weak_mods();
        bool shifted = mods & MOD_MASK_SHIFT;
        uint16_t output = shifted ? razen_morphs[index].shifted : razen_morphs[index].tap;
        tap_morph(razen_morphs[index].tap, razen_morphs[index].shifted);
        remember_repeat(output, shifted ? mods & ~MOD_MASK_SHIFT : mods);
        if (output == KC_BSPC) {
            pop_history();
        } else if (text_key(output)) {
            append_history(output, 0);
        } else {
            clear_history();
        }
        return false;
    }

    for (uint8_t index = 0; index < razen_macro_count; index++) {
        if (razen_macros[index].trigger != keycode) {
            continue;
        }
        layer_move(razen_macros[index].layer);
        tap_code16(razen_macros[index].keycode);
        clear_history();
        return false;
    }

    for (uint8_t index = 0; index < razen_sequence_count; index++) {
        if (razen_sequences[index].trigger != keycode) {
            continue;
        }
        for (uint8_t key = 0; key < razen_sequences[index].length; key++) {
            tap_code16_delay(razen_sequences[index].keys[key], RAZEN_SEQUENCE_DELAY);
        }
        remember_repeat(razen_sequences[index].keys[razen_sequences[index].length - 1], 0);
        clear_history();
        return false;
    }

    return process_adaptive(keycode, record);
}

bool remember_last_key_user(uint16_t keycode, keyrecord_t *record, uint8_t *remembered_mods) {
    (void)record;
    bool remember = keycode != razen_magic_keycode && !IS_QK_TAP_DANCE(keycode) && !custom_keycode(keycode);
    if (remember) {
        repeat_mods = *remembered_mods;
        repeat_timer = timer_read32();
    }
    return remember;
}

static bool home_row_key(uint16_t keycode) {
    for (uint8_t index = 0; index < razen_home_row_key_count; index++) {
        if (razen_home_row_keys[index] == keycode) {
            return true;
        }
    }
    return false;
}

static bool balanced_key(uint16_t keycode) {
    for (uint8_t index = 0; index < razen_balanced_key_count; index++) {
        if (razen_balanced_keys[index] == keycode) {
            return true;
        }
    }
    return false;
}

static bool hold_preferred_key(uint16_t keycode) {
    for (uint8_t index = 0; index < razen_hold_preferred_key_count; index++) {
        if (razen_hold_preferred_keys[index] == keycode) {
            return true;
        }
    }
    return false;
}

uint16_t get_tapping_term(uint16_t keycode, keyrecord_t *record) {
    (void)record;
    if (IS_QK_TAP_DANCE(keycode)) {
        return razen_tap_dance_data[QK_TAP_DANCE_GET_INDEX(keycode)].term_ms;
    }
    if (keycode == razen_magic_keycode) {
        return RAZEN_MAGIC_TAPPING_TERM;
    }
    return home_row_key(keycode) ? RAZEN_HOME_ROW_TAPPING_TERM : TAPPING_TERM;
}

uint16_t get_quick_tap_term(uint16_t keycode, keyrecord_t *record) {
    (void)record;
    if (keycode == razen_magic_keycode) {
        return RAZEN_MAGIC_QUICK_TAP_TERM;
    }
    if (home_row_key(keycode)) {
        return RAZEN_HOME_ROW_QUICK_TAP_TERM;
    }
    for (uint8_t index = 0; index < razen_quick_tap_count; index++) {
        if (razen_quick_taps[index].keycode == keycode) {
            return razen_quick_taps[index].term_ms;
        }
    }
    return QUICK_TAP_TERM;
}

bool get_permissive_hold(uint16_t keycode, keyrecord_t *record) {
    (void)record;
#ifdef RAZEN_HOME_ROW_MODS
    if (home_row_key(keycode)) {
        return true;
    }
#endif
    return balanced_key(keycode);
}

bool get_hold_on_other_key_press(uint16_t keycode, keyrecord_t *record) {
    (void)record;
    return hold_preferred_key(keycode);
}

#ifdef RAZEN_HOME_ROW_MODS
uint16_t get_flow_tap_term(uint16_t keycode, keyrecord_t *record, uint16_t previous_keycode) {
    (void)record;
    uint16_t previous = get_tap_keycode(previous_keycode);
    if (!home_row_key(keycode) || !text_key(previous) || get_mods() || get_oneshot_mods() || get_weak_mods()) {
        return 0;
    }
    return FLOW_TAP_TERM;
}
#endif

uint16_t get_combo_term(uint16_t combo_index, combo_t *combo) {
    (void)combo;
    return combo_index < razen_combo_count ? razen_combos[combo_index].term_ms : COMBO_TERM;
}

bool combo_should_trigger(uint16_t combo_index, combo_t *combo, uint16_t keycode, keyrecord_t *record) {
    (void)keycode;
    if (combo_index >= razen_combo_count) {
        return true;
    }
    const razen_combo_t *meta = &razen_combos[combo_index];
    uint8_t layer = get_highest_layer(layer_state | default_layer_state);
    bool idle = !record->event.pressed || combo->state || current_keypress_idle >= meta->idle_ms;
    return idle && (meta->layers & (1UL << layer));
}

#if defined(RAZEN_LAYER_CHORD_ENABLE) || defined(RAZEN_LAYER_MOD_CHORD_ENABLE)
bool process_combo_key_release(uint16_t combo_index, combo_t *combo, uint8_t key_index, uint16_t keycode) {
    (void)combo_index;
    (void)key_index;
#ifdef RAZEN_LAYER_CHORD_ENABLE
    for (uint8_t index = 0; index < razen_layer_chord_count; index++) {
        razen_layer_chord_t *chord = &razen_layer_chords[index];
        if (combo->keycode != chord->trigger) {
            continue;
        }
        if (keycode == chord->parent_position) {
            chord->parent_pressed = false;
            layer_off(chord->parent_layer);
        } else if (keycode == chord->child_position) {
            chord->child_pressed = false;
            layer_off(chord->child_layer);
        }
        if (!chord->parent_pressed && !chord->child_pressed && chord->tap_keycode != KC_NO &&
            !chord->interrupted && timer_elapsed(chord->timer) < chord->tapping_term) {
            tap_code16(chord->tap_keycode);
        }
        return false;
    }
#endif
#ifdef RAZEN_LAYER_MOD_CHORD_ENABLE
    for (uint8_t index = 0; index < razen_layer_mod_chord_count; index++) {
        razen_layer_mod_chord_t *chord = &razen_layer_mod_chords[index];
        if (combo->keycode != chord->trigger) {
            continue;
        }
        if (keycode == chord->layer_position) {
            chord->layer_pressed = false;
            layer_off(chord->layer);
        }
        for (uint8_t modifier = 0; modifier < chord->modifier_count; modifier++) {
            if (keycode == chord->modifier_positions[modifier]) {
                release_layer_mod(chord, modifier);
            }
        }
        if (!chord->layer_pressed && !chord->modifiers_pressed) {
            chord->active = false;
        }
        return false;
    }
#endif
    return false;
}

bool process_combo_key_repress(uint16_t combo_index, combo_t *combo, uint8_t key_index, uint16_t keycode) {
    (void)combo_index;
    (void)key_index;
#ifdef RAZEN_LAYER_CHORD_ENABLE
    for (uint8_t index = 0; index < razen_layer_chord_count; index++) {
        razen_layer_chord_t *chord = &razen_layer_chords[index];
        if (combo->keycode != chord->trigger) {
            continue;
        }
        if (keycode == chord->parent_position) {
            chord->parent_pressed = true;
            layer_on(chord->parent_layer);
        } else if (keycode == chord->child_position) {
            chord->child_pressed = true;
            layer_on(chord->child_layer);
        } else {
            return false;
        }
        return true;
    }
#endif
#ifdef RAZEN_LAYER_MOD_CHORD_ENABLE
    for (uint8_t index = 0; index < razen_layer_mod_chord_count; index++) {
        razen_layer_mod_chord_t *chord = &razen_layer_mod_chords[index];
        if (combo->keycode != chord->trigger) {
            continue;
        }
        chord->active = true;
        if (keycode == chord->layer_position) {
            chord->layer_pressed = true;
            layer_on(chord->layer);
            return true;
        }
        for (uint8_t modifier = 0; modifier < chord->modifier_count; modifier++) {
            if (keycode == chord->modifier_positions[modifier]) {
                press_layer_mod(chord, modifier);
                return true;
            }
        }
        return false;
    }
#endif
    return false;
}
#endif

#ifdef ENCODER_ENABLE
bool encoder_update_user(uint8_t index, bool clockwise) {
    (void)index;
    tap_code(clockwise ? KC_VOLU : KC_VOLD);
    return false;
}
#endif

#ifdef OLED_ENABLE
oled_rotation_t oled_init_user(oled_rotation_t rotation) {
    return rotation;
}

bool oled_task_user(void) {
    static const char *const names[] = RAZEN_LAYER_NAMES;
    uint8_t layer = get_highest_layer(layer_state | default_layer_state);
    oled_write_ln(layer < sizeof(names) / sizeof(names[0]) ? names[layer] : "", false);
    return false;
}
#endif
