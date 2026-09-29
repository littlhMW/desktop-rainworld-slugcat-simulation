"""从用户本机 Rain World 安装提取图集到 ~/.slugcatpet/assets。"""
from __future__ import annotations
import re
import sys
from pathlib import Path

from ._paths import assets_dir, bundled_assets_dir
from .i18n import t

# 图集名：base + MSC 各含贴图与 UI
ATLASES = ("rainWorld", "rainworldmsc",
           "uiSprites", "uispritesmsc")
# 可选图集：不是每台机器 / 每个版本都取得到。缺了渲染回落程序化绘制，不阻塞启动。
ATLASES_OPTIONAL = ("shelterGate",)
_ATLAS_REL = Path("RainWorld_Data") / "resources.assets"
_ATLAS_ERR = {"rainWorld": "err_base_fail", "rainworldmsc": "err_msc_missing",
              "uiSprites": "err_ui_fail", "uispritesmsc": "err_uimsc_missing"}


class SetupError(RuntimeError):
    """导入失败，message 面向用户、可照做。"""


def atlases_present(d: Path) -> bool:
    """核心 4 张图集是否在位（shelterGate 是可选的，缺了不算缺失）。"""
    return all((d / f).exists() for f in
               ("rainWorld", "rainWorld.png", "rainworldmsc", "rainworldmsc.png",
                "uiSprites", "uiSprites.png", "uispritesmsc", "uispritesmsc.png"))


def atlases_complete(d: Path) -> bool:
    """核心 4 张 + 可选图集全在位。"""
    return atlases_present(d) and all((d / f).exists() for f in
                                      ("shelterGate", "shelterGate.png"))


# 定位 Steam 安装

def _drive_roots() -> list[Path]:
    if sys.platform == "win32":
        return [Path(f"{c}:\\") for c in "CDEFGHIJKLMNOP"
                if Path(f"{c}:\\").exists()]
    # mac / linux Steam 默认库
    home = Path.home()
    return [home / "Library/Application Support/Steam",
            home / ".steam/steam", home / ".local/share/Steam"]


def _steam_root() -> Path | None:
    if sys.platform == "win32":
        try:
            import winreg
            for hive, key, val in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            ):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        p = Path(winreg.QueryValueEx(k, val)[0])
                        if p.exists():
                            return p
                except OSError:
                    pass
        except Exception:
            pass
    return None


def _steam_libraries() -> list[Path]:
    """枚举所有 Steam 库根目录。"""
    roots: list[Path] = []
    sr = _steam_root()
    if sr:
        roots.append(sr)
    for d in _drive_roots():
        roots += [d / "Program Files (x86)" / "Steam", d / "Steam",
                  d / "SteamLibrary", d]
    libs: list[Path] = []
    seen: set[Path] = set()
    for r in roots:
        if r in seen or not r.exists():
            continue
        seen.add(r)
        libs.append(r)
        vdf = r / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            txt = vdf.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r'"path"\s*"([^"]+)"', txt):
                p = Path(m.group(1).replace("\\\\", "\\"))
                if p not in seen and p.exists():
                    seen.add(p)
                    libs.append(p)
    return libs


def detect_install() -> Path | None:
    """返回 Rain World 游戏根目录，找不到返回 None。"""
    for lib in _steam_libraries():
        game = lib / "steamapps" / "common" / "Rain World"
        if (game / _ATLAS_REL).exists():
            return game
    return None


# 提取

def extract_atlases(install: Path, dest: Path | None = None,
                    names=None) -> Path:
    """从游戏 resources.assets 提取图集到 dest（默认 ~/.slugcatpet/assets）。

    ``names=None`` 提取全部（核心 4 张 + 可选）；给名字就只提那几张
    （用来给旧素材包单独补 shelterGate，不必重导整包）。
    核心图集缺失一律报错；可选图集取不到只是跳过。
    """
    install = Path(install)
    res = install / _ATLAS_REL
    if not res.exists():
        raise SetupError(t("err_atlas_missing", res=res))
    try:
        import UnityPy
    except ImportError as e:
        raise SetupError(t("err_no_unitypy")) from e

    dest = Path(dest or assets_dir())
    dest.mkdir(parents=True, exist_ok=True)
    want = set(names or (ATLASES + ATLASES_OPTIONAL))
    got: dict[str, set[str]] = {}
    env = UnityPy.load(str(res))
    for obj in env.objects:
        if obj.type.name not in ("Texture2D", "TextAsset"):
            continue
        d = obj.read()
        name = getattr(d, "m_Name", None) or getattr(d, "name", None)
        if name not in want:
            continue
        if obj.type.name == "Texture2D":
            d.image.save(str(dest / f"{name}.png"))
            got.setdefault(name, set()).add("png")
        else:
            raw = d.m_Script if hasattr(d, "m_Script") else d.script
            if isinstance(raw, str):
                raw = raw.encode("utf-8", "surrogateescape")
            (dest / name).write_bytes(raw)
            got.setdefault(name, set()).add("map")

    for name, key in _ATLAS_ERR.items():
        if name in want and got.get(name) != {"png", "map"}:
            raise SetupError(t(key))
    return dest


def ensure_atlases() -> Path:
    """已导入则直接返回，否则自动定位安装并提取。

    旧素材包（只有核心 4 张）会就地把可选的 shelterGate 补上；补不到也不阻塞
    启动 —— 门渲染回落到程序化门板。
    """
    for d in (assets_dir(), bundled_assets_dir()):
        if atlases_complete(d):
            return d
    for d in (assets_dir(), bundled_assets_dir()):
        if atlases_present(d):
            install = detect_install()
            if install:
                try:
                    extract_atlases(install, d, names=ATLASES_OPTIONAL)
                except Exception:
                    pass
            return d
    install = detect_install()
    if not install:
        raise SetupError(t("err_no_install"))
    return extract_atlases(install)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "dump":
        # 图集之外的整包逆向资料库（资源/精灵/骨架/动画/逻辑/报告）
        from .rwdump import extract as rwdump
        return rwdump.main(argv[1:])
    install = Path(argv[0]) if argv else detect_install()
    if install is None:
        print("未找到 Rain World 安装。\n"
              "用法：python -m slugcatpet.gameassets <游戏根目录>\n"
              "      python -m slugcatpet.gameassets dump [--install DIR] [--decomp DIR]")
        return 2
    try:
        dest = extract_atlases(install)
    except SetupError as e:
        print(f"导入失败：{e}")
        return 1
    print(f"已从 {install} 导入图集到 {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
