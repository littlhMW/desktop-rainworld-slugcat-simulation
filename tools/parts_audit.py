# -*- coding: utf-8 -*-
r"""已移植对象「尺寸/位置/图层」审计工具。

做三件事：
  1. 对每个已移植实体，调 tools/parts_table.py 把原版精灵表（层级/元件/尺寸/变换）
     抓成 docs/PARTS_REFERENCE.md —— 之后任何人核对都有机械表可查；
  2. 拿「我们能自动读到的数值」（反编译里的 BodyChunk rad/mass、Limb 参数、TailSegment 等）
     跟「我们代码里的常量」逐条对拍，结果写进 docs/PARTS_AUDIT.md；
  3. 把人工核对过的结论（不一致清单）一并落到文档里。

用法：
    D:\spenv\Scripts\python.exe -X utf8 tools/parts_audit.py            # 生成两份文档
    D:\spenv\Scripts\python.exe -X utf8 tools/parts_audit.py --check     # 只跑对拍，非零退出=有偏差
"""
from __future__ import annotations
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEC = Path(os.environ.get("RW_DECOMP", ROOT.parent / "scratch" / "decomp_full"))
DOCS = ROOT / "docs"

# ── 实体清单：名字 → 原版源码（*Graphics 或物件本体）+ 我们的文件 ──
ENTITIES = [
    ("蜥蜴",        "LizardGraphics",  "slugcatpet/world/lizard_gfx.py"),
    ("禅乌贼",      "CicadaGraphics",  "slugcatpet/world/squidcada_gfx.py"),
    ("拾荒者",      "ScavengerGraphics", "slugcatpet/world/scavenger.py"),
    ("蝠蝇",        "FlyGraphics",     "slugcatpet/world/batfly_gfx.py"),
    ("爆米花",      "SeedCob",         "slugcatpet/world/seedcob.py"),
    ("矛",          "Spear",           "slugcatpet/world/spear.py"),
    ("珍珠",        "DataPearl",       "slugcatpet/world/pearl.py"),
    ("蛞蝓猫(手/尾)", "PlayerGraphics", "slugcatpet/rendering/graphics.py"),
    ("爆炸特效",    "ExplosionLight",  "slugcatpet/world/explosionfx_draw.py"),
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def decomp(name: str) -> str:
    p = DEC / (name if name.endswith(".cs") else name + ".cs")
    return read(p) if p.exists() else ""


# ── 自动对拍规格： (说明, 原版取值函数, 我们文件, 我们常量名) ──
def chunk_n(owner: str, i: int):
    """取原版 new BodyChunk(this, i, ..., rad, mass) 的 (rad, mass)。"""
    src = decomp(owner)
    m = re.search(r"new BodyChunk\([^,]+,\s*%d,\s*new Vector2\([^)]*\),\s*([\d.]+)f,\s*([^)]*)\)" % i, src)
    if not m:
        return None
    rad = float(m.group(1))
    try:
        mass = float(m.group(2).strip().rstrip('f'))
    except ValueError:
        mass = None                      # 质量是算出来的（num / 2f 之类）
    return (rad, mass)


def conn_n(owner: str, i: int):
    """取原版 bodyChunkConnections[i] 的距离。"""
    src = decomp(owner)
    m = re.search(r"bodyChunkConnections\[%d\]\s*=\s*new BodyChunkConnection\([^,]+,\s*[^,]+,\s*([\d.]+)f" % i, src)
    return float(m.group(1)) if m else None


def our_const(rel: str, name: str):
    """读我们文件里的模块级常量（只认数字字面量）。"""
    src = read(ROOT / rel)
    m = re.search(r"^%s\s*=\s*([\d.]+)" % re.escape(name), src, re.M)
    return float(m.group(1)) if m else None


CHECKS = [
    ("矛 chunk0.rad",        lambda: chunk_n("Spear", 0)[0],      "slugcatpet/world/spear.py", "RAD"),
    ("矛 chunk0.mass",       lambda: chunk_n("Spear", 0)[1],      "slugcatpet/world/spear.py", "MASS"),
    ("珍珠 chunk0.rad",      lambda: chunk_n("DataPearl", 0)[0],  "slugcatpet/world/pearl.py", "RAD"),
    ("珍珠 chunk0.mass",     lambda: chunk_n("DataPearl", 0)[1],  "slugcatpet/world/pearl.py", "MASS"),
    ("禅乌贼 chunk0.rad",    lambda: (chunk_n("Cicada", 0) or (None, None))[0],     "slugcatpet/world/squidcada.py", "RAD"),
    ("禅乌贼 两截间距",       lambda: conn_n("Cicada", 0),         "slugcatpet/world/squidcada_gfx.py", "CHUNK_GAP"),
    ("拾荒者 chunk1.rad(髋)", lambda: chunk_n("Scavenger", 1)[0],  "slugcatpet/world/scavenger.py", "BODY_RAD"),
    ("拾荒者 chunk2.rad(头)", lambda: chunk_n("Scavenger", 2)[0],  "slugcatpet/world/scavenger.py", "HEAD_RAD"),
]

# ── 人工核对过的结论（不一致清单的唯一事实源） ──
FINDINGS = [
    ("✅", "矛", "chunk0 rad 5 / mass 0.07（Spear.cs:286）", "同值；杆长 53px 取 SmallSpear 贴图"),
    ("✅", "珍珠", "chunk0 rad 5 / mass 0.07（DataPearl.cs:184）", "同值；bounce 0.4 / surfaceFriction 0.4 同值"),
    ("✅", "禅乌贼", "chunk0 rad 7.5、两截间距 14（Cicada.cs:131）", "同值；触须 ConnectToPoint 24/19×tentacleLength 同值"),
    ("⚠️", "禅乌贼", "chunk1 rad 7.0（第二截）", "我们只有主 chunk（7.5）+ 14px 偏移，第二截没有独立半径："
     "贴墙/压地时比原版略薄，不影响观感"),
    ("⚠️", "拾荒者", "身体是 3 截：胸 9.5 / 髋 7.0 / 头 5.0（Scavenger.cs:1611 起）+ 截间连接",
     "我们仍按 1 截 rad 7.0（髋）跑物理：三个半径常量现在都与原版一致（BODY_RAD 7 / HEAD_RAD 5），"
     "但**没有第二、三截的质点**，所以贴墙/被矛插时的接触点比原版粗一档；要彻底对齐需要把拾荒者改成三质点身体"),
    ("⚠️", "拾荒者", "ScavengerGraphics 的精灵表（面具/尖刺/腿/眼）",
     "我们的画法是自己拼的色块，不是逐件对表：面具/腿的**图层顺序与尺寸**只能算「像」，"
     "参考表在 docs/PARTS_REFERENCE.md 的 ScavengerGraphics 一节"),
    ("✅", "蛞蝓猫尾巴", "TailSegment rad 6/4/2.5、conn 4/7/7（PlayerGraphics.cs:1770 起）", "同值（core/tail.py）"),
    ("✅", "蛞蝓猫手", "SlugcatHand rad 3 / sfFric 0.8 / aFric 1.0 / huntSpeed 7 / quickness 0.5，"
     "ConnectToPoint 20（SlugcatHand.cs:17）", "huntSpeed 7、quickness 0.5、拴绳 20 同值；"
     "手走的就是 Limb 的「速度朝目标插值 → 够近吸附 → 拴绳约束」模型"),
    ("⚠️", "蛞蝓猫手", "Limb.pushOutOfTerrain（手不许插进地形）", "我们的手没有地形推挤：贴墙/贴地时手会画进墙里"),
    ("✅", "蜥蜴", "LizardBreeds 步态 9 参数 / LizardLimb 迈步模型", "第 33 轮已逐品种照抄（见 README 第 33 轮）"),
    ("⚠️", "蜥蜴", "LizardGraphics 的体节圆/背刺/头片图层", "体节圆与四肢是我们按同一套参数重画的，"
     "件数与下标顺序不完全等同原版（原版用 sprite 下标循环），参考表见 PARTS_REFERENCE.md"),
    ("✅", "爆米花", "SeedCob 图层：茎→豆荚→种子(按层)→外壳→叶片；外壳在所有种子之上", "第 32 轮已按表对齐（tools/README 有结论）"),
    ("✅", "爆炸特效", "ExplosionLight 的半径/时长", "第 30 轮按原版数值对齐"),
]


def gen_reference() -> None:
    DOCS.mkdir(exist_ok=True)
    out = ["# 原版部件参考表（机械生成）", "",
           "由 `tools/parts_audit.py` 调 `tools/parts_table.py` 直接从反编译源码抓取，",
           "**不要手改**；重新生成：`python tools/parts_audit.py`。", "",
           "读法：`idx` 是 `sLeaser.sprites[]` 下标 = 同容器内的绘制顺序（后画的盖前面的）；",
           "`atlas WxH` 是元件原始像素，实际屏幕尺寸 = 该尺寸 × `DrawSprites` 里赋的 scale。", ""]
    for zh, cls, _our in ENTITIES:
        out.append(f"## {zh}（{cls}）")
        out.append("")
        try:
            r = subprocess.run([sys.executable, "-X", "utf8", str(HERE / "parts_table.py"), cls],
                               capture_output=True, text=True, encoding="utf-8", timeout=120)
            body = (r.stdout or "").split("\n")
            out.extend(body[3:] if len(body) > 3 else body)
        except Exception as exc:               # 缺源码/超时都别炸，记为待补
            out.append(f"（抓取失败：{exc}）")
        out.append("")
    (DOCS / "PARTS_REFERENCE.md").write_text("\n".join(out), encoding="utf-8", newline="\n")
    print("write", DOCS / "PARTS_REFERENCE.md")


def gen_audit(rows) -> None:
    DOCS.mkdir(exist_ok=True)
    lines = ["# 已移植对象：尺寸/位置/图层审计", "",
             "审计对象：蜥蜴 / 拾荒者 / 珍珠 / 矛 / 爆米花 / 蝠蝇 / 禅乌贼 / 蛞蝓猫(手·尾) / 爆炸特效。",
             "原版数值一律取自反编译（`work/scratch/decomp_full`），贴图数值取自图集 JSON；",
             "机械参考表见 `docs/PARTS_REFERENCE.md`（由 `tools/parts_audit.py` 生成）。", "",
             "## 一、自动对拍（数值级）", "",
             "| 项目 | 原版 | 我们的常量 | 结论 |",
             "| --- | --- | --- | --- |"]
    bad = 0
    for name, orig, rel, const in rows:
        ours = our_const(rel, const)
        if orig is None or ours is None:
            verdict, o_s = "⚠️ 读不到（源码/常量缺失）", "-"
        elif abs(orig - ours) < 1e-6:
            verdict, o_s = "✅ 一致", f"`{const} = {ours:g}`"
        else:
            verdict, o_s = f"❌ 偏差 {ours - orig:+g}", f"`{const} = {ours:g}`"
            bad += 1
        lines.append(f"| {name} | {orig if orig is not None else '-'} | {o_s} | {verdict} |")
    lines += ["", "## 二、人工核对结论（不一致清单）", "",
              "| 结论 | 对象 | 原版 | 我们的现状 |", "| --- | --- | --- | --- |"]
    for mark, obj, orig, ours in FINDINGS:
        lines.append(f"| {mark} | {obj} | {orig} | {ours} |")
    lines += ["", "## 三、已知的系统性偏差", "",
              "- **图层顺序**：能机械抓的都在 `PARTS_REFERENCE.md`；我们的绘制函数多数是「按同一套参数重画」，",
              "  不是逐 `sLeaser.sprites[]` 下标照搬，所以「件数/顺序」只在标了 ✅ 的对象上做过对齐。",
              "- **循环下标**：原版大量用 `sprites[SpriteXxxStart + n]` 批量赋值，工具只能给出行，",
              "  需要人工代入循环变量（工具 `tools/README.md` 有说明）。",
              "- **Mesh 类精灵**（禅乌贼触须/蛞蝓猫尾巴）没有 atlas 尺寸，形状由顶点代码决定，",
              "  审计按「公式是否照抄」判定，而不是按像素尺寸。",
              ""]
    (DOCS / "PARTS_AUDIT.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("write", DOCS / "PARTS_AUDIT.md")
    return bad


def main() -> int:
    rows = []
    for name, fn, rel, const in CHECKS:
        try:
            rows.append((name, fn(), rel, const))
        except Exception:
            rows.append((name, None, rel, const))
    if "--check" in sys.argv:
        bad = 0
        for name, orig, rel, const in rows:
            ours = our_const(rel, const)
            ok = orig is not None and ours is not None and abs(orig - ours) < 1e-6
            print(("OK  " if ok else "DIFF") + f" {name}: 原版={orig} 我们={ours}")
            bad += 0 if ok else 1
        return 1 if bad else 0
    gen_reference()
    bad = gen_audit(rows)
    print(f"对拍偏差 {bad} 条（详见 docs/PARTS_AUDIT.md）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
