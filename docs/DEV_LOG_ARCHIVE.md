# 开发记录归档

此文件保留历史开发阶段的主要修复记录。README 只保留当前使用所需信息。

## 2026-10-01

### R138 · §8 咬合参数补齐 + §13 花纹复刻核对 + §14.1 面条蝇绘制优化

**§8 咬合参数补齐（`world/lizard.py`）** —— 把公开反编译里的粉蜥咬合参数真正落进桌宠逻辑，不再是「距离够近就结算伤害」的一锤子买卖。

- 新增 `LizardBreed` 参数 `bite_delay / bite_in_front / bite_homing_speed / lounge_distance / lounge_speed`，粉蜥档一字不改：`biteDelay=12`、`biteInFront=25`、`biteHomingSpeed=1.7`、`loungeDistance=150`、`loungeSpeed=1.0`。
- `bite_in_front` 留 `None` 时按 `25.0 * attempt_bite_radius / 80.0` 折算，`_bite_reach()` 改成 `head_rad + BITE_IN_FRONT_K(0.64) * bite_in_front * body_size_fac`，所以**每个品种的咬距与旧口径逐位相同**（实测 `bite_in_front / 25.0 * 80.0 == attempt_bite_radius` 全品种成立），`e2e_hunt.py` 等旧断言零改动。
- `_start_bite()` 改成真正的 **AttemptBite**：不再当场结算，而是 `bite_wind = biteDelay` 进入前摇；前摇里张嘴（`jaw = 1.0`）、`bite_hold = BITE_HOLD + wind`、`bite_cd = COOLDOWN_TICKS + wind`、掷好的伤害暂存 `_bite_wind_dmg`。
- 新增 `_bite_homing()`：前摇每 tick 沿「头 → 目标」方向压上去，步长 `bite_homing_speed * BITE_HOMING_STEP(0.30) * body_size_fac`，并给 `_body_impulse` 一个前压——这才是「边瞄边咬」，而不是站着等。
- 新增 `_snap_jaws()`：前摇结束那一帧才真正咬合；目标跑出 `_bite_reach() * BITE_SNAP_SLACK(1.6)` → **落空**（不写 `bite_event`），否则 `bite_event = (obj, dmg)`。`_look_rate()` 在前摇期按 `bite_homing_speed / BITE_HOMING_REF(1.7)` 缩放转头速度（粉蜥 = 旧值）。
- `_lunge()`：`reach` 改用 `_bite_reach()`；`d <= lounge_distance * body_size_fac` 时顶速乘 `lounge_speed`、加速度乘 `LOUNGE_ACCEL_FAC(1.35)` —— `loungeSpeed` 从死参数变成「近身扑击的顶速比」。
- 新增 `BREED_BITE` 表，12 个品种各一行 `(biteDelay, biteHomingSpeed, loungeDistance, loungeSpeed)`：pink(12,1.70,150,1.00) / green(10,1.20,190,1.20) / blue(14,1.90,110,0.70) / yellow(12,1.60,150,1.00) / white(12,2.00,170,0.85) / red(8,2.20,230,1.35) / black(12,1.70,160,1.10) / salamander(14,1.50,140,0.90) / cyan(10,1.90,200,1.15) / caramel(15,1.40,120,0.70) / zoop(12,1.60,140,0.90) / eel(13,1.60,140,0.95)；未登记品种走粉蜥档。
- `kill()` 清 `bite_wind / _bite_wind_obj / _bite_wind_dmg`，死蜥不会带着半截前摇。

**§13 花纹复刻核对（`world/lizard_cos.py`）** —— 对着原版那条 else-if 链逐品种核对，抓到两个真 bug。

- **eel / zoop 的 DLC 分支原来和主链并存**：原版是一整条 else-if，旧写法把它们写成独立 `if`，于是这两种还会再走一遍主链。改成互斥后 eel 平均族数 **5.33 → 4.00**（不再同时长尾长尾鳞 + 尾羽 + 尾鳍），zoop **3.30 → 2.00**（尾羽只出一次）；eel 也不再长主链专属的 LongHeadScales / BumpHawk。
- **`PHYS_KINDS` 砍成三族**：`TailTuft / AxolotlGills / LongHeadScales`；去掉 `LongShoulderScales`（实例最多，红蜥一趟两条）→ 降级为静态装饰，运行时不再逐片做摆锤。
- 核对实测（每族每 600 只的家族数，改后）：pink 1.62 / green 1.85 / blue 1.88 / yellow 2.28 / white **0**（原版 else-if 排除白蜥）/ red 4.14 / black 2.24 / salamander 2.11 / cyan 2.77 / caramel 1.59 / zoop 2.00 / eel 4.00。固有族全对：black→Whiskers、yellow→Antennae、cyan→JumpRings、salamander→AxolotlGills+TailFin。同种子同结果。

