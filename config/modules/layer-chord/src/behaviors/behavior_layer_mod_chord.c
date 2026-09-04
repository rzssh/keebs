#define DT_DRV_COMPAT zmk_behavior_layer_mod_chord

#include <zephyr/device.h>
#include <zephyr/sys/util.h>
#include <version.h>

#include <drivers/behavior.h>

#include <zmk/behavior.h>
#include <zmk/event_manager.h>
#include <zmk/events/keycode_state_changed.h>
#include <zmk/events/position_state_changed.h>
#include <zmk/keymap.h>

struct behavior_layer_mod_chord_config {
    const struct zmk_behavior_binding *modifiers;
    const struct zmk_behavior_binding *sticky_modifiers;
    const uint32_t *modifier_positions;
    const zmk_keymap_layer_id_t *activation_layers;
    uint32_t tapping_term_ms;
    uint32_t combo_term_ms;
    uint8_t modifier_count;
    uint8_t activation_layer_count;
    uint8_t trigger_modifiers;
    zmk_keymap_layer_id_t layer;
    uint32_t layer_position;
};

struct behavior_layer_mod_chord_data {
    struct zmk_behavior_binding_event modifier_events[4];
    int64_t modifier_timestamps[4];
    int64_t layer_timestamp;
    uint8_t modifier_positions_pressed;
    uint8_t modifiers_pressed;
    uint8_t modifiers_used;
    bool active;
    bool combo_released;
    bool layer_position_pressed;
    bool layer_pressed;
};

static struct behavior_layer_mod_chord_data *active_session(zmk_keymap_layer_id_t layer);
#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_LAYER_CHORD)
bool zmk_layer_chord_position(uint32_t position);
#endif

static int activate_layer(zmk_keymap_layer_id_t layer) {
#if KERNEL_VERSION_MAJOR >= 4
    return zmk_keymap_layer_activate(layer, false);
#else
    return zmk_keymap_layer_activate(layer);
#endif
}

static int deactivate_layer(zmk_keymap_layer_id_t layer) {
#if KERNEL_VERSION_MAJOR >= 4
    return zmk_keymap_layer_deactivate(layer, false);
#else
    return zmk_keymap_layer_deactivate(layer);
#endif
}

static int press_modifier(const struct behavior_layer_mod_chord_config *config,
                          struct behavior_layer_mod_chord_data *data, uint8_t index,
                          struct zmk_behavior_binding_event event) {
    uint8_t mask = BIT(index);
    if (data->modifiers_pressed & mask) {
        return 0;
    }
    event.position = config->modifier_positions[index];
    int ret = zmk_behavior_invoke_binding(&config->modifiers[index], event, true);
    if (ret >= 0) {
        data->modifier_events[index] = event;
        data->modifiers_pressed |= mask;
        data->modifiers_used &= ~mask;
    }
    return ret;
}

static int tap_sticky_modifier(const struct behavior_layer_mod_chord_config *config,
                               uint8_t index, struct zmk_behavior_binding_event event) {
    event.position = config->modifier_positions[index];
    int ret = zmk_behavior_invoke_binding(&config->sticky_modifiers[index], event, true);
    if (ret >= 0) {
        ret = zmk_behavior_invoke_binding(&config->sticky_modifiers[index], event, false);
    }
    return ret;
}

static int release_modifier(const struct behavior_layer_mod_chord_config *config,
                            struct behavior_layer_mod_chord_data *data, uint8_t index,
                            int64_t timestamp, bool sticky) {
    uint8_t mask = BIT(index);
    if (!(data->modifiers_pressed & mask)) {
        return 0;
    }
    data->modifiers_pressed &= ~mask;
    struct zmk_behavior_binding_event event = data->modifier_events[index];
    event.timestamp = timestamp;
    int ret = zmk_behavior_invoke_binding(&config->modifiers[index], event, false);
    if (sticky && !(data->modifiers_used & mask) &&
        timestamp - data->modifier_events[index].timestamp < config->tapping_term_ms) {
        int current = zmk_behavior_invoke_binding(&config->sticky_modifiers[index], event, true);
        if (ret >= 0 && current < 0) {
            ret = current;
        }
        current = zmk_behavior_invoke_binding(&config->sticky_modifiers[index], event, false);
        if (ret >= 0 && current < 0) {
            ret = current;
        }
    }
    data->modifiers_used &= ~mask;
    return ret;
}

