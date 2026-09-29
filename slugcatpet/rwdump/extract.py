# -*- coding: utf-8 -*-
"""RainWorldExtractor v2 指挥 —— 把正版安装 + 反编译源码串成资料库。

    python -m slugcatpet.rwdump.extract [--install DIR] [--decomp DIR] [--out DIR]
                                        [--graphics-only] [--no-images] [--show]

四个阶段，各自落盘（不堆在内存里）：

1. `assets/`   Texture2D / Sprite / TextAsset / Material / Shader / MonoBehaviour / MonoScript
2. `atlases/` + `sprites/`   四张图集的帧表与逐帧几何（frame/pivot/bounds/anchor）
3. `creatures/` + `logic/`   反编译源码里「精灵图 + 写入语句」
4. `rigs/` + `animations/` + `layers.json`   逻辑骨架、帧族、层序
5. `reports/`  缺件清单、可查询索引、精灵/骨架预览图

`manifest.json` 记工具版本、输入指纹（sha1）、各阶段计数与警告。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .. import _paths
from . import assets as A
from . import code as C
from . import report as RP
from . import rig as R
from . import shelter as SH

TOOL = "RainWorldExtractor"
VERSION = "2.0"


def _json(path: Path, obj) -> None:
    A._write_json(path, obj)


def _stage(manifest: dict, name: str, **kv) -> None:
    manifest["stages"][name] = kv


def _atlas_src(out: Path, install, warnings: list, log):
    """图集源目录：资料库自带 > 用户已导入的 assets > 从正版现导一份。"""
    for cand in (out / "atlas_src", _paths.assets_dir()):
        if A.atlas_src_present(cand):
            return cand
    dest = out / "atlas_src"
    try:
        from ..gameassets import extract_atlases
        extract_atlases(install, dest)
        log("  从正版导出图集 → %s" % dest)
        return dest
    except Exception as e:
        warnings.append("图集导出失败：%r" % (e,))
        return out / "atlas_src"


ALL_STAGES = ("assets", "sprites", "code", "rigs", "shelters")


def extract(install=None, out=None, decomp=None, graphics_only: bool = False,
            images: bool = True, log=print, stages=None) -> dict:
    warnings: list = []
    want = set(ALL_STAGES if stages is None else stages)
    if graphics_only:
        want -= {"code", "rigs"}
    out = Path(out or _paths.dump_dir())
    out.mkdir(parents=True, exist_ok=True)
    if decomp is None:
        decomp = _paths.decomp_dir()
    install = Path(install) if install else None

    manifest = {
        "tool": TOOL, "version": VERSION,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "out": str(out),
        "install": str(install) if install else None,
        "decomp": str(decomp) if decomp else None,
        "stages": {},
        "warnings": warnings,
    }

    # ── 1/2：资源层 + 图集层 ─────────────────────────────────────────
    atlas_db: dict = {}
    sprite_index: dict = {}
    if install and (install / "RainWorld_Data" / "resources.assets").exists() and want & {"assets", "sprites"}:
        log("扫资源 …")
        info = A.scan_assets(install, out / "assets", warnings)
        _stage(manifest, "assets", counts=info["counts"], files=info["files"],
               produced=info["produced"])
        log("读图集 …")
        src = _atlas_src(out, install, warnings, log)
        unity_sprites = {}
        for rec in (json.loads((out / "assets" / "sprites.json").read_text(encoding="utf-8"))
                    ["objects"] if (out / "assets" / "sprites.json").exists() else []):
            if rec.get("name") in A.ATLAS_NAMES:
                unity_sprites[rec["name"]] = rec
        atlas_db = A.build_atlas_db(src, unity_sprites, out, warnings)
        sprite_index = json.loads((out / "sprites" / "index.json").read_text(encoding="utf-8"))["sprites"]
        _stage(manifest, "atlases",
               frames={k: v["frame_count"] for k, v in atlas_db.items()},
               sprites=len(sprite_index))
        log("  图集 %s 帧；精灵索引 %d 条"
            % ({k: v["frame_count"] for k, v in atlas_db.items()}, len(sprite_index)))
    elif want & {"assets", "sprites"}:
        warnings.append("没给 --install（或目录不对），跳过资源层/图集层")
        log("跳过资源层（没给 --install）")

    lookup = (lambda e: e in sprite_index) if sprite_index else None

    # ── 3：逻辑层 / 生物层 ───────────────────────────────────────────
    classes: dict = {}
    refs: list = []
    if decomp and "code" in want:
        log("扫反编译源码 %s …" % decomp)
        classes, refs = C.scan_decomp(Path(decomp), warnings, lookup)
        creatures = R.build_creatures(classes)
        for rec in creatures:
            _json(out / "creatures" / (rec["class"] + ".json"), rec)
        _json(out / "creatures" / "index.json",
              {"count": len(creatures),
               "creatures": [{"class": c["class"], "file": c["file"],
                              "sprite_count": c["sprite_count"],
                              "total_sprites": c["total_sprites"]} for c in creatures]})
        logic = R.build_logic(Path(decomp), warnings)
        for rec in logic:
            _json(out / "logic" / (rec["class"] + ".json"), rec)
        _json(out / "logic" / "refs.json",
              {"count": len(refs), "references": refs})
        _stage(manifest, "logic", classes=len(classes), references=len(refs),
               creatures=len(creatures), logic_files=len(logic))
        log("  生物 %d 只；代码引用 %d 条" % (len(classes), len(refs)))
    elif "code" in want:
        if not decomp:
            warnings.append("没给 --decomp（且没找到反编译源码），跳过逻辑层/骨架层")
        log("跳过逻辑层")

    # ── 4：骨架 / 帧族 / 层序 ────────────────────────────────────────
    if decomp and "rigs" in want:
        log("抽骨架 / 层序 …")
        _json(out / "layers.json", R.extract_layers(Path(decomp), warnings))
        rig = R.extract_player_rig(Path(decomp), classes, warnings)
        rig["anchors"] = R.sprite_anchors(classes)
        _json(out / "rigs" / "player.json", rig)
        _json(out / "rigs" / "index.json",
              {"rigs": [{"class": rig["class"],
                         "body_chunks": len(rig.get("body_chunks", [])),
                         "tail_branches": len(rig.get("tail_branches", [])),
                         "sprites": len(rig.get("sprites", []))}]})
        _stage(manifest, "rigs", body_chunks=len(rig.get("body_chunks", [])),
               tail_branches=len(rig.get("tail_branches", [])),
               sprite_index=len(rig.get("sprite_index", {})))

    # ── 4b：庇护所几何 / 门机构 / 层序 ─────────────────────────────
    if "shelters" in want:
        log("抽庇护所几何 …")
        try:
            summ = SH.build(install, decomp, out, warnings, log)
            _stage(manifest, "shelters", **summ)
        except Exception as e:
            warnings.append("庇护所提取失败：%r" % (e,))
            log("  庇护所提取失败：%r" % (e,))

    families: list = []
    if atlas_db:
        families = R.frame_families(atlas_db)
        for fam in families:
            _json(out / "animations" / (fam["prefix"] + ".json"), fam)
        _json(out / "animations" / "cached_names.json",
              R.cached_frame_families(Path(decomp), sprite_index, warnings)
              if decomp and "rigs" in want else {"declarations": []})
        _json(out / "animations" / "index.json",
              {"count": len(families),
               "families": [{"prefix": f["prefix"], "atlas": f["atlas"], "role": f["role"],
                             "count": f["count"], "ticks_per_frame": f["ticks_per_frame"],
                             "loop": f["loop"], "condition": f["condition"]}
                            for f in families]})
        _stage(manifest, "animations", families=len(families))

    # ── 5：报告 ─────────────────────────────────────────────────────
    if sprite_index and refs:
        unresolved = RP.resolve_unresolved(sprite_index, refs)
        _json(out / "reports" / "unresolved.json", unresolved)
        _stage(manifest, "unresolved", **unresolved["counts"])
        log("  缺件 %d（其中 %d 条是占位图）"
            % (unresolved["counts"]["missing"], unresolved["counts"]["benign_missing"]))
    elif refs:
        warnings.append("没有图集索引，缺件对拍跳过（先跑一遍 --extract-sprites）")
    if sprite_index:
        RP.write_sprite_index_html(out / "reports" / "sprite_index.html",
                                   sprite_index, families)
    if images and atlas_db:
        log("画预览图 …")
        rp = out / "reports"
        ok = RP.animation_sheet(rp / "animation_sheet.png", atlas_db,
                                _paths.assets_dir(), families)
        layout = _paths.resource_dir() / "layouts" / "survivor.json"
        ok2 = RP.rig_preview(rp / "rig_preview.png", _paths.assets_dir(),
                             atlas_db, layout, R.sprite_anchors(classes))
        _stage(manifest, "images", animation_sheet=bool(ok), rig_preview=bool(ok2))

    manifest["warning_count"] = len(warnings)
    _json(out / "manifest.json", manifest)
    log("完成 → %s" % out)
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m slugcatpet.rwdump.extract",
                                 description="RainWorldExtractor v2")
    ap.add_argument("--install", help="Rain World 游戏根目录（默认自动定位）")
    ap.add_argument("--decomp", help="反编译源码目录（默认 RW_DECOMP / work/scratch/decomp_full）")
    ap.add_argument("--out", help="输出目录（默认 ~/.slugcatpet/rainworld_dump）")
    ap.add_argument("--graphics-only", action="store_true",
                    help="只做资源/图集，不扫反编译源码")
    ap.add_argument("--extract-assets", action="store_true", help="只做资源层")
    ap.add_argument("--extract-sprites", action="store_true", help="只做图集/精灵层")
    ap.add_argument("--extract-rigs", action="store_true", help="只做骨架/层序/帧族")
    ap.add_argument("--extract-code", action="store_true", help="只做逻辑/生物层")
    ap.add_argument("--extract-shelters", action="store_true", help="只做庇护所几何/门机构")
    ap.add_argument("--no-images", action="store_true", help="不生成 PNG 预览")
    ap.add_argument("--show", action="store_true", help="只打印已生成资料库的摘要")
    args = ap.parse_args(list(argv) if argv is not None else None)

    out = Path(args.out or _paths.dump_dir())
    if args.show:
        mf = out / "manifest.json"
        if not mf.exists():
            print("还没有资料库：%s" % out)
            return 1
        print(mf.read_text(encoding="utf-8"))
        return 0

    install = args.install
    if not install:
        try:
            from ..gameassets import detect_install
            install = detect_install()
        except Exception:
            install = None
    picked = {name for name, on in (("assets", args.extract_assets),
                                    ("sprites", args.extract_sprites),
                                    ("rigs", args.extract_rigs),
                                    ("code", args.extract_code),
                                    ("shelters", args.extract_shelters)) if on}
    extract(install=install, out=out, decomp=args.decomp,
            graphics_only=args.graphics_only, images=not args.no_images,
            stages=picked or None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())