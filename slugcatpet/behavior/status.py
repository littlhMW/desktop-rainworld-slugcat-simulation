# -*- coding: utf-8 -*-
"""行为态 → 给人看的一行短状态词（状态面板里显示在名字旁边）。

单一事实源：状态名在本仓库只有 behavior/fsm.py 的 self.state 一处；
这里只做「状态 → i18n key」的映射，文案在 i18n._STR 的 st_* 组。
新增状态忘了登记也不会崩：落到 st_other。
"""
from __future__ import annotations

# 主状态 → i18n key
_STATES = {
    "IdleStand": "st_idle",
    "PostThrowWander": "st_wander",
    "PostThrowStand": "st_cool_down",
    "MakeWay": "st_make_way",
    "ScoldBlocker": "st_scold",
    "ChaseCursor": "st_chase_cursor",
    "FetchFruit": "st_fetch",
    "CatchFly": "st_catch_fly",
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
    "Ascension": "st_ascend",
    "AngryStone": "st_angry_stone",
    "PyroMaul": "st_maul",
    "PyroRomp": "st_romp",
    "RivSnatch": "st_snatch",
    "RivFlip": "st_flip",
    "EatCob": "st_cob",
    "SeedCob": "st_cob",
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
        return "st_hunt" if _armed(beh) else "st_seek_spear"
    if st == "Socialize":
        k = _SOCIAL.get(getattr(beh, "_social_kind", None))
        if k is not None:
            return k
    return _STATES.get(st, "st_other")


def status_text(beh) -> str:
    """行为对象 → 当前状态的中/英文案。"""
    from ..i18n import t
    return t(status_key(beh))