**§14.1 面条蝇绘制优化（`rendering/primitives.py` + `world/needleworm_gfx.py`）** —— 用户本轮授权「允许完成优化哪怕改变外观」，所以按收益优先动绘制批处理。

- `primitives.py` 新增 `ribbon_many(painter, groups, flat=None)`：把多条带状几何合进**一个** `QPainterPath` 一次 `drawPath`；`groups = [(points, halfwidths, colors), ...]`，`flat` 给定时整批纯色，否则按每条颜色均值拉一条渐变；`pts` 允许直接是 `QPolygonF`。
- `_ring()` 优化：一次填满 `2n` 定长表（省掉两个中间 list + `reversed/extend`），下标特判首尾代替 `points[i-1] if i else`，`normal(i)` 闭包内联。**`math.hypot` 保留没换**：一度改成 `sqrt(dx*dx+dy*dy)`，实测本机 hypot 反而略快（65.9 → 64.4 ms/4000 环），而且换 sqrt 会让 `e2e_r81` 的「顶点序列与原 ribbon 逐位相同」守护失效（300 组里 83 组差 1 ulp）—— 零收益的改动不做，已回退。
- `needleworm_gfx.py`：新增 `_COLS_CACHE` + `_body_cols(body, det, cb0, n)`，身体「沿体长渐暗」的用色表按 key 缓存（以前每只每帧重算 ~20 次 `_mix`）；`_draw_wings` 的 3 对翅收进 `groups` 后一次 `ribbon_many`，眼（`JetFishEyeB`）收集后统一 `blit`，`wing_col` 提到循环外；6 条腿同样合批一次画。
- 实测（`_bench_nw.py`，40 只成体，直接调 `draw_needleworm`）：**34.22 → 29.32 ms/frame（−14.3%，0.856 → 0.733 ms/只）**；幼体 15.98 → 15.3 ms（0.399 ms/只）；`drawPath` 调用数每帧 **480 → 200**。
- 试过但**撤回**：翅的「模板环 + `QTransform` 刚体变换」实测 29.37 vs 29.28 ms **打平**，白加复杂度 → 撤回；上下边开放折线（`2n` → `2n+2` 点）会改变自交区填充、视觉风险且收益小 → 未做；两条腿并进一个环、翅膀停在 ~12 → 外观/收益都不划算 → 未做。

**测试**：新增 `work/scratch/e2e_r132.py`（约 45 项，全绿）—— §8 粉蜥反编译值/全品种五参数/品种间有差异/**咬距逐位不变**/AttemptBite 不结算/`bite_hold = 18+delay`/前摇张嘴/前压冲量/第 11 帧未咬、第 12 帧 `_snap_jaws`/前摇跑掉=落空/`_look_rate` 随 `bite_homing_speed` 变且粉蜥=旧值/lounge 顶速比 = `lounge_speed`/红>蓝/`kill()` 清前摇；§13 三族/肩鳞静态/zoop 尾羽只出一次/族数 < 2.5/eel 主链专属族 = 0/eel 仍有鳃+尾鳞且族数 < 4.5/white 零花纹/五品种固有族/同种子同结果；§14.1 `ribbon_many` 存在/源码里翅腿都走合批/`_body_cols` 按引用复用/节数不同不同表/实画有像素/8 只混 40 tick 不炸。`run_all19.ps1` 已登记（122 个脚本）。

另外按本轮改动更新了两个既有守护：

- `e2e_r46.py`：翅/腿改走 `ribbon_many` 合批后，原来只 spy `G.ribbon` 的探针看不到它们。给探针加了 `ribbon_many` 分支，把 `groups` 摊回逐条「伪 ribbon 调用」，腿 6 条 / 翅 4 张 / 挂点 / 翅长这些几何断言原样保留，没有放松。
- `e2e_r97.py`：`PHYS_KINDS` 断言从旧的「LongBodyScales 四族」改成 §13 的三族 `TailTuft/AxolotlGills/LongHeadScales`，并补一条「LongShoulderScales 已是静态装饰」。这是规格变更（§13 明确「真正需要动态的只有少数几个明显的部件」），不是回归。

全量回归：`run_all19.ps1` **122 个脚本 fails=0 []**。

