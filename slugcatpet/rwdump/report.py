# -*- coding: utf-8 -*-
"""报告层：缺件清单 + 可查询索引 + 精灵/骨架预览图。

* `reports/unresolved.json` —— 代码引用了但图集里没有的元件（`missing_sprite`），
  以及图集里有、却没任何代码引用的元件（`unused_sprite`）。前者是硬缺件。
* `reports/sprite_index.html` —— 一张可直接搜的精灵表（名字/图集/尺寸/pivot/帧族）。
* `reports/animation_sheet.png` —— 语义帧族总览，每个族一行。
* `reports/rig_preview.png` —— 用真实锚点把逻辑部件摆成一只蛞蝓猫（骨架自检）。
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

# 本作图表集 key → 游戏图集名（rendering/atlas.py:AtlasSet.KEYS）
ATLAS_KEY = {"base": "rainWorld", "msc": "rainworldmsc",
             "ui": "uiSprites", "uimsc": "uispritesmsc"}

# 正常缺件：程序化网格 / 引擎内置 / 只在调试里用的占位图，不算问题
BENIGN = ("pixel", "Futile_White", "LevelTexture", "Debug")


def _benign(name: str) -> bool:
    return name.startswith(BENIGN) or name.startswith("Debug")


def resolve_unresolved(sprite_index: dict, refs: list) -> dict:
    """代码 refs 与图集索引对拍。"""
    known = set(sprite_index)
    referenced = {}
    for r in refs:
        referenced.setdefault(r["element"], []).append(
            {"kind": r["kind"], "file": r["file"], "line": r["line"], "class": r["class"]})
    missing, benign, dynamic = [], [], []
    for name in sorted(referenced):
        if name in known:
            continue
        rows = referenced[name]
        kinds = {r["kind"] for r in rows}
        row = {"element": name, "referenced_by": rows[:8],
               "ref_count": len(rows),
               "severity": "low" if _benign(name) else "high"}
        if any(k.endswith("_prefix") for k in kinds):
            row["kinds"] = sorted(kinds)
            dynamic.append(row)          # "LizardArm" + graphic：运行时才成整名
        elif _benign(name):
            benign.append(row)
        else:
            missing.append(row)
    families = {}
    for name in sorted(known):
        import re
        fam = re.sub(r"\d+$", "", name)
        families.setdefault(fam, 0)
        families[fam] += 1
    return {
        "missing_sprite": missing,
        "benign_missing": benign,
        "dynamic_prefix": dynamic,
        "counts": {"referenced": len(referenced), "atlas_frames": len(known),
                   "missing": len(missing), "benign_missing": len(benign),
                   "dynamic_prefix": len(dynamic)},
        "note": "missing_sprite = 代码引用了但四张图集里找不到的元件（硬缺件）；"
                "benign_missing = 程序化网格/引擎内置占位（pixel、Futile_White…）；"
                "dynamic_prefix = `\"LizardArm\" + graphic` 这类运行时拼接的前缀，"
                "逐帧名要展开后才有意义。",
    }


def write_sprite_index_html(path: Path, sprite_index: dict, families: list) -> None:
    rows = []
    fam_of = {}
    for f in families:
        for n in f["frames"]:
            fam_of[n] = f["prefix"]
    for name in sorted(sprite_index):
        r = sprite_index[name]
        rows.append(
            "<tr><td class='n'>%s</td><td>%s</td><td>%s</td><td>%sx%s</td>"
            "<td>%s,%s</td><td>%.2f,%.2f</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (html.escape(name), r["atlas"], r["texture"],
               r["source_size"][0], r["source_size"][1],
               r["frame"][2], r["frame"][3],
               r["pivot"][0], r["pivot"][1],
               "是" if r["rotated"] else "", "是" if r["trimmed"] else "",
               html.escape(fam_of.get(name, ""))))
    doc = """<!doctype html><html lang="zh"><meta charset="utf-8">
