#include "razen.h"
#include "adaptive.h"

#include "repeat_key.h"

static uint16_t history[6];
static uint8_t history_mods[6];
static uint8_t history_len;
static uint32_t history_timer;
static const razen_adaptive_rule_t *active_swap;
static uint16_t suppressed_keycode = KC_NO;
static uint32_t last_keypress_timer;
static uint32_t current_keypress_idle = UINT32_MAX;
static uint32_t repeat_timer;
static uint8_t repeat_mods;
#ifdef RAZEN_VIM_ADAPTIVE_GUARD_ENABLE
static bool adaptives_enabled = true;
#endif

static bool shift_active(void) {
    return (get_mods() | get_oneshot_mods() | get_weak_mods()) & MOD_MASK_SHIFT;
}

bool caps_word_press_user(uint16_t keycode) {
    for (uint8_t index = 0; index < razen_morph_count; index++) {
        if (razen_morphs[index].trigger == keycode) {
            keycode = razen_morphs[index].tap;
            break;
        }
    }

    switch (keycode) {
        case KC_A ... KC_Z:
            add_weak_mods(MOD_BIT(KC_LSFT));
            return true;
        case KC_1 ... KC_0:
        case KC_BSPC:
        case KC_DEL:
        case KC_UNDS:
        case KC_MINS:
        case KC_QUOT:
            return true;
        default:
            return false;
    }
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
    } else if (tap == CW_TOGG) {
        caps_word_on();
    } else {
        tap_code16(tap);
    }
}

static void clear_history(void) {
    history_len = 0;
    history_timer = 0;
    active_swap = NULL;
}

#ifdef RAZEN_VIM_ADAPTIVE_GUARD_ENABLE
bool led_update_user(led_t led_state) {
    uint8_t code = led_state.compose | (led_state.kana << 1) | (led_state.scroll_lock << 2);
    bool enabled = code == 0 || code == 2 || code == 5;
    if (enabled != adaptives_enabled) {
        adaptives_enabled = enabled;
        clear_history();
    }
    return true;
}
#endif

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

static bool follows_lowercase_with_shift(uint8_t mods) {
    return (mods & MOD_MASK_SHIFT) && history_len && history[history_len - 1] >= KC_A &&
           history[history_len - 1] <= KC_Z && !(history_mods[history_len - 1] & MOD_MASK_SHIFT);
}

static bool emit_adaptive(uint16_t keycode, uint16_t basic, keyrecord_t *record,
                          const uint16_t *emit, uint8_t emit_len, uint8_t mods, bool caps_word) {
    suppressed_keycode = keycode;
    if (caps_word) {
        process_caps_word(basic, record);
    }
    uint16_t repeated = KC_NO;
    for (uint8_t output = 0; output < emit_len; output++) {
        uint16_t emitted = emit[output];
        tap_code16(emitted);
        if (emitted == KC_BSPC) {
            pop_history();
        } else {
            append_history(emitted, mods & MOD_MASK_SHIFT);
            repeated = emitted;
        }
    }
    if (repeated != KC_NO) {
        remember_repeat(repeated, mods);
    }
    return false;
}

