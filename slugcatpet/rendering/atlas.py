"""图集加载与裁切，支持 tint 着色。"""
from __future__ import annotations
import json
from collections import OrderedDict
from pathlib import Path
from PySide6.QtGui import QImage, QPixmap, QColor, QPainter
from .._paths import assets_dir, bundled_assets_dir


class AtlasAssetsMissing(RuntimeError):
    """图集素材缺失：需先从用户自己的正版 Rain World 安装导入。"""


def resolve_assets_dir() -> Path:
    """优先用户导入目录，回落仓库内 dev 目录，都没有则报错。"""
    for d in (assets_dir(), bundled_assets_dir()):
        if (d / "rainWorld.png").exists():
            return d
    raise AtlasAssetsMissing(
        "未找到 Rain World 图集素材。需先从你自己的正版游戏一次性导入：\n"
        "  python -m slugcatpet.gameassets\n"
        f"它会把 rainWorld / rainworldmsc 图集提取到 {assets_dir()}。\n"
        "注意：Saint 来自 Downpour(More Slugcats) DLC，需拥有该 DLC。"
    )


class Atlas:
    _CACHE_CAP = 512   # LRU 上限

    def __init__(self, name: str, base: Path):
        """name 不带扩展名，如 'rainWorld'。base 目录下需有 name(映射) + name.png(图)。"""
        self.image = QImage(str(base / f"{name}.png"))
        if self.image.isNull():
            raise FileNotFoundError(f"atlas image not found: {name}.png")
        with open(base / name, "r", encoding="utf-8") as f:
            self.frames = json.load(f)["frames"]
        # 帧表是只读的，把每帧要用的字段一次性摊平：sprite()/source_size() 在
        # 绘制热路径上（每帧上百次），省掉逐次翻 dict 取嵌套字段。
        # 元组序：(x, y, w, h, srcW, srcH, rotated, trimmed, spriteSourceSize)
        meta = {}
        for fname, e in self.frames.items():
            fr = e["frame"]
            ss = e.get("sourceSize", fr)
            meta[fname] = (fr["x"], fr["y"], fr["w"], fr["h"],
                           ss["w"], ss["h"],
                           bool(e.get("rotated")), bool(e.get("trimmed")),
                           e.get("spriteSourceSize"))
        self._meta = meta
        self._cache: "OrderedDict[tuple, QPixmap]" = OrderedDict()

    def has(self, frame_name: str) -> bool:
        return self._key(frame_name) in self.frames

    @staticmethod
    def _key(frame_name: str) -> str:
        return frame_name if frame_name.endswith(".png") else frame_name + ".png"

    def sprite(self, frame_name: str, tint: QColor | None = None,
               padded: bool = True) -> QPixmap:
        """裁出某帧，tint 正片叠底着色；padded=True 还原原始画布。"""
        ck = (frame_name, tint.rgba() if tint else None, padded)
        if ck in self._cache:
            self._cache.move_to_end(ck)
            return self._cache[ck]
        m = self._meta[self._key(frame_name)]
        sub = self.image.copy(m[0], m[1], m[2], m[3])
        if m[6]:
            from PySide6.QtGui import QTransform
            sub = sub.transformed(QTransform().rotate(-90))
        if tint is not None:
            sub = self._apply_tint(sub, tint)
        if padded and m[7]:
            ss_w, ss_h = m[4], m[5]
            off = m[8]
            canvas = QImage(ss_w, ss_h, QImage.Format.Format_ARGB32_Premultiplied)
            canvas.fill(QColor(0, 0, 0, 0))
            p = QPainter(canvas)
            p.drawImage(off["x"], off["y"], sub)
            p.end()
            sub = canvas
        pm = QPixmap.fromImage(sub)
        self._cache[ck] = pm
        if len(self._cache) > self._CACHE_CAP:   # 超限淘汰最久未用
            self._cache.popitem(last=False)
        return pm

    def replace_image(self, image: QImage) -> None:
        """把底层贴图换成预处理过的版本（帧缓存随之作废）。"""
        self.image = image
        self._cache.clear()

    def source_size(self, frame_name: str) -> tuple[int, int]:
        """原始画布尺寸 = 注册坐标系大小。"""
        m = self._meta[self._key(frame_name)]
        return m[4], m[5]

    @staticmethod
    def _apply_tint(img: QImage, color: QColor) -> QImage:
        """正片叠底染色。"""
        out = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        p = QPainter(out)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        p.fillRect(out.rect(), color)
        p.end()
        # Multiply 会吃掉透明区，需重新遮罩
        mask = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        p2 = QPainter(out)
        p2.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p2.drawImage(0, 0, mask)
        p2.end()
        return out

    def frame_names(self) -> list[str]:
        return sorted(n[:-4] if n.endswith(".png") else n for n in self.frames)


class AtlasSet:
    """统一管理多张图集，按 key 取图，并能反查帧在哪张图里。"""

    KEYS = {"base": "rainWorld", "msc": "rainworldmsc",
            "ui": "uiSprites", "uimsc": "uispritesmsc",
            # 庇护所大门（ShelterDoor.InitiateSprites 的 42 张 ShelterGate_*）。
            # 旧素材包没有这一张 —— 缺了直接跳过，渲染回落到程序化门板。
            "gate": "shelterGate"}

    def __init__(self, base: Path | None = None):
        base = base or resolve_assets_dir()
        self.atlases = {}
        for k, name in self.KEYS.items():
            try:
                self.atlases[k] = Atlas(name, base)
            except (FileNotFoundError, OSError, ValueError, KeyError):
                continue      # 可选图集缺失：不阻塞启动
        # 帧表只读，查询缓存永不失效
        self._where: dict[str, str | None] = {}
        self._ssize: dict[tuple[str, str], tuple[int, int]] = {}

    def get(self, key: str) -> Atlas:
        return self.atlases[key]

    def sprite(self, key: str, frame: str, tint: QColor | None = None,
               padded: bool = True) -> QPixmap:
        return self.atlases[key].sprite(frame, tint, padded)

    def source_size(self, key: str, frame: str) -> tuple[int, int]:
        ck = (key, frame)
        v = self._ssize.get(ck)
        if v is None:
            v = self.atlases[key].source_size(frame)
            self._ssize[ck] = v
        return v

    def find_atlas(self, frame: str) -> str | None:
        try:
            return self._where[frame]
        except KeyError:
            pass
        for k, at in self.atlases.items():
            if at.has(frame):
                self._where[frame] = k
                return k
        self._where[frame] = None
        return None
