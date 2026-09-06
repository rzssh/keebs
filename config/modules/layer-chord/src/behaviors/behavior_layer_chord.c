#define DT_DRV_COMPAT zmk_behavior_layer_chord

#include <zephyr/device.h>
#include <zephyr/sys/util.h>
#include <version.h>

#include <drivers/behavior.h>

#include <zmk/behavior.h>
#include <zmk/event_manager.h>
#include <zmk/events/layer_state_changed.h>
#include <zmk/events/position_state_changed.h>
#include <zmk/keymap.h>

struct behavior_layer_chord_config {
    zmk_keymap_layer_id_t parent_layer;
    zmk_keymap_layer_id_t child_layer;
    zmk_keymap_layer_id_t parent_overlay_layer;
    zmk_keymap_layer_id_t child_overlay_layer;
    uint32_t parent_position;
    uint32_t child_position;
    bool ordered;
};

struct behavior_layer_chord_data {
    bool active;
    bool parent_pressed;
    bool child_pressed;
    bool child_latest;
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

static void update_ordered_layers(const struct device *dev) {
    const struct behavior_layer_chord_config *config = dev->config;
    struct behavior_layer_chord_data *data = dev->data;
    bool both = (data->parent_pressed || data->child_pressed) &&
                zmk_keymap_layer_active(config->parent_layer) &&
                zmk_keymap_layer_active(config->child_layer);
    zmk_keymap_layer_id_t selected = data->child_latest ? config->child_overlay_layer
                                                       : config->parent_overlay_layer;
    zmk_keymap_layer_id_t rejected = data->child_latest ? config->parent_overlay_layer
                                                       : config->child_overlay_layer;
    if (zmk_keymap_layer_active(rejected)) {
        deactivate_layer(rejected);
    }
    if (both) {
        if (!zmk_keymap_layer_active(selected)) {
            activate_layer(selected);
        }
    } else if (zmk_keymap_layer_active(selected)) {
        deactivate_layer(selected);
    }
}

static int layer_chord_pressed(struct zmk_behavior_binding *binding,
                               struct zmk_behavior_binding_event event) {
    (void)event;
    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    const struct behavior_layer_chord_config *config = dev->config;
    struct behavior_layer_chord_data *data = dev->data;
    if (config->ordered) {
        bool child = binding->param1;
        if (child) {
            data->child_pressed = true;
            data->child_latest = true;
        } else {
            data->parent_pressed = true;
            data->child_latest = false;
        }
        int ret = activate_layer(child ? config->child_layer : config->parent_layer);
        if (ret < 0) {
            return ret;
        }
        update_ordered_layers(dev);
        return ZMK_BEHAVIOR_OPAQUE;
    }
    int ret = activate_layer(config->parent_layer);
    if (ret < 0) {
        return ret;
    }
    ret = activate_layer(config->child_layer);
    if (ret < 0) {
        deactivate_layer(config->parent_layer);
        return ret;
    }
    data->active = true;
    data->parent_pressed = true;
    data->child_pressed = true;
    return ZMK_BEHAVIOR_OPAQUE;
}

static int layer_chord_released(struct zmk_behavior_binding *binding,
                                struct zmk_behavior_binding_event event) {
    (void)event;
    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    const struct behavior_layer_chord_config *config = dev->config;
    struct behavior_layer_chord_data *data = dev->data;
    if (config->ordered) {
        bool child = binding->param1;
        if (child) {
            data->child_pressed = false;
            if (data->parent_pressed) {
                data->child_latest = false;
            }
        } else {
            data->parent_pressed = false;
            if (data->child_pressed) {
                data->child_latest = true;
            }
        }
        deactivate_layer(child ? config->child_layer : config->parent_layer);
        update_ordered_layers(dev);
        return ZMK_BEHAVIOR_OPAQUE;
    }
    if (data->parent_pressed) {
        data->parent_pressed = false;
        deactivate_layer(config->parent_layer);
    }
    if (data->child_pressed) {
        data->child_pressed = false;
        deactivate_layer(config->child_layer);
    }
    data->active = false;
    return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api layer_chord_driver_api = {
    .binding_pressed = layer_chord_pressed,
    .binding_released = layer_chord_released,
};

#define LAYER_CHORD_DEVICE(inst) DEVICE_DT_INST_GET(inst),
static const struct device *layer_chord_devices[] = {
    DT_INST_FOREACH_STATUS_OKAY(LAYER_CHORD_DEVICE)};

bool zmk_layer_chord_position(uint32_t position) {
    for (size_t index = 0; index < ARRAY_SIZE(layer_chord_devices); index++) {
        const struct behavior_layer_chord_config *config = layer_chord_devices[index]->config;
        if (position == config->parent_position || position == config->child_position) {
            return true;
        }
    }
    return false;
}

static int layer_chord_position_listener(const zmk_event_t *event) {
    const struct zmk_position_state_changed *position_event =
        as_zmk_position_state_changed(event);
    if (position_event == NULL) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    for (size_t index = 0; index < ARRAY_SIZE(layer_chord_devices); index++) {
        const struct device *dev = layer_chord_devices[index];
        const struct behavior_layer_chord_config *config = dev->config;
        struct behavior_layer_chord_data *data = dev->data;
        if (!data->active || config->ordered) {
            continue;
        }
        if (position_event->position == config->parent_position) {
            if (position_event->state && !data->parent_pressed) {
                activate_layer(config->parent_layer);
                data->parent_pressed = true;
            } else if (!position_event->state && data->parent_pressed) {
                data->parent_pressed = false;
                deactivate_layer(config->parent_layer);
            }
        } else if (position_event->position == config->child_position) {
            if (position_event->state && !data->child_pressed) {
                activate_layer(config->child_layer);
                data->child_pressed = true;
            } else if (!position_event->state && data->child_pressed) {
                data->child_pressed = false;
                deactivate_layer(config->child_layer);
            }
        }
        if (!data->parent_pressed && !data->child_pressed) {
            data->active = false;
        }
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(layer_chord, layer_chord_position_listener);
ZMK_SUBSCRIPTION(layer_chord, zmk_position_state_changed);

static int layer_chord_layer_listener(const zmk_event_t *event) {
    const struct zmk_layer_state_changed *layer_event = as_zmk_layer_state_changed(event);
    if (layer_event == NULL || layer_event->state) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    for (size_t index = 0; index < ARRAY_SIZE(layer_chord_devices); index++) {
        const struct device *dev = layer_chord_devices[index];
        const struct behavior_layer_chord_config *config = dev->config;
        struct behavior_layer_chord_data *data = dev->data;
        if (config->ordered) {
            update_ordered_layers(dev);
            continue;
        }
        if (data->parent_pressed && layer_event->layer == config->parent_layer) {
            activate_layer(config->parent_layer);
        }
        if (data->child_pressed && layer_event->layer == config->child_layer) {
            activate_layer(config->child_layer);
        }
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(layer_chord_layer, layer_chord_layer_listener);
ZMK_SUBSCRIPTION(layer_chord_layer, zmk_layer_state_changed);

#define LAYER_CHORD_INST(inst)                                                                    \
    static struct behavior_layer_chord_data layer_chord_data_##inst;                              \
    static const struct behavior_layer_chord_config layer_chord_config_##inst = {                  \
        .parent_layer = DT_INST_PROP(inst, parent_layer),                                          \
        .child_layer = DT_INST_PROP(inst, child_layer),                                            \
        .parent_overlay_layer = DT_INST_PROP_OR(inst, parent_overlay_layer, 0),                    \
        .child_overlay_layer = DT_INST_PROP_OR(inst, child_overlay_layer, 0),                      \
        .parent_position = DT_INST_PROP(inst, parent_position),                                    \
        .child_position = DT_INST_PROP(inst, child_position),                                      \
        .ordered = DT_INST_NODE_HAS_PROP(inst, parent_overlay_layer),                              \
    };                                                                                             \
    BEHAVIOR_DT_INST_DEFINE(inst, NULL, NULL, &layer_chord_data_##inst,                            \
                            &layer_chord_config_##inst, POST_KERNEL,                               \
                            CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &layer_chord_driver_api);

DT_INST_FOREACH_STATUS_OKAY(LAYER_CHORD_INST)
