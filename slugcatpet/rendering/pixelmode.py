"""像素模式开关：整体按 1:1 逻辑像素渲染后再按整数倍最近邻放大，还原原版像素观感。

Rain World 本体是硬边像素画：精灵按原生像素贴出、没有任何抗锯齿。
桌宠原本直接把矢量路径（躯干/绳带/网格）画到设备像素上，边缘是抗锯齿的灰阶，
放大后看起来是「矢量图」而不是「像素画」。像素模式下所有绘制关闭抗锯齿，
先在 WL×HL 的低分辨率缓冲里 1:1 画完，再整数倍放大 —— 与本体观感一致。
"""
from __future__ import annotations

from PySide6.QtGui import QPainter

PIXEL = False


def aa_hint(p: QPainter, on: bool = True) -> None:
    """按像素模式设置抗锯齿；像素模式下恒关。"""
    p.setRenderHint(QPainter.RenderHint.Antialiasing, bool(on) and not PIXEL)


def pen_width(w: float) -> float:
    """描边宽度：像素模式下 <1px 的宽度只会画出 alpha≈w 的半透明像素（锯齿发虚）。

    原版没有半透明描边，细描边在低分辨率缓冲里会留下 50% 透明度的「毛边」，
    放大后就是用户看到的半透明锯齿。像素模式下抬到 1px，得到干净硬边。
    """
    if PIXEL and w < 1.0:
        return 1.0
    return float(w)
