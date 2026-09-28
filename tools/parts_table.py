# -*- coding: utf-8 -*-
"""从反编译源码里机械地抽出「精灵表」：下标（=绘制层级）→ 元件 → 尺寸 → 变换。

用法:
    python parts.py CicadaGraphics            # 单个
    python parts.py CicadaGraphics SeedCob    # 多个（SeedCob 不是 *Graphics，也可直接给文件名）

原理（对照 Futile/RoomCamera 的绘制模型）:
  * 层级 = sLeaser.sprites[] 的下标（同容器内按子节点顺序绘制）;
  * 尺寸 = atlas 元件原始像素 × DrawSprites 里赋的 scale/scaleX/scaleY;
  * 位置 = DrawSprites 里赋的 x/y（多数是 anchor 决定）。
所以只要把 InitiateSprites / DrawSprites / ApplyPalette 里对该下标的赋值抓出来，
就能得到一张可核对的部件表。
"""
import os, re, sys, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # work/slugcatpet
# 反编译源码目录（Rain World 本体；本仓库不收录，需本地准备）
DEC = Path(os.environ.get("RW_DECOMP", ROOT.parent / "scratch" / "decomp_full"))
# 图集目录（rainWorld / rainworldmsc / uiSprites ...）
ASSETS = Path(os.environ.get("SLUGCATPET_ASSETS",
                             Path.home() / ".slugcatpet" / "assets"))

ATLAS = {}
for name in ("rainWorld", "rainworldmsc", "uiSprites", "uispritesmsc"):
    p = ASSETS / name
    if not p.exists():
        continue
    for k, v in json.load(open(p, encoding="utf-8"))["frames"].items():
        ATLAS.setdefault(k[:-4] if k.endswith(".png") else k, (v["frame"]["w"], v["frame"]["h"], name))


def index_helpers(src):
    """{SpriteFn: 表达式} 例如 StalkSprite -> 'part'。"""
    out = {}
    for m in re.finditer(r"public\s+int\s+(\w*Sprite\w*)\s*(?:\((.*?)\))?\s*(?:=>|\{)\s*(?:return\s+)?([^;{}]+);", src):
        fn, args, body = m.group(1), (m.group(2) or "").strip(), m.group(3).strip()
        out[fn] = (args, body)
    return out


NOMINAL_N = 100.0        # 只为排序：把 seedPositions.Length 之类的未知量当 100


def numeric(expr, env=None):
    """把 Sprites[X] 的下标表达式折成可排序的数（未知符号按 0 计，*组* 按 NOMINAL_N 分档）。"""
    e = expr.strip()
    for k, v in (env or {}).items():
        e = re.sub(r"\b" + k + r"\b", str(v), e)
    e = re.sub(r"\b\w+\.\w+\b", str(NOMINAL_N), e)   # x.Length / iVars.foo
    e = re.sub(r"Mathf\.\w+", "", e)
    e = re.sub(r"\w+\(", "(", e)                        # 去掉函数名，避免 eval 报警
    e = re.sub(r"\b[A-Za-z_]\w*\b", "0", e)            # 其余未知量
    try:
        return float(eval(e, {"__builtins__": {}}, {}))
    except Exception:
        return 1e9


