# 开发记录归档

此文件保留历史开发阶段的主要修复记录。README 只保留当前使用所需信息。

## 2026-10-01

### R134 · 蜥蜴移动速度按状态分级（巡逻 / 追猎 / 叼东西）

- **问题**（用户：「蜥蜴发呆巡逻，看见猎物，叼东西的速度应该做出区别」）：
  旧口径给巡逻 / 调查 / 叼东西写死了 **绝对** 上限 1.8～2.4 px/tick，与品种无关；
  只有绿蜥（base 6.7）追猎快得过自己巡逻，粉 / 蓝 / 白 / 黄 / 红 / 黑 / 蝾螈 / 青 / 鳗鱼
  全是「慢悠悠地追」。叼东西更荒谬：`clampf(…, ±1.8) * 0.55` 对绿蜥只有 0.99，
  比它自己巡逻的 2.4 还慢。
- **改法：一律「品种基准速度 × 状态系数」**（`world/lizard.py`）：
  - 新增 `_move_base()` = `max(breed.base_speed, MOVE_SPEED_FLOOR)`、
    `_state_speed(mult)` = `_move_base() * mult`。
  - `MOVE_SPEED_FLOOR = 1.5`：焦糖蜥 base 0.65，纯相对量会让它贴地不动；
    下限只保证「走得动」，不改状态之间的先后次序。
  - `PATROL_SPEED = 0.30`、`SNIFF_SPEED = 0.38`（循声调查 / 走上墙点 / 黄蜥分工位 /
    跟朋友）、`HUNT_SPEED = 0.80`（再乘 sprint：惰性 0.55 / 冲刺 1.0）。
  - `CARRY_SPEED_FAC` 0.55 → **0.36**，语义从「绝对速度打折」改成「相对基准的系数」。
  - 13 个调用点全部改用 `_state_speed`：`_route_tick`、盯住对象、`_climb_plan`
    走上墙点 / 起跳后空中修正 / 走去起跳点、`_follow`、`_threat_tick` 逃跑、
    `_injured_tick`、`_noise_tick`、黄蜥分工位 / 跟同伴、`_lunge`、叼东西回巢、
    `_wander` 巡逻。
  - `_plan_for()` 传给 `plan_approach` 的 `base_speed` 也改成 `self._move_base()`，
    否则焦糖蜥会按 0.65 预判跳跃弧、却按 1.5 移动。
- **口径**（12 品种，次序合法）：
  `发呆 0 < 巡逻 < 叼东西 < 调查 < 追猎(惰性) < 追猎(冲刺) < 逃跑`。
  粉蜥 1.23 / 1.48 / 1.56 / 1.80 / 3.28 / 4.59，绿蜥 2.01 / 2.41 / 2.55 / 2.95 /
  5.36 / 7.50（px/tick）。
  实际开跑并不比旧版慢：粉蜥巡逻 300 tick 的 mean|vx| 0.552 → 0.642、
  走过的路程 199 → 231 px —— 旧的绝对上限大多数时候根本没碰到，真正起作用的是
  「离目标多远」那项比例，这也是「速度上看不出区别」的根子。
- **测试**：新增 `work/scratch/e2e_r129.py`（四组：12 品种状态速度严格递增；
  巡逻不再是与品种无关的定值；实跑 `_wander` vs `_lunge`；叼东西 < 本品种追猎），
  已接进 `run_all19.ps1`。
  口径更新 `e2e_r120` ②：「有支撑时身体被 AI 推进」从**净位移 > 30 px** 改为
  **路程 > 40 px 且 mean|vx| > 3 × NO_GRIP_SPEED** —— 蜥蜴巡逻会来回折返，
  净位移取决于随机方向，不能代表「身体有没有被 AI 推进」；新口径在旧代码上
  也通过（旧 0.552 / 新 0.642），且仍能抓住「全身被夹成 0.1 滑行」。
  全量回归 `fails=0`。
- **本轮未做**：用户贴的「蜥蜴与蛞蝓猫双导航系统审计」文档里其余 26 条
  （双寻路器统一、`direct` fallback 无视地形、Dijkstra O(V²) → heapq、
  `SurfaceGraph` 建边加 SpatialGrid、`geometry_version` 拆分等）未动。

### R133 · 蜥蜴软体链弹性下调 + 「昨晚未做项」逐条核对（面条蝇空间索引实证否决）