**未做（留档）**：§2/§5/§6 驯服社交 / 黄蜥 Pack / AttemptBite→Grasp→Carry 分层（**用户明确说驯服相关暂时不做**）；§9.1 `_strip_path()` 把 head+seg 平滑成一条软管的拓扑级改动（风险大，需单开一轮）；§9/§10 动作序列（PrepareToLounge 式分节点冲量、Attack 四阶段姿态）。

### R137 · §37 AI 时间片 + §20 竖线跨高度参数化搜索 + §17 猎物链合并成 PreyState

- **背景**：R136 结尾留了三条「要做但单独一轮」的审计项（§37 / §20 / §17），本轮连同上一轮遗留一次做完；三项都不是新 bug，是那份规范里**架构层面的欠账**。
- **口径**：三项都只动**结构与调度**，不动任何行为参数、不动外观、不动伤害。

**① §37 AI 时间片（纯性能项，规格见文档第三十七节）**

- 规格：感知每 2~3 tick、目标选择每 4 tick、路线事件 10~20 tick、LOS 缓存 3~5 tick、Pack 10 tick、声音 5 tick；**物理 / 攻击碰撞 / 抓取仍每 tick**；8 只蜥蜴错峰到 4 个 tick 上。
- 实装：
  - `lizard_ai.PERCEIVE_EVERY = 3` + `Lizard.should_scan(tick)`：`(tick + id) % PERCEIVE_EVERY == 0` 才重建观察，**按 id 错峰**（不会全场挤在同一帧）；`_scanned` 保证「从没看过」的第一次必扫。
  - `perceive(..., scan=False)`：不扫就 `mem.miss()` 让置信度照常衰减，然后**直接返回上一份 `obs`**；地形 / 遮挡 / 同伴 / 归属仍然逐 tick 刷新（所以物理和碰撞不受影响）。
  - 猎物归属改成**每 tick 一张全场共用表** `items._step_lizards()` 里建一次（`{id(prey_obj): owner}`），`Lizard._claimed_by()` 直接查表 —— 消掉了「每只蜥蜴 × 每个候选 × 所有同伴」的 O(N²) `owns()` 扫描。
  - `_observe()` 只算**一次** LOS（旧版 `los_blocked` 与 `sees()` 各算一遍）；超过任何消费者会用到的半径就不判遮挡。
  - 新增 `lizard_ai.prune_side()` / `los_blocked_idx()`：起点（自己）一 tick 裁一次、终点（每个目击对象）一 tick 缓一次，视线判定只遍历两端都留下的遮挡物。
- 实测（`_bench_lz2.py`，关掉 cProfile 的干净 A/B，只切 `lizard.py` 的 `PERCEIVE_EVERY`）：

  | 场景 | 每 tick 全扫（EVERY=1） | 时间片（EVERY=3） |
  | --- | --- | --- |
  | 30 只蜥蜴 | 16.1 / 17.0 ms | **9.40 / 9.44 ms** |
  | 60 只蜥蜴 | 75.3 ms | **35.6 ms** |

  （EVERY=4 与 EVERY=3 基本持平：9.3 ms，所以取 3 而不是 4。R136 交接里「126.9 → 34.6 ms」那组数含 `cProfile` 的 2~3 倍自身开销，只作同口径对比，不作为绝对值。）

**② §20 竖线跨高度参数化搜索（文档第二十节）**

- 问题：TerrainGraph 里每根竖线只有 `bottom/top` 两个节点，`_link_beams()` 只在两端建连接 —— 「挂在墙中间要出去」「目标在另一根杆的这一层」AI 会认为**没路线**（蛞蝓猫的 SurfaceGraph 在这一点更丰富，PoleJumpReach 支持任意高度搜索）。
- 修法：**保留端点图，只在需要时插桩**，不预先离散化所有高度。
  - `TerrainQuery.attach_points(caps, x, y, tx, ty)`：对「我当前的高度」「目标当前的高度」两个 y，挑 `abs(s.x - px) <= caps.climb_reach` 且 `s.top + 8 < py < s.bot - 8` 的竖线，**去重**后返回插桩点。
  - `_build_graph` 多一段「②b 按需插桩」：给每个插桩点建节点（`stand` 沿用同一根线的能力判定），`can` 时再建 4 条 **both=False** 的爬边。
  - **climb 槽口径变了**：爬边给的是「要走的那一段」（当前高度→线顶 / 线底→当前高度），不再是整条线 —— 所以 `e2e_r116` 两处断言从 `(212.0, 60.0, 700.0, 1)` 改成 `(212.0, 60.0, 400.0, 1)`、`climb_bot` 从 `700.0` 改成 `400.0`。**这是口径变更，不是回归。**
  - `route / reach_result / reachable / returnable` 全部改成 `for g in self._graphs(...)`：先试基础端点图，失败了才试插桩图；没有插桩需求时**缓存键不变**，仍然是原来那张图（`_attach_key` 把插桩点量化到 24px 桶）。
  - 新增 `_same_line(a, b)`：⑤跳跃 / ⑥跳下的建边循环里 `if a == b or _same_line(a, b): continue`。**这是本轮的关键修复** —— 否则插桩节点会和同一根线的线顶/线底互建「跳跃」边，蓝蜥爬到 y≈180 后被 `jump` 反复弹回（`e2e_r117` 就卡在这里，加完 `_same_line` 自己就绿了）。

