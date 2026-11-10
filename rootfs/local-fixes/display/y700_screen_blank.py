#!/usr/bin/python3
"""Blank the Y700 backlight without powering down the panel/touch controller."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import struct
import sys
import time

BACKLIGHT = Path('/sys/class/backlight/aw99706-backlight/brightness')
STATE = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'y700-screen-blank.json'
NAME = 'org.y700.ScreenBlank'
OBJECT = '/org/y700/ScreenBlank'
EVENT = struct.Struct('@llHHi')
EVIOCGRAB = 0x40044590
TOUCH_NAME = 'NVTCapacitiveTouchScreen'


def restore_saved():
    if not STATE.exists():
        return
    value = json.loads(STATE.read_text())['brightness']
    maximum = int((BACKLIGHT.parent / 'max_brightness').read_text())
    if not isinstance(value, int) or not 0 < value <= maximum:
        raise RuntimeError('Invalid saved brightness')
    BACKLIGHT.write_text(str(value))
    STATE.unlink(missing_ok=True)


class ContactState:
    def __init__(self):
        self.slot = 0
        self.slots = set()
        self.button = False
        self.new_contact = False

    @property
    def down(self):
        return self.button or bool(self.slots)

    def event(self, kind, code, value):
        if kind == 1 and code == 330:  # BTN_TOUCH
            self.new_contact |= value == 1 and not self.button
            self.button = value != 0
        elif kind == 3 and code == 47:  # ABS_MT_SLOT
            self.slot = value
        elif kind == 3 and code == 57:  # ABS_MT_TRACKING_ID
            self.new_contact |= value >= 0 and self.slot not in self.slots
            if value < 0:
                self.slots.discard(self.slot)
            else:
                self.slots.add(self.slot)


class BlankController:
    """Keep the waking touch grabbed until all fingers have left the glass."""
    def __init__(self, read, write, save, clear, grab, now=time.monotonic):
        self.read, self.write, self.save, self.clear, self.grab, self.now = read, write, save, clear, grab, now
        self.blank = False
        self.grabbed = False
        self.saved = 1
        self.armed_at = 0
        self.ignore_held = False

    def off(self, held=False):
        if self.blank:
            return
        value = self.read()
        if value <= 0:
            raise RuntimeError('Panel already off; cannot save a usable brightness')
        self.saved = value
        self.save(value)
        self.blank = True
        try:
            self.grab(True)
            self.grabbed = True
            self.write(0)
        except BaseException:
            self.on()
            raise
        self.armed_at = self.now() + 0.25
        self.ignore_held = held

    def on(self, consume_touch=False):
        if self.blank or self.grabbed:
            # Keep recovery state and the grab if restoring brightness fails.
            self.write(self.saved)
            self.clear()
            self.blank = False
        if self.grabbed and not consume_touch:
            self.grab(False)
            self.grabbed = False

    def touch_frame(self, contact):
        if self.ignore_held:
            if not contact.down:
                self.ignore_held = False
        elif self.blank and contact.new_contact and self.now() >= self.armed_at:
            self.on(consume_touch=True)
        if self.grabbed and not self.blank and not contact.down:
            self.grab(False)
            self.grabbed = False
        contact.new_contact = False


def daemon():
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import Gio, GLib

    DBusGMainLoop(set_as_default=True)
    session = dbus.SessionBus()
    system = dbus.SystemBus()
    restore_saved()
    devices = {}
    contact = ContactState()
    touch_fd = None
    pressed_at = None
    last_power = -10.0
    inhibitor = None
    loop = GLib.MainLoop()
    manager = dbus.Interface(system.get_object('org.freedesktop.login1', '/org/freedesktop/login1'),
                             'org.freedesktop.login1.Manager')
    user_path = manager.GetUser(dbus.UInt32(os.getuid()))
    user_props = dbus.Interface(system.get_object('org.freedesktop.login1', user_path),
                               'org.freedesktop.DBus.Properties')
    session_path = user_props.Get('org.freedesktop.login1.User', 'Display')[1]
    active_props = dbus.Interface(system.get_object('org.freedesktop.login1', session_path),
                                 'org.freedesktop.DBus.Properties')

    def active():
        return bool(active_props.Get('org.freedesktop.login1.Session', 'Active'))

    def save(value):
        temporary = STATE.with_suffix('.new')
        temporary.write_text(json.dumps({'brightness': value}) + '\n')
        temporary.chmod(0o600)
        temporary.replace(STATE)

    def grab(enabled):
        if touch_fd is None:
            if enabled:
                raise RuntimeError('Touchscreen is unavailable')
            return
        try:
            fcntl.ioctl(touch_fd, EVIOCGRAB, int(enabled))
        except OSError:
            if enabled:
                raise

    controller = BlankController(lambda: int(BACKLIGHT.read_text()),
                                 lambda value: BACKLIGHT.write_text(str(value)), save,
                                 lambda: STATE.unlink(missing_ok=True), grab)

    def reset_idle():
        try:
            session.call_blocking('org.freedesktop.ScreenSaver', '/ScreenSaver',
                                  'org.freedesktop.ScreenSaver', 'SimulateUserActivity', '', (), timeout=2)
        except dbus.DBusException:
            pass

    def wake(consume=False):
        was_blank = controller.blank
        controller.on(consume)
        if was_blank:
            reset_idle()
            print('Display on; previous brightness restored', flush=True)

    def off():
        if not active():
            raise RuntimeError('Graphical session is not active')
        if bool(dbus.Interface(system.get_object('org.freedesktop.login1', '/org/freedesktop/login1'),
                               'org.freedesktop.DBus.Properties').Get('org.freedesktop.login1.Manager', 'PreparingForSleep')):
            raise RuntimeError('A system suspend is already being prepared')
        if int((BACKLIGHT.parent / 'bl_power').read_text()) != 0:
            raise RuntimeError('Panel is powered down; use the tap-to-wake screen-off action')
        controller.off(contact.down)
        print('Backlight off; touch remains active', flush=True)

    def toggle():
        if controller.blank:
            wake()
        else:
            off()

    def release_if_stuck():
        if controller.grabbed and not controller.blank:
            # A missing release must never strand touchscreen input.
            wake()
        return False

    def input_ready(fd, condition):
        nonlocal pressed_at, last_power
        if condition & (GLib.IO_HUP | GLib.IO_ERR):
            remove_device(fd)
            return False
        try:
            data = os.read(fd, EVENT.size * 128)
            if not data:
                remove_device(fd)
                return False
            for offset in range(0, len(data) - EVENT.size + 1, EVENT.size):
                _, _, kind, code, value = EVENT.unpack_from(data, offset)
                if fd == touch_fd:
                    if kind == 0 and code == 3:  # SYN_DROPPED
                        wake()
                        contact.slots.clear()
                        contact.button = False
                    elif kind == 0 and code == 0:
                        was_blank = controller.blank
                        controller.touch_frame(contact)
                        if was_blank and not controller.blank:
                            reset_idle()
                            print('Display on from tap; waking contact consumed', flush=True)
                            GLib.timeout_add_seconds(5, release_if_stuck)
                    else:
                        contact.event(kind, code, value)
                elif kind == 1 and code == 116:  # KEY_POWER
                    if value == 1:
                        pressed_at = time.monotonic()
                    elif value == 0 and pressed_at is not None:
                        now = time.monotonic()
                        if now - pressed_at < 1 and now - last_power > 0.35 and active():
                            last_power = now
                            toggle()
                        pressed_at = None
                elif controller.blank and active() and ((kind == 1 and value == 1) or (kind == 2 and value)):
                    wake()
        except BlockingIOError:
            pass
        except Exception as error:
            print(f'Input handling error: {error}', file=sys.stderr, flush=True)
            try:
                wake()
            except Exception:
                loop.quit()
        return True

    def remove_device(fd):
        nonlocal touch_fd
        if fd == touch_fd:
            wake()
            touch_fd = None
        if fd in devices:
            devices.pop(fd)
            os.close(fd)

    def scan_devices(*unused):
        nonlocal touch_fd
        known = set(devices.values())
        for name in Path('/dev/input').glob('event*'):
            if name in known:
                continue
            fd = None
            try:
                label = (Path('/sys/class/input') / name.name / 'device/name').read_text().strip()
                fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
                if label == TOUCH_NAME:
                    if touch_fd is not None:
                        os.close(fd)
                        continue
                    keys = bytearray(96)
                    fcntl.ioctl(fd, 0x80004518 | (len(keys) << 16), keys, True)
                    contact.button = bool(keys[330 // 8] & (1 << (330 % 8)))
                    touch_fd = fd
                devices[fd] = name
                GLib.io_add_watch(fd, GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, input_ready)
            except (OSError, ValueError):
                if fd is not None:
                    os.close(fd)
                continue
        return False

    class Service(dbus.service.Object):
        @dbus.service.method(NAME, in_signature='', out_signature='')
        def Off(self):
            off()

        @dbus.service.method(NAME, in_signature='', out_signature='')
        def On(self):
            wake()

        @dbus.service.method(NAME, in_signature='', out_signature='')
        def Toggle(self):
            toggle()

        @dbus.service.method(NAME, in_signature='', out_signature='s')
        def Status(self):
            return json.dumps({'blank': controller.blank, 'touch_available': touch_fd is not None,
                               'touch_grabbed': controller.grabbed, 'active_session': active()})

    def prepare_sleep(preparing):
        # Let real suspend use the existing kernel/radio/sensor policy.
        wake()

    def session_changed(interface, changed, invalid):
        if interface == 'org.freedesktop.login1.Session' and not changed.get('Active', True):
            wake()

    system.add_signal_receiver(prepare_sleep, signal_name='PrepareForSleep',
                               dbus_interface='org.freedesktop.login1.Manager')
    system.add_signal_receiver(session_changed, signal_name='PropertiesChanged',
                               dbus_interface='org.freedesktop.DBus.Properties', path=str(session_path))
    scan_devices()
    if touch_fd is None:
        raise RuntimeError('Cannot open the Y700 touchscreen')
    monitor = Gio.File.new_for_path('/dev/input').monitor_directory(Gio.FileMonitorFlags.NONE, None)
    monitor.connect('changed', lambda *unused: GLib.idle_add(scan_devices))
    # Keep logind's fallback power action from racing the desktop handler.
    inhibitor = manager.Inhibit('handle-power-key', 'Y700 tap-to-wake',
                                'Short power press toggles the backlight', 'block').take()
    bus_name = dbus.service.BusName(NAME, bus=session, do_not_queue=True)
    service = Service(bus_name, OBJECT)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: (loop.quit(), False)[1])
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: (loop.quit(), False)[1])
    print('Ready: short Power blanks the backlight; one tap restores it', flush=True)
    try:
        loop.run()
    finally:
        wake()
        if inhibitor is not None:
            os.close(inhibitor)
        for fd in list(devices):
            os.close(fd)
        monitor.cancel()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['daemon', 'off', 'on', 'toggle', 'status', 'restore-saved'])
    action = parser.parse_args().action
    if action == 'restore-saved':
        restore_saved()
    elif action == 'daemon':
        daemon()
    else:
        import dbus
        bus = dbus.SessionBus()
        interface = dbus.Interface(bus.get_object(NAME, OBJECT), NAME)
        result = getattr(interface, action.capitalize())()
        if result is not None:
            print(result)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