- **蜥蜴软体链：整体弹性稍降**（用户「太 Q 弹了」）。只动蜥蜴自己的链体常量，不碰
  `core/chunkphys` 的全局默认（那会影响蛞蝓猫）：
  - `SEG_ALIGN` 0.16 → **0.22**：链节「接在父节延长线上」的软约束收敛更快，身体不再一节一节晃回来。
  - `SEG_BEND_K` 0.30 → **0.18**、`SEG_BEND_MAX` 2.4 → **1.5**：转身 / 急停时往转向侧甩的
    冲量及其单节上限一起压小。
  - 实测（新增 `e2e_r128`：直行 60 tick 后一 tick 反向，量躯干各节到体轴的垂距）：
    粉蜥峰值 2.97 → 2.81px、全程最大甩动 50.3 → 45.9px；绿蜥 51.9 → 48.5px；
    蓝蜥 35.5 → 31.0px。尾巴摆动基本保留（停下后仍有 3.3px 摆动），没有调成硬棍。
  - 口径更新 `e2e_r76` A11：链体回到体轴的软约束变快后，2 tick 内朝向变化上限
    20° → 32°，同时**补上「2 tick 后仍必须留有 > 5° 的残余弯曲」** —— 防的还是同一件事：
    旧版是把方向直接写成水平（瞬间摊平 45°），现在是软拉，只是快了些。
- **「昨晚未做项」逐条核对**（结论：只有一项真缺，且实测不该做）：
  - 蜥蜴脚支撑状态机（FindGrip → planted → body support → release → next step）、
    身体轴向转身层（`look_dir` / `desired_move_dir` / `velocity_dir` / `body_dir` / `turn_mode`）、
    AI 避友伤（攻击意图 + 弹道预测 + Planner 重定位：`_shot_path_clear` / `_note_attack_intent` /
    `_avoid_friendly`）、矛大师取食闭环（`_needle_feed_amount` → `body.food_eat`）——
    **都已在前几轮实装**，本轮未重复改。
  - **面条蝇空间索引：做了、量了、撤回**。按计划加了 `SpatialList`（成体×成体、成体×飞行武器
    各一张每 tick 重建的 160px 网格），实测反而更慢，已整段还原：世界只有约 12×7 格，
    `NW_ATTEMPT_DIST = 120` 或「到最近猎物的距离」动辄覆盖半个世界，粗筛省下的遍历抵不过
    建索引 + 拼候选表。实测 `_tick_needleworms()`：网格 2.15 ms/tick vs 全表 2.08 ms/tick。
- **面条蝇真正的热点（本轮实测留档）**：60 只成体的 `_tick_needleworms()` 只花
  **1.8~2.1 ms/tick**（AI 与物理都不是瓶颈）；同一批的 `_draw_needleworms()` 是
  **52 ms/帧**，其中每只每帧 12 条 `ribbon()`（`QPainterPath` + `QLinearGradient` + 抗锯齿填充）
  占约 55%。真要再提速得从「每帧少铺几条渐变多边形」入手（例如 6 条腿并成一次填充，
  腿的色带本来就是 `[body, body, det]`），但那会动外观，未在本轮擅自动。

### R132 · 地形分类断根 + 骨针/矛成杆/杆顶弧/竖直扫掠/蜥蜴比例/猫崽预览/面条蝇性能

- **地形分类断根**（`world/terrain.py`）：以后任何 AI 都不许再「看起来像一条竖线就当杆」。
  - `vpoles()` = 真竖杆 + **窗口自己的左右边缘** `(0,0,hl)` / `(wl,0,hl)`；不再把
    `win.wall_surfaces` 塞进 pole —— 那是「墙壁被当成杆子爬」的根源（用户报）。
  - `walls()` = 庇护所竖实心条 + `win.wall_surfaces` 的可见墙段：**背景墙是墙，不是杆**。
  - `_build_graph`：竖线节点 `stand = can`（`caps.wall_climb / pole_climb`）——不会爬杆的
    品种（绿 / 焦糖蜥）不再把竖线当落脚点（用户报「掉落时判定站在杆子上」）。
- **骨针生命周期**：`needle_tick` 在针被拿起（CARRIED/MOUSE、held_by、stuck_to）时不再褪
  ——旧实现褪尽那一 tick 会把**手里这根**直接标 GONE，就是「点一下（捡起来）就立刻消失」。
  `draw_needle` 褪到 0 且不是杆时**直接不画**（旧实现 clamp 到 0.01，画成几乎纯黑 = 「隐形
  但没有消失」）；钉成杆的针照旧留着（新增 `pinned` 参数）。
