#define DT_DRV_COMPAT zmk_behavior_alpha_repeat

#include <string.h>

#include <zephyr/device.h>

#include <drivers/behavior.h>

#include <zmk/behavior.h>
#include <zmk/event_manager.h>
#include <zmk/events/keycode_state_changed.h>
#include <zmk/hid.h>
#include <zmk/keys.h>

#define ALPHA_REPEAT_HISTORY_SIZE 16

struct alpha_repeat_key {
    uint16_t usage_page;
    uint16_t keycode;
    uint8_t modifiers;
};

struct behavior_alpha_repeat_data {
    struct zmk_keycode_state_changed remembered;
    struct zmk_keycode_state_changed active;
    struct alpha_repeat_key history[ALPHA_REPEAT_HISTORY_SIZE];
    uint8_t history_len;
};

static int alpha_repeat_pressed(struct zmk_behavior_binding *binding,
                                struct zmk_behavior_binding_event event) {
    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    struct behavior_alpha_repeat_data *data = dev->data;
    if (!data->remembered.usage_page) {
        data->active = (struct zmk_keycode_state_changed){0};
        return ZMK_BEHAVIOR_OPAQUE;
    }
    data->active = data->remembered;
    data->active.state = true;
    data->active.timestamp = event.timestamp;
    raise_zmk_keycode_state_changed(data->active);
    return ZMK_BEHAVIOR_OPAQUE;
}

static int alpha_repeat_released(struct zmk_behavior_binding *binding,
                                 struct zmk_behavior_binding_event event) {
    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    struct behavior_alpha_repeat_data *data = dev->data;
    if (!data->active.usage_page) {
        return ZMK_BEHAVIOR_OPAQUE;
    }
    data->active.state = false;
    data->active.timestamp = event.timestamp;
    raise_zmk_keycode_state_changed(data->active);
    data->active = (struct zmk_keycode_state_changed){0};
    return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api alpha_repeat_driver_api = {
    .binding_pressed = alpha_repeat_pressed,
    .binding_released = alpha_repeat_released,
};

static bool is_backspace(const struct alpha_repeat_key *key) {
    return key->usage_page == ZMK_HID_USAGE_PAGE(BACKSPACE) &&
           key->keycode == ZMK_HID_USAGE_ID(BACKSPACE);
}

static bool is_repeatable(const struct alpha_repeat_key *key) {
    return key->usage_page == ZMK_HID_USAGE_PAGE(A) &&
           !is_mod(key->usage_page, key->keycode);
}

static void update_remembered(struct behavior_alpha_repeat_data *data) {
    data->remembered = (struct zmk_keycode_state_changed){0};
    for (int i = data->history_len - 1; i >= 0; i--) {
        if (!is_repeatable(&data->history[i])) {
            continue;
        }
        data->remembered.usage_page = data->history[i].usage_page;
        data->remembered.keycode = data->history[i].keycode;
        data->remembered.implicit_modifiers = data->history[i].modifiers;
        return;
    }
}

static void append_history(struct behavior_alpha_repeat_data *data,
                           struct alpha_repeat_key key) {
    if (data->history_len == ALPHA_REPEAT_HISTORY_SIZE) {
        memmove(data->history, data->history + 1,
                sizeof(data->history[0]) * (ALPHA_REPEAT_HISTORY_SIZE - 1));
        data->history_len--;
    }
    data->history[data->history_len++] = key;
    update_remembered(data);
}

static int alpha_repeat_listener(const zmk_event_t *event) {
    const struct zmk_keycode_state_changed *key = as_zmk_keycode_state_changed(event);
    if (key == NULL || !key->state) {
        return ZMK_EV_EVENT_BUBBLE;
    }
    struct alpha_repeat_key pressed = {
        .usage_page = key->usage_page,
        .keycode = key->keycode,
        .modifiers =
            key->implicit_modifiers | key->explicit_modifiers | zmk_hid_get_explicit_mods(),
    };
    const struct device *dev = DEVICE_DT_INST_GET(0);
    struct behavior_alpha_repeat_data *data = dev->data;
    if (is_backspace(&pressed)) {
        if (pressed.modifiers) {
            data->history_len = 0;
        } else if (data->history_len) {
            data->history_len--;
        }
        update_remembered(data);
    } else if (is_repeatable(&pressed)) {
        append_history(data, pressed);
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(behavior_alpha_repeat, alpha_repeat_listener);
ZMK_SUBSCRIPTION(behavior_alpha_repeat, zmk_keycode_state_changed);

static struct behavior_alpha_repeat_data alpha_repeat_data;

BEHAVIOR_DT_INST_DEFINE(0, NULL, NULL, &alpha_repeat_data, NULL, POST_KERNEL,
                        CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &alpha_repeat_driver_api);
