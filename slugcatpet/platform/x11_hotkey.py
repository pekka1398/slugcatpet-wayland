"""X11 全局热键：独立线程 XGrabKey 抓根窗口按键，命中时发 Qt 信号。

原本 control/hotkey.py 那套只做了 Windows（RegisterHotKey），Linux 从没接上。
这里直接拿 python-xlib 抓根窗口的按键事件，不需要桌面环境有额外的全局热键
框架支持。默认 Ctrl+Alt+P，同时处理 NumLock/CapsLock 附加态（否则开着
NumLock 时热键会失灵）。
"""
from __future__ import annotations
from PySide6.QtCore import QThread, Signal


class X11HotkeyThread(QThread):
    triggered = Signal()

    def __init__(self, keysym_name: str = "p", mods=("control", "mod1"), parent=None):
        super().__init__(parent)
        self._keysym_name = keysym_name
        self._mod_names = mods
        self._stop = False
        self._display = None

    def stop(self):
        self._stop = True
        try:
            if self._display is not None:
                self._display.close()
        except Exception:
            pass

    def run(self):
        try:
            from Xlib import X, display, XK
        except Exception:
            return
        mod_map = {"control": X.ControlMask, "mod1": X.Mod1Mask,   # Alt
                   "shift": X.ShiftMask, "mod4": X.Mod4Mask}        # Super
        base_mod = 0
        for name in self._mod_names:
            base_mod |= mod_map.get(name, 0)

        try:
            d = display.Display()
        except Exception:
            return
        self._display = d
        try:
            root = d.screen().root
            keysym = XK.string_to_keysym(self._keysym_name)
            keycode = d.keysym_to_keycode(keysym)
            if not keycode:
                return
            lock_masks = (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask)
            for lm in lock_masks:
                try:
                    root.grab_key(keycode, base_mod | lm, True, X.GrabModeAsync, X.GrabModeAsync)
                except Exception:
                    pass
            d.sync()
            while not self._stop:
                ev = d.next_event()
                if self._stop:
                    break
                if ev.type == X.KeyPress:
                    self.triggered.emit()
        except Exception:
            pass
        finally:
            try:
                for lm in lock_masks:
                    root.ungrab_key(keycode, base_mod | lm, root)
            except Exception:
                pass
            try:
                d.close()
            except Exception:
                pass