- **矛扎墙按角度成杆**（`world/spear.py`）：`pinned` 与「这一撞算不算扎进去」拆开。判定改
  用**矛轴（尾→尖）vs 表面法线**（`EMBED_AXIS_COS`，30° 锥，原版 `ContactPoint == throwDir`
  口径）：尖头正对墙面 → `embed_in_bar` → 杆；横着拍 / 从上往下蹭到顶面 → 新增的
  `lodge_in_surface()`（插住、保持撞上角度、**可拔出来**、不注册杆）。没掷出的矛蹭到墙
  也只停住不成杆 —— 旧实现「顶面无条件插住 + 没掷出的也插住」才是「矛到墙必定成杆」。
- **杆顶弧半径**（`behavior/pole_climb.py`）：删掉硬编码 `ARC_R=17`，改 `PoleClimber.arc_r`
  读这只猫真实的 `body._conn_stand`（幼崽 12 / 成年 17）。旧实现把幼崽两个 chunk 摆到 17px
  间距，解钉时距离约束把误差当冲量吃下去 → 变形。
- **通用竖直扫掠**（`core/chunkphys.py`）：新增 `sweep_drop_top(...)`（任何圆点可复用），
  `_solid_blocks` 的落顶补判改用**这一帧真实位移**（不再看 `vy`，位置被外部写过时 vy 可能
  是 0）并补上「往上穿底边」的对称分支；蜥蜴 `_collide_solids(prev_y)` 与软体头
  `_step_head_point` 接同一份扫掠 —— 修「从墙上方杆子落下来穿透壁」「从杆上摔下穿墙」。
- **蜥蜴地面查询带能力**（`world/lizard.py::_ground_y` 传 `self.caps`）：无杆能力品种不再把
  横杆杆面当成地面。
- **蜥蜴视觉比例**（`world/lizard_gfx.py`）：新增 `BODY_VIS_SQUASH=0.90` /
  `TAIL_VIS_STRETCH=1.22` / `TAIL_VIS_TAPER=0.14`，**只变形 spine**（躯干绕臀压短、尾巴从
  臀后拉长、尾梢收细更慢）。物理长度 / 碰撞半径 / 咬合范围一律不动，腿按物理位置画。
- **猫崽放置预览**（`world/items.py`）：进放置模式就先定下这一只的身份（`_pup_pending` =
  最低空位 k），预览与 `place_slugpup()` 共用 `pup-{k}`（外观由
  `pup_appearance(_pers_seed(pet_id, ...))` 决定，旧实现预览用 "pup-preview" ⇒ 必然不是同一只）；
  取消放置丢弃预留身份。
- **面条蝇性能**（`world/needleworm_gfx.py` / `world/needleworm.py` / `world/items.py`）：
  - `palette(nw)` 按 `(hue, lightness, hue_div, cos_bools)` 缓存（这四项 `__init__` 后不再变），
    不再每帧每只重算整条 HSL/RGB。
  - `_nw_weapon_seen` 的清理从「每只虫各扫一遍」改成每 tick 一次 `_prune_weapon_seen()`；
    距离判定改平方比较（省每对一次 `hypot`）。
  - `_step_big` 同族扫描：平方距离 + 只有赢家才 `_cat_from_other()` 建目标字典。
  - `even_out_temps` 新增 `_temp_moving` 计数：表里全部收敛就直接返回，不再每只虫每 tick
    把整张会无限增长的表扫一遍（`influence_temp_like / influence_like` 置脏）。
- 回归：口径更新 `e2e_r126`（矛扎墙必须设出手点 `_throw_x/_throw_y`；尖头朝墙里 = 90°），
  新增 `e2e_r127`（本轮 7 组行为），全量 **116 个脚本 fails=0**。

### R129 · 蜥蜴身体拓扑重排（3 核心 body chunk + 视觉头）+ 白蜥伪装常态化

