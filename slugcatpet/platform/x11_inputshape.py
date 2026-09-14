"""X11 XShape 输入透传：只裁剪鼠标命中区（ShapeInput），不碰可视形状（ShapeBounding）。

Qt 的 QWidget.setMask() 会同时裁掉可视渲染和输入区，在原生显示的窗口上会把
超出遮罩框的部件（尾巴/舌头/甩出的残影）直接切掉。这里绕开 Qt，直接用 XShape
的 Input 通道，保持整窗可视不变，只限制点击命中范围。
"""
from __future__ import annotations

_display = None


def _get_display():
    global _display
    if _display is None:
        from Xlib import display
        _display = display.Display()
    return _display


def _window(winid: int):
    return _get_display().create_resource_object("window", winid)


def set_input_rects(winid: int, rects) -> None:
    """把可点击区限制为给定矩形并集；rects 为空则给 1x1 占位（近似全穿透）。"""
    try:
        from Xlib import X
        from Xlib.ext import shape
        win = _window(winid)
        rs = [(int(x), int(y), max(1, int(w)), max(1, int(h))) for x, y, w, h in rects] or [(0, 0, 1, 1)]
        win.shape_rectangles(shape.SO.Set, shape.SK.Input, X.Unsorted, 0, 0, rs)
        _get_display().flush()
    except Exception:
        pass


def clear_input_shape(winid: int, width: int, height: int) -> None:
    """恢复整窗可点击（清除 Input 裁剪）。"""
    set_input_rects(winid, [(0, 0, max(1, int(width)), max(1, int(height)))])
