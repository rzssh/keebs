#define DT_DRV_COMPAT zmk_behavior_layer_mod_chord

#include <zephyr/device.h>
#include <zephyr/sys/util.h>
#include <version.h>

#include <drivers/behavior.h>

#include <zmk/behavior.h>
#include <zmk/event_manager.h>
#include <zmk/events/layer_state_changed.h>
#include <zmk/events/position_state_changed.h>
#include <zmk/keymap.h>

struct behavior_layer_mod_chord_config {
    const struct zmk_behavior_binding *modifiers;
    const uint32_t *modifier_positions;
    uint8_t modifier_count;
    zmk_keymap_layer_id_t layer;
    uint32_t layer_position;
};

struct behavior_layer_mod_chord_data {
    struct zmk_behavior_binding_event modifier_events[4];
    uint8_t modifiers_pressed;
    bool active;
    bool layer_pressed;
};

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

static int release_modifier(const struct behavior_layer_mod_chord_config *config,
                            struct behavior_layer_mod_chord_data *data, uint8_t index,
                            int64_t timestamp) {
    if (!(data->modifiers_pressed & BIT(index))) {
        return 0;
    }
    data->modifiers_pressed &= ~BIT(index);
    data->modifier_events[index].timestamp = timestamp;
    return zmk_behavior_invoke_binding(&config->modifiers[index], data->modifier_events[index],
                                       false);
}

static int release_modifiers(const struct behavior_layer_mod_chord_config *config,
                             struct behavior_layer_mod_chord_data *data, int64_t timestamp) {
    int ret = 0;
    for (uint8_t index = 0; index < config->modifier_count; index++) {
        int current = release_modifier(config, data, index, timestamp);
        if (ret >= 0 && current < 0) {
            ret = current;
        }
    }
    return ret;
}

static int layer_mod_chord_pressed(struct zmk_behavior_binding *binding,
                                   struct zmk_behavior_binding_event event) {
    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    const struct behavior_layer_mod_chord_config *config = dev->config;
    struct behavior_layer_mod_chord_data *data = dev->data;
    int ret = activate_layer(config->layer);
    if (ret < 0) {
        return ret;
    }
    data->active = true;
    data->layer_pressed = true;
    data->modifiers_pressed = 0;
    for (uint8_t index = 0; index < config->modifier_count; index++) {
        event.position = config->modifier_positions[index];
        ret = zmk_behavior_invoke_binding(&config->modifiers[index], event, true);
        if (ret < 0) {
            release_modifiers(config, data, event.timestamp);
            deactivate_layer(config->layer);
            data->active = false;
            data->layer_pressed = false;
            return ret;
        }
        data->modifier_events[index] = event;
        data->modifiers_pressed |= BIT(index);
    }
    return ZMK_BEHAVIOR_OPAQUE;
}

