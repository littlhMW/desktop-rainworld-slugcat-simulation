# -*- coding: utf-8 -*-
"""行为态 → 给人看的一行短状态词（状态面板里显示在名字旁边）。

单一事实源：状态名在本仓库只有 behavior/fsm.py 的 self.state 一处；
这里只做「状态 → i18n key」的映射，文案在 i18n._STR 的 st_* 组。
新增状态忘了登记也不会崩：落到 st_other。
"""
from __future__ import annotations

# 主状态 → i18n key
# 猎杀类（飞虫 / 蜥蜴 / 爆米花 / 备好家伙的 FightThreat）统一显示成「猎杀」，
# 「猎杀的是什么」交给下面的 _STATE_TARGET / _STATE_CTRL 第二段。
_STATES = {
    "IdleStand": "st_idle",
    "PostThrowWander": "st_wander",
    "PostThrowStand": "st_cool_down",
    "MakeWay": "st_make_way",
    "DodgeShot": "st_dodge_shot",
    "ScoldBlocker": "st_scold",
    "ChaseCursor": "st_chase_cursor",
    "FetchFruit": "st_fetch",
    "CatchFly": "st_hunt_live",
    "ItemPlay": "st_item_play",
    "HelpFeed": "st_help_feed",
    "CoverAlly": "st_cover",
    "FleeLizard": "st_flee",
    "CrawlAway": "st_crawl",
    "FightThreat": "st_fight",
    "PoleClimb": "st_pole_climb",
    "HPole": "st_hpole",
    "SeekHPole": "st_seek_hpole",
    "CeilingHang": "st_ceiling",
    "RelocateToWall": "st_to_wall",
    "TongueClimb": "st_tongue",
    "CursorLick": "st_lick_cursor",
    "HuntFly": "st_hunt_live",
    "Ascension": "st_ascend",
    "AngryStone": "st_angry_stone",
    "PyroMaul": "st_maul",
    "PyroRomp": "st_romp",
    "RivSnatch": "st_snatch",
    "RivFlip": "st_flip",
    "EatCob": "st_hunt_live",
    "SeedCob": "st_hunt_live",
    "ClearCorpse": "st_clear_corpse",
    "Sleep": "st_sleep",
    "LieDown": "st_lie",
    "WakeSequence": "st_wake_up",
    "Stunned": "st_stunned",
    "Dragged": "st_dragged",
    "Dead": "st_dead",
    "Airborne": "st_air",
    "Swimming": "st_swim",
    "SeekWarmth": "st_warmth",
    "StormSeekShelter": "st_storm_seek",
    "ShelterSleep": "st_shelter_sleep",
}

# 社交欲望态：按 _social_kind 细分
_SOCIAL = {
    "point": "st_point",
    "scold": "st_scold",
    "protest": "st_scold",
    "pet": "st_pet",
    "pat": "st_pat",
    "revive": "st_revive",
    "wake": "st_wake_peer",
    "gift": "st_gift",
    "crouch_walk": "st_crouch_walk",
    "watch": "st_watch",
}


def _armed(beh) -> bool:
    """手上/背上有没有家伙（决定 FightThreat 是「找矛」还是「准备猎杀」）。"""
    b = getattr(beh, "body", None)
    return bool(getattr(b, "carried_spear", None) is not None
                or getattr(b, "carried_stone", None) is not None
                or getattr(b, "back_spear", None) is not None)


def status_key(beh) -> str:
    """行为对象 → i18n key。"""
    st = getattr(beh, "state", None)
    if st == "FightThreat":
        return "st_hunt_live" if _armed(beh) else "st_seek_spear"
    if st == "Socialize":
        k = _SOCIAL.get(getattr(beh, "_social_kind", None))
        if k is not None:
            return k
    return _STATES.get(st, "st_other")


def status_text(beh) -> str:
    """行为对象 → 当前状态的中/英文案。"""
    from ..i18n import t
    return t(status_key(beh))


# ── 状态面板第二段：目标是什么 ──
# 字段名一律取自 fsm.__init__ 里真实存在的那些（别手写没声明的名字）。
# 状态 → 这个态真正在用的目标字段（按优先级）
_STATE_TARGET = {
    "MakeWay": ("_makeway_of", "_blocker_target"),
    "DodgeShot": ("_dodge_from",),
    "ScoldBlocker": ("_blocker_target", "_pole_blocker"),
    "Socialize": ("_social_target", "_protest_target", "_apology_target",
                  "_thank_target"),
    "ItemPlay": ("_itemplay_target",),
    "HelpFeed": ("_help_target",),
    "CoverAlly": ("_help_target", "_cover_ally"),
    "FleeLizard": ("_flee_from",),
    "CrawlAway": ("_crawl_from",),
    "FightThreat": ("_fight_target",),
    "AngryStone": ("_fight_target",),
    "PyroMaul": ("_slam_target",),
    "PyroRomp": ("_fight_target",),
    "RivSnatch": ("_fight_target",),
    "ClearCorpse": ("_clear_target",),
    "SeekWarmth": ("_warm_goal_obj",),
    "StormSeekShelter": ("_storm_goal_obj",),
    "ShelterSleep": ("_storm_goal_obj",),
    "Swimming": ("_swim_goal",),
    "HPole": ("_hp_goal_obj", "_hp_step_obj"),
    "SeekHPole": ("_hp_goal_obj",),
    "PoleClimb": ("_hp_goal_obj", "_poleclimb_pole"),
    "CeilingHang": ("_air_pole_target",),
    "RelocateToWall": ("_air_pole_target",),
    "Airborne": ("_air_pole_target", "_zerog_target"),
    "EatCob": ("_cob",),
    "SeedCob": ("_cob",),
    "TongueClimb": (),
}