**③ §17 猎物链只有一个状态对象：`PreyState`（文档第十七节）**

- 问题：同一条链（看到 → 追踪 → 咬倒 → 占有 → 叼住 → 回巢 → 放下 → 守卫）被拆在 `PreyTracker` + `target/target_obj` + `carry_obj/carry_body/carry_den/carry_corner` + `guard_obj/guard_t` + `mem` 里，于是到处是「A is not None and B is not None」这种组合判断，同一条链有好几个互相独立的说法。
- 修法：
  - `lizard_ai.PreyState(PreyTracker)`：**唯一状态对象**。归属那一段（`obj/state/killed/fainted/claim_tick` 与 `claim/hunting/refresh/owns/owned/delivered/release`）继承自 `PreyTracker`，**一个字节都没改**，所以 `self.prey.xxxx` 老调用照旧可用；`target/target_obj/carry_*/guard_*/mem` 全搬进来。
  - 链上位置由 `phase` 一处说了算：`idle / track / downed / carry / guard`（优先级 carry > downed > guard > track）；再给三个判据 `carrying`（=`carry_body is not None`，原版 CarryObject）、`chasing`（= 盯着或叼着，**守着巢穴不算**）、`busy`（=`phase != "idle"`）。
  - `reset()` 整条链归零（换目标 / 被吓跑 / 清零重来）。
  - `lizard.py`：9 个老字段**从 `__slots__` 里删掉**，改成类级 `property`，由模块级 `_prey_field(name)` 工厂生成，读写都代理到 `self.prey`。这样**全部老调用点（含跨文件）行为完全不变**，但存储只剩一份。
  - 组合判断收进 `PreyState`：`_camo_hide` → `self.prey.chasing`；`offer_alert` / `absorb_alert` / `_hunt_util` / `claimed_obj` / `_carry_intent` / `_st_returnprey` → `self.prey.carrying`。改完 `lizard.py` 里 `carry_body is not None` / `carry_obj is not None` **各 0 处**（原来 14 + 12 处）。
- **说明**：文档把 `stage_obj` 也列进了这条链，但它是「当前行为正对着的那条 `Observation`」的持有者（`world/lizard_ai.Observation` 记录），不是猎物链上的状态，搬进 `PreyState` 反而是错的，所以留原样。

**④ 回归测试**

- 新增 `work/scratch/e2e_r131.py`（约 40 项，已接进 `run_all19.ps1`，现在共 **121 个脚本**）：
  - §37：错峰（每只 3 tick 只扫一次、不同 id 不同 tick）/ 归属表共用 / 认领者看自己不算被认领 / 没表时线性退回 / 杆子挡视线 / 远处不判遮挡 / 起点裁剪同 tick 只算一次 / 降频后照样锁猎物。
  - §20：插桩点就是两个高度 / 只落够得着的线 / 端点图不通 → 插桩图通 / climb 槽是分段 / 墙上节点集合 == `[100.0, 110.0, 291.0, 460.0]` / 不重复插桩 / 无需求时复用同一张缓存图。
  - §17：`PreyState` 继承关系 / `Lizard.prey` 是 `PreyState` / 9 个字段不再占 slot / 老名字是 property / 代理读写双向一致 / `phase` 四个分支 / `reset()` / `mem` 合入 / 源码层面不再有 carry 组合判断。
- 全量 **121 个脚本 fails=0**。

**⑤ 本轮仍未做（明确记录，不是遗忘）**

