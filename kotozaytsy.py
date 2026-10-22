#!/usr/bin/env python3
"""Transparent kitten-bunny desktop pet for Hyprland."""

import json
import math
import random
import shutil
import subprocess
import time
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gtk, Gtk4LayerShell as LayerShell, GLib


SPRITE = Path(__file__).with_name("kotobunny.png")
SOUNDS = Path(__file__).parent
SETTINGS = Path.home() / ".config" / "kotozaytsy" / "settings.json"
MIN_SIZE, MAX_SIZE = 150, 420
MIN_Y, MAX_Y = -160, 200
JUMP_HEIGHT = 205
GRAVITY = 1850.0


class Kotozaytsy(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="ru.kotozaytsy.hyprland")
        self.settings = self.load_settings()
        self.started = time.monotonic()
        self.last_tick = self.started
        self.jump_started = None
        self.next_jump = self.started + random.uniform(6.0, 12.0)
        self.pet_x = None
        self.walk_direction = random.choice((-1, 1))
        self.walk_pause_until = self.started + 1.0
        self.fall_started = None
        self.fall_from_dy = 0.0
        self.landing_started = None
        self.next_position_save = self.started + 3.0
        self.grabbed = False
        self.grab_dy = 0.0
        self.grab_dx = 0.0
        self.grab_target_dx = 0.0
        self.grab_target_dy = 0.0
        self.grab_vy = 0.0
        self.fall_offset = 0.0
        self.fall_velocity = 0.0
        self.walk_velocity = 0.0
        self.monitors = []
        self.monitor_rects = []
        self.active_monitor_index = 0
        self.drag_source_index = 0
        self.drag_start_global_x = 0.0
        self.drag_start_global_top = 0.0
        self.drag_display_global_x = 0.0
        self.drag_display_global_top = 0.0
        self.drag_velocity_x = 0.0
        self.drag_velocity_y = 0.0
        self.opened_settings_from_right_click = False
        self.settings_window = None

    @staticmethod
    def load_settings():
        settings = {"size": 320, "y": 0, "attach_cursor": True, "walk": True, "sounds": True}
        try:
            saved = json.loads(SETTINGS.read_text())
            settings["size"] = int(max(MIN_SIZE, min(MAX_SIZE, saved.get("size", 320))))
            settings["y"] = int(max(MIN_Y, min(MAX_Y, saved.get("y", 0))))
            settings["attach_cursor"] = bool(saved.get("attach_cursor", True))
            settings["walk"] = bool(saved.get("walk", True))
            settings["sounds"] = bool(saved.get("sounds", True))
            if saved.get("x") is not None:
                settings["x"] = float(saved["x"])
            settings["monitor"] = saved.get("monitor")
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return settings

    def save_settings(self):
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        if self.pet_x is not None:
            self.settings["x"] = round(self.pet_x, 1)
        if self.monitors:
            self.settings["monitor"] = self.monitor_name(self.monitors[self.active_monitor_index])
        SETTINGS.write_text(json.dumps(self.settings, indent=2) + "\n")

    @staticmethod
    def monitor_name(monitor):
        try:
            return monitor.get_connector() or monitor.get_model()
        except (AttributeError, TypeError):
            return monitor.get_model()

    def do_activate(self):
        display = Gdk.Display.get_default()
        model = display.get_monitors()
        self.monitors = [model.get_item(i) for i in range(model.get_n_items())]
        if not self.monitors:
            self.monitors = [None]
        self.monitor_rects = []
        for monitor in self.monitors:
            if monitor is None:
                self.monitor_rects.append((0, 0, 1920, 1080))
            else:
                r = monitor.get_geometry()
                self.monitor_rects.append((r.x, r.y, r.width, r.height))

        wanted_monitor = self.settings.get("monitor")
        selected = next((i for i, m in enumerate(self.monitors)
                         if m is not None and self.monitor_name(m) == wanted_monitor), None)
        if selected is None:
            selected = next((i for i, r in enumerate(self.monitor_rects)
                             if r[0] == 0 and r[1] == 0), 0)
        self.active_monitor_index = selected
        self.monitor = self.monitors[selected]
        self._set_active_geometry()
        rx, ry, rw, rh = self.monitor_rects[selected]
        self.pet_x = self.clamp_x(float(self.settings.get("x", rw / 2)), self.settings["size"])

        self.windows = []
        self.canvases = []
        for index, monitor in enumerate(self.monitors):
            _x, _y, width, height = self.monitor_rects[index]
            window = Gtk.ApplicationWindow(application=self)
            window.set_title("Котозайцы")
            window.set_decorated(False)
            window.set_default_size(width, height)
            window.set_resizable(False)
            window.add_css_class("pet-window")
            LayerShell.init_for_window(window)
            if monitor is not None:
                LayerShell.set_monitor(window, monitor)
            LayerShell.set_namespace(window, f"kotozaytsy-{index}")
            LayerShell.set_layer(window, LayerShell.Layer.OVERLAY)
            for edge in (LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
                LayerShell.set_anchor(window, edge, True)
            LayerShell.set_anchor(window, LayerShell.Edge.TOP, False)
            LayerShell.set_margin(window, LayerShell.Edge.BOTTOM, 0)
            LayerShell.set_exclusive_zone(window, -1)
            LayerShell.set_keyboard_mode(window, LayerShell.KeyboardMode.ON_DEMAND)

            canvas = Gtk.DrawingArea()
            canvas.set_content_width(width)
            canvas.set_content_height(height)
            canvas.set_draw_func(lambda area, cr, w, h, i=index: self.draw(i, area, cr, w, h))
            window.set_child(canvas)

            drag = Gtk.GestureDrag()
            drag.set_button(0)
            drag.connect("drag-begin", lambda g, x, y, i=index: self.on_drag_begin(g, x, y, i))
            drag.connect("drag-update", lambda g, dx, dy, i=index: self.on_drag_update(g, dx, dy, i))
            drag.connect("drag-end", lambda g, dx, dy, i=index: self.on_drag_end(g, dx, dy, i))
            canvas.add_controller(drag)
            keys = Gtk.EventControllerKey()
            keys.connect("key-pressed", self.on_key)
            window.add_controller(keys)
            self.windows.append(window)
            self.canvases.append(canvas)

        self.window = self.windows[selected]
        self.canvas = self.canvases[selected]
        try:
            self.sprite = GdkPixbuf.Pixbuf.new_from_file(str(SPRITE))
        except Exception as exc:
            raise SystemExit(f"Не удалось загрузить {SPRITE.name}: {exc}")

        css = Gtk.CssProvider()
        css.load_from_data(b"window.pet-window, window.pet-window > * { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(
            display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        for window in self.windows:
            window.present()
        GLib.timeout_add(4, self.tick)

    def _set_active_geometry(self):
        self.monitor = self.monitors[self.active_monitor_index]
        _x, _y, self.screen_width, self.stage_height = self.monitor_rects[self.active_monitor_index]
        if hasattr(self, "windows") and self.windows:
            self.window = self.windows[self.active_monitor_index]
            self.canvas = self.canvases[self.active_monitor_index]

    def _monitor_for_point(self, x, y):
        for i, (rx, ry, rw, rh) in enumerate(self.monitor_rects):
            if rx <= x < rx + rw and ry <= y < ry + rh:
                return i
        def distance(rect):
            rx, ry, rw, rh = rect
            cx = min(max(x, rx), rx + rw)
            cy = min(max(y, ry), ry + rh)
            return (x - cx) ** 2 + (y - cy) ** 2
        return min(range(len(self.monitor_rects)), key=lambda i: distance(self.monitor_rects[i]))

    def on_drag_begin(self, gesture, x, y, monitor_index):
        if gesture.get_current_button() == Gdk.BUTTON_SECONDARY:
            self.active_monitor_index = monitor_index
            self._set_active_geometry()
            self.open_settings()
            self.opened_settings_from_right_click = True
            return
        if monitor_index != self.active_monitor_index:
            return
        self.grabbed = True
        self.drag_source_index = monitor_index
        rx, ry, _rw, rh = self.monitor_rects[monitor_index]
        size = self.settings["size"]
        self.drag_start_global_x = rx + self.pet_x
        self.drag_start_global_top = ry + rh - size - self.settings["y"]
        self.drag_display_global_x = self.drag_start_global_x
        self.drag_display_global_top = self.drag_start_global_top
        self.drag_velocity_x = self.drag_velocity_y = 0.0
        self.grab_dx = self.grab_dy = 0.0
        self.grab_target_dx = self.grab_target_dy = 0.0
        self.grab_vy = 0.0
        self.last_drag_event = time.monotonic()
        self.jump_started = None

    def on_drag_update(self, _gesture, dx, dy, _monitor_index):
        if not self.grabbed or not self.settings["attach_cursor"]:
            return
        now = time.monotonic()
        elapsed = max(now - self.last_drag_event, 0.008)
        self.grab_vy = max(-1500.0, min(1500.0, (dy - self.grab_target_dy) / elapsed))
        self.last_drag_event = now
        self.grab_target_dx, self.grab_target_dy = dx, dy

    def on_drag_end(self, _gesture, dx, dy, _monitor_index):
        if self.opened_settings_from_right_click:
            self.opened_settings_from_right_click = False
            return
        if not self.grabbed:
            return
        if self.settings["attach_cursor"]:
            self.grab_target_dx, self.grab_target_dy = dx, dy
        moved = abs(self.grab_target_dx) > 4 or abs(self.grab_target_dy) > 4
        size = self.settings["size"]
        target_x = self.drag_start_global_x + self.grab_target_dx
        target_top = self.drag_start_global_top + self.grab_target_dy
        index = self._monitor_for_point(target_x, target_top + size / 2)
        rx, ry, rw, rh = self.monitor_rects[index]
        target_top = max(ry, min(ry + rh - size, target_top))
        self.active_monitor_index = index
        self._set_active_geometry()
        self.pet_x = target_x - rx
        base_top = ry + rh - size - self.settings["y"]
        self.grab_dy = target_top - base_top
        self.grab_dx = 0.0
        self.grabbed = False
        if moved:
            if abs(self.grab_dy) > 4:
                self.fall_offset = min(0.0, self.grab_dy)
                self.fall_velocity = max(0.0, self.grab_vy)
                self.fall_started = time.monotonic()
                self.landing_started = None
            else:
                self.fall_started = None
                self.landing_started = time.monotonic()
                self.play_sound("land.wav")
            self.walk_pause_until = time.monotonic() + random.uniform(5.0, 9.0)
            self.save_settings()
        else:
            self.jump_started = time.monotonic()
            self.play_sound("meow.wav")
        self.grab_dx = self.grab_dy = 0.0

    def open_settings(self):
        if self.settings_window is not None:
            self.settings_window.present()
            return

        dialog = Gtk.Window(application=self)
        dialog.set_title("Настройки котозайца")
        dialog.set_default_size(390, 390)
        dialog.set_resizable(False)
        dialog.set_transient_for(self.window)
        self.settings_window = dialog
        dialog.connect("close-request", self.on_settings_closed)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20)
        box.set_margin_bottom(18)
        box.set_margin_start(22)
        box.set_margin_end(22)
        dialog.set_child(box)

        title = Gtk.Label(label="Настройки котозайца")
        title.set_xalign(0)
        title.add_css_class("title-2")
        box.append(title)

        self.size_label = Gtk.Label()
        self.size_label.set_xalign(0)
        self.size_label.set_text(f"Размер: {self.settings['size']} px")
        box.append(self.size_label)
        size_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, MIN_SIZE, MAX_SIZE, 10
        )
        size_scale.set_draw_value(False)
        size_scale.set_value(self.settings["size"])
        size_scale.connect("value-changed", self.on_size_changed)
        box.append(size_scale)

        self.y_label = Gtk.Label()
        self.y_label.set_xalign(0)
        self.update_y_label()
        box.append(self.y_label)
        y_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, MIN_Y, MAX_Y, 10
        )
        y_scale.set_draw_value(False)
        y_scale.set_value(self.settings["y"])
        y_scale.connect("value-changed", self.on_y_changed)
        box.append(y_scale)

        attach = Gtk.CheckButton(label="Прикреплять котозайца к курсору за шкирку")
        attach.set_active(self.settings["attach_cursor"])
        attach.connect("toggled", self.on_attach_toggled)
        box.append(attach)

        walking = Gtk.CheckButton(label="Гулять вдоль нижнего края")
        walking.set_active(self.settings["walk"])
        walking.connect("toggled", self.on_walk_toggled)
        box.append(walking)

        sounds = Gtk.CheckButton(label="Звуки прыжка и приземления")
        sounds.set_active(self.settings["sounds"])
        sounds.connect("toggled", self.on_sounds_toggled)
        box.append(sounds)

        hint = Gtk.Label(label="После перетаскивания котозаяц приземлится на новом месте. Он не сбрасывает X назад; ползунка для X нет.")
        hint.set_xalign(0)
        hint.set_wrap(True)
        hint.add_css_class("dim-label")
        box.append(hint)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.set_halign(Gtk.Align.END)
        close_button = Gtk.Button(label="Готово")
        close_button.connect("clicked", lambda *_: dialog.close())
        quit_button = Gtk.Button(label="Выйти")
        quit_button.add_css_class("destructive-action")
        quit_button.connect("clicked", lambda *_: self.quit())
        buttons.append(close_button)
        buttons.append(quit_button)
        box.append(buttons)
        dialog.present()

    def on_settings_closed(self, _window):
        self.settings_window = None
        return False

    def on_size_changed(self, scale):
        self.settings["size"] = int(round(scale.get_value() / 10) * 10)
        if self.pet_x is not None:
            self.pet_x = self.clamp_x(self.pet_x, self.settings["size"])
        self.size_label.set_text(f"Размер: {self.settings['size']} px")
        self.save_settings()
        self.canvas.queue_draw()

    def on_y_changed(self, scale):
        self.settings["y"] = int(round(scale.get_value() / 10) * 10)
        self.update_y_label()
        self.save_settings()
        self.canvas.queue_draw()

    def on_attach_toggled(self, button):
        self.settings["attach_cursor"] = button.get_active()
        self.save_settings()

    def on_walk_toggled(self, button):
        self.settings["walk"] = button.get_active()
        self.walk_pause_until = time.monotonic()
        self.save_settings()

    def on_sounds_toggled(self, button):
        self.settings["sounds"] = button.get_active()
        self.save_settings()

    def play_sound(self, name):
        if not self.settings.get("sounds", True):
            return
        sound = SOUNDS / name
        if not sound.is_file():
            return
        player = shutil.which("pw-play") or shutil.which("paplay")
        if player:
            try:
                subprocess.Popen(
                    [player, str(sound)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError:
                pass

    def update_y_label(self):
        value = self.settings["y"]
        if value < 0:
            description = f"{abs(value)} px ниже края (прячется глубже)"
        elif value > 0:
            description = f"{value} px выше края"
        else:
            description = "на нижнем краю экрана"
        self.y_label.set_text(f"Положение Y: {description}")

    def on_key(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            if self.settings_window is not None:
                self.settings_window.close()
            else:
                self.quit()
            return True
        return False

    def tick(self):
        now = time.monotonic()
        dt = min(max(now - self.last_tick, 0.0), 0.05)
        self.last_tick = now

        walking_now = (
            self.settings["walk"] and not self.grabbed
            and self.jump_started is None and self.fall_started is None
            and now >= self.walk_pause_until
        )
        if walking_now:
            desired = self.walk_direction * 120.0
            self.walk_velocity += max(-500.0 * dt, min(500.0 * dt, desired - self.walk_velocity))
            self.pet_x += self.walk_velocity * dt
            half = self.settings["size"] / 2
            left, right = half + 18, self.screen_width - half - 18
            if self.pet_x <= left:
                self.pet_x = left
                self.walk_direction = 1
                self.walk_velocity = 0.0
                self.walk_pause_until = now + random.uniform(0.35, 0.8)
            elif self.pet_x >= right:
                self.pet_x = right
                self.walk_direction = -1
                self.walk_velocity = 0.0
                self.walk_pause_until = now + random.uniform(0.35, 0.8)

        if (not self.grabbed and self.jump_started is None
                and self.fall_started is None and now >= self.next_jump):
            self.jump_started = now
            self.next_jump = now + random.uniform(8.0, 15.0)
        if not self.grabbed and self.jump_started is not None and now - self.jump_started > 0.86:
            self.jump_started = None
        if self.fall_started is not None:
            self.fall_velocity += GRAVITY * dt
            self.fall_offset += self.fall_velocity * dt
            if self.fall_offset >= 0.0:
                self.fall_offset = 0.0
                self.fall_started = None
                self.landing_started = now
                self.play_sound("land.wav")
        if self.landing_started is not None and now - self.landing_started > 0.75:
            self.landing_started = None
        if self.settings["walk"] and now >= self.next_position_save:
            self.save_settings()
            self.next_position_save = now + 3.0
        if self.grabbed and self.settings["attach_cursor"]:
            size = self.settings["size"]
            target_x = self.drag_start_global_x + self.grab_target_dx
            target_top = self.drag_start_global_top + self.grab_target_dy
            index = self._monitor_for_point(target_x, target_top + size / 2)
            rx, ry, rw, rh = self.monitor_rects[index]
            target_top = max(ry, min(ry + rh - size, target_top))
            old_x, old_top = self.drag_display_global_x, self.drag_display_global_top
            alpha = 1.0 - math.exp(-120.0 * dt)
            self.drag_display_global_x += (target_x - self.drag_display_global_x) * alpha
            self.drag_display_global_top += (target_top - self.drag_display_global_top) * alpha
            instant_vx = (self.drag_display_global_x - old_x) / max(dt, 0.001)
            instant_vy = (self.drag_display_global_top - old_top) / max(dt, 0.001)
            velocity_alpha = 1.0 - math.exp(-28.0 * dt)
            self.drag_velocity_x += (instant_vx - self.drag_velocity_x) * velocity_alpha
            self.drag_velocity_y += (instant_vy - self.drag_velocity_y) * velocity_alpha
            if index != self.active_monitor_index:
                previous_index = self.active_monitor_index
                self.active_monitor_index = index
                self._set_active_geometry()
                self.canvases[previous_index].queue_draw()
                self.canvases[index].queue_draw()
            rx, ry, _rw, rh = self.monitor_rects[self.active_monitor_index]
            self.pet_x = self.drag_display_global_x - rx
            base_top = ry + rh - size - self.settings["y"]
            self.grab_dx = 0.0
            self.grab_dy = self.drag_display_global_top - base_top
        self.canvas.queue_draw()
        return GLib.SOURCE_CONTINUE

    def clamp_x(self, x, size):
        half = size / 2
        left, right = half + 18, self.screen_width - half - 18
        return max(left, min(right, x))

    def pose(self, now, width, height):
        image_scale = self.settings["size"] / max(
            self.sprite.get_width(), self.sprite.get_height()
        )
        sw = self.sprite.get_width() * image_scale
        sh = self.sprite.get_height() * image_scale
        x = self.pet_x - sw / 2
        y = height - sh - self.settings["y"]
        tilt = 0.0
        squash = 1.0

        if self.grabbed:
            x += self.grab_dx
            y += self.grab_dy
            flail = math.sin(now * 27.0)
            tilt = 0.055 * flail
            squash = 1.0 + 0.035 * flail
        elif self.fall_started is not None:
            y += self.fall_offset
            tilt = min(0.24, self.fall_velocity / GRAVITY * 0.22) * math.sin(now * 9.0)
            squash = 1.0 + min(0.045, self.fall_velocity / GRAVITY * 0.04)
        elif self.landing_started is not None:
            t = now - self.landing_started
            squash = 1.0 - 0.14 * math.exp(-11.0 * t) * math.cos(23.0 * t)
            tilt = 0.045 * math.exp(-9.0 * t) * math.sin(19.0 * t)
        elif self.jump_started is not None:
            t = min((now - self.jump_started) / 0.86, 1.0)
            lift = JUMP_HEIGHT * math.sin(math.pi * t) ** 0.72
            y -= lift
            squash = 1.0 + 0.055 * math.sin(2 * math.pi * t)
            tilt = 0.035 * math.sin(3 * math.pi * t)
        else:
            step = math.sin((now - self.started) * 13.0)
            if self.settings["walk"] and now >= self.walk_pause_until:
                y -= 8.0 * abs(step)
                squash = 1.0 + 0.028 * step
                tilt = self.walk_direction * 0.035 * step
            else:
                y -= 2.0 * abs(step)
                squash = 1.0 + 0.008 * step
                tilt = 0.006 * step

        return x, y, sw, sh, image_scale, tilt, squash

    def update_input_region(self, monitor_index, now, width, height):
        surface = self.windows[monitor_index].get_surface()
        if surface is None:
            return
        if monitor_index != self.active_monitor_index:
            surface.set_input_region(cairo.Region())
            return
        x, y, sw, sh, _scale, _tilt, _squash = self.pose(now, width, height)
        left = max(0, int(math.floor(x)))
        top = max(0, int(math.floor(y)))
        right = min(width, int(math.ceil(x + sw)))
        bottom = min(height, int(math.ceil(y + sh)))
        if right <= left or bottom <= top:
            surface.set_input_region(cairo.Region())
            return
        surface.set_input_region(cairo.Region(cairo.RectangleInt(left, top, right-left, bottom-top)))

    def draw_sprite(self, cr, x, y, sw, sh, image_scale, tilt, squash, alpha=1.0):
        if alpha < 0.999:
            cr.push_group()
        cr.save()
        cr.translate(x + sw / 2, y + sh)
        cr.rotate(tilt)
        cr.scale(1.0, squash)
        cr.translate(-sw / 2, -sh)
        cr.scale(image_scale, image_scale)
        Gdk.cairo_set_source_pixbuf(cr, self.sprite, 0, 0)
        cr.rectangle(0, 0, self.sprite.get_width(), self.sprite.get_height())
        cr.fill()
        cr.restore()
        if alpha < 0.999:
            cr.pop_group_to_source()
            cr.paint_with_alpha(alpha)

    def draw(self, monitor_index, _area, cr, width, height):
        now = time.monotonic()
        if monitor_index != self.active_monitor_index:
            # Clear the old output as the pet crosses displays. Otherwise its
            # last frame stays cached and looks like a second, distant pet.
            cr.save()
            cr.set_operator(cairo.OPERATOR_CLEAR)
            cr.paint()
            cr.restore()
            surface = self.windows[monitor_index].get_surface()
            if surface is not None:
                surface.set_input_region(cairo.Region())
            return
        x, y, sw, sh, image_scale, tilt, squash = self.pose(now, width, height)
        speed = math.hypot(self.drag_velocity_x, self.drag_velocity_y)

        # The cutout faces right. Mirror during a leftward walk so the muzzle
        # points along the travel direction; leave the idle/drag pose intact.
        walking_left = (
            self.settings["walk"] and not self.grabbed
            and self.jump_started is None and self.fall_started is None
            and now >= self.walk_pause_until and self.walk_direction < 0
        )
        draw_x = x
        if walking_left:
            cr.save()
            cr.translate(2 * x + sw, 0)
            cr.scale(-1.0, 1.0)
            self.draw_sprite(cr, draw_x, y, sw, sh, image_scale, tilt, squash)
            cr.restore()
        else:
            # While grabbed, a tiny lean and compression make speed readable.
            if self.grabbed:
                tilt += max(-0.16, min(0.16, -self.drag_velocity_x / 1500.0))
                squash *= 1.0 + min(0.045, speed / 5000.0)
            self.draw_sprite(cr, draw_x, y, sw, sh, image_scale, tilt, squash)
        self.update_input_region(monitor_index, now, width, height)


if __name__ == "__main__":
    Kotozaytsy().run()