def table(cls):
    path = DEC / (cls if cls.endswith(".cs") else cls + ".cs")
    if not path.exists():
        print("!! 找不到", path)
        return
    src = path.read_text(encoding="utf-8", errors="replace")
    helpers = index_helpers(src)

    # 先把每个 helper 方法体里的形参换成一个具体值，展开成常量表达式
    def expand(expr):
        """把 SpriteHeadEnd - 1 这类表达式里所有下标助手递归展开成常量表达式。"""
        e = expr.strip()
        free = [fn for fn, (a, _b) in helpers.items() if not a.strip()]
        for _ in range(12):
            before = e
            for fn in sorted(free, key=len, reverse=True):
                e = re.sub(r"\b" + fn + r"\b", "(" + helpers[fn][1] + ")", e)
            for fn, (args, body) in helpers.items():
                if not args.strip():
                    continue
                names = [a.strip().split()[-1] for a in args.split(",")]
                for m in list(re.finditer(r"\b" + fn + r"\(([^()]*)\)", e)):
                    argv = [a.strip() for a in m.group(1).split(",")]
                    if len(argv) != len(names) or not all(re.fullmatch(r"[\d.]+", a) for a in argv):
                        continue
                    nb = body
                    for k, v in zip(names, argv):
                        nb = re.sub(r"\b" + k + r"\b", v, nb)
                    e = e[:m.start()] + "(" + nb + ")" + e[m.end():]
            if e == before:
                break
        return e

    def _expand_old(expr):
        e = expr.strip()
        for _ in range(6):
            for fn, (args, body) in helpers.items():
                m = re.fullmatch(fn + r"\((.*)\)", e)
                if m:
                    argv = [a.strip() for a in m.group(1).split(",")] if args else []
                    names = [a.strip().split()[-1].strip() for a in args.split(",")] if args.strip() else []
                    env = dict(zip(names, argv))
                    nb = body
                    for k, v in env.items():
                        nb = re.sub(r"\b" + k + r"\b", v, nb)
                    e = nb.strip()
                elif e == fn:
                    e = body
        return e

    rows = {}
    for m in re.finditer(r"sLeaser\.sprites\[([^\]]+)\]\s*(?:\.(\w+)\s*)?=", src):
        raw, prop = m.group(1).strip(), m.group(2)
        if raw in ("i", "0", "1", "2"):          # 循环变量/i 之类的临时写法
            pass
        idx = expand(raw)
        e = rows.setdefault(idx, {"raw": set(), "elems": [], "props": []})
        e["raw"].add(raw)
        line = src[m.start(): src.find(";", m.start()) + 1].strip().replace("\n", " ")
        line = re.sub(r"\s+", " ", line)[:150]
        e["props"].append((prop or "(赋对象)", line))

    # 元素名：InitiateSprites 里的 FSprite("x") / GetElementWithName("x")
    elems = {}
    raw_elems = {}          # idx -> 未展开的 element 右值（用于尺寸占位展开）

    # 先建局部变量表：很多 Graphics 是 FSprite x = new FSprite("..."); sprites[IDX] = x;
    varelem = {}
    for m in re.finditer(r"\b(?:FSprite|TriangleMesh|FSprite\[\])\s+(\w+)\s*=\s*([^;]+);", src):
        v, rhs = m.group(1), m.group(2)
        got = None
        mm = re.search(r"FSprite\(\"([^\"]+)\"\)", rhs)
        if mm:
            got = mm.group(1)
        if got is None:
            mm = re.search(r"GetElementWithName\(([^)]*)\)", rhs)
            if mm:
                got = mm.group(1).strip().strip('"')
        if got is None:
            mm = re.search(r"MakeLongMesh\(([^)]*)\)", rhs)
            if mm:
                got = "TriangleMesh([" + mm.group(1) + "])"
        if got is None:
            mm = re.fullmatch(r"\s*(\w+)\s*", rhs)
            if mm:
                got = ("@" + mm.group(1))
        if got:
            varelem[v] = got
    for _ in range(4):                      # 解析 a = b 的别名
        for k, v in list(varelem.items()):
            if v.startswith("@") and varelem.get(v[1:], "").split(":")[0] not in ("", None):
                varelem[k] = varelem[v[1:]]

    def elem_of(expr):
        e = expr.strip()
        if e.startswith("new FSprite("):
            t = e[len("new FSprite("):].strip(");").strip().strip('"')
            return t
        if e.startswith("TriangleMesh.MakeLongMesh("):
            return "TriangleMesh([" + e[len("TriangleMesh.MakeLongMesh("):].strip(");") + "])"
        return varelem.get(e, e if not e.startswith("@") else None)

    for m in re.finditer(r"sLeaser\.sprites\[([^\]]+)\]\s*=\s*([^;]+);", src):
        el = elem_of(m.group(2))
        if el:
            elems.setdefault(expand(m.group(1).strip()), el)
    for m in re.finditer(r"sLeaser\.sprites\[([^\]]+)\]\.element\s*=\s*([^;]+);", src):
        rhs = re.sub(r"\s+", " ", m.group(2)).strip()
        g = re.search(r"GetElementWithName\((.*)\)\s*$", rhs)
        key = g.group(1).strip() if g else rhs
        key = key.strip()
        if key:
            k2 = expand(m.group(1).strip())
            lit = key.strip('"')
            elems.setdefault(k2, lit if "+" not in key else key)
            raw_elems.setdefault(k2, key)
    for m in re.finditer(r"sLeaser\.sprites\[([^\]]+)\]\s*=\s*TriangleMesh\.MakeLongMesh\(([^)]*)\)", src):
        elems[expand(m.group(1).strip())] = "TriangleMesh([" + m.group(2) + "])"

    print("=" * 100)
    print(f"# {path.name}   精灵总数: " +
          (re.search(r"totalSprites\s*=\s*([^;]+);", src).group(1).strip() if re.search(r"totalSprites\s*=\s*([^;]+);", src) else "?"))
    print("# 层级 = 下标顺序（同容器内后画的盖在前面的）；atlas WxH = 元件原始像素，")
    print("# 实际屏幕尺寸 = 该尺寸 × DrawSprites 里对应的 scale/scaleX/scaleY。")
    print(f"{'idx':>6}  {'下标写法':<22} {'元件':<26} {'atlas WxH':<11} 变换(DrawSprites/Palette)")
    for idx in sorted(rows, key=lambda v: numeric(v, {})):
        e = rows[idx]
        if "Debug" in idx or "Debug" in elems.get(idx, ""):
            continue                        # Release 构建不画调试精灵
        el = raw_elems.get(idx, elems.get(idx, "?"))
        size = ATLAS.get(el)
        size_s = f"{size[0]}x{size[1]}" if size else "-"
        if size is None:
            # "Cicada" + num3 + "body" 这种：把中间的数字占位展开成 atlas 里真实存在的帧
            mm = re.fullmatch(r'"([^"]*)"\s*\+\s*\w+\s*\+\s*"([^"]*)"', el)
            if mm:
                cand = []
                for v in range(0, 11):
                    nm = f"{mm.group(1)}{v}{mm.group(2)}"
                    if nm not in ATLAS:
                        break
                    cand.append(f"{v}:{ATLAS[nm][0]}x{ATLAS[nm][1]}")
                if cand:
                    size_s = " ".join(cand)
        raws = "/".join(sorted(e["raw"]))
        print(f"{idx:>6}  {raws:<22} {el:<26} {size_s:<11}")
        for prop, line in e["props"]:
            if prop in ("scale", "scaleX", "scaleY", "rotation", "x", "y", "alpha", "element", "color", "(赋对象)"):
                print(f"{'':>8}    · {line}")
    for idx in sorted(rows, key=lambda v: numeric(v, {})):
        if elems.get(idx) == "?":
            print(f"# 注意 idx={idx} 没有静态元件名（可能是运行时 element 赋值）")


if __name__ == "__main__":
    for a in sys.argv[1:]:
        table(a)