- §8 咬合参数补全（`biteDelay=12` / `biteInFront=25` / `biteHomingSpeed=1.7` / `loungeDistance` / `loungeSpeed`）：现有 `COOLDOWN_TICKS=150` / `_bite_reach()` 是前几轮调好的另一套口径，直接换会动扑咬手感，要单独一轮调参 + 实测。
- §13 `lizard_cos.py` 大砍（只留 TailTuft / AxolotlGills / LongHeadScales 动态）：改外观，需对着参考图核对。
- §2 驯服社交拆 `like` / `tempLike` / `FriendTracker`、§5 Yellow 独立 Pack 层、§6 `AttemptBite / Grasp / Carry` 分层：重构级改动。
- §9/§10 动作序列（`Attack_Prepare/Lunge/Bite/Recover`、后空翻的角动量、`bodyWiggleCounter`）：属姿态动画层。
- §14.1 面条蝇绘制优化：R133 实测瓶颈在 Qt 绘制（每只每帧 12 条渐变 ribbon ≈55%），几何空间索引（`SpatialList`）反而更慢已撤回；能动的只有「少铺渐变 / 降 stop 数 / 6 条腿并成一次填充」，都会动外观，与「外形复刻优先」冲突。

### R136 · 竖杆顶端判定（「一爬就被瞬移到底部」）+ 蜥蜴放置预览 + 玩耍候选（拔矛玩 / 矛大师不玩自己的矛）

- **背景**：用户贴了「Rain World 蜥蜴桌宠——修改意见汇总」（14 节 + 引用链接）。这是一份**整体设计/需求规范**，不是一条新 bug；本轮先把其中**可操作、可验证**的部分落地，其余逐条审计并在下面留档。
- **审计结论（先说已经做完的，本轮没重复改）**：
  - 文档称「`Lizard.decide()` 用了 `self.injured` 但 `__slots__` 里没有这个字段」——**不成立**：`lizard.py:2433` 的 `injured` 是 property，实现就是 `LizardInjuryTracker.Utility`（`SCurve(InverseLerp(0.2, 0.9, 1 - health), 0.01)`），即文档 §11.5 建议的降级写法。
  - §1 Tracker 分层 / §3 PathFinder+AImap 语义 / §4 品种能力从 BreedParams 派生 / §7 花纹独立 RNG：R129–R135 已实装（`LizardBreed` / `BREED_TRAITS` / `lizard_cos` 独立 `crng` / `TerrainQuery`）。
  - §9/§10「运动结果怎么变成身体姿势」：R129 已做**身体拓扑重排**（3 核心 body chunk + 视觉软体头）与 `look_dir` / `body_dir` / `chain_dir` 三通道的限速转身（`_step_turn`）、`_body_impulse` 动作冲量；§11.1 那三个时间常数的分层就是现在的实现。
  - §14.2 矛大师骨针自然消失：R132 实装（`needle_disconnect` → `needle_fade_wait` 先保持黑 → `needle_fade` 渐隐 → `state = GONE`；`draw_needle` 在 `fade <= 0` 且非 `pinned` 时直接不画），`e2e_r127` 已覆盖「拿起不褪 / 扎住不褪 / pinned 不消失」。
  - §14.5 学会放手：`Creature.ITEM_PRIO`（石头 1 < 果子 2 < 矛 3）+ `pick_hand` 选最低价值的受害者手 + `_take_hand` 落地下手，已经实现；本轮补了回归测试（见下）。

**① 竖杆「一尝试爬就瞬间极快被打到底部」（文档 §14.7）**
- 根因在 `world/pole.py::Pole.top_y`：它写死返回 `self.by`。而 `place_pole_line` 的 `(ax, ay)` 是**按下鼠标**那一点、`(bx, by)` 是**松开**那一点 —— 从上往下拉的竖杆 `ay < by`，`by` 是**杆底**。
  于是 `_enter_tip` 的触发条件 `c1.y <= pole.top_y + TIP_ENTER_PAD` 在猫一抓住杆时就成立 → `_enter_tip()` → `_snap_axis()` 把 `chunk1` 直接写到 `by`（杆底）、`chunk0` 写到 `by - arc_r`，相位进 `tip` 并**钉死**在那儿。
  表现为「一爬就瞬间被打到底部」；重画杆子时拉的方向不同，所以「有概率修好」。
- 修法：`top_y = min(ay, by)`，新增对称的 `bottom_y = max(ay, by)`，`x` 取两端中点。
- 实测（`e2e_r130`）：旧代码 5 tick 后相位变 `tip`、`chunk1` 从 500 被瞬移到 800；新代码停在 `climb`，150 tick 内**向上爬 266px**，全程没有掉到起点下方。
- 影响面：`pole_reach.py` 也读 `top_y`（可站立杆顶高度），同一处一并修好。

