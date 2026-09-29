# -*- coding: utf-8 -*-
"""逻辑层（Code / Logic / Creature）：从反编译 C# 里机械抽出「精灵图」与「写入语句」。

不猜、不看图：全部靠 `InitiateSprites` / `AddToContainer` / `ApplyPalette` /
`DrawSprites` 这四个方法的字面写法，规则与 `docs/DECOMPILE_PROCESS.md` 第 2/3/5 节一致。

* 下标 = `sLeaser.sprites[i] = …` 的 i，**就是绘制顺序**（同容器内后画盖前画）；
  循环变量 / `SpriteXxxStart + n` 这类运行时下标原样留在 `index_expr` 里，能静态求值的
  （常量、常量算术、`public int SpriteXxxStart => …;` 这类下标助手）另外填 `index`。
* 容器 = `AddToContainer` 里 `container[k].AddChild(...)` 的 k，决定跨容器顺序。
* 变换 = `DrawSprites` 里对该下标赋的 `x/y/rotation/scaleX/scaleY/anchorX/anchorY/
  alpha/element`，RHS **原样**保留成字符串，另外把引用到的身体节抽成 `depends_on`。
* 每个精灵还带 `flip`（scaleX 里出现 -1 / Sign / flipX 之类）与 `palette`。
* `anchor`：`anchorY` 是常量时按 `docs/DECOMPILE_PROCESS.md` 第 4 节换算成 `qt_ay`。

`element` 支持三种写法：字面量、`"A" + expr + "B"`（动态拼接）、`TriangleMesh(...)`。
动态拼接会把中间数字展开成候选帧名，交由上层与图集对拍（`reports/unresolved.json`）。
"""
from __future__ import annotations

import re
from pathlib import Path

CONST_RE = re.compile(
    r"(?:private|public|protected|internal)?\s*(?:const|static\s+readonly)\s+int\s+"
    r"([A-Za-z_]\w*)\s*=\s*([^;]+);")
# 下标助手：public int SpriteHeadStart => SpriteLimbsEnd;   /   public int F(int i) => i + 3;
HELPER_RE = re.compile(
    r"public\s+int\s+(\w*Sprite\w*)\s*(?:\(([^)]*)\))?\s*(?:=>|\{)\s*"
    r"(?:return\s+)?([^;{}]+);")
METHOD_RE = re.compile(
    r"\b(?:public|private|protected|internal)\s+(?:override\s+|virtual\s+|new\s+|static\s+)*"
    r"(?:void|IEnumerable<[^>]+>|[A-Za-z_][\w<>\[\],.\s]*?)\s+(\w+)\s*\(([^)]*)\)\s*\{")
SPRITE_ASSIGN_RE = re.compile(r"sLeaser\.sprites\[([^\]]+)\]\s*=\s*([^;]+);")
PROP_ASSIGN_RE = re.compile(r"sLeaser\.sprites\[([^\]]+)\]\.(\w+)\s*=\s*([^;]+);")
CHILD_RE = re.compile(
    r"(?:sLeaser|Leaser)\.container\[([^\]]+)\]\.AddChild\(\s*(?:sLeaser|Leaser)\.sprites\[([^\]]+)\]")
# 具名容器：ReturnFContainer("Foreground").AddChild(...) / newContatiner.AddChild(...)
CHILD_FC_RE = re.compile(
    r"ReturnFContainer\(\s*\"([^\"\\]*)\"\s*\)\.AddChild\(\s*(?:sLeaser|Leaser)\.sprites\[([^\]]+)\]")
CHILD_VAR_RE = re.compile(
    r"\b(\w+)\.AddChild\(\s*(?:sLeaser|Leaser)\.sprites\[([^\]]+)\]")
# layer 名（RoomCamera.SpriteLayerIndex）
LAYER_RE = re.compile(r"SpriteLayerIndex\.Add\(\s*\"([^\"\\]*)\"\s*,\s*(\d+)\s*\)")
VAR_DECL_RE = re.compile(r"\b(?:FSprite|TriangleMesh|FSprite\[\])\s+(\w+)\s*=\s*([^;]+);")
TOTAL_RE = re.compile(r"[Tt]otalSprites\s*=\s*([^;]+);")
SPRITE_ARRAY_RE = re.compile(r"sLeaser\.sprites\s*=\s*new\s+FSprite\[([^\]]+)\]")

DRAW_PROPS = ("x", "y", "rotation", "scaleX", "scaleY", "anchorX", "anchorY",
              "alpha", "isVisible")

