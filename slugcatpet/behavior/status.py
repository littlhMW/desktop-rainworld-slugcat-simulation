# -*- coding: utf-8 -*-
"""行为态 → 给人看的一行短状态词（状态面板里显示在名字旁边）。

单一事实源：状态名在本仓库只有 behavior/fsm.py 的 self.state 一处；
这里只做「状态 → i18n key」的映射，文案在 i18n._STR 的 st_* 组。
新增状态忘了登记也不会崩：落到 st_other。
"""
from __future__ import annotations

# 主状态 → i18n key
# 当前动作只描述正在执行的步骤；最终意图由 target_text 独立给出。
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
    "Slam": "st_slam",
    "RivSnatch": "st_snatch",
    "RivFlip": "st_flip",
    "EatCob": "st_hunt_live",
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


# ── 状态面板第二段：最终意图 ──


def _peer_name(pet, peers):
    try:
        from ..ui.catmenu import pet_label
        return pet_label(pet, peers) if peers else pet_label(pet, [pet])
    except Exception:
        return str(getattr(pet, "variant", "") or "")


def _threat_name(obj):
    """只为战斗目标取物种名，不把路径中间对象当成意图。"""
    from ..i18n import t
    if obj is None:
        return ""
    from ..world.lizard import Lizard
    from ..world.batfly import BatFly
    from ..world.squidcada import Squidcada
    from ..world.needleworm import NeedleWorm
    from ..world.scavenger import Scavenger
    for cls, key in ((Lizard, "tg_lizard"), (Scavenger, "tg_scavenger"),
                     (NeedleWorm, "tg_needleworm"), (Squidcada, "tg_squidcada"),
                     (BatFly, "tg_batfly")):
        if isinstance(obj, cls):
            return t(key)
    return ""


def target_text(beh, peers=None) -> str:
    """行为对象 → 本次行为想达成的结果，而不是路上接触的物体。"""
    if beh is None:
        return ""
    try:
        from ..i18n import t
        st = getattr(beh, "state", None)
        peers = list(peers) if peers else None

        if st in ("Dead", "Dragged", "Stunned"):
            return ""
        if st == "StormSeekShelter":
            return t("goal_shelter")
        if st == "ShelterSleep":
            return t("goal_wait_storm")
        if st in ("FleeLizard", "CrawlAway", "DodgeShot", "CoverAlly"):
            return t("goal_safety")
        if st == "MakeWay":
            return t("goal_clear_path")
        if st == "SeekWarmth":
            return t("goal_warm")
        if st in ("FetchFruit", "CatchFly", "HuntFly", "EatCob"):
            return t("goal_karma" if getattr(beh, "_fetch_karma", False)
                     and st == "FetchFruit" else "goal_feed_self")
        if st == "HelpFeed":
            return t("goal_feed_peer")
        if st in ("SeekHPole", "HPole", "PoleClimb", "Airborne"):
            food = (getattr(beh, "_hp_goal_obj", None)
                    or getattr(beh, "_hp_step_obj", None)
                    or getattr(beh, "_hp_jump_goal", None))
            if food is not None:
                return t("goal_feed_self")
            if st == "PoleClimb" and getattr(beh, "_flee_from", None) is not None:
                return t("goal_safety")
            if st in ("SeekHPole", "PoleClimb"):
                return t("goal_reach_height")
            return ""
        if st in ("CeilingHang", "RelocateToWall", "TongueClimb"):
            return t("goal_safety") if getattr(beh, "water_threat", lambda: 0.0)() > 0.5 else t("goal_reach_height")
        if st == "FightThreat":
            obj = _threat_name(getattr(beh, "_fight_target", None))
            return t("goal_repel_target", target=obj) if obj else t("goal_defend")
        if st == "Slam":
            obj = _threat_name(getattr(beh, "_slam_target", None))
            return t("goal_repel_target", target=obj) if obj else t("goal_defend")
        if st in ("AngryStone", "PyroMaul"):
            return t("goal_defend")
        if st == "Socialize":
            kind = getattr(beh, "_social_kind", None)
            peer = getattr(beh, "_social_target", None)
            if kind == "revive":
                name = _peer_name(peer, peers) if peer is not None else ""
                return t("goal_revive_target", target=name) if name else t("goal_revive")
            if kind == "wake":
                return t("goal_wake_peer")
            if kind == "gift":
                return t("goal_befriend")
            if kind == "protest" or kind == "scold":
                return t("goal_protest")
            return t("goal_social")
        if st == "ClearCorpse":
            return t("goal_clear_corpse")
        if st in ("ChaseCursor", "CursorLick", "RivSnatch"):
            return t("goal_play_cursor")
        if st == "ItemPlay":
            return t("goal_play")
        if st in ("Sleep", "LieDown"):
            return t("goal_rest")
        if st == "Swimming":
            return t("goal_surface")
        if st == "ScoldBlocker":
            return t("goal_clear_path")
        if st in ("PyroRomp", "RivFlip"):
            return t("goal_play")
        if st == "Ascension":
            return t("goal_ascend")
        if st in ("IdleStand", "PostThrowWander", "PostThrowStand", "WakeSequence"):
            return ""
        return ""
    except Exception:
        return ""


def status_pair(beh, peers=None):
    """状态面板一次给两段：(当前动作, 最终意图)。"""
    if beh is None:
        return "", ""
    return status_text(beh), target_text(beh, peers)