**② 蜥蜴放置预览「头在左上角、身体拉伸到鼠标」（文档 §14.6）**
- `items._lay_lizard_hint()` 只摆了 `lz.x/y`、`seg`、`legs`，**没摆 R129 新增的软体头点**。渲染头点读的是 `head_lx → head_x`，不摆就停在构造时的 `(head_conn, 0)` ＝屏幕左上角；身体却在光标处 → 看起来就是「头在左上角、身体从左上角拉到鼠标」。
- 修法：头点摆到光标，驱动点（链根 `x/y`）退到光标后方 `head_conn`，链节再依次向左；与 `Lizard.__init__` 的初始几何（`head = x + head_conn`、`seg[0] = x - head_conn`）一致。

**③ 玩耍候选：拔下矛玩（仅拔能拔的）+ 矛大师不玩自己的矛（文档 §14.3 / §14.4）**
- `fsm._nearest_play_item()` 取矛时用 `not pinned` 一刀切，与 `_spear_usable`（工匠才拔得动钉成杆的矛）重复且矛盾。改成直接用 `_spear_usable(sp)`：斜擦插墙的矛（`lodge_in_surface`，`pinned=False`）所有猫都能拔下来玩，钉成杆的矛只有工匠能拔 ⇒ 只有工匠把它当玩具。
- 新增：`tail_needle` 品种（矛大师）跳过 `sp.needle` 的矛 —— 尾针是它唯一的取食工具，不是玩具。非矛大师的猫照旧可以玩别人掉的骨针。

**④ 回归测试**：新增 `work/scratch/e2e_r130.py`（32 项：竖杆顶端双向 / 爬升相位与位移 / 预览几何 / 玩耍候选 6 例 / 槽位让位 8 例），已接进 `run_all19.ps1`。
反向验证过：把 `top_y` 改回 `by` 时该脚本立刻 FAIL（`chunk1` 被瞬移到 800、相位 `tip`、150 tick 位移 −0.9px）。全量 **120 个脚本 fails=0**。

- **本轮未做（明确记录，不是遗忘）**：
  - §14.1 面条蝇绘制优化：R133 已实测（60 只成体 AI+物理 1.8~2.1 ms/tick，绘制 **52 ms/帧**，其中每只每帧 12 条 `ribbon()`（`QPainterPath` + 逐段 `setColorAt` + 抗锯齿渐变填充）占 ≈55%）。能动的只有「少铺几条渐变多边形 / 降 stop 数 / 6 条腿并成一次填充」，都会动外观，与用户「外形复刻优先」相冲突，本轮不擅自改。
  - §8 参数补全（`biteDelay=12` / `biteInFront=25` / `biteHomingSpeed=1.7` / `loungeDistance` / `loungeSpeed`）：现有 `COOLDOWN_TICKS=150`、`_bite_reach()` 是前几轮调好的另一套口径，直接换原版数值会动扑咬手感，需要单独一轮调参 + 实测，不塞进本轮。
  - §13 `lizard_cos.py` 大砍（只留 TailTuft / AxolotlGills / LongHeadScales 动态）：改的是外观，需先对着参考图核对，未动。
  - §2 驯服社交拆 `like` / `tempLike` / `FriendTracker`、§5 Yellow 独立 Pack 层、§6 `AttemptBite / Grasp / Carry` 分层：属于重构级改动，未动。
  - §9/§10 剩余的 `FightingStance` / `PrepareToLounge → Lounge` 逐 chunk 冲量序列与 `bodyWiggleCounter`：拓扑与三通道已在 R129 就位，但这些具体动作序列未做。

### R135 · 双导航系统合并（蜥蜴 TerrainQuery ↔ 蛞蝓猫 SurfaceGraph 收成一套）

- **背景**（用户：「那份文档全部实现。需要达成统一」，指「精简版：蜥蜴与蛞蝓猫双导航系统审计」）：
  代码里已有两套完整但互相不认识的导航 —— `world/terrain.py`（蜥蜴：面/杆/墙 → TerrainGraph）与
  `planning/surface.py`（蛞蝓猫：锚点图 SurfaceGraph）。同一件事（走过去 / 跳过去 / 爬上去）
  在两边是两种数据结构、两套寻路、两套几何扫描。本轮把**几何、图、寻路器**三件事收成一套。

**① 共用几何（`planning/navgeom.py`，上轮新建，本轮开始被两边真正共用）**
- `SurfaceGraph.build()` 不再自己扫 `chunkphys.platforms()` / `win.poles` / `win.shelters`，
  改成从 `navgeom.nav_geometry(pet.window)` 取面（文档 §21）。于是「这里有没有一块面 /
  一根杆 / 一面墙」全世界只有一个答案，蜥蜴和猫看到的是同一批 `Surface` 对象。