<title>Rain World 精灵索引</title>
<style>
body{font:13px/1.5 -apple-system,'Segoe UI',sans-serif;margin:16px;background:#14161a;color:#dfe3ea}
h1{font-size:16px}input{background:#22262d;color:#dfe3ea;border:1px solid #3a4048;padding:6px 8px;width:280px}
table{border-collapse:collapse;margin-top:10px;width:100%}
th,td{border-bottom:1px solid #262b33;padding:3px 8px;text-align:left;white-space:nowrap}
th{position:sticky;top:0;background:#1b1f25;cursor:pointer}
td.n{font-family:ui-monospace,Consolas,monospace;color:#9fd0ff}
tr:hover{background:#1e232a}
</style>
<h1>Rain World 精灵索引 · @@COUNT@@ 帧</h1>
<input id=q placeholder="筛选：名字 / 图集 / 帧族" oninput="flt()">
<table id=t><thead><tr><th>名字</th><th>图集</th><th>贴图</th><th>原始尺寸</th>
<th>帧尺寸</th><th>pivot</th><th>旋转</th><th>裁剪</th><th>帧族</th></tr></thead>
<tbody>@@ROWS@@</tbody></table>
<script>
function flt(){var v=document.getElementById('q').value.toLowerCase();
var rs=document.querySelectorAll('#t tbody tr');
for(var i=0;i<rs.length;i++){rs[i].style.display=rs[i].innerText.toLowerCase().indexOf(v)<0?'none':'';}}
</script></html>"""
    doc = doc.replace("@@COUNT@@", str(len(sprite_index)))
    doc = doc.replace("@@ROWS@@", "\n".join(rows))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8", newline="\n")


def rig_anchor(anchors: dict, frame: str) -> dict:
    """帧 → 锚点；同族回退到 `Xxx0`（PlayerArm5 → PlayerArm0）。"""
    if frame in anchors:
        return anchors[frame]
    return anchors.get(re.sub(r"\d+$", "", frame) + "0") or {}


def _open_atlas(assets_dir: Path, atlas_name: str):
    from PIL import Image
    p = Path(assets_dir) / (atlas_name + ".png")
    return Image.open(p).convert("RGBA") if p.exists() else None


def _crop(img, rec):
    """按 TexturePacker 语义裁一帧，还原旋转与裁剪（口径同 rendering/atlas.py）。"""
    x, y, w, h = rec["frame"]
    from PIL import Image
    sub = img.crop((x, y, x + w, y + h))
    if rec["rotated"]:
        sub = sub.transpose(Image.Transpose.ROTATE_270)     # ≡ Qt rotate(-90)
    if rec["trimmed"]:
        sw, sh = rec["source_size"]
        rx, ry, _rw, _rh = rec["source_rect"]
        canvas = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        canvas.paste(sub, (rx, ry))
        sub = canvas
    return sub


def animation_sheet(path: Path, atlas_db: dict, assets_dir: Path,
                    families: list, max_frames: int = 24) -> bool:
    """语义帧族总览：每个族一行，左边标族名。"""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return False
    picked = [f for f in families if f["role"] != "sprite_sequence"][:26]
    if not picked:
        return False
    imgs = {k: _open_atlas(assets_dir, k) for k in atlas_db}
    scale = 2
    cell = 56 * scale
    rows = []
    for fam in picked:
        row = []
        for name in fam["frames"][:max_frames]:
            rec = atlas_db[fam["atlas"]]["frames"][name]
            src = imgs.get(fam["atlas"])
            if src is None:
                continue
            sub = _crop(src, rec).resize(
                (max(1, rec["source_size"][0] * scale), max(1, rec["source_size"][1] * scale)),
                Image.NEAREST)
            row.append(sub)
        rows.append((fam["prefix"], row))
    if not rows:
        return False
    width = 120 + cell * max(1, min(max_frames, max(len(r[1]) for r in rows)))
    height = 22 + len(rows) * (cell + 6)
    sheet = Image.new("RGBA", (width, height), (20, 22, 26, 255))
    d = ImageDraw.Draw(sheet)
    for i, (name, row) in enumerate(rows):
        top = 20 + i * (cell + 6)
        d.text((6, top + cell // 2 - 6), "%s x%d" % (name, len(row)), fill=(200, 210, 225, 255))
        for j, im in enumerate(row):
            sheet.alpha_composite(im, (120 + j * cell + (cell - im.width) // 2,
                                       top + (cell - im.height) // 2))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    return True


def rig_preview(path: Path, assets_dir: Path, atlas_db: dict,
                layout_path: Path | None, anchors: dict | None = None) -> bool:
    """把布局里的逻辑部件按真实锚点摆出来，用来肉眼核对骨架。"""
    try:
        from PIL import Image
    except Exception:
        return False
    if layout_path is None or not Path(layout_path).exists():
        return False
    doc = json.loads(Path(layout_path).read_text(encoding="utf-8"))
    scale = int(doc.get("canvas_scale") or 2)
    W = int(doc.get("canvas_w") or 56) * scale
    H = int(doc.get("canvas_h") or 70) * scale
    canvas = Image.new("RGBA", (W, H), (22, 24, 28, 255))
    imgs = {k: _open_atlas(assets_dir, k) for k in atlas_db}
    for part in doc.get("parts", []):
        if not part.get("visible", True):
            continue
        atlas_name = ATLAS_KEY.get(part.get("atlas"), part.get("atlas"))
        db = atlas_db.get(atlas_name)
        if db is None:
            continue
        rec = db["frames"].get(part["frame"])
        src = imgs.get(atlas_name)
        if rec is None or src is None:
            continue
        sub = _crop(src, rec)
        if part.get("mirror"):
            sub = sub.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if part.get("angle"):
            sub = sub.rotate(-float(part["angle"]), expand=True, resample=Image.BICUBIC)
        s = float(part.get("scale") or 1.0) * scale
        if s != 1.0:
            sub = sub.resize((max(1, int(sub.width * s)), max(1, int(sub.height * s))),
                             Image.NEAREST)
        ax = rec["anchor"]["x"]
        ay = rec["anchor"]["qt_ay"]
        info = rig_anchor(anchors or {}, part["frame"])
        if info.get("ax") is not None:
            ax = float(info["ax"])
        if info.get("qt_ay") is not None:
            ay = float(info["qt_ay"])
        if part.get("anchor"):                     # 布局里的手调锚点优先
            ax = float(part["anchor"][0])
            ay = float(part["anchor"][1])
        px = int(float(part["x"]) * scale - sub.width * ax)
        py = int(float(part["y"]) * scale - sub.height * ay)
        canvas.alpha_composite(sub, (px, py))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)
    return True