"""界面文案中英两套 + 运行期取串。语言由 env / exe 名定，两个打包 exe 各自定死。"""
from __future__ import annotations
import os
import sys
from pathlib import Path


def _detect_lang() -> str:
    env = os.environ.get("SLUGCATPET_LANG", "").strip().lower()
    if env in ("zh", "en"):
        return env
    if getattr(sys, "frozen", False) and Path(sys.executable).stem.lower().endswith("-en"):
        return "en"
    return "zh"


LANG = _detect_lang()

_STR = {
    # —— 通用 / 产品名 ——
    "app_title":      {"zh": "蛞蝓猫桌宠", "en": "Slugcat Pet"},

    # —— setup_panel：首次导入面板 ——
    "setup_importing":   {"zh": "正在导入素材…", "en": "Importing assets…"},
    "setup_hint_init":   {"zh": "首次启动需从你的游戏读取画面，请稍候",
                          "en": "First launch needs to read the picture from your game, please wait"},
    "setup_hint_busy":   {"zh": "首次启动需从你的游戏读取素材，请稍候。未来不再需要读取",
                          "en": "First launch needs to read assets from your game, please wait. Won't be needed again in the future"},
    "setup_hint_error":  {"zh": "点【选择 RainWorld 文件夹】手动指定：选中的文件夹里应能看到 RainWorld.exe 和 RainWorld_Data 文件夹",
                          "en": "Click [Select RainWorld folder] to specify manually: the chosen folder should contain RainWorld.exe and the RainWorld_Data folder"},
    "setup_quit":        {"zh": "退出", "en": "Quit"},
    "setup_pick":        {"zh": "选择 RainWorld 文件夹", "en": "Select RainWorld folder"},
    "setup_unexpected":  {"zh": "导入时发生意外错误：{e}", "en": "Unexpected error during import: {e}"},

    # —— tabbar：图标盘 tooltip ——
    "tip_vpole":   {"zh": "放竖杆", "en": "Place vertical pole"},
    "tip_hpole":   {"zh": "放横杆", "en": "Place horizontal pole"},
    "tip_fruit":   {"zh": "放果子", "en": "Place fruit"},
    "tip_stone":   {"zh": "放石头", "en": "Place stone"},
    "tip_lamp":    {"zh": "放灯笼", "en": "Place lantern"},
    "tip_slimemold": {"zh": "放黏菌", "en": "Place slime mold"},
    "tip_batfly":  {"zh": "放蝙蝠", "en": "Place batfly"},
    "tip_lizard":  {"zh": "放蜥蜴", "en": "Place lizard"},
    "tip_squidcada": {"zh": "放蝉乌贼", "en": "Place squidcada"},
    "tip_needleworm": {"zh": "放面条蝇", "en": "Place needleworm"},
    "tip_scavenger": {"zh": "放拾荒者", "en": "Place scavenger"},
    "tip_pearl":   {"zh": "放珍珠", "en": "Place pearl"},
    "tip_spear":   {"zh": "放矛", "en": "Place spear"},
    "tip_seedcob": {"zh": "放爆米花", "en": "Place popcorn plant"},
    "tip_karmaflower": {"zh": "放业力花", "en": "Place karma flower"},
    "tip_slugpup": {"zh": "放猫崽", "en": "Place slugpup"},
    "tip_clear":   {"zh": "清除可交互实体", "en": "Clear placed items"},
    "tip_shelter": {"zh": "放庇护所", "en": "Place shelter"},

    # —— settings：自然生成生物列表 ——
    "settings_spawn_section": {"zh": "自然生成", "en": "Natural spawn"},
    "tip_erase":   {"zh": "删除模式（点谁删谁）", "en": "Erase mode (click to delete)"},

    # —— 左下角暴雨 HUD ——
    "hud_rain_cycle":  {"zh": "平静期", "en": "Calm"},
    "hud_rain":        {"zh": "征兆期", "en": "Omen"},
    "hud_hibernation": {"zh": "暴雨期", "en": "Storm"},
    "hud_starvation":  {"zh": "饥饿", "en": "Starvation"},


    # —— tabbar：toast ——
    "toast_max_fruit":  {"zh": "场上最多 3 个果子", "en": "At most 3 fruits on the field"},
    "toast_max_stone":  {"zh": "场上最多 3 个石头", "en": "At most 3 stones on the field"},
    "toast_max_slimemold": {"zh": "场上最多 3 个黏菌", "en": "At most 3 slime molds on the field"},
    "toast_max_batfly": {"zh": "场上最多 3 只蝙蝠", "en": "At most 3 batflies on the field"},
    "toast_max_lizard": {"zh": "场上最多 2 只蜥蜴", "en": "At most 2 lizards on the field"},
    "toast_max_vpole":  {"zh": "场上最多 2 根竖杆", "en": "At most 2 vertical poles on the field"},
    "toast_max_hpole":  {"zh": "场上最多 2 根横杆", "en": "At most 2 horizontal poles on the field"},
    "toast_no_object":  {"zh": "场上没有物体", "en": "No objects on the field"},

    # —— tabbar：动作按钮 ——
    "btn_quit_app":  {"zh": "退出程序", "en": "Quit program"},

    # —— 杀死确认弹窗（猫菜单「杀死该猫」复用）——
    "dlg_confirm_title":  {"zh": "确认", "en": "Confirm"},
    "dlg_kill_text":      {"zh": "确定要杀死 {name} 吗？", "en": "Are you sure you want to kill {name}?"},
    "dlg_kill_yes":       {"zh": "杀死", "en": "Kill"},
    "dlg_kill_no":        {"zh": "取消", "en": "Cancel"},

    # —— hud：状态面板字段名 ——
    "hud_karma":    {"zh": "业力", "en": "Karma"},
    "hud_stamina":  {"zh": "体力", "en": "Stamina"},
    "hud_satiety":  {"zh": "饱食", "en": "Satiety"},
    "hud_affection":{"zh": "心情", "en": "Mood"},
    "hud_cold":     {"zh": "寒冷", "en": "Cold"},
    "hud_op_hint":  {"zh": "右键蛞蝓猫或点击此行可操作",
                     "en": "Right-click the slugcat or click this row to operate"},

    # —— 皮名（variant 显示名） ——
    # 中文名统一采用官方译名表（僧侣/求生者/溪流/守望者/饕餮/怪猫/猎手/工匠/矛大师/圣徒）
    "variant_monk":       {"zh": "僧侣", "en": "Monk"},
    "variant_survivor":   {"zh": "求生者", "en": "Survivor"},
    "variant_rivulet":    {"zh": "溪流", "en": "Rivulet"},
    "variant_watcher":    {"zh": "守望者", "en": "Watcher"},
    "variant_gourmand":   {"zh": "饕餮", "en": "Gourmand"},
    "variant_inv":        {"zh": "怪猫", "en": "Inv"},
    "variant_hunter":     {"zh": "猎手", "en": "Hunter"},
    "variant_artificer":  {"zh": "工匠", "en": "Artificer"},
    "variant_spearmaster": {"zh": "矛大师", "en": "Spearmaster"},
    "variant_saint":      {"zh": "圣徒", "en": "Saint"},
    "variant_slugpup":    {"zh": "猫崽", "en": "Slugpup"},
    "variant_wip_note": {"zh": "（外观差异待后续）", "en": "(appearance differences TBD)"},

    # —— 猫菜单 ——
    "menu_kill_pet":       {"zh": "杀掉该猫", "en": "Kill this cat"},
    "menu_reset_pet":      {"zh": "重置该猫", "en": "Reset this cat"},
    "menu_reincarnating":  {"zh": "转世中…", "en": "Reincarnating…"},
    "menu_open_settings":  {"zh": "打开设置", "en": "Open settings"},
    "menu_control_pet":    {"zh": "控制该猫", "en": "Control this cat"},
    "menu_exit_control":   {"zh": "退出控制", "en": "Exit control"},

    # —— 控制 HUD ——
    "ctrlhud_title":        {"zh": "控制中：{name}", "en": "Controlling: {name}"},
    "ctrlhud_paused":       {"zh": "已暂停 · 点击继续", "en": "Paused · click to resume"},
    "ctrlhud_exit":         {"zh": "退出控制 (Esc)", "en": "Exit control (Esc)"},
    "ctrlhud_keys":         {"zh": "{move} 移动，{jump} 跳跃",
                             "en": "{move} to move, {jump} to jump"},

    # —— 设置窗 ——
    "settings_title":        {"zh": "设置", "en": "Settings"},
    "settings_cats_section": {"zh": "蛞蝓猫", "en": "Slugcats"},
    "settings_add":          {"zh": "添加", "en": "Add"},
    "settings_remove":       {"zh": "移除", "en": "Remove"},
    "settings_max_pets":     {"zh": "最多 10 只", "en": "At most 10 cats"},
    "settings_min_pets":     {"zh": "至少保留 1 只", "en": "Keep at least 1 cat"},
    "settings_remove_confirm": {"zh": "确定移除 {name}？", "en": "Remove {name}?"},
    "settings_env_section":  {"zh": "环境", "en": "Environment"},
    "settings_env_none":     {"zh": "无", "en": "None"},
    "settings_snow":         {"zh": "暴风雪", "en": "Blizzard"},
    "settings_zerog":        {"zh": "无重力", "en": "Zero gravity"},
    "settings_water":        {"zh": "涨水", "en": "Flood"},
    "settings_storm_env":    {"zh": "暴雨", "en": "Storm"},

    # —— settings：雨循环 ——
    "settings_storm_section":   {"zh": "雨循环", "en": "Rain cycle"},
    "settings_storm_enable":    {"zh": "开启雨循环", "en": "Enable rain cycle"},
    "settings_storm_focus_minutes":   {"zh": "平静期（分钟）", "en": "Calm (minutes)"},
    "settings_storm_warning_minutes": {"zh": "征兆期（分钟）", "en": "Omen (minutes)"},
    "settings_storm_sleep_minutes":   {"zh": "暴雨期（分钟）", "en": "Storm (minutes)"},
    "settings_storm_apply":     {"zh": "应用时长", "en": "Apply durations"},
    "settings_show_hud":     {"zh": "显示状态面板", "en": "Show status panel"},
    "settings_pick_title":   {"zh": "选择皮", "en": "Pick a variant"},
    "settings_pick_cat":     {"zh": "选择要添加的蛞蝓猫", "en": "Choose a slugcat to add"},
    "settings_ok":           {"zh": "确定", "en": "OK"},
    "settings_cancel":       {"zh": "取消", "en": "Cancel"},


    # —— HUD：面板标题与关闭按钮 ——
    "hud_title":     {"zh": "蛞蝓猫状态", "en": "Slugcat status"},
    "hud_close_tip": {"zh": "关闭面板（Ctrl+Alt+H 可再打开）",
                      "en": "Close panel (reopen with Ctrl+Alt+H)"},

    # —— HUD：名字旁的实时状态词（behavior/status.py 出 key）——
    "st_idle": {"zh": "发呆", "en": "Idle"},
    "st_wander": {"zh": "四处走动", "en": "Wandering"},
    "st_cool_down": {"zh": "平静下来", "en": "Cooling down"},
    "st_make_way": {"zh": "让路", "en": "Making way"},
    "st_scold": {"zh": "指指点点", "en": "Point-pointing"},
    "st_point": {"zh": "指向", "en": "Pointing"},
    "st_pet": {"zh": "抚摸", "en": "Petting"},
    "st_pat": {"zh": "拍拍", "en": "Patting"},
    "st_revive": {"zh": "复活同伴", "en": "Reviving a peer"},
    "st_wake_peer": {"zh": "摇醒同伴", "en": "Waking a peer"},
    "st_gift": {"zh": "送礼", "en": "Giving a gift"},
    "st_watch": {"zh": "围观", "en": "Watching"},
    "st_crouch_walk": {"zh": "匍匐潜行", "en": "Sneaking"},
    "st_chase_cursor": {"zh": "追鼠标", "en": "Chasing cursor"},
    "st_fetch": {"zh": "觅食", "en": "Foraging"},
    "st_hunt_live": {"zh": "猎杀", "en": "Hunting"},
    "st_item_play": {"zh": "玩耍", "en": "Playing"},
    "st_help_feed": {"zh": "帮同伴取食", "en": "Feeding a peer"},
    "st_cover": {"zh": "躲在同伴背后", "en": "Taking cover"},
    "st_flee": {"zh": "逃跑", "en": "Fleeing"},
    "st_crawl": {"zh": "匍匐躲开", "en": "Crawling away"},
    "st_fight": {"zh": "准备战斗", "en": "Ready to fight"},
    "st_seek_spear": {"zh": "找矛", "en": "Looking for a spear"},
    "st_pole_climb": {"zh": "爬杆", "en": "Climbing a pole"},
    "st_hpole": {"zh": "抱横杆", "en": "On the beam"},
    "st_seek_hpole": {"zh": "找横杆", "en": "Seeking a beam"},
    "st_ceiling": {"zh": "吊顶", "en": "Hanging from the ceiling"},
    "st_to_wall": {"zh": "去墙边", "en": "Heading to the wall"},
    "st_tongue": {"zh": "荡舌", "en": "Swinging on tongue"},
    "st_lick_cursor": {"zh": "舔鼠标", "en": "Licking the cursor"},
    "st_ascend": {"zh": "超度", "en": "Ascending"},
    "st_angry_stone": {"zh": "砸石头", "en": "Throwing stones"},
    "st_maul": {"zh": "撕咬", "en": "Mauling"},
    "st_romp": {"zh": "爆跳", "en": "Blast-jumping"},
    "st_snatch": {"zh": "抢夺", "en": "Snatching"},
    "st_flip": {"zh": "翻滚", "en": "Rolling"},
    "st_clear_corpse": {"zh": "清理尸体", "en": "Hauling a corpse"},
    "st_sleep": {"zh": "睡觉", "en": "Sleeping"},
    "st_lie": {"zh": "趴着休息", "en": "Resting"},
    "st_wake_up": {"zh": "起床", "en": "Waking up"},
    "st_stunned": {"zh": "昏迷中", "en": "Stunned"},
    "st_dragged": {"zh": "被拎起来了", "en": "Being held"},
    "st_dead": {"zh": "已死亡", "en": "Dead"},
    "st_air": {"zh": "在空中", "en": "Airborne"},
    "st_swim": {"zh": "游泳", "en": "Swimming"},
    "st_warmth": {"zh": "取暖", "en": "Warming up"},
    "st_storm_seek": {"zh": "冲回庇护所", "en": "Running to shelter"},
    "st_shelter_sleep": {"zh": "在庇护所里睡着", "en": "Sleeping in shelter"},
    "st_other": {"zh": "—", "en": "—"},
    # —— HUD：状态第二段「目标是什么」（behavior/status.py 出词）——
    "tg_cursor": {"zh": "鼠标", "en": "the cursor"},
    "tg_place": {"zh": "那个位置", "en": "that spot"},
    "tg_peer": {"zh": "同伴", "en": "a peer"},
    "tg_peer_dead": {"zh": "同伴的尸体", "en": "a peer's body"},
    "tg_corpse": {"zh": "（尸体）", "en": " (corpse)"},
    "tg_lizard": {"zh": "蜥蜴", "en": "a lizard"},
    "tg_scavenger": {"zh": "拾荒者", "en": "a scavenger"},
    "tg_needleworm": {"zh": "面条蝇", "en": "a needleworm"},
    "tg_squidcada": {"zh": "蝉乌贼", "en": "a squidcada"},
    "tg_batfly": {"zh": "蝠蝇", "en": "a batfly"},
    "tg_cob": {"zh": "爆米花", "en": "a popcorn plant"},
    "tg_flower": {"zh": "业力花", "en": "a karma flower"},
    "tg_fruit": {"zh": "果子", "en": "a fruit"},
    "tg_slimemold": {"zh": "黏菌", "en": "a slime mold"},
    "tg_lamp": {"zh": "灯笼", "en": "a lantern"},
    "tg_pearl": {"zh": "珍珠", "en": "a pearl"},
    "tg_spear": {"zh": "矛", "en": "a spear"},
    "tg_stone": {"zh": "石头", "en": "a stone"},
    "tg_pole": {"zh": "杆子", "en": "a pole"},
    "tg_hpole": {"zh": "横杆", "en": "a beam"},
    "tg_shelter": {"zh": "庇护所", "en": "the shelter"},
    "hud_target": {"zh": "目标", "en": "Target"},
    # —— tabbar：打开设置 ——
    "btn_open_settings": {"zh": "打开设置", "en": "Open settings"},

    # —— main：单实例 ——
    "already_running": {"zh": "蛞蝓猫桌宠已在运行", "en": "Slugcat Pet is already running"},

    # —— main：托盘菜单 / 通知 ——
    "tray_settings": {"zh": "设置", "en": "Settings"},
    "tray_hud":     {"zh": "显示/隐藏状态面板 (Ctrl+Alt+H)", "en": "Show/Hide status panel (Ctrl+Alt+H)"},
    "tray_quit":    {"zh": "退出程序", "en": "Quit program"},
    "tray_abort":   {"zh": "中止光标劫持 (Ctrl+Alt+Q)", "en": "Abort cursor hijack (Ctrl+Alt+Q)"},
    "tray_hijack":  {"zh": "允许劫持光标", "en": "Allow cursor hijack"},
    "tray_started": {"zh": "已启动。被超度的光标按 Ctrl+Alt+Q 解除；Ctrl+Alt+X 退出程序。",
                     "en": "Launched. Press Ctrl+Alt+Q to release a salvaged cursor; Ctrl+Alt+X to quit the program."},

    # —— gameassets：导入报错（显示在 setup 面板） ——
    "err_atlas_missing":  {"zh": "未找到游戏图集文件：{res}\n请选择 RainWorld 文件夹（其中应有 RainWorld.exe 和 RainWorld_Data 文件夹）。",
                           "en": "Game atlas file not found: {res}\nPlease select the RainWorld folder (which should contain RainWorld.exe and the RainWorld_Data folder)."},
    "err_no_unitypy":     {"zh": "缺少依赖 UnityPy，请先运行：pip install UnityPy",
                           "en": "Missing dependency UnityPy, please run first: pip install UnityPy"},
    "err_base_fail":      {"zh": "基础图集 rainWorld 提取失败，游戏文件可能损坏或版本不兼容。",
                           "en": "Base atlas rainWorld extraction failed; game files may be corrupted or the version incompatible."},
    "err_msc_missing":    {"zh": "未找到 rainworldmsc 图集——Saint 属于 Downpour(More Slugcats) DLC，需要在 Steam 拥有该 DLC 才能导入。",
                           "en": "rainworldmsc atlas not found — Saint belongs to the Downpour (More Slugcats) DLC; you need to own that DLC on Steam to import."},
    "err_ui_fail":        {"zh": "UI 图集 uiSprites 提取失败，游戏文件可能损坏或版本不兼容。",
                           "en": "UI atlas uiSprites extraction failed; game files may be corrupted or the version incompatible."},
    "err_uimsc_missing":  {"zh": "未找到 uispritesmsc 图集——业力图标需 Downpour(More Slugcats) DLC。",
                           "en": "uispritesmsc atlas not found — the karma icons need the Downpour (More Slugcats) DLC."},
    "err_no_install":     {"zh": "未能自动定位 Rain World 安装。\n请点下方按钮，手动选择你的 RainWorld 文件夹。",
                           "en": "Could not automatically locate the Rain World installation.\nPlease click the button below to manually select your RainWorld folder."},
}


def t(key: str, **kw) -> str:
    e = _STR.get(key)
    if e is None:
        return key
    s = e.get(LANG) or e.get("zh") or key
    return s.format(**kw) if kw else s