static int release_modifiers(const struct behavior_layer_mod_chord_config *config,
                             struct behavior_layer_mod_chord_data *data, int64_t timestamp,
                             bool sticky) {
    int ret = 0;
    for (uint8_t index = 0; index < config->modifier_count; index++) {
        int current = release_modifier(config, data, index, timestamp, sticky);
        if (ret >= 0 && current < 0) {
            ret = current;
        }
    }
    return ret;
}

static int start_session(const struct behavior_layer_mod_chord_config *config,
                         struct behavior_layer_mod_chord_data *data,
                         struct zmk_behavior_binding_event event, bool sticky_released) {
    int ret = 0;
    data->active = true;
    data->combo_released = sticky_released;
    data->layer_pressed = data->layer_position_pressed;
    data->modifiers_pressed = 0;
    data->modifiers_used = 0;
    if (data->layer_pressed) {
        ret = activate_layer(config->layer);
        if (ret < 0) {
            data->active = false;
            data->layer_pressed = false;
            return ret;
        }
    }
    for (uint8_t index = 0; index < config->modifier_count; index++) {
        if (data->modifier_positions_pressed & BIT(index)) {
            ret = press_modifier(config, data, index, event);
        } else if (sticky_released && (config->trigger_modifiers & BIT(index))) {
            ret = tap_sticky_modifier(config, index, event);
        }
        if (ret < 0) {
            release_modifiers(config, data, event.timestamp, false);
            if (data->layer_pressed) {
                deactivate_layer(config->layer);
            }
            data->active = false;
            data->layer_pressed = false;
            return ret;
        }
    }
    if (!data->layer_pressed && !data->modifiers_pressed && data->combo_released) {
        data->active = false;
    }
    return ZMK_BEHAVIOR_OPAQUE;
}

static int layer_mod_chord_pressed(struct zmk_behavior_binding *binding,
                                   struct zmk_behavior_binding_event event) {
    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    const struct behavior_layer_mod_chord_config *config = dev->config;
    struct behavior_layer_mod_chord_data *data = dev->data;
    if (active_session(config->layer) != NULL) {
        return ZMK_BEHAVIOR_OPAQUE;
    }
    return start_session(config, data, event, true);
}