static bool process_adaptive(uint16_t keycode, keyrecord_t *record) {
    if (!record->event.pressed) {
        if (suppressed_keycode == keycode) {
            suppressed_keycode = KC_NO;
            return false;
        }
        return true;
    }

#ifdef RAZEN_VIM_ADAPTIVE_GUARD_ENABLE
    if (!adaptives_enabled) {
        clear_history();
        return true;
    }
#endif

    uint16_t basic = tap_keycode(keycode, record);
    if (basic == KC_NO) {
        return true;
    }
    bool caps_word = is_caps_word_on();
    uint8_t mods = get_mods() | get_oneshot_mods() | get_weak_mods();
    if (caps_word) {
        mods |= MOD_BIT(KC_LSFT);
    }
    if (basic == KC_BSPC) {
        active_swap = NULL;
        if (mods) {
            clear_history();
        } else {
            pop_history();
        }
        return true;
    }

    uint8_t layer = get_highest_layer(layer_state | default_layer_state);
    bool camel_case_boundary = follows_lowercase_with_shift(mods);
    bool skip_rules = false;
    if (active_swap) {
        bool valid = active_swap->layer == layer && history_timer &&
                     timer_elapsed32(history_timer) <= active_swap->timeout_ms &&
                     !(active_swap->strict_modifiers &&
                       (mods & ~(active_swap->allow_shift ? MOD_MASK_SHIFT : 0))) &&
                     !camel_case_boundary;
        if (valid && (basic == active_swap->swap_left || basic == active_swap->swap_right)) {
            uint16_t emitted = basic == active_swap->swap_left ? active_swap->swap_right
                                                               : active_swap->swap_left;
            return emit_adaptive(keycode, basic, record, &emitted, 1, mods, caps_word);
        }
        active_swap = NULL;
        skip_rules = true;
    }
    for (uint8_t index = 0; !skip_rules && index < razen_adaptive_rule_count; index++) {
        const razen_adaptive_rule_t *rule = &razen_adaptive_rules[index];
        if (camel_case_boundary || rule->layer != layer || rule->input != basic || !history_timer ||
            timer_elapsed32(history_timer) > rule->timeout_ms ||
            (rule->strict_modifiers && (mods & ~(rule->allow_shift ? MOD_MASK_SHIFT : 0))) || !history_matches(rule)) {
            continue;
        }
        active_swap = rule->swap_left == KC_NO ? NULL : rule;
        return emit_adaptive(keycode, basic, record, rule->emit, rule->emit_len, mods, caps_word);
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
        (!(repeated >= KC_A && repeated <= KC_Z) && !repeat_mods && !RAZEN_MAGIC_PLAIN_REPEATABLE(repeated))) {
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

static bool execute_sequence(uint16_t trigger) {
    for (uint8_t index = 0; index < razen_sequence_count; index++) {
        if (razen_sequences[index].trigger != trigger) {
            continue;
        }
        for (uint8_t key = 0; key < razen_sequences[index].length; key++) {
            tap_code16_delay(razen_sequences[index].keys[key], RAZEN_SEQUENCE_DELAY);
        }
        remember_repeat(razen_sequences[index].keys[razen_sequences[index].length - 1], 0);
        clear_history();
        return true;
    }
    return false;
}

static void execute_hold(razen_tap_dance_t *data) {
    if (data->hold_kind == RAZEN_HOLD_SEQUENCE) {
        execute_sequence(data->hold);
        return;
    }
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
    } else if (data->hold_kind == RAZEN_HOLD_LAYER) {
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
#ifdef RAZEN_LAYER_TRANSITION_ENABLE
    for (uint8_t index = 0; index < razen_layer_transition_count; index++) {
        if (razen_layer_transitions[index].trigger == keycode) {
            return true;
        }
    }
#endif
#ifdef RAZEN_LAYER_MODIFIER_ENABLE
    for (uint8_t index = 0; index < razen_layer_modifier_count; index++) {
        if (razen_layer_modifiers[index].trigger == keycode) {
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

#ifdef RAZEN_LAYER_MODIFIER_ENABLE
static void press_layer_modifier(razen_layer_modifier_t *state, uint8_t index) {
    uint8_t mask = 1U << index;
    if (state->modifiers_pressed & mask) {
        return;
    }
    uint8_t modifier = state->modifiers[index];
    set_oneshot_mods(get_oneshot_mods() & ~modifier);
    register_mods(modifier);
    state->modifiers_pressed |= mask;
    state->modifiers_used &= ~mask;
    state->timers[index] = timer_read();
}

static void release_layer_modifier(razen_layer_modifier_t *state, uint8_t index) {
    uint8_t mask = 1U << index;
    if (!(state->modifiers_pressed & mask)) {
        return;
    }
    uint8_t modifier = state->modifiers[index];
    unregister_mods(modifier);
    if (!(state->modifiers_used & mask) && timer_elapsed(state->timers[index]) < state->tapping_term) {
        add_oneshot_mods(modifier);
    }
    state->modifiers_pressed &= ~mask;
    state->modifiers_used &= ~mask;
}

static razen_layer_modifier_t *active_layer_modifier_session(uint8_t layer) {
    for (uint8_t index = 0; index < razen_layer_modifier_count; index++) {
        if (razen_layer_modifiers[index].layer == layer && razen_layer_modifiers[index].active) {
            return &razen_layer_modifiers[index];
        }
    }
    return NULL;
}

static bool layer_control_position(uint16_t position) {
    for (uint8_t index = 0; index < razen_layer_modifier_count; index++) {
        if (razen_layer_modifiers[index].layer_position == position) {
            return true;
        }
    }
#ifdef RAZEN_LAYER_TRANSITION_ENABLE
    for (uint8_t index = 0; index < razen_layer_transition_count; index++) {
        if (razen_layer_transitions[index].parent_position == position ||
            razen_layer_transitions[index].child_position == position) {
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

static bool eager_layer_modifier_candidate(const razen_layer_modifier_t *state) {
    uint8_t layer = get_highest_layer(layer_state | default_layer_state);
    if (!(state->activation_layers & (1UL << layer)) || !state->layer_position_pressed ||
        (state->modifier_positions_pressed & state->trigger_modifiers) != state->trigger_modifiers ||
        timer_elapsed32(state->layer_timer) > state->combo_term) {
        return false;
    }
    for (uint8_t index = 0; index < state->modifier_count; index++) {
        if ((state->trigger_modifiers & (1U << index)) &&
            timer_elapsed32(state->modifier_timers[index]) > state->combo_term) {
            return false;
        }
    }
    return true;
}

static razen_layer_modifier_t *best_eager_layer_modifier_candidate(uint8_t layer) {
    razen_layer_modifier_t *best = NULL;
    uint8_t best_count = 0;
    for (uint8_t index = 0; index < razen_layer_modifier_count; index++) {
        razen_layer_modifier_t *state = &razen_layer_modifiers[index];
        uint8_t count = __builtin_popcount(state->trigger_modifiers);
        if (state->layer == layer && count > best_count && eager_layer_modifier_candidate(state)) {
            best = state;
            best_count = count;
        }
    }
    return best;
}

static void start_layer_modifier_session(razen_layer_modifier_t *state, bool sticky_released) {
    state->active = true;
    state->layer_pressed = state->layer_position_pressed;
    state->modifiers_pressed = 0;
    state->modifiers_used = 0;
    if (state->layer_pressed) {
        layer_on(state->layer);
    }
    for (uint8_t index = 0; index < state->modifier_count; index++) {
        uint8_t mask = 1U << index;
        if (state->modifier_positions_pressed & mask) {
            press_layer_modifier(state, index);
        } else if (sticky_released && (state->trigger_modifiers & mask)) {
            add_oneshot_mods(state->modifiers[index]);
        }
    }
    if (!state->layer_pressed && !state->modifiers_pressed) {
        state->active = false;
    }
}
#endif

#ifdef RAZEN_LAYER_TRANSITION_ENABLE
static void release_layer_transition_position(uint16_t position) {
    for (uint8_t index = 0; index < razen_layer_transition_count; index++) {
        razen_layer_transition_t *transition = &razen_layer_transitions[index];
        if (position == transition->parent_position && transition->parent_pressed) {
            transition->parent_pressed = false;
            layer_off(transition->parent_layer);
        } else if (position == transition->child_position && transition->child_pressed) {
            transition->child_pressed = false;
            layer_off(transition->child_layer);
        }
    }
}
#endif

bool pre_process_record_user(uint16_t keycode, keyrecord_t *record) {
    bool continue_processing = true;
#if defined(RAZEN_LAYER_TRANSITION_ENABLE) || defined(RAZEN_LAYER_MODIFIER_ENABLE)
    uint16_t position = keymap_key_to_keycode(L_COMBO_REF, record->event.key);
#endif
#ifdef RAZEN_LAYER_TRANSITION_ENABLE
    if (!record->event.pressed) {
        release_layer_transition_position(position);
    }
#endif
#ifdef RAZEN_LAYER_MODIFIER_ENABLE
    for (uint8_t index = 0; index < razen_layer_modifier_count; index++) {
        razen_layer_modifier_t *state = &razen_layer_modifiers[index];
        if (position == state->layer_position) {
            state->layer_position_pressed = record->event.pressed;
            if (record->event.pressed) {
                state->layer_timer = timer_read32();
            }
        }
        for (uint8_t modifier = 0; modifier < state->modifier_count; modifier++) {
            if (position == state->modifier_positions[modifier]) {
                if (record->event.pressed) {
                    state->modifier_positions_pressed |= 1U << modifier;
                    state->modifier_timers[modifier] = timer_read32();
                } else {
                    state->modifier_positions_pressed &= ~(1U << modifier);
                }
            }
        }
    }
    if (record->event.pressed) {
        for (uint8_t index = 0; index < razen_layer_modifier_count; index++) {
            razen_layer_modifier_t *state = &razen_layer_modifiers[index];
            if (!state->layer_position_pressed || !state->modifier_positions_pressed ||
                active_layer_modifier_session(state->layer) != NULL) {
                continue;
            }
            razen_layer_modifier_t *candidate = best_eager_layer_modifier_candidate(state->layer);
            if (candidate != NULL) {
                start_layer_modifier_session(candidate, false);
            }
        }
    }
    for (uint8_t index = 0; index < razen_layer_modifier_count; index++) {
        razen_layer_modifier_t *state = &razen_layer_modifiers[index];
        if (!state->active) {
            continue;
        }
        bool layer_position = position == state->layer_position;
        int8_t modifier_index = -1;
        for (uint8_t modifier = 0; modifier < state->modifier_count; modifier++) {
            if (position == state->modifier_positions[modifier]) {
                modifier_index = modifier;
                break;
            }
        }
        bool managed_modifier =
            modifier_index >= 0 && (state->modifiers_pressed & (1U << modifier_index));
        if (record->event.pressed) {
            if (layer_position) {
                if (!state->layer_pressed) {
                    state->layer_pressed = true;
                    layer_on(state->layer);
                }
            } else if (modifier_index >= 0 && state->layer_position_pressed) {
                press_layer_modifier(state, modifier_index);
                managed_modifier = state->modifiers_pressed & (1U << modifier_index);
            } else if (!layer_control_position(position)) {
                state->modifiers_used |= state->modifiers_pressed;
            }
        } else {
            if (layer_position && state->layer_pressed) {
                state->layer_pressed = false;
                layer_off(state->layer);
            } else if (managed_modifier) {
                release_layer_modifier(state, modifier_index);
            }
            if (!state->layer_pressed && !state->modifiers_pressed) {
                state->active = false;
            }
        }
        if (managed_modifier && !(state->trigger_modifiers & (1U << modifier_index))) {
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
    if (record->event.pressed) {
        for (uint8_t index = 0; index < razen_layer_stack_count; index++) {
            razen_layer_stack_t *stack = &razen_layer_stacks[index];
            if (stack->parent_pressed && stack->parent_trigger != keycode) {
                stack->interrupted[0] = true;
            }
            if (stack->child_pressed && stack->child_trigger != keycode) {
                stack->interrupted[1] = true;
            }
        }
    }
    for (uint8_t index = 0; index < razen_layer_stack_count; index++) {
        razen_layer_stack_t *stack = &razen_layer_stacks[index];
        bool parent = stack->parent_trigger == keycode;
        if (!parent && stack->child_trigger != keycode) {
            continue;
        }
        uint8_t side = parent ? 0 : 1;
        if (record->event.pressed) {
            stack->interrupted[side] = parent ? stack->child_pressed : stack->parent_pressed;
            stack->timers[side] = timer_read();
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
        } else {
            bool tapped = stack->tap_keycodes[side] != KC_NO && !stack->interrupted[side] &&
                          timer_elapsed(stack->timers[side]) < stack->tapping_terms[side];
            if (parent) {
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
            if (tapped) {
                tap_code16(stack->tap_keycodes[side]);
            }
        }
        return false;
    }
#endif

#ifdef RAZEN_LAYER_TRANSITION_ENABLE
    if (record->event.pressed) {
        for (uint8_t index = 0; index < razen_layer_transition_count; index++) {
            razen_layer_transition_t *transition = &razen_layer_transitions[index];
            if ((transition->parent_pressed || transition->child_pressed) && transition->trigger != keycode) {
                transition->interrupted = true;
            }
        }
    }
    for (uint8_t index = 0; index < razen_layer_transition_count; index++) {
        razen_layer_transition_t *transition = &razen_layer_transitions[index];
        if (transition->trigger != keycode) {
            continue;
        }
        if (record->event.pressed) {
            transition->timer = timer_read();
            transition->interrupted = false;
            transition->parent_pressed = true;
            transition->child_pressed = true;
            layer_on(transition->parent_layer);
            layer_on(transition->child_layer);
            clear_history();
        } else {
            transition->parent_pressed = false;
            transition->child_pressed = false;
            layer_off(transition->child_layer);
            layer_off(transition->parent_layer);
        }
        return false;
    }
#endif

#ifdef RAZEN_LAYER_MODIFIER_ENABLE
    for (uint8_t index = 0; index < razen_layer_modifier_count; index++) {
        razen_layer_modifier_t *state = &razen_layer_modifiers[index];
        if (state->trigger != keycode) {
            continue;
        }
        if (record->event.pressed && active_layer_modifier_session(state->layer) == NULL) {
            start_layer_modifier_session(state, true);
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

    for (uint8_t index = 0; index < razen_morph_count; index++) {
        razen_morph_t *morph = &razen_morphs[index];
        if (morph->trigger != keycode) {
            continue;
        }
        if (!record->event.pressed) {
            if (morph->active_output != KC_NO) {
                unregister_code16(morph->active_output);
                morph->active_output = KC_NO;
                return false;
            }
            return true;
        }
        if (is_caps_word_on() && (morph->tap == KC_DOT || morph->tap == KC_COMM)) {
            caps_word_off();
        }
        uint8_t mods = get_mods() | get_oneshot_mods() | get_weak_mods();
        bool shifted = mods & MOD_MASK_SHIFT;
        uint16_t output = shifted ? morph->shifted : morph->tap;
        remember_repeat(output, shifted ? mods & ~MOD_MASK_SHIFT : mods);
        if (output == KC_BSPC) {
            pop_history();
        } else if (text_key(output)) {
            append_history(output, 0);
        } else {
            clear_history();
        }
        if (shifted) {
            return true;
        }
        if (output == CW_TOGG) {
            caps_word_on();
        } else {
            register_code16(output);
            morph->active_output = output;
        }
        return false;
    }

    if (!record->event.pressed) {
        return process_adaptive(keycode, record);
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

    if (execute_sequence(keycode)) {
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

#if defined(RAZEN_LAYER_TRANSITION_ENABLE) || defined(RAZEN_LAYER_MODIFIER_ENABLE)
bool process_combo_key_release(uint16_t combo_index, combo_t *combo, uint8_t key_index, uint16_t keycode) {
    (void)combo_index;
    (void)key_index;
#ifdef RAZEN_LAYER_TRANSITION_ENABLE
    for (uint8_t index = 0; index < razen_layer_transition_count; index++) {
        razen_layer_transition_t *transition = &razen_layer_transitions[index];
        if (combo->keycode != transition->trigger) {
            continue;
        }
        if (keycode == transition->parent_position) {
            transition->parent_pressed = false;
            layer_off(transition->parent_layer);
        } else if (keycode == transition->child_position) {
            transition->child_pressed = false;
            layer_off(transition->child_layer);
        }
        if (!transition->parent_pressed && !transition->child_pressed && transition->tap_keycode != KC_NO &&
            !transition->interrupted && timer_elapsed(transition->timer) < transition->tapping_term) {
            tap_code16(transition->tap_keycode);
        }
        return false;
    }
#endif
#ifdef RAZEN_LAYER_MODIFIER_ENABLE
    for (uint8_t index = 0; index < razen_layer_modifier_count; index++) {
        razen_layer_modifier_t *state = &razen_layer_modifiers[index];
        if (combo->keycode != state->trigger) {
            continue;
        }
        if (keycode == state->layer_position) {
            state->layer_pressed = false;
            layer_off(state->layer);
        }
        for (uint8_t modifier = 0; modifier < state->modifier_count; modifier++) {
            if (keycode == state->modifier_positions[modifier]) {
                release_layer_modifier(state, modifier);
            }
        }
        if (!state->layer_pressed && !state->modifiers_pressed) {
            state->active = false;
        }
        return false;
    }
#endif
    return false;
}

bool process_combo_key_repress(uint16_t combo_index, combo_t *combo, uint8_t key_index, uint16_t keycode) {
    (void)combo_index;
    (void)key_index;
#ifdef RAZEN_LAYER_TRANSITION_ENABLE
    for (uint8_t index = 0; index < razen_layer_transition_count; index++) {
        razen_layer_transition_t *transition = &razen_layer_transitions[index];
        if (combo->keycode != transition->trigger) {
            continue;
        }
        if (keycode == transition->parent_position) {
            transition->parent_pressed = true;
            layer_on(transition->parent_layer);
        } else if (keycode == transition->child_position) {
            transition->child_pressed = true;
            layer_on(transition->child_layer);
        } else {
            return false;
        }
        return true;
    }
#endif
#ifdef RAZEN_LAYER_MODIFIER_ENABLE
    for (uint8_t index = 0; index < razen_layer_modifier_count; index++) {
        razen_layer_modifier_t *state = &razen_layer_modifiers[index];
        if (combo->keycode != state->trigger) {
            continue;
        }
        state->active = true;
        if (keycode == state->layer_position) {
            state->layer_pressed = true;
            layer_on(state->layer);
            return true;
        }
        for (uint8_t modifier = 0; modifier < state->modifier_count; modifier++) {
            if (keycode == state->modifier_positions[modifier]) {
                press_layer_modifier(state, modifier);
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
