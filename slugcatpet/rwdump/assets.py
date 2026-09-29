# -*- coding: utf-8 -*-
"""资源层（Asset / Atlas）：UnityPy 扫正版安装，产出可查询的资源与精灵几何数据库。

这一层只回答「游戏里到底有什么」，不猜任何东西：

* `assets/*.json`  —— Texture2D / Sprite / TextAsset / Material / Shader /
  MonoBehaviour / MonoScript 的逐个索引，字段名与 Unity 的 TypeTree 对齐
  （`m_Name` → `name`、`m_Rect` → `rect`…），复查时可直接对照 UnityPy 原始字段。
* `atlases/<atlas>.json` —— 把 `rainWorld` / `rainworldmsc` / `uiSprites` /
  `uispritesmsc` 四张图集的 TexturePacker 映射拍平成帧表，并补上 Unity `Sprite`
  对象里的 `pivot` / `pixels_to_units`。
* `sprites/<Name>.json` + `sprites/index.json` —— 每个精灵一格：atlas、frame、
  source_size、source_rect、rotated、trimmed、pivot、bounds、anchor。
  这是别人问「BodyA 到底多大、锚在哪」时唯一该查的地方。

锚点换算口径与 `docs/DECOMPILE_PROCESS.md` 第 4 节一致：FSprite 的
`_textureRect.y = -anchorY * height`，我们的 `blit` 的 `ay` 从贴图顶边量，故
`ay = 1 - anchorY`；`anchorX` 同向不换算。
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

GAME_FILES = ("resources.assets", "sharedassets0.assets",
              "globalgamemanagers.assets", "level0")

ATLAS_NAMES = ("rainWorld", "rainworldmsc", "uiSprites", "uispritesmsc")
ATLAS_TEXTURE = {"rainWorld": "rainWorld.png", "rainworldmsc": "rainWorldMSC.png",
                 "uiSprites": "uisprites.png", "uispritesmsc": "uiSpritesMSC.png"}

# Unity Sprite 在 Rain World 里就是「整张图集一块」，FSprite 默认锚是 0.5/0.5
FAILSAFE_PIVOT = (0.5, 0.5)


def _sha1(path: Path, limit: int | None = None) -> str:
    h = hashlib.sha1()
    read = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
            read += len(b)
            if limit is not None and read >= limit:
                break
    return h.hexdigest()


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")
    tmp.replace(path)


def _vec(v):
    """UnityPy 的 Vector2f / Rectf → 元组。"""
    if v is None:
        return None
    if isinstance(v, (tuple, list)):
        return [float(x) for x in v]
    for attrs in (("x", "y"), ("x", "y", "width", "height")):
        if all(hasattr(v, a) for a in attrs):
            return [float(getattr(v, a)) for a in attrs]
    return None


def _rect4(r):
    if r is None:
        return None
    try:
        return {"x": float(r.x), "y": float(r.y),
                "w": float(r.width), "h": float(r.height)}
    except Exception:
        return None


# ── Layer 1：扫 assets ───────────────────────────────────────────────

def _scan_one_file(path: Path, index: dict, warnings: list) -> dict:
    """扫单个 Unity 文件，把各类对象追加进 index。返回本文件的对象计数。"""
    import UnityPy
    counts: dict[str, int] = {}
    env = UnityPy.load(str(path))
    for obj in env.objects:
        tname = obj.type.name
        counts[tname] = counts.get(tname, 0) + 1
        bucket = index.setdefault(tname, [])
        rec = {"file": path.name, "path_id": obj.path_id}
        try:
            if tname == "Texture2D":
                d = obj.read()
                rec.update(name=d.m_Name, width=int(d.m_Width), height=int(d.m_Height),
                           format=str(d.m_TextureFormat),
                           mip_count=int(getattr(d, "m_MipCount", 0) or 0),
                           is_readable=bool(getattr(d, "m_IsReadable", False)),
                           image_size=int(getattr(d, "m_CompleteImageSize", 0) or 0),
                           filter_mode=int(getattr(d, "m_FilterMode", 0) or 0),
                           aniso=int(getattr(d, "m_Aniso", 0) or 0))
            elif tname == "Sprite":
                tt = obj.read_typetree()
                rd = tt.get("m_RD", {}) or {}
                tex = rd.get("texture") or {}
                rec.update(name=tt.get("m_Name"),
                           rect=_rect4(tt.get("m_Rect")),
                           offset=_vec(tt.get("m_Offset")),
                           pivot=_vec(tt.get("m_Pivot")),
                           pixels_to_units=float(tt.get("m_PixelsToUnits") or 100.0),
                           extrude=float(tt.get("m_Extrude") or 0.0),
                           border=_vec(tt.get("m_Border")),
                           is_polygon=bool(tt.get("m_IsPolygon")),
                           texture_path_id=int(tex.get("m_PathID", 0) or 0),
                           texture_file_id=int(tex.get("m_FileID", 0) or 0),
                           pixels_per_unit_raw=int(rd.get("settingsRaw", 0) or 0))
            elif tname == "TextAsset":
                d = obj.read()
                raw = getattr(d, "m_Script", None)
                if isinstance(raw, str):
                    raw = raw.encode("utf-8", "surrogateescape")
                raw = raw or b""
                rec.update(name=d.m_Name, bytes=len(raw), sha1=hashlib.sha1(raw).hexdigest())
                try:
                    txt = raw.decode("utf-8-sig", "replace")
                    rec["kind"] = ("texturepacker"
                                   if '"frames"' in txt[:4096] else "text")
                    rec["head"] = txt[:120].replace("\n", " ")
                except Exception:
                    rec["kind"] = "binary"
            elif tname == "MonoScript":
                d = obj.read()
                rec.update(name=d.m_Name,
                           class_name=getattr(d, "m_ClassName", None),
                           namespace=getattr(d, "m_Namespace", None),
                           assembly=getattr(d, "m_AssemblyName", None))
            elif tname == "Material":
                d = obj.read()
                rec.update(name=d.m_Name, shader=str(getattr(d, "m_Shader", None)))
            elif tname == "Shader":
                d = obj.read()
                rec.update(name=getattr(d, "m_Name", None),
                           has_parsed_form=bool(getattr(d, "m_ParsedForm", None)))
            elif tname == "MonoBehaviour":
                d = obj.read()
                rec.update(name=getattr(d, "m_Name", None),
                           script=str(getattr(d, "m_Script", None)))
            else:
                rec.update(name=getattr(obj, "name", None))
        except Exception as e:                      # 单个对象读失败不拖垮整趟
            rec["error"] = repr(e)[:200]
            warnings.append("%s/%s path_id=%s 读取失败：%s"
                            % (path.name, tname, obj.path_id, repr(e)[:120]))
        bucket.append(rec)
    return counts


def scan_assets(install: Path, out: Path, warnings: list) -> dict:
    """扫全部 Unity 数据文件 → assets/*.json。返回计数与来源指纹。"""
    install = Path(install)
    data = install / "RainWorld_Data"
    index: dict[str, list] = {}
    files: list[dict] = []
    counts: dict[str, int] = {}
    for name in GAME_FILES:
        p = data / name
        if not p.exists():
            warnings.append("缺少 %s" % p)
            continue
        got = _scan_one_file(p, index, warnings)
        for k, v in got.items():
            counts[k] = counts.get(k, 0) + v
        files.append({"name": name, "bytes": p.stat().st_size, "sha1": _sha1(p)})

    out.mkdir(parents=True, exist_ok=True)
    produced = []
    for tname, rows in index.items():
        rows.sort(key=lambda r: (r.get("name") or "", r.get("path_id") or 0))
        fn = tname.lower() + "s.json"
        _write_json(out / fn, {"type": tname, "count": len(rows), "objects": rows})
        produced.append(fn)
    return {"counts": counts, "files": files, "produced": produced}


# ── Layer 2：图集 / 精灵几何 ────────────────────────────────────────

def _load_texture_packer(path: Path) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def build_atlas_db(assets_dir: Path, unity_sprites: dict, out: Path,
                   warnings: list) -> dict:
    """四张图集 → atlases/*.json + sprites/<Name>.json + sprites/index.json。

    unity_sprites: {name: Unity Sprite 记录}，用来补 pivot / pixels_to_units。
    返回内存版 {atlas_name: {"frames": {name: 记录}, "meta":…, "texture":…}}。
    """
    assets_dir = Path(assets_dir)
    atlas_out = out / "atlases"
    sprite_out = out / "sprites"
    db: dict[str, dict] = {}
    index: dict[str, dict] = {}
    total = 0
    for name in ATLAS_NAMES:
        map_path = assets_dir / name
        png = assets_dir / ATLAS_TEXTURE[name]
        if not map_path.exists():
            warnings.append("图集映射缺失：%s（先跑一次图集导入）" % map_path)
            continue
        doc = _load_texture_packer(map_path)
        raw_frames = doc.get("frames", {})
        us = unity_sprites.get(name) or {}
        pivot = us.get("pivot") or list(FAILSAFE_PIVOT)
        pivot_source = "unity_sprite" if us.get("pivot") else "failsafe_default"
        tex_size = None
        if png.exists():
            meta_size = (doc.get("meta") or {}).get("size") or {}
            tex_size = [int(meta_size.get("w") or 0), int(meta_size.get("h") or 0)]
        frames = {}
        for fname, e in raw_frames.items():
            key = fname[:-4] if fname.endswith(".png") else fname
            fr = e.get("frame") or {}
            ss = e.get("sourceSize") or fr
            sss = e.get("spriteSourceSize") or {"x": 0, "y": 0,
                                                "w": ss.get("w", 0), "h": ss.get("h", 0)}
            rec = {
                "name": key,
                "atlas": name,
                "texture": ATLAS_TEXTURE[name],
                "frame": [int(fr.get("x", 0)), int(fr.get("y", 0)),
                          int(fr.get("w", 0)), int(fr.get("h", 0))],
                "rotated": bool(e.get("rotated")),
                "trimmed": bool(e.get("trimmed")),
                "source_size": [int(ss.get("w", 0)), int(ss.get("h", 0))],
                "source_rect": [int(sss.get("x", 0)), int(sss.get("y", 0)),
                                int(sss.get("w", 0)), int(sss.get("h", 0))],
                "pivot": list(pivot),
                "anchor": {"x": float(pivot[0]),
                           "unity_anchor_y": float(pivot[1]),
                           "qt_ay": 1.0 - float(pivot[1])},
                "bounds": [0, 0, int(ss.get("w", 0)), int(ss.get("h", 0))],
            }
            frames[key] = rec
        db[name] = {"name": name, "texture": {"file": ATLAS_TEXTURE[name],
                                              "size": tex_size},
                    "meta": doc.get("meta") or {},
                    "sprite_object": us or None,
                    "pivot_source": pivot_source,
                    "frame_count": len(frames),
                    "frames": frames}
        atlas_doc = {k: v for k, v in db[name].items() if k != "frames"}
        atlas_doc["frames"] = [frames[k] for k in sorted(frames)]
        _write_json(atlas_out / (name + ".json"), atlas_doc)
        for k, rec in frames.items():
            index[k] = {"atlas": name, "texture": rec["texture"],
                        "frame": rec["frame"], "source_size": rec["source_size"],
                        "rotated": rec["rotated"], "trimmed": rec["trimmed"],
                        "pivot": rec["pivot"]}
        total += len(frames)
    # 每个精灵一格
    sprite_out.mkdir(parents=True, exist_ok=True)
    for k in sorted(index):
        _write_json(sprite_out / (k + ".json"), db[index[k]["atlas"]]["frames"][k])
    _write_json(sprite_out / "index.json",
                {"count": len(index), "sprites": index})
    return db


def atlas_src_present(d) -> bool:
    """目录里是否已有四张图集的 TexturePacker 映射 + PNG。"""
    from pathlib import Path as _P
    d = _P(d)
    return all((d / n).exists() and (d / ATLAS_TEXTURE[n]).exists() for n in ATLAS_NAMES)


def sprite_owner_of(atlas_db: dict, element: str):
    """element 属于哪张图集（跨图集查询）。"""
    for name, a in atlas_db.items():
        if element in a["frames"]:
            return name
    return None