# DrawSprites 里读到的运行时量 → 依赖名
DEP_IDENTS = ("timeStacker", "animationFrame", "sleepCurl", "breath", "energy",
              "headRotation", "spearProg", "swallowAndRegurgitateCounter",
              "blink", "sitting", "inFrontOfCamera", "airborne", "flipX")
FLIP_HINT_RE = re.compile(r"\bSign\s*\(|flipX|LooksFlipped|-\s*1(?:\.0f?|f)?\b")
_NAME_OK_RE = re.compile(r"^[A-Za-z][\w.\-]{0,40}$")


def mask(src: str) -> str:
    """把注释与字符串替换成空格（保留长度与换行），用于安全地做括号匹配/定位。"""
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if src[k] != "\n":
                    out[k] = " "
            i = j
        elif c == "@" and i + 1 < n and src[i + 1] == '"':
            j = i + 2
            while j < n:
                if src[j] == '"':
                    if j + 1 < n and src[j + 1] == '"':
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            for k in range(i, min(j, n)):
                if src[k] != "\n":
                    out[k] = " "
            i = j
        elif c == '"':
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == '"':
                    j += 1
                    break
                j += 1
            for k in range(i, min(j, n)):
                if src[k] != "\n":
                    out[k] = " "
            i = j
        elif c == "'":
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "'":
                    j += 1
                    break
                j += 1
            for k in range(i, min(j, n)):
                if src[k] != "\n":
                    out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