- 蜥蜴身体拓扑改成原版形状：**3 个核心 body chunk 是驱动体**，头（含下颚 / 眼睛 / 牙）
  降级为挂在驱动点前方的**软体末端**，不再是「AI 直接写的独立头点 + 拖在后面的链节」。
  - `_step_chain` 的链根 = `seg[0]`（≡ `x/y`，AI 驱动点）：约束循环、弯曲 / 步态都在
    `seg[1:]` 上跑，避免把驱动点当普通链节。
  - 新增 `_step_head_point()`：头按弹簧追 `x + chain_dir * head_conn`，带 `HEAD_GRAV`
    重力、空气阻力、地形 / 竖杆 / 背景墙碰撞与地面夹取；新增 `head_x / head_y /
    head_lx / head_ly / head_vx / head_vy`。
  - 嘴点（`_mouth_point`）、头部朝向（`_head_dir`）、外观脊线（`_cosmetic_spine`）、
    深度（`_step_depth`）、脏矩形（`bounding_pad`）全部改读软体头点；渲染头点用
    `head_lx/head_x` 插值，跟手但不抖。
  - 连带修复：AI 意图不再被脚支撑压死（新增 `_want_vx` / `_drive_vx`，`_step_turn`
    优先读它）；链体基线改用「锚点 → 第 1 节」，不再退化成一根竖直硬棍。
- 白蜥伪装改回原版口径：**潜伏不动 = 每 tick 满频率提取周边背景主色**（整只，含头），
  发起攻击 / 被攻击立刻垮掉，受伤期间不由自主地胡乱变色。
  - 删除呼吸灯（`CAMO_SAMPLE_TICKS` / `CAMO_BREATH_TICKS` / `CAMO_PULSE_TICKS` /
    `CAMO_MIX_MAX`）；新增 `CAMO_COLOR_RATE=0.25`、`CAMO_FADE_IN=0.10`、
    `CAMO_FADE_OUT=0.50`、`CAMO_HIDE_VX=1.2`、`CAMO_FLICKER_TICKS=90`、
    `CAMO_FLICKER_STEP=3`。
  - 采样仍然只取**背景**（`bgcolor.dominant_around` 会把我们自己画的前景挖掉），
    别的猫 / 生物路过不会带着白蜥一起变色；淡出到 ≈0 后忘掉旧色，下次潜伏重新采。
  - `lizard_gfx.head_color` 也吃迷彩（眼 / 牙 / 口腔保持原色），即**伪装时头部也变色**。
- 蜥蜴脚支撑死锁修复（用户报「脚黏在平面 / 被拽走时脚把蜥蜴无视障碍拽回去」）：
  脚离髋超过上限时置 `airborne`（不再同一 tick 被重踩成支点）、未钉住的脚落地要过
  `joint * LEG_MAX_STRETCH` 距离门、释放脚时留不可破的最少支撑数、超长锚点改为反推到
  腿长边缘而不是放开。
- 回归：口径更新 `e2e_r33 / r38 / r60 / r76 / r97 / r99 / r102 / r118 / r124`（都与
  新拓扑或新伪装口径相关），全量 **115 个脚本 fails=0**。
- 打包：重建 `dist/SlugcatPet`，重打 `outputs/SlugCatPet-win64.zip`（313 项，
  71,814,871 B，SHA256 `300F319039FE10990E61FEE803BADE78BC243C3EEECEB51F7C75B0C7630D6F75`）。

## 2026-09-30

- 修复蜥蜴身体链、转向、嘴部与地面约束。
- 修复食物逐口消耗、打断进食后的口数与外观状态。
- 完善矛飞行、真实命中点、身体附着与墙体碰撞。
- 修复业力花重复拾取问题。
- 完善同伴救援、按压复活与救援目标寻路。
- 暴雨改为环境持续状态；手动暴雨不会自动结束；暴雨期间冻结自动复活/转生，但允许同伴救援复活。
- 庇护所入口按屏幕左右位置确定方向，暴雨避难目标进入屋内而不是停在门口。
- Hunter 使用背部矛槽；Spearmaster 允许双手持矛；其他猫最多一支。
- Saint 超度改为业力花槽满即可，成功后消耗一格业力花。
- Saint 舌头、矛加入庇护所实墙碰撞。
- 加强窗口边缘与地面的生物碰撞。
- 修复猫崽放置类型错误：放置猫崽必须调用 place_slugpup()，不能落入默认果实分支。

## 历史阶段

### R101
庇护所自由尺寸、入口简化、三容器持矛结构、雨循环术语整理。

### R99
暴雨流程、饱食/冬眠判定、蜥蜴墙面导航与白蜥背景迷彩。

### R98
矛大师白针规则、业力花命中、设置面板整理。

### R97
庇护所真实碰撞与寻路、猫崽、猎杀状态合并、矛大师双针、蜥蜴外观与身体物理。

### R96
雨循环与手动暴雨、庇护所底墙及入口碰撞。

### 更早阶段
包括食物、矛、蜥蜴、蝉乌贼、面条蝇、拾荒者、表情、社交、存档、性能与逆向资料库等基础功能建设。