static int layer_mod_chord_released(struct zmk_behavior_binding *binding,
                                    struct zmk_behavior_binding_event event) {
    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    const struct behavior_layer_mod_chord_config *config = dev->config;
    struct behavior_layer_mod_chord_data *data = dev->data;
    int ret = release_modifiers(config, data, event.timestamp);
    if (data->layer_pressed) {
        data->layer_pressed = false;
        deactivate_layer(config->layer);
    }
    data->active = false;
    return ret < 0 ? ret : ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api layer_mod_chord_driver_api = {
    .binding_pressed = layer_mod_chord_pressed,
    .binding_released = layer_mod_chord_released,
};

#define LAYER_MOD_CHORD_DEVICE(inst) DEVICE_DT_INST_GET(inst),
static const struct device *layer_mod_chord_devices[] = {
    DT_INST_FOREACH_STATUS_OKAY(LAYER_MOD_CHORD_DEVICE)};

static int layer_mod_chord_position_listener(const zmk_event_t *event) {
    const struct zmk_position_state_changed *position_event =
        as_zmk_position_state_changed(event);
    if (position_event == NULL || position_event->state) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    for (size_t device_index = 0; device_index < ARRAY_SIZE(layer_mod_chord_devices);
         device_index++) {
        const struct device *dev = layer_mod_chord_devices[device_index];
        const struct behavior_layer_mod_chord_config *config = dev->config;
        struct behavior_layer_mod_chord_data *data = dev->data;
        if (!data->active) {
            continue;
        }
        if (position_event->position == config->layer_position && data->layer_pressed) {
            data->layer_pressed = false;
            deactivate_layer(config->layer);
        }
        for (uint8_t modifier_index = 0; modifier_index < config->modifier_count;
             modifier_index++) {
            if (position_event->position == config->modifier_positions[modifier_index]) {
                release_modifier(config, data, modifier_index, position_event->timestamp);
            }
        }
        if (!data->layer_pressed && !data->modifiers_pressed) {
            data->active = false;
        }
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(layer_mod_chord, layer_mod_chord_position_listener);
ZMK_SUBSCRIPTION(layer_mod_chord, zmk_position_state_changed);

static int layer_mod_chord_layer_listener(const zmk_event_t *event) {
    const struct zmk_layer_state_changed *layer_event = as_zmk_layer_state_changed(event);
    if (layer_event == NULL || layer_event->state) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    for (size_t index = 0; index < ARRAY_SIZE(layer_mod_chord_devices); index++) {
        const struct device *dev = layer_mod_chord_devices[index];
        const struct behavior_layer_mod_chord_config *config = dev->config;
        const struct behavior_layer_mod_chord_data *data = dev->data;
        if (data->layer_pressed && layer_event->layer == config->layer) {
            activate_layer(config->layer);
        }
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(layer_mod_chord_layer, layer_mod_chord_layer_listener);
ZMK_SUBSCRIPTION(layer_mod_chord_layer, zmk_layer_state_changed);

#define TRANSFORM_BINDING(index, node) ZMK_KEYMAP_EXTRACT_BINDING(index, node)
#define TRANSFORMED_BINDINGS(inst)                                                                \
    {LISTIFY(DT_INST_PROP_LEN(inst, bindings), TRANSFORM_BINDING, (, ), DT_DRV_INST(inst))}

#define LAYER_MOD_CHORD_INST(inst)                                                                \
    BUILD_ASSERT(DT_INST_PROP_LEN(inst, bindings) ==                                              \
                     DT_INST_PROP_LEN(inst, modifier_positions),                                  \
                 "modifier bindings and positions must have matching lengths");                  \
    BUILD_ASSERT(DT_INST_PROP_LEN(inst, bindings) <= 4, "at most four modifiers are supported"); \
    static const struct zmk_behavior_binding layer_mod_chord_modifiers_##inst[] =                 \
        TRANSFORMED_BINDINGS(inst);                                                               \
    static const uint32_t layer_mod_chord_positions_##inst[] =                                    \
        DT_INST_PROP(inst, modifier_positions);                                                   \
    static struct behavior_layer_mod_chord_data layer_mod_chord_data_##inst;                      \
    static const struct behavior_layer_mod_chord_config layer_mod_chord_config_##inst = {         \
        .modifiers = layer_mod_chord_modifiers_##inst,                                            \
        .modifier_positions = layer_mod_chord_positions_##inst,                                   \
        .modifier_count = DT_INST_PROP_LEN(inst, bindings),                                       \
        .layer = DT_INST_PROP(inst, layer),                                                       \
        .layer_position = DT_INST_PROP(inst, layer_position),                                     \
    };                                                                                            \
    BEHAVIOR_DT_INST_DEFINE(inst, NULL, NULL, &layer_mod_chord_data_##inst,                       \
                            &layer_mod_chord_config_##inst, POST_KERNEL,                           \
                            CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &layer_mod_chord_driver_api);

DT_INST_FOREACH_STATUS_OKAY(LAYER_MOD_CHORD_INST)