def brace_body(masked: str, open_idx: int):
    """从 `{` 的下标找到配对的 `}`；返回 (body_start, body_end)，失败给 None。"""
    if open_idx < 0 or open_idx >= len(masked) or masked[open_idx] != "{":
        return None
    depth = 0
    for i in range(open_idx, len(masked)):
        c = masked[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return (open_idx + 1, i)
    return None


CLASS_DECL_RE = re.compile(r"\b(?:class|struct)\s+(\w+)")


def _next_brace(masked: str, i: int):
    """从 i 起找第一个 { 或 ;（跳过泛型约束/基类列表）。"""
    j = i
    while j < len(masked):
        c = masked[j]
        if c == "{":
            return "{", j
        if c == ";":
            return ";", j
        j += 1
    return None, None


def nested_class_ranges(masked: str) -> list:
    """文件里嵌套类/结构体的方法体区间 —— 外层类的方法表要跳过它们。"""
    decls = list(CLASS_DECL_RE.finditer(masked))
    ranges = []
    for m in decls[1:]:                    # decls[0] 是外层类，不跳
        kind, pos = _next_brace(masked, m.end())
        if kind != "{":
            continue
        br = brace_body(masked, pos)
        if br:
            ranges.append(br)
    return ranges


def methods(masked: str, skip=()):
    """外层类的方法表：名字 → (body_start, body_end)。同名取第一个。"""
    out = {}
    for m in METHOD_RE.finditer(masked):
        s = m.start()
        if any(a <= s < b for a, b in skip):
            continue
        name = m.group(1)
        if name in out:
            continue
        br = brace_body(masked, m.end() - 1)
        if br:
            out[name] = br
    return out


def class_name(masked: str, src: str) -> str | None:
    m = re.search(r"\b(?:public|internal)\s+(?:sealed\s+|abstract\s+|partial\s+)*"
                  r"class\s+(\w+)", masked)
    return m.group(1) if m else None


# ── 常量表 / 下标助手 / 静态求值 ────────────────────────────────────

def constants(src: str, masked: str) -> dict:
    """类里的 const / static readonly int（表达式里可以互相引用）。"""
    out = {}
    for _ in range(4):
        changed = False
        for m in CONST_RE.finditer(masked):
            name = m.group(1)
            if name in out:
                continue
            v = eval_int(src[m.start(2):m.end(2)].strip(), out)
            if v is not None:
                out[name] = v
                changed = True
        if not changed:
            break
    return out


def index_helpers(masked: str) -> dict:
    """`public int SpriteHeadStart => SpriteLimbsEnd;` 这类下标助手 → {名字: (形参, 表达式)}。"""
    out = {}
    for m in HELPER_RE.finditer(masked):
        out[m.group(1)] = ((m.group(2) or "").strip(), m.group(3).strip())
    return out


def expand_helpers(expr: str, helpers: dict, rounds: int = 12) -> str:
    """把下标助手递归展开成常量表达式（`SpriteHeadStart` → `SpriteLimbsEnd` → …）。"""
    e = expr.strip()
    free = [fn for fn, (a, _b) in helpers.items() if not a]
    for _ in range(rounds):
        before = e
        for fn in sorted(free, key=len, reverse=True):
            e = re.sub(r"\b" + fn + r"\b", "(" + helpers[fn][1] + ")", e)
        for fn, (args, body) in helpers.items():
            if not args:
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


def eval_int(expr: str, consts: dict):
    """常量算术求值：只认数字、常量名、+ - * ( )；求不出来给 None。"""
    e = (expr or "").strip()
    if not e:
        return None
    e2 = re.sub(r"[A-Za-z_]\w*", lambda m: str(consts[m.group(0)])
                if m.group(0) in consts else m.group(0), e)
    if not re.fullmatch(r"[\d\s+\-*/()]+", e2):
        return None
    try:
        return int(eval(e2, {"__builtins__": {}}, {}))     # noqa: S307 仅数字与运算符
    except Exception:
        return None


def eval_index(expr: str, consts: dict, helpers: dict):
    """先展开下标助手，再求值。返回 (值或 None, 展开后的表达式)。"""
    e = expand_helpers(expr, helpers) if helpers else expr.strip()
    return eval_int(e, consts), e


def resolve_var(varelem: dict, name: str, depth: int = 0) -> str | None:
    if depth > 6:
        return None
    v = varelem.get(name)
    if v is None:
        return None
    if isinstance(v, str) and v.startswith("@"):
        return resolve_var(varelem, v[1:], depth + 1)
    return v if isinstance(v, str) else None


def _elem_from_expr(expr: str) -> str | None:
    """把赋值右值变成「元件描述」字符串。"""
    e = expr.strip()
    m = re.search(r"new\s+FSprite\(\s*\"([^\"\\]*)\"", e)
    if m:
        return m.group(1)
    m = re.search(r"GetElementWithName\(\s*\"([^\"\\]*)\"", e)
    if m:
        return m.group(1)
    m = re.search(r"MakeLongMesh\(([^)]*)\)", e)
    if m:
        return "TriangleMesh([" + m.group(1) + "])"
    m = re.search(r"new\s+TriangleMesh\(\s*\"([^\"\\]*)\"", e)
    if m:
        return m.group(1)
    m = re.fullmatch(r"\"([^\"\\]*)\"", e)
    if m:
        return m.group(1)
    if "+" in e and '"' in e:                   # "A" + expr + "B"
        parts = re.findall(r'\"([^\"\\]*)\"|([A-Za-z_][\w.\[\]]*)', e)
        keep = [(p[0], p[1]) for p in parts if p[0] or p[1]]
        lit = "".join(p[0] for p in keep)
        if lit and any(p[1] for p in keep):
            return "".join(('"%s"' % a) if a else ("{%s}" % b) for a, b in keep)
    return None


def expand_dynamic(elem: str, atlas_lookup, limit: int = 16) -> dict | None:
    """`"Cicada"{n}body` → 展开成图集里真实存在的候选帧。"""
    if "{" not in elem:
        return None
    head, _, rest = elem.partition("{")
    mid, _, tail = rest.partition("}")
    head = head.strip('"')
    tail = tail.strip('"')
    mid = mid.strip()
    cands = [f"{head}{i}{tail}" for i in range(limit)]
    return {"head": head, "var": mid, "tail": tail,
            "candidates": cands,
            "resolved_candidates": [c for c in cands if atlas_lookup(c)]}


def _depends_on(exprs) -> dict:
    chunks, tail, limbs, idents = [], [], [], []
    for e in exprs:
        if not e:
            continue
        chunks += re.findall(r"bodyChunks\[(\d+)\]", e)
        tail += re.findall(r"\btail\[(\d+)\]", e)
        limbs += re.findall(r"\blimbs\[(\d+)\]", e)
        idents += [i for i in DEP_IDENTS if re.search(r"\b%s\b" % i, e)]
    return {"body_chunks": sorted({int(c) for c in chunks}),
            "tail": sorted({int(t) for t in tail}),
            "limbs": sorted({int(x) for x in limbs}),
            "runtime": sorted(set(idents))}


# ── 单个类 ──────────────────────────────────────────────────────────

def scan_class(path: Path, atlas_lookup=None) -> dict | None:
    src = path.read_text(encoding="utf-8", errors="replace")
    msk = mask(src)
    name = class_name(msk, src)
    if not name:
        return None
    consts = constants(src, msk)
    helpers = index_helpers(msk)
    ms = methods(msk, nested_class_ranges(msk))

    def locals_in(br) -> dict:
        """只在该方法体内建局部变量表 —— 不同方法里的 num/num2 互不相干。"""
        out = {}
        seg = msk[br[0]:br[1]]
        for m in VAR_DECL_RE.finditer(seg):
            var = m.group(1)
            rhs = src[br[0] + m.start(2):br[0] + m.end(2)].strip()
            got = _elem_from_expr(rhs)
            if got:
                out[var] = got
            elif re.fullmatch(r"\w+", rhs):
                out[var] = "@" + rhs
        return out

    def elem_of(rhs: str, loc: dict):
        e = _elem_from_expr(rhs)
        if e is not None:
            return e
        mm = re.fullmatch(r"\s*(\w+)\s*", rhs.strip())
        if mm:
            return resolve_var(loc, mm.group(1))
        return None

    sprites: dict[str, dict] = {}

    def slot(idx_expr: str) -> dict:
        key = idx_expr.strip()
        rec = sprites.get(key)
        if rec is None:
            val, expanded = eval_index(key, consts, helpers)
            rec = {"index_expr": key, "index_expanded": expanded, "index": val,
                   "element": None, "element_expr": None, "container": None,
                   "draw": {}, "palette": None, "flip": None, "anchor": None,
                   "debug": "Debug" in key,
                   "index_exprs": [key]}
            sprites[key] = rec
        return rec

    def do_initiate(br):
        loc = locals_in(br)
        for m in SPRITE_ASSIGN_RE.finditer(msk, br[0], br[1]):
            rec = slot(msk[m.start(1):m.end(1)])
            rhs = src[m.start(2):m.end(2)].strip()
            el = elem_of(rhs, loc)
            if el and not rec["element"]:
                rec["element"] = el
                rec["element_expr"] = rhs
        # 锚点/朝向常常只在 InitiateSprites 里设一次（BodySprite.anchorY = 0.7894737f）
        for m in PROP_ASSIGN_RE.finditer(msk, br[0], br[1]):
            prop = m.group(2)
            if prop not in DRAW_PROPS:
                continue
            rec = slot(msk[m.start(1):m.end(1)])
            rec["draw"].setdefault(prop, src[m.start(3):m.end(3)].strip())

    def do_container(br):
        for m in CHILD_RE.finditer(msk, br[0], br[1]):
            k = msk[m.start(1):m.end(1)].strip()
            val, expanded = eval_index(k, consts, helpers)
            rec = slot(msk[m.start(2):m.end(2)])
            rec["container"] = val if val is not None else expanded
        for kind, rx in (("fc", CHILD_FC_RE), ("var", CHILD_VAR_RE)):
            for m in rx.finditer(src if kind == "fc" else msk, br[0], br[1]):
                rec = slot(msk[m.start(2):m.end(2)])
                if rec["container"] is None:
                    rec["container"] = (src[m.start(1):m.end(1)].strip()
                                        if kind == "fc" else "@" + m.group(1))

    def do_draw(br):
        loc = locals_in(br)
        for m in PROP_ASSIGN_RE.finditer(msk, br[0], br[1]):
            prop = m.group(2)
            if prop not in DRAW_PROPS and prop not in ("element", "color"):
                continue
            val = src[m.start(3):m.end(3)].strip()
            rec = slot(msk[m.start(1):m.end(1)])
            if prop == "element":
                el = elem_of(val, loc)
                if el:
                    rec["element"] = el
                    rec["element_expr"] = val
                continue
            if prop == "color":
                rec["palette"] = val
                continue
            rec["draw"][prop] = val
            if prop in ("scaleX", "scaleY") and FLIP_HINT_RE.search(val):
                rec["flip"] = {"axis": "x" if prop == "scaleX" else "y", "source": val}

    def do_palette(br):
        for m in PROP_ASSIGN_RE.finditer(msk, br[0], br[1]):
            if m.group(2) != "color":
                continue
            slot(msk[m.start(1):m.end(1)])["palette"] = src[m.start(3):m.end(3)].strip()

    for key, fn in (("InitiateSprites", do_initiate), ("AddToContainer", do_container),
                    ("DrawSprites", do_draw), ("ApplyPalette", do_palette)):
        br = ms.get(key)
        if br:
            fn(br)

    out_sprites = []
    for rec in sprites.values():
        exprs = [rec["draw"].get(k) for k in
                 ("x", "y", "rotation", "scaleX", "scaleY")]
        rec["depends_on"] = _depends_on(exprs)
        if rec["element"] and "{" in rec["element"] and atlas_lookup:
            rec["dynamic"] = expand_dynamic(rec["element"], atlas_lookup)
        ay = rec["draw"].get("anchorY")
        ax = rec["draw"].get("anchorX")
        try:
            fs = re.findall(r"-?\d+(?:\.\d+)?", ay or "")
            fx = re.findall(r"-?\d+(?:\.\d+)?", ax or "")
            anchor = {}
            if len(fs) == 1:
                anchor["unity_anchor_y"] = float(fs[0])
                anchor["qt_ay"] = 1.0 - float(fs[0])
            if len(fx) == 1:
                anchor["anchor_x"] = float(fx[0])
            rec["anchor"] = anchor or None
        except Exception:
            rec["anchor"] = None
        out_sprites.append(rec)
    out_sprites.sort(key=lambda r: (r["index"] is None, r["index"] or 0, r["index_expr"]))

    total = None
    tm = TOTAL_RE.search(msk)
    if tm:
        total = src[tm.start(1):tm.end(1)].strip()
    if total is None:
        am = SPRITE_ARRAY_RE.search(msk)
        if am:
            raw = re.sub(r"\s+", " ", src[am.start(1):am.end(1)].strip())
            total = raw if raw.isdigit() else ">= %d" % len(out_sprites)
    used_containers = sorted({r["container"] for r in out_sprites
                              if isinstance(r["container"], str)})
    return {"class": name, "file": path.name,
            "containers": used_containers,
            "namespace": (re.search(r"namespace\s+([\w.]+)", msk) or [None, None])[1],
            "total_sprites": total,
            "constants": {k: v for k, v in sorted(consts.items())},
            "sprites": out_sprites}


# ── 全量扫描 ────────────────────────────────────────────────────────

EXTRA_CLASSES = ("SeedCob.cs", "Pole.cs", "KarmaFlower.cs", "BatFly.cs", "Fly.cs",
                 "Lizard.cs", "Player.cs", "Scavenger.cs", "NeedleWorm.cs",
                 "Cicada.cs", "SquidCada.cs", "Spear.cs")


def iter_cs(root: Path):
    for p in sorted(Path(root).rglob("*.cs")):
        if p.name.endswith(".decompiled.cs"):
            continue
        yield p


def scan_decomp(root: Path, warnings: list, atlas_lookup=None):
    """扫反编译源码：返回 (classes, references)。

    classes: {类名: 精灵图}
    references: [{element, kind, file, line, class}] —— 代码里出现过的元件名，
                交给上层与图集对拍（reports/unresolved.json）。
    """
    classes: dict[str, dict] = {}
    refs: list[dict] = []
    seen_ref = set()
    patterns = (
        ("FSprite", re.compile(r"new\s+FSprite\(\s*\"([^\"\\]*)\"")),
        ("GetElementWithName", re.compile(r"GetElementWithName\(\s*\"([^\"\\]*)\"")),
        ("element", re.compile(r"\.element\s*=\s*\"([^\"\\]*)\"")),
    )
    for p in iter_cs(root):
        rel = p.name
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            warnings.append("读不到 %s：%r" % (p, e))
            continue
        msk = mask(src)
        cls = class_name(msk, src)
        for kind, rx in patterns:
            for m in rx.finditer(src):
                lit = m.group(1)
                if not _NAME_OK_RE.match(lit):
                    continue
                tail = src[m.end():m.end() + 8]
                if re.match(r"\s*\+", tail):
                    kind = kind + "_prefix"        # "LizardArm" + graphic，运行时拼接
                key = (lit, rel, kind)
                if key in seen_ref:
                    continue
                seen_ref.add(key)
                refs.append({"element": lit, "kind": kind, "file": rel,
                             "line": src.count("\n", 0, m.start()) + 1, "class": cls})
        if p.name.endswith("Graphics.cs") or p.name in EXTRA_CLASSES:
            try:
                rec = scan_class(p, atlas_lookup)
            except Exception as e:
                warnings.append("解析 %s 失败：%r" % (p.name, e))
                rec = None
            if rec and rec["sprites"]:
                classes[rec["class"]] = rec
    return classes, refs