static int layer_mod_chord_released(struct zmk_behavior_binding *binding,
                                    struct zmk_behavior_binding_event event) {
    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    const struct behavior_layer_mod_chord_config *config = dev->config;
    struct behavior_layer_mod_chord_data *data = active_session(config->layer);
    if (data == NULL) {
        data = dev->data;
    }
    data->combo_released = true;
    int ret = 0;
    if (!data->layer_position_pressed && data->layer_pressed) {
        data->layer_pressed = false;
        ret = deactivate_layer(config->layer);
    }
    for (uint8_t index = 0; index < config->modifier_count; index++) {
        if (!(data->modifier_positions_pressed & BIT(index))) {
            int current = release_modifier(config, data, index, event.timestamp, true);
            if (ret >= 0 && current < 0) {
                ret = current;
            }
        }
    }
    if (!data->layer_pressed && !data->modifiers_pressed) {
        data->active = false;
    }
    return ret < 0 ? ret : ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api layer_mod_chord_driver_api = {
    .binding_pressed = layer_mod_chord_pressed,
    .binding_released = layer_mod_chord_released,
};

#define LAYER_MOD_CHORD_DEVICE(inst) DEVICE_DT_INST_GET(inst),
static const struct device *layer_mod_chord_devices[] = {
    DT_INST_FOREACH_STATUS_OKAY(LAYER_MOD_CHORD_DEVICE)};

static struct behavior_layer_mod_chord_data *active_session(zmk_keymap_layer_id_t layer) {
    for (size_t index = 0; index < ARRAY_SIZE(layer_mod_chord_devices); index++) {
        const struct device *dev = layer_mod_chord_devices[index];
        const struct behavior_layer_mod_chord_config *config = dev->config;
        struct behavior_layer_mod_chord_data *data = dev->data;
        if (config->layer == layer && data->active) {
            return data;
        }
    }
    return NULL;
}

static bool enabled_on_active_layer(const struct behavior_layer_mod_chord_config *config) {
    zmk_keymap_layer_id_t layer = zmk_keymap_highest_layer_active();
    for (uint8_t index = 0; index < config->activation_layer_count; index++) {
        if (config->activation_layers[index] == layer) {
            return true;
        }
    }
    return false;
}

static const struct device *best_eager_candidate(zmk_keymap_layer_id_t layer) {
    const struct device *best = NULL;
    uint8_t best_count = 0;
    for (size_t index = 0; index < ARRAY_SIZE(layer_mod_chord_devices); index++) {
        const struct device *dev = layer_mod_chord_devices[index];
        const struct behavior_layer_mod_chord_config *config = dev->config;
        struct behavior_layer_mod_chord_data *data = dev->data;
        uint8_t triggers = config->trigger_modifiers;
        if (config->layer != layer || !enabled_on_active_layer(config) ||
            !data->layer_position_pressed ||
            (data->modifier_positions_pressed & triggers) != triggers) {
            continue;
        }
        int64_t first = data->layer_timestamp;
        int64_t last = first;
        for (uint8_t modifier = 0; modifier < config->modifier_count; modifier++) {
            if (triggers & BIT(modifier)) {
                first = MIN(first, data->modifier_timestamps[modifier]);
                last = MAX(last, data->modifier_timestamps[modifier]);
            }
        }
        uint8_t count = __builtin_popcount(triggers);
        if (last - first <= config->combo_term_ms && count > best_count) {
            best = dev;
            best_count = count;
        }
    }
    return best;
}

static bool layer_control_position(uint32_t position) {
    for (size_t index = 0; index < ARRAY_SIZE(layer_mod_chord_devices); index++) {
        const struct behavior_layer_mod_chord_config *config =
            layer_mod_chord_devices[index]->config;
        if (position == config->layer_position) {
            return true;
        }
    }
#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_LAYER_CHORD)
    return zmk_layer_chord_position(position);
#else
    return false;
#endif
}

static int layer_mod_chord_position_listener(const zmk_event_t *event) {
    const struct zmk_position_state_changed *position_event =
        as_zmk_position_state_changed(event);
    if (position_event == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    for (size_t device_index = 0; device_index < ARRAY_SIZE(layer_mod_chord_devices);
         device_index++) {
        const struct device *dev = layer_mod_chord_devices[device_index];
        const struct behavior_layer_mod_chord_config *config = dev->config;
        struct behavior_layer_mod_chord_data *data = dev->data;
        if (position_event->position == config->layer_position) {
            data->layer_position_pressed = position_event->state;
            if (position_event->state) {
                data->layer_timestamp = position_event->timestamp;
            }
        }
        for (uint8_t index = 0; index < config->modifier_count; index++) {
            if (position_event->position == config->modifier_positions[index]) {
                WRITE_BIT(data->modifier_positions_pressed, index, position_event->state);
                if (position_event->state) {
                    data->modifier_timestamps[index] = position_event->timestamp;
                }
            }
        }
    }

    if (position_event->state) {
        for (size_t device_index = 0; device_index < ARRAY_SIZE(layer_mod_chord_devices);
             device_index++) {
            const struct device *dev = layer_mod_chord_devices[device_index];
            const struct behavior_layer_mod_chord_config *config = dev->config;
            struct behavior_layer_mod_chord_data *data = dev->data;
            if (!data->layer_position_pressed || !data->modifier_positions_pressed ||
                active_session(config->layer) != NULL) {
                continue;
            }
            const struct device *candidate = best_eager_candidate(config->layer);
            if (candidate == NULL) {
                continue;
            }
            const struct behavior_layer_mod_chord_config *candidate_config = candidate->config;
            struct zmk_behavior_binding_event binding_event = {
                .layer = candidate_config->layer,
                .position = position_event->position,
                .timestamp = position_event->timestamp,
#if IS_ENABLED(CONFIG_ZMK_SPLIT)
                .source = position_event->source,
#endif
            };
            start_session(candidate_config, candidate->data, binding_event, false);
        }
    }

    bool capture = false;
    for (size_t device_index = 0; device_index < ARRAY_SIZE(layer_mod_chord_devices);
         device_index++) {
        const struct device *dev = layer_mod_chord_devices[device_index];
        const struct behavior_layer_mod_chord_config *config = dev->config;
        struct behavior_layer_mod_chord_data *data = dev->data;
        if (!data->active) {
            continue;
        }
        bool layer_position = position_event->position == config->layer_position;
        int8_t modifier_index = -1;
        for (uint8_t index = 0; index < config->modifier_count; index++) {
            if (position_event->position == config->modifier_positions[index]) {
                modifier_index = index;
                break;
            }
        }
        bool managed_modifier =
            modifier_index >= 0 && (data->modifiers_pressed & BIT(modifier_index));
        if (position_event->state) {
            struct zmk_behavior_binding_event binding_event = {
                .layer = config->layer,
                .position = position_event->position,
                .timestamp = position_event->timestamp,
#if IS_ENABLED(CONFIG_ZMK_SPLIT)
                .source = position_event->source,
#endif
            };
            if (layer_position) {
                if (!data->layer_pressed) {
                    data->layer_pressed = true;
                    activate_layer(config->layer);
                }
            } else if (modifier_index >= 0 && data->layer_position_pressed) {
                press_modifier(config, data, modifier_index, binding_event);
                managed_modifier = data->modifiers_pressed & BIT(modifier_index);
            } else if (!layer_control_position(position_event->position)) {
                data->modifiers_used |= data->modifiers_pressed;
            }
        } else {
            if (layer_position && data->layer_pressed) {
                data->layer_pressed = false;
                deactivate_layer(config->layer);
            } else if (managed_modifier) {
                release_modifier(config, data, modifier_index, position_event->timestamp, true);
            }
            if (!data->layer_pressed && !data->modifiers_pressed) {
                data->active = false;
            }
        }
        if (managed_modifier && !(config->trigger_modifiers & BIT(modifier_index))) {
            capture = true;
        }
    }
    return capture ? ZMK_EV_EVENT_CAPTURED : ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(layer_mod_chord, layer_mod_chord_position_listener);
ZMK_SUBSCRIPTION(layer_mod_chord, zmk_position_state_changed);

static void mark_modifiers_used(void) {
    for (size_t index = 0; index < ARRAY_SIZE(layer_mod_chord_devices); index++) {
        struct behavior_layer_mod_chord_data *data = layer_mod_chord_devices[index]->data;
        if (data->active) {
            data->modifiers_used |= data->modifiers_pressed;
        }
    }
}

static int layer_mod_chord_output_listener(const zmk_event_t *event) {
    const struct zmk_keycode_state_changed *keycode = as_zmk_keycode_state_changed(event);
    if (keycode != NULL && keycode->state && !is_mod(keycode->usage_page, keycode->keycode)) {
        mark_modifiers_used();
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(layer_mod_chord_output, layer_mod_chord_output_listener);
ZMK_SUBSCRIPTION(layer_mod_chord_output, zmk_keycode_state_changed);

#define TRANSFORM_BINDING(index, node, prop)                                                      \
    {                                                                                              \
        .behavior_dev = DEVICE_DT_NAME(DT_PHANDLE_BY_IDX(node, prop, index)),                     \
        .param1 = COND_CODE_0(DT_PHA_HAS_CELL_AT_IDX(node, prop, index, param1), (0),             \
                              (DT_PHA_BY_IDX(node, prop, index, param1))),                         \
        .param2 = COND_CODE_0(DT_PHA_HAS_CELL_AT_IDX(node, prop, index, param2), (0),             \
                              (DT_PHA_BY_IDX(node, prop, index, param2))),                         \
    }
#define TRANSFORMED_BINDINGS(inst, prop)                                                          \
    {LISTIFY(DT_INST_PROP_LEN(inst, prop), TRANSFORM_BINDING, (, ), DT_DRV_INST(inst), prop)}

#define LAYER_MOD_CHORD_INST(inst)                                                                \
    BUILD_ASSERT(DT_INST_PROP_LEN(inst, bindings) ==                                              \
                     DT_INST_PROP_LEN(inst, sticky_bindings),                                     \
                 "modifier and sticky bindings must have matching lengths");                    \
    BUILD_ASSERT(DT_INST_PROP_LEN(inst, bindings) ==                                              \
                     DT_INST_PROP_LEN(inst, modifier_positions),                                  \
                 "modifier bindings and positions must have matching lengths");                 \
    BUILD_ASSERT(DT_INST_PROP_LEN(inst, bindings) <= 4, "at most four modifiers are supported"); \
    BUILD_ASSERT(DT_INST_PROP(inst, trigger_modifiers) < BIT(DT_INST_PROP_LEN(inst, bindings)),    \
                 "trigger modifiers must identify modifier bindings");                           \
    static const struct zmk_behavior_binding layer_mod_chord_modifiers_##inst[] =                 \
        TRANSFORMED_BINDINGS(inst, bindings);                                                     \
    static const struct zmk_behavior_binding layer_mod_chord_sticky_modifiers_##inst[] =          \
        TRANSFORMED_BINDINGS(inst, sticky_bindings);                                              \
    static const uint32_t layer_mod_chord_positions_##inst[] =                                    \
        DT_INST_PROP(inst, modifier_positions);                                                   \
    static const zmk_keymap_layer_id_t layer_mod_chord_activation_layers_##inst[] =                \
        DT_INST_PROP(inst, activation_layers);                                                    \
    static struct behavior_layer_mod_chord_data layer_mod_chord_data_##inst;                      \
    static const struct behavior_layer_mod_chord_config layer_mod_chord_config_##inst = {         \
        .modifiers = layer_mod_chord_modifiers_##inst,                                            \
        .sticky_modifiers = layer_mod_chord_sticky_modifiers_##inst,                              \
        .modifier_positions = layer_mod_chord_positions_##inst,                                   \
        .activation_layers = layer_mod_chord_activation_layers_##inst,                             \
        .tapping_term_ms = DT_INST_PROP(inst, tapping_term_ms),                                   \
        .combo_term_ms = DT_INST_PROP(inst, combo_term_ms),                                       \
        .modifier_count = DT_INST_PROP_LEN(inst, bindings),                                       \
        .activation_layer_count = DT_INST_PROP_LEN(inst, activation_layers),                      \
        .trigger_modifiers = DT_INST_PROP(inst, trigger_modifiers),                               \
        .layer = DT_INST_PROP(inst, layer),                                                       \
        .layer_position = DT_INST_PROP(inst, layer_position),                                     \
    };                                                                                            \
    BEHAVIOR_DT_INST_DEFINE(inst, NULL, NULL, &layer_mod_chord_data_##inst,                       \
                            &layer_mod_chord_config_##inst, POST_KERNEL,                           \
                            CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &layer_mod_chord_driver_api);

DT_INST_FOREACH_STATUS_OKAY(LAYER_MOD_CHORD_INST)
