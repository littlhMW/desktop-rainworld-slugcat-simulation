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
    "app_title":      {"zh": "桌面雨世界-蛞蝓猫模拟", "en": "Desktop Rain World — Slugcat Simulation"},

    # —— setup_panel：首次导入面板 ——
    "setup_importing":   {"zh": "正在导入素材…", "en": "Importing assets…"},
    "setup_hint_init":   {"zh": "首次启动需读取游戏素材，请稍候",
                          "en": "First launch needs to import game assets, please wait"},
    "setup_hint_busy":   {"zh": "首次启动需读取游戏素材，请稍候。之后无需重复导入",
                          "en": "First launch imports game assets. This is only needed once"},
    "setup_hint_error":  {"zh": "请选择 RainWorld 文件夹，里面应有 RainWorld.exe 和 RainWorld_Data",
                          "en": "Select the RainWorld folder containing RainWorld.exe and RainWorld_Data"},
    "setup_quit":        {"zh": "退出", "en": "Quit"},
    "setup_pick":        {"zh": "选择 RainWorld 文件夹", "en": "Select RainWorld folder"},
    "setup_unexpected":  {"zh": "导入时发生意外错误：{e}", "en": "Unexpected error during import: {e}"},

    # —— tabbar：图标盘 tooltip ——
    "tip_vpole":   {"zh": "竖杆", "en": "Vertical pole"},
    "tip_hpole":   {"zh": "横杆", "en": "Horizontal pole"},
    "tip_pole":    {"zh": "杆", "en": "Pole"},
    "tip_wall":    {"zh": "墙壁", "en": "Wall"},
    "tip_fruit":   {"zh": "果子", "en": "Fruit"},
    "tip_stone":   {"zh": "石头", "en": "Stone"},
    "tip_lamp":    {"zh": "灯笼", "en": "Lantern"},
    "tip_slimemold": {"zh": "黏菌", "en": "Slime mold"},
    "tip_batfly":  {"zh": "蝙蝠", "en": "Batfly"},
    "tip_lizard":  {"zh": "蜥蜴", "en": "Lizard"},
    "tip_squidcada": {"zh": "蝉乌贼", "en": "Squidcada"},
    "tip_needleworm": {"zh": "面条蝇", "en": "Needleworm"},
    "tip_scavenger": {"zh": "拾荒者", "en": "Scavenger"},
    "tip_pearl":   {"zh": "珍珠", "en": "Pearl"},
    "tip_spear":   {"zh": "矛", "en": "Spear"},
    "tip_seedcob": {"zh": "爆米花", "en": "Popcorn plant"},
    "tip_karmaflower": {"zh": "业力花", "en": "Karma flower"},
    "tip_slugpup": {"zh": "猫崽", "en": "Slugpup"},
    "tip_clear":   {"zh": "清除所有实体", "en": "Clear all entities"},
    "tip_shelter": {"zh": "庇护所", "en": "Shelter"},

    # —— settings：自然生成生物列表 ——
    "settings_spawn_section": {"zh": "自然生成", "en": "Natural spawn"},
    "settings_spawn_period": {"zh": "生成间隔", "en": "Spawn interval"},
    "settings_spawn_period_val": {"zh": "{n} 秒", "en": "{n}s"},
    "settings_spawn_period_tip": {"zh": "所有勾选的生物共用此间隔；数值越小，生成越频繁。",
                                  "en": "All selected creatures share this interval; shorter intervals spawn more often."},
    "tip_erase":   {"zh": "删除", "en": "Erase"},

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
                     "en": "Right-click a cat or click its row"},

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
    "ctrlhud_keys":         {"zh": "{move} 移动，{jump} 跳跃；S 长按睡眠；右键拾取，左键投掷",
                             "en": "{move} move, {jump} jump; hold S to sleep; right-click pick up, left-click throw"},

    # —— 设置窗 ——
    "settings_title":        {"zh": "设置", "en": "Settings"},
    "settings_cats_section": {"zh": "蛞蝓猫阵容", "en": "Slugcat roster"},
    "settings_add":          {"zh": "添加", "en": "Add"},
    "settings_remove":       {"zh": "移除", "en": "Remove"},
    "settings_max_pets":     {"zh": "最多 10 只", "en": "At most 10 cats"},
    "settings_min_pets":     {"zh": "至少保留 1 只", "en": "Keep at least 1 cat"},
    "settings_add_none":     {"zh": "添加失败（详见 error.log）",
                              "en": "Could not add cat (see error.log)"},
    "settings_add_failed":   {"zh": "添加{variant}失败：{why}",
                              "en": "Could not add {variant}: {why}"},
    "settings_remove_confirm": {"zh": "确定移除 {name}？", "en": "Remove {name}?"},
    "settings_env_section":  {"zh": "环境效果", "en": "Environment"},
    "settings_mouse_section": {"zh": "鼠标权限", "en": "Mouse permissions"},
    "settings_mouse_interaction": {"zh": "允许蛞蝓猫与鼠标互动",
                                    "en": "Allow slugcats to interact with the cursor"},
    "settings_mouse_interaction_tip": {
        "zh": "允许抓取、击落、攀爬、攻击或舔舐鼠标。",
        "en": "Allows grabbing, knocking down, climbing, attacking or licking the cursor."},
    "settings_mouse_attention": {"zh": "允许蛞蝓猫注意鼠标",
                                  "en": "Allow slugcats to notice the cursor"},
    "settings_mouse_attention_tip": {
        "zh": "允许看向和追逐鼠标；关闭后 AI 不会把鼠标作为目标。",
        "en": "Allows looking at and chasing the cursor; off removes it from AI goals."},
    "settings_mouse_passthrough": {"zh": "允许鼠标穿透桌宠窗口",
                                    "en": "Allow the cursor to pass through the pet window"},
    "settings_mouse_passthrough_tip": {
        "zh": "开启后桌宠区域完全穿透，只能点击桌面内容；关闭后仅桌宠部件和面板接收鼠标，空白处仍可点击桌面。",
        "en": "When enabled, the entire pet area passes through to desktop content; off keeps pet parts and panels clickable while blank areas still pass through."},
    "settings_pause_world": {"zh": "暂停世界", "en": "Pause world"},
    "settings_pause_world_tip": {
        "zh": "暂停 AI、物理、环境和雨循环；设置与状态面板仍可查看。",
        "en": "Pause AI, physics, environment and rain cycles while keeping the UI visible."},
    "settings_env_none":     {"zh": "无", "en": "None"},
    "settings_snow":         {"zh": "暴风雪", "en": "Blizzard"},
    "settings_zerog":        {"zh": "无重力", "en": "Zero gravity"},
    "settings_water":        {"zh": "涨水", "en": "Flood"},
    "settings_storm_env":    {"zh": "暴雨", "en": "Storm"},

    # —— settings：雨循环 ——
    "settings_storm_section":   {"zh": "雨循环", "en": "Rain cycle"},
    "settings_storm_enable":    {"zh": "启用雨循环", "en": "Enable rain cycle"},
    "settings_storm_block":     {"zh": "暴雨期间拦截桌面点击",
                                 "en": "Block desktop clicks during storms"},
    "settings_storm_block_tip": {
        "zh": "暴雨期间阻止点击穿透到其他窗口；任务栏不受影响。",
        "en": "Prevents storm clicks from reaching other windows; the taskbar is unaffected."},
    "settings_storm_lethal":    {"zh": "暴雨期间点击随机杀死一只蛞蝓猫",
                                 "en": "Storm clicks kill one random slugcat"},
    "settings_storm_lethal_tip": {
        "zh": "暴雨期间每次点击随机杀死一只蛞蝓猫，包括庇护所内的个体。",
        "en": "Each click during a storm kills one random slugcat, including those in shelters."},
    "settings_storm_focus_minutes":   {"zh": "平静（分钟）", "en": "Calm (minutes)"},
    "settings_storm_warning_minutes": {"zh": "征兆（分钟）", "en": "Omen (minutes)"},
    "settings_storm_sleep_minutes":   {"zh": "暴雨（分钟）", "en": "Storm (minutes)"},
    "settings_storm_apply":     {"zh": "应用时长", "en": "Apply durations"},

    # —— settings：AI 行为 ——
    "settings_ai_section":        {"zh": "战斗规则", "en": "Combat rules"},
    "settings_friendly_fire_protect": {"zh": "启用友军伤害保护",
                                       "en": "Friendly-fire protection"},
    "settings_friendly_fire_protect_tip": {
        "zh": "启用后，同伴免疫矛和石头造成的伤害与眩晕。",
        "en": "Allies ignore spear and stone damage and stun when enabled."},
    "settings_meow_section": {"zh": "猫叫音频", "en": "Meow audio"},
    "settings_meow_enable": {"zh": "启用猫叫（需 Push To Meow）", "en": "Enable meows (Push To Meow required)"},
    "settings_meow_tip": {
        "zh": "需订阅并下载 Steam 创意工坊的 Push To Meow。叫声概率由饥饿、危险和活动状态决定。",
        "en": "Subscribe to and download Push To Meow from Steam Workshop. Hunger, danger and activity affect meow chance."},
    "settings_meow_missing": {
        "zh": "未检测到 Push To Meow 音频，请先订阅并下载创意工坊项目。",
        "en": "Push To Meow audio was not found. Subscribe to and download the Workshop item first."},
    "settings_meow_ready": {"zh": "已找到猫叫素材", "en": "Meow audio found"},
    "settings_meow_volume": {"zh": "音量", "en": "Volume"},
    "settings_meow_volume_val": {"zh": "{n}%", "en": "{n}%"},
    "settings_waa_enable": {"zh": "waa ~", "en": "waa ~"},
    "settings_waa_tip": {
        "zh": "蛞蝓猫将发出强大而具有魄力的叫声威慑敌人。",
        "en": "The slugcat emits a powerful, commanding call to intimidate enemies."},
    "settings_waa_missing": {"zh": "未找到本机《雨世界》游戏资源。", "en": "Local Rain World game resources were not found."},
    "settings_waa_idle": {"zh": "勾选后从本机游戏准备音轨。", "en": "Enable to prepare audio from your local game."},
    "settings_waa_preparing": {"zh": "正在从本机游戏准备音轨…", "en": "Preparing audio from your local game..."},
    "settings_waa_ready": {"zh": "本机音轨已就绪。", "en": "Local audio is ready."},
    "settings_waa_failed": {"zh": "音轨准备失败，悬停查看详情。", "en": "Audio preparation failed; hover for details."},
    "settings_sfx_section": {"zh": "世界音效", "en": "World sounds"},
    "settings_sfx_enable": {"zh": "启用世界与动作音效", "en": "Enable world and action sounds"},
    "settings_sfx_tip": {"zh": "控制雨声、蜥蜴咬合及动作反馈等音效；不影响猫叫。", "en": "Controls rain, lizard bites and action sounds; meows have separate controls."},
    "settings_sfx_volume": {"zh": "音量", "en": "Volume"},
    "settings_sfx_volume_val": {"zh": "{n}%", "en": "{n}%"},
    "settings_hud_section":       {"zh": "状态面板", "en": "Status panel"},
    "settings_show_hud":     {"zh": "显示状态面板", "en": "Show status panel"},
    "settings_pick_title":   {"zh": "选择皮", "en": "Pick a variant"},
    "settings_pick_cat":     {"zh": "选择要添加的蛞蝓猫", "en": "Choose a slugcat to add"},
    "settings_ok":           {"zh": "确定", "en": "OK"},
    "settings_cancel":       {"zh": "取消", "en": "Cancel"},


    # —— HUD：面板标题与关闭按钮 ——
    "hud_title":     {"zh": "蛞蝓猫状态", "en": "Slugcat status"},
    "hud_resize_tip": {"zh": "拖动右下角可调整面板大小",
                       "en": "Drag the corner to resize the panel"},
    "hud_close_tip": {"zh": "关闭面板（Ctrl+Alt+H 可再打开）",
                      "en": "Reopen with Ctrl+Alt+H"},

    # —— HUD：名字旁的实时状态词（behavior/status.py 出 key）——
    "st_idle": {"zh": "待机", "en": "Idle"},
    "st_wander": {"zh": "漫游", "en": "Wandering"},
    "st_cool_down": {"zh": "恢复体力", "en": "Recovering"},
    "st_make_way": {"zh": "让路", "en": "Making way"},
    "st_dodge_shot": {"zh": "规避投掷物", "en": "Evading a projectile"},
    "st_scold": {"zh": "训斥", "en": "Scolding"},
    "st_point": {"zh": "指向", "en": "Pointing"},
    "st_pet": {"zh": "抚摸", "en": "Petting"},
    "st_pat": {"zh": "拍拍", "en": "Patting"},
    "st_revive": {"zh": "救活同伴", "en": "Reviving ally"},
    "st_wake_peer": {"zh": "摇醒同伴", "en": "Waking a peer"},
    "st_gift": {"zh": "送礼", "en": "Giving a gift"},
    "st_watch": {"zh": "围观", "en": "Watching"},
    "st_crouch_walk": {"zh": "匍匐潜行", "en": "Crouch-walking"},
    "st_chase_cursor": {"zh": "追鼠标", "en": "Chasing cursor"},
    "st_fetch": {"zh": "取食", "en": "Getting food"},
    "st_hunt_live": {"zh": "捕猎", "en": "Hunting"},
    "st_item_play": {"zh": "玩耍", "en": "Playing"},
    "st_help_feed": {"zh": "帮同伴取食", "en": "Helping ally"},
    "st_cover": {"zh": "掩护同伴", "en": "Taking cover"},
    "st_flee": {"zh": "逃跑", "en": "Fleeing"},
    "st_crawl": {"zh": "匍匐躲避", "en": "Crawling away"},
    "st_fight": {"zh": "应对威胁", "en": "Responding to threat"},
    "st_seek_spear": {"zh": "找矛", "en": "Looking for a spear"},
    "st_pole_climb": {"zh": "爬杆", "en": "Climbing a pole"},
    "st_hpole": {"zh": "横杆上", "en": "On beam"},
    "st_seek_hpole": {"zh": "找横杆", "en": "Seeking a beam"},
    "st_ceiling": {"zh": "挂顶", "en": "Ceiling cling"},
    "st_to_wall": {"zh": "去墙边", "en": "Heading to the wall"},
    "st_tongue": {"zh": "用舌攀爬", "en": "Tongue climbing"},
    "st_lick_cursor": {"zh": "舔鼠标", "en": "Licking the cursor"},
    "st_ascend": {"zh": "超度", "en": "Ascending"},
    "st_angry_stone": {"zh": "砸石头", "en": "Throwing stones"},
    "st_maul": {"zh": "撕咬", "en": "Mauling"},
    "st_romp": {"zh": "爆跳", "en": "Blast-jumping"},
    "st_slam": {"zh": "震击", "en": "Slam"},
    "st_snatch": {"zh": "抢夺", "en": "Snatching"},
    "st_flip": {"zh": "后空翻", "en": "Backflipping"},
    "st_clear_corpse": {"zh": "拖尸", "en": "Hauling corpse"},
    "st_sleep": {"zh": "睡觉", "en": "Sleeping"},
    "st_lie": {"zh": "趴着", "en": "Lying down"},
    "st_wake_up": {"zh": "起身", "en": "Getting up"},
    "st_stunned": {"zh": "眩晕", "en": "Stunned"},
    "st_dragged": {"zh": "被拎着", "en": "Held"},
    "st_dead": {"zh": "死亡", "en": "Dead"},
    "st_air": {"zh": "空中", "en": "Airborne"},
    "st_swim": {"zh": "游泳", "en": "Swimming"},
    "st_warmth": {"zh": "取暖", "en": "Warming up"},
    "st_storm_seek": {"zh": "回庇护所", "en": "Returning to shelter"},
    "st_shelter_sleep": {"zh": "庇护所睡觉", "en": "Shelter sleep"},
    "st_other": {"zh": "处理中", "en": "Processing"},
    # —— HUD：状态第二段「目标是什么」（behavior/status.py 出词）——
    "tg_cursor": {"zh": "鼠标", "en": "Cursor"},
    "tg_place": {"zh": "位置", "en": "Spot"},
    "tg_peer": {"zh": "同伴", "en": "Ally"},
    "tg_peer_dead": {"zh": "尸体", "en": "Corpse"},
    "tg_corpse": {"zh": "尸体", "en": "corpse"},
    "tg_lizard": {"zh": "蜥蜴", "en": "Lizard"},
    "tg_scavenger": {"zh": "拾荒者", "en": "Scavenger"},
    "tg_needleworm": {"zh": "面条蝇", "en": "Needleworm"},
    "tg_squidcada": {"zh": "蝉乌贼", "en": "Squidcada"},
    "tg_batfly": {"zh": "蝙蝠蝇", "en": "BatFly"},
    "tg_cob": {"zh": "爆米花", "en": "Popcorn plant"},
    "tg_flower": {"zh": "业力花", "en": "Karma flower"},
    "tg_fruit": {"zh": "果子", "en": "Fruit"},
    "tg_slimemold": {"zh": "黏菌", "en": "Slime mold"},
    "tg_lamp": {"zh": "灯笼", "en": "Lantern"},
    "tg_pearl": {"zh": "珍珠", "en": "Pearl"},
    "tg_spear": {"zh": "矛", "en": "Spear"},
    "tg_stone": {"zh": "石头", "en": "Stone"},
    "tg_pole": {"zh": "杆子", "en": "Pole"},
    "tg_hpole": {"zh": "横杆", "en": "Beam"},
    "tg_shelter": {"zh": "庇护所", "en": "Shelter"},
    "hud_target": {"zh": "目标", "en": "Target"},
    # —— HUD：最终意图（状态可能经过杆、墙等中间步骤） ——
    "goal_shelter": {"zh": "进入庇护所", "en": "Enter shelter"},
    "goal_wait_storm": {"zh": "等待暴雨结束", "en": "Wait out the storm"},
    "goal_safety": {"zh": "到达安全位置", "en": "Reach safety"},
    "goal_clear_path": {"zh": "清出通道", "en": "Clear the path"},
    "goal_warm": {"zh": "恢复体温", "en": "Restore body heat"},
    "goal_feed_self": {"zh": "满足进食需求", "en": "Find food"},
    "goal_feed_peer": {"zh": "帮助同伴进食", "en": "Feed an ally"},
    "goal_karma": {"zh": "取得业力花", "en": "Get a karma flower"},
    "goal_reach_height": {"zh": "到达目标高度", "en": "Reach the target height"},
    "goal_defend": {"zh": "解除威胁", "en": "Neutralize the threat"},
    "goal_repel_target": {"zh": "解除威胁：{target}", "en": "Neutralize: {target}"},
    "goal_revive": {"zh": "救活同伴", "en": "Revive an ally"},
    "goal_revive_target": {"zh": "救活：{target}", "en": "Revive: {target}"},
    "goal_wake_peer": {"zh": "唤醒同伴", "en": "Wake an ally"},
    "goal_befriend": {"zh": "与蜥蜴建立关系", "en": "Befriend a lizard"},
    "goal_protest": {"zh": "解决社交冲突", "en": "Resolve a social conflict"},
    "goal_social": {"zh": "与同伴互动", "en": "Interact with an ally"},
    "goal_clear_corpse": {"zh": "移走尸体", "en": "Clear the corpse"},
    "goal_play_cursor": {"zh": "与鼠标互动", "en": "Interact with the cursor"},
    "goal_play": {"zh": "进行活动", "en": "Perform the activity"},
    "goal_rest": {"zh": "休息", "en": "Rest"},
    "goal_surface": {"zh": "浮到水面", "en": "Reach the surface"},
    "goal_ascend": {"zh": "完成超度", "en": "Complete ascension"},
    # —— tabbar：打开设置 ——
    "btn_open_settings": {"zh": "打开设置", "en": "Open settings"},

    # —— main：单实例 ——
    "already_running": {"zh": "桌面雨世界-蛞蝓猫模拟已在运行", "en": "Desktop Rain World — Slugcat Simulation is already running"},

    # —— main：托盘菜单 / 通知 ——
    "tray_settings": {"zh": "设置", "en": "Settings"},
    "tray_hud":     {"zh": "显示/隐藏状态面板 (Ctrl+Alt+H)", "en": "Show/Hide status panel (Ctrl+Alt+H)"},
    "tray_mouse_section": {"zh": "鼠标权限", "en": "Mouse permissions"},
    "tray_mouse_interaction": {"zh": "蛞蝓猫与鼠标互动", "en": "Slugcat interaction with cursor"},
    "tray_mouse_attention": {"zh": "蛞蝓猫注意鼠标", "en": "Slugcats notice cursor"},
    "tray_mouse_passthrough": {"zh": "鼠标穿透桌宠窗口", "en": "Cursor passes through pet window"},
    "tray_pause_world": {"zh": "暂停世界", "en": "Pause world"},
    "tray_quit":    {"zh": "退出程序", "en": "Quit program"},
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