- 只剩「屋外走带」（按猫此刻站在哪一层把被庇护所挡住的地面切段）仍按猫自己算 ——
  它本来就是每只猫自己的东西，但用的仍是同一份庇护所几何。

**② 共用图与寻路器（`planning/navgraph.py`）**
- `NavGraph` 不再只认「下标式终点」：新增 `edge_dst(e)` 收口（文档 §39），边的终点既可以是
  节点下标（蜥蜴 `NavigationEdge`），也可以是节点对象（蛞蝓猫 `SurfaceEdge`，还带实测轨迹
  `plan` / 落点 `land_x` / 终点姿态 `pose`）。`radj` / 反向可达 / Tarjan SCC / Dijkstra / A*
  于是**只有一份实现**。
- `NavGraph.edges(u)` 同时吃 `list[list]` 与 `dict` 两种邻接表形状，历史调用方和测试里的
  `g.adj.get(i, ())` 照旧能用。
- `SurfaceGraph` 继承 `NavGraph`：反向邻接 / SCC / `can_return` 全部复用；
  `_returnable`（原版 accessibility「去了还回得来」）改成 `NavGraph._reachers(start)`，
  删掉本地那份重写的反向 BFS。
- `SurfaceGraph.idx()` 从 `list.index()` 的 O(N) 线性扫描改成 O(1)（节点自己记 `nid`）——
  它在 `_compute_returnable` / `route_to` 的热路径里被调用 O(E) 次。
- `route_to()` 的「每次取 min 扫一遍全部 best」改成 heapq 标准 Dijkstra（文档 §3），
  语义不变（finish 仍是普通 terminal 边、仍然比较完才收尾），复杂度 O((V+E) log V)。

**③ 缓存身份改成「导航几何版本」（文档 §24/§26）**
- `SurfaceRoute` 的图缓存键 / 路线缓存键去掉了 `world_version`（世界每 tick 都在变：猫眨眼、
  果子掉、鼠标动都算），改成 `NavGeometry.version`（只在平台 / 杆 / 墙 / 庇护所**内容**变化时 +1）。
  于是「平台没动、猫也没动」时整张图不再每帧被丢掉重建。
- 新增 `surface._nav_version(pet)`，没有 window 的单元测试退回旧的两个版本号。

**④ 动作层不再自己挑竖线（文档 §6）**
- `Lizard._climb_plan()` 旧版是「Planner 没给 climb 段就自己遍历 `climb_surfaces` 挑一根线」。
  现在只要 `self.plan` 还活着（`alive(tick)`）就**只承接** Planner 的路线：是 `climb_*` 就照抄
  `(上墙点, 线顶, 线底, 方向)`，是 `walk/drop/jump` 就什么都不做 —— 不再出现「规划说往右走、
  动作层却抓了左边的窗口竖边一路爬上屏幕顶」。
- 新增 `_CLIMB_MODES = {climb_wall: wall, climb_pole: pole, climb_edge: edge}`：`climb_edge`
  （窗口左右竖边）第一次有了动作层承接路径，`_plan_from_legs` / `_route_tick` 也认得它。

**⑤ 卡住检测接进路线执行（文档 §28）**
- `Lizard` 新增 `_stuck = StuckDetector()`：手里有一条正式路线、却连着两个 24 tick 窗口都没挪窝，
  就丢掉这条路线并 `_climb_release()`，下一 tick 重新问图 —— 而不是永远顶在一面爬不上去的墙上。
  `owner` 取当前段的终点 x，段落推进/换目标时自动重新计时。

**⑥ 视线遮挡改用共用几何（文档 §8/§9）**
- `items._lizard_blockers()` 不再只发杆子：直接取 `NavGeometry.obstacles`（庇护所墙条、背景墙、
  窗口竖边、杆——同一条 capsule 与 `seg_seg_dist2` 判交），于是「挡不挡视线」和「走不走得过去」
  用的是同一份几何。没有几何层时退回只发杆子，至少不比旧版弱。

**⑦ 黄蜥情报不再无限续命（文档 §16）**
- `PackAlert.decayed()` 旧版把时间戳刷成「现在」，于是 `fresh()` 永远成立、一条早就过期的情报
  能在群体里被无限转发。现在保留原始 `tick`，衰减只体现在 `confidence` 与新增的 `hops` 上，
  `PACK_ALERT_TICKS` 的保鲜终于真的会到期。
