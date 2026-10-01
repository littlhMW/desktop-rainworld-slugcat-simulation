"""姿态过渡与趴行掉头状态机（控制路径与 AI 共用，y↓），cy==+1 脚踩地。

R157 起这里不再只是「控制路径专用」：``crawl_turn_entry`` / ``crawl_turn_delay``
是控制态和 AI（``core/creature.py::_movement_update`` 的 Crawl 分支）**唯一**的
CrawlTurn 判据。两条路各写一份判据正是「玩家操作的猫匍匐/转身是对的、AI 猫不对」
的来源；翻身力本身也统一放在 ``SlugcatBody._crawl_turn``（照 Player.cs:7518）。
"""
from __future__ import annotations

CRAWL_TURN_MAX = 40     # 一次 CrawlTurn 最多多少帧（几何判据一直不满足也不卡死）


def toggle_standing(body, inp0, inp1) -> None:
    """上键升沿→standing=true(StandUp 意图)；下键升沿→standing=false(DownOnFours 意图)。"""
    if inp0.y == 1 and inp1.y != 1:
        # 坡度/头顶实心检查：pet 无坡/砖 → 恒真
        body.standing = True
    elif inp0.y == -1 and inp1.y != -1:
        body.standing = False


def update_counters(body) -> None:
    """上/下身接地帧计数（控制专属）；触地判定用 on_floor。"""
    c0, c1 = body.chunk0, body.chunk1
    body._lower_on_ground = (getattr(body, "_lower_on_ground", 0) + 1) if c1.on_floor else 0
    body._upper_off_ground = 0 if c0.on_floor else (getattr(body, "_upper_off_ground", 0) + 1)


def anim_forces(body, move_x: int) -> None:
    """姿态动画分支每帧力，可改 bodyMode/清 animation。"""
    c0, c1 = body.chunk0, body.chunk1
    flip = body.facing
    anim = body.animation

    if anim == "CrawlTurn":
        # 翻身力只有一份实现（SlugcatBody._crawl_turn，逐行对拍 Player.cs:7518）。
        # 旧版这里是第二份拷贝：控制态改动不会传到 AI，AI 改动也不会传到控制态。
        body._crawl_turn(move_x)

    elif anim == "StandUp":
        if body.standing:
            c0.vx *= 0.7                            # 上身横速阻尼
            body.bodyMode = "Stand"                 # pet 恒真，略去检查
            if c0.y < c1.y - 3.0:                   # 头升过臀+3
                body.animation = None
        else:
            body.animation = "DownOnFours"          # 中途又要趴 → 反向

    elif anim == "DownOnFours":
        if not body.standing:
            c0.vy += 2.0
            c0.vx += flip                           # 上身朝前
            c1.vx -= flip                           # 臀朝后（前扑剪切）
            if c0.y > c1.y or c0.on_floor:          # 头落臀下 或 头触地
                body.animation = None
        else:
            body.animation = "StandUp"              # 中途又要站 → 反向


def crawl_turn_delay(body) -> None:
    """Crawl 态每帧 ++，离 Crawl 清零（控制态与 AI 共用同一份计数）。"""
    body._crawl_turn_delay = (getattr(body, "_crawl_turn_delay", 0) + 1) if body.bodyMode == "Crawl" else 0


def crawl_turn_entry(body, move_x: int) -> bool:
    """够不够条件换 CrawlTurn：反着爬 + 已连爬 5 帧 + 此刻没有别的姿态动画。

    原版 Player.cs:9088-9100：朝身体反方向爬先按 0.75 减速，连着 5 帧以上还在
    反着爬就换 CrawlTurn（原地翻过来），而不是一路倒着滑。控制态与 AI 共用这一份。
    """
    if body.animation is not None or move_x == 0 or body.bodyMode != "Crawl":
        return False
    c0, c1 = body.chunk0, body.chunk1
    if (move_x > 0) != (c0.x < c1.x):
        return False
    if getattr(body, "_crawl_turn_delay", 0) <= 5:
        return False
    body._crawl_turn_delay = 0
    body._crawl_turn_left = CRAWL_TURN_MAX
    body.animation = "CrawlTurn"
    return True


def posture_entry(body, move_x: int) -> None:
    """各姿态模式块的过渡入口，仅空闲时进。"""
    if body.animation is not None:
        return
    c0, c1 = body.chunk0, body.chunk1
    mode = body.bodyMode
    if mode == "Crawl":
        if body.standing and getattr(body, "_lower_on_ground", 0) >= 3:
            body.animation = "StandUp"
        else:
            crawl_turn_entry(body, move_x)          # pet 无砖，略去实心判定
    elif mode == "Stand":
        if (not body.standing
                and getattr(body, "_lower_on_ground", 0) >= 5
                and getattr(body, "_upper_off_ground", 0) >= 5):
            body.animation = "DownOnFours"