# 状态 → 该态挂在控制器对象上的目标（取食器 / 抓虫器 / 猎虫器）
_STATE_CTRL = {
    "FetchFruit": "fetch",
    "CatchFly": "flycatch",
    "HuntFly": "flyhunt",
}

# 光标类：目标不是实体，直接给词
_CURSOR_STATES = ("ChaseCursor", "CursorLick")


def _target_obj(beh):
    """行为对象 → 当前目标（拿不到就 None）。"""
    st = getattr(beh, "state", None)
    if st in _CURSOR_STATES:
        return "cursor"
    for name in _STATE_TARGET.get(st, ()):
        o = getattr(beh, name, None)
        if o is not None:
            return o
    holder = _STATE_CTRL.get(st)
    if holder:
        h = getattr(beh, holder, None)
        v = getattr(h, "target", None) if h is not None else None
        if v is not None:
            return v
    # 不扫兜底：别的态留下的残留目标会被当成现在追的东西，比空着更误导。
    return None


def _peer_name(pet, peers):
    try:
        from ..ui.catmenu import pet_label
        return pet_label(pet, peers) if peers else pet_label(pet, [pet])
    except Exception:
        return str(getattr(pet, "variant", "") or "")


def _describe(obj, beh, peers):
    """目标对象 → 中文/英文短词。认不出来就给空串（宁可不写，别瞎写）。"""
    from ..i18n import t
    if obj is None:
        return ""
    if obj == "cursor":
        return t("tg_cursor")
    if isinstance(obj, (tuple, list)):
        return t("tg_place")
    if isinstance(obj, (int, float)):
        return t("tg_place")
    if obj is getattr(beh, "body", None) or obj is getattr(beh, "win", None):
        return ""                                   # 指向自己不算目标
    # 同伴（猫 / 幼崽）：PetUnit 有 .variant + .body
    if (hasattr(obj, "variant") and getattr(obj, "body", None) is not None
            and getattr(obj, "behavior", None) is not None):
        dead = bool(getattr(obj.body, "dead", False))
        name = _peer_name(obj, peers)
        key = "tg_peer_dead" if dead else "tg_peer"
        return t(key) + ((" · " + name) if name else "")
    from ..world.lizard import Lizard
    from ..world.batfly import BatFly
    from ..world.squidcada import Squidcada
    from ..world.needleworm import NeedleWorm
    from ..world.scavenger import Scavenger
    from ..world.seedcob import Seed, SeedCob
    from ..world.slimemold import SlimeMold
    from ..world.karmaflower import KarmaFlower
    from ..world.fruit import Fruit
    from ..world.spear import Spear
    from ..world.stone import Stone
    from ..world.pearl import Pearl
    from ..world.lamp import Lamp
    from ..world.pole import Pole
    from ..world.shelter import Shelter
    from ..world.hpole import HPoleController
    dead_suffix = t("tg_corpse") if getattr(obj, "dead", False) else ""
    for cls, key in ((Shelter, "tg_shelter"),
                     (Lizard, "tg_lizard"), (Scavenger, "tg_scavenger"),
                     (NeedleWorm, "tg_needleworm"), (Squidcada, "tg_squidcada"),
                     (BatFly, "tg_batfly"), (SeedCob, "tg_cob"), (Seed, "tg_cob"),
                     (KarmaFlower, "tg_flower"), (Fruit, "tg_fruit"),
                     (SlimeMold, "tg_slimemold"), (Lamp, "tg_lamp"),
                     (Pearl, "tg_pearl"), (Spear, "tg_spear"), (Stone, "tg_stone"),
                     (Pole, "tg_pole"), (HPoleController, "tg_hpole")):
        if isinstance(obj, cls):
            return t(key) + dead_suffix
    return ""


def target_text(beh, peers=None) -> str:
    """行为对象 → 「目标是什么」的中/英文案；没有目标返回空串。"""
    if beh is None:
        return ""
    try:
        return _describe(_target_obj(beh), beh, list(peers) if peers else None)
    except Exception:
        return ""


def status_pair(beh, peers=None):
    """状态面板一次给两段：(在做什么, 目标是什么)。"""
    if beh is None:
        return "", ""
    return status_text(beh), target_text(beh, peers)
