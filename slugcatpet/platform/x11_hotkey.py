"""X11 全局热键：独立线程 XGrabKey 抓根窗口按键，命中时发 Qt 信号。

原本 control/hotkey.py 那套只做了 Windows（RegisterHotKey），Linux 从没接上。
这里直接拿 python-xlib 抓根窗口的按键事件，不需要桌面环境有额外的全局热键
框架支持。默认 Ctrl+Alt+P，同时处理 NumLock/CapsLock 附加态（否则开着
NumLock 时热键会失灵）。
"""
from __future__ import annotations
import select

from PySide6.QtCore import QThread, Signal


class X11HotkeyThread(QThread):
    triggered = Signal()
    POLL_TIMEOUT = 0.2      # 秒；退出延迟上限，也是空转频率

    def __init__(self, keysym_name: str = "p", mods=("control", "mod1"), parent=None):
        super().__init__(parent)
        self._keysym_name = keysym_name
        self._mod_names = mods
        self._stop = False
        self._display = None

    def stop(self):
        """只置停止标志：连接由 run() 自己收尾。

        别在这里 close()——Xlib 的 Display 不是线程安全的，主线程关连接既不能
        叫醒阻塞在 next_event() 的本线程，还会跟它抢同一个 socket。轮询循环
        最多 POLL_TIMEOUT 秒就回来看一次标志，wait() 因此总能等到。
        """
        self._stop = True

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
            fd = d.fileno()
            while not self._stop:
                # select 等连接可读，超时回来查停止标志；next_event() 直接堵着
                # 的话退出时叫不醒，QThread.wait() 必然超时报「线程仍在运行」
                try:
                    readable, _, _ = select.select([fd], [], [], self.POLL_TIMEOUT)
                except (OSError, ValueError):
                    break
                if self._stop:
                    break
                if not readable:
                    continue
                for _ in range(d.pending_events()):
                    ev = d.next_event()
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