- `absorb_alert()` 的「哪条更新」判断同步改成（原始时间戳更新）或（同时间戳但转发次数更少）。

**⑧ 调查类行为走地形路线（文档 §29/§30）**
- 新增 `Lizard._vertical_detour(gx, gy)`：记忆里的位置（最后看见 / 最后听见）明显不在同一层时，
  先向地形层要一条正式路线（爬杆 / 上墙 / 掉下去都算路）并装成 `self.plan`，由 `_route_tick` /
  `_climb_plan` / `_approach_tick` 接管；同层或图里没路线时才退回直线趋近。
- `_investigate_tick`（InvestigatePos）与 `_noise_tick`（InvestigateSound）都接上了它。

**⑨ 猎物归属只有一个说法（文档 §18）**
- **问题**：`owner` 这个名字在两处指两件事 —— `Observation.owner` 是「这只猎物已经被
  **别的蜥蜴**认领」，`PreyTracker.owner` 是「我自己的归属记录」；后者还和同名的
  `PreyTracker.obj` **恒等**（`claim()` 里写的是 `self.obj = self.owner = obj`），
  于是「咬倒了吗」只能靠 owner 是不是 None 猜。
- `Observation.owner` → **`claimed_by`**，`Lizard._prey_owner()` → `_claimed_by()`。
- `PreyTracker` 删掉 `owner` 槽：归属 = `obj` + `state`，新增 `owned()`
  （`state == "downed"`，`hunting` 只是兴趣不算归属），`refresh()` / `owns()` /
  `delivered()` 全部改成读它。

**⑩ 逃 / 猎 改成效用 + 迟滞（文档 §40）**
- `decide()` 的 ① 不再只问 `threat_t > 0`：新增 `_flee_outweighs_hunt()`，
  `_flee_util()` 按威胁距离给分（贴到 30% 警觉半径 = `FLEE_UTIL`），
  `_hunt_util()` 按目标距离给分（进咬合距离 = `HUNT_UTIL`，嘴里有肉直接满），
  切换要拉开 `FLEE_HUNT_HYSTERESIS = 0.12`；已经在逃时反向要求猎明显更划算才回头。
  于是「猎物已经在嘴边」不会再被一个远处的威胁打断，也不会在边界上每帧横跳。

**⑪ 结清 R132 记录在案的四项**（上一轮的「本轮未做」清单）
- 「双寻路器统一」= ①②；「Dijkstra O(V²) → heapq」= ②；
  「`SurfaceGraph` 建边加 SpatialGrid」= `_link_jumps` 改成按 x 排序 + `bisect`
  的横向窗口粗筛（旧实现是节点两两比，40 块平台就是上千次 `land_sweep` 级别判定）；
  「`geometry_version` 拆分」= ③。

**测试**
- 口径更新（都是本轮**有意**改掉的行为，不是放宽断言）：
  - `e2e_r117`：「蓝蜥照多段路线走到墙脚并爬到墙顶」——这条**本来是 FAIL** 的
    （蓝蜥一路向左抓住窗口竖边爬上去，永远到不了 x=700 的墙），④ 修好之后通过。
  - `e2e_r83`：「缓存 key 含起点 x」的 key 形状断言跟着 ③ 改（`(nav_v, hy, x, gx, gy)`），
    并补了一条「key 里没有 world_version」的正向断言。
  - `e2e_r116`：「Planner 的 climb 路线被动作层照单执行（不依赖 climb_surfaces）」在旧口径下
    靠「plan 是 climb_* 才 return」侥幸成立；④ 之后动作层对着任何活着的 plan 都不再自选，语义更严。
- 全量 `run_all19.ps1`（119 脚本）：`fails=0`。

**未做（明确记录，不是遗忘）**
- §20「竖线的跨高度参数化搜索」：竖线目前仍只发「顶端 + 底端」两个节点。要加中间锚点，
  会同时改动 `e2e_r117` 里「上墙段的 climb 槽 = 线顶」这条口径，需要单独一轮做。
- §37「AI 时间片（感知 2~3 tick / 目标 4 / LOS 3~5 / Pack 10 / 声音 5）」：属纯性能项，
  与行为正确性解耦，留到下一次性能轮（和面条蝇的空间索引一起做更划算）。
- §17「PreyState 字段合并」：蜥蜴这边没有独立的 PreyState 类（归属记在
  `PreyTracker`、追逐记在 `Memory`、搬运记在 `carry_*` 字段上），要合并得先决定
  搬运动作是否也归进这个状态机 —— 属取食行为重构，不是纯重命名，留到那一轮。
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
