# 开发记录归档

此文件保留历史开发阶段的主要修复记录。README 只保留当前使用所需信息。

## 2026-10-01

### R154 · 匍匐按反编译修正（趴姿投影 / 抬髋 / CrawlTurn）/ 骨针不再卡住不褪

现象两件：① 匍匐与匍匐行走的动作都不对；② 矛大师的骨针褪色卡死，要等鼠标点一下才直接消失。
两条都对着反编译（`Player.cs` / `PlayerGraphics.cs` / `Spear.cs`）核过。

**① 匍匐：三处反编译抄错 + 少了一个 CrawlTurn**

* **收回趴姿的条件**（`core/creature.py` 与 `control/moves.py` 两条移动路径）：旧写
  `if self.standing or move_x != 0:` —— 「正在走」也被当成「要站起来」，于是「先走起来再想趴」
  的猫每帧 `crawl_pose -= 0.08`，永远压不下去：立着骨架贴地滑行。改成只看 `self.standing`。
* **趴姿投影只在原地跑**：旧写 `if move_x == 0 ...: self._crawl_pose()`，而原版
  `PlayerGraphics.cs:2049-2060` 的 Crawl 偏移动与不动都施加。现改成 `_crawl_pose(moving=...)`
  两态都跑；`moving=True` 时不阻尼速度、不把髋拖回 `crawl_anchor`（那是「趴着不动」才要的）。
* **抬髋条件抄反**：原版 `Player.cs:9126` 是「胸**不**贴地（`ContactPoint.y > -1`）且髋比胸低 3px
  → 逐帧抬髋」，旧实现写成 `c0.on_floor and c1.y > c0.y + 3.0 → c1.y -= 1.0`，条件与符号都反。
* **补上 CrawlTurn**（原版 `Player.cs:9088-9100` + `7518-7535`）：反着爬先 `dyn *= 0.75`，
  `crawlTurnDelay > 5` 且还在反着爬 → `animation = CrawlTurn`，每帧给身体一对反向力把身体
  原地翻过来（已翻过来就抬上身收尾），而不是一路倒着滑。离开 `Crawl` 时清 `crawlTurnDelay`
  （原版 `Player.cs:12425-12431`）。
* `_crawl_pose` 里「头往身体当前那一侧摆，不跟 `facing`」：`facing` 在掉头那一帧就翻了，
  用它会把头从髋上硬拖到另一侧（穿身而过），等翻过来再算。

**② 骨针：卡住不褪 = 两处把「黑化走完」当成了终点**

* `world/spear.py::needle_tick()` 的 `if self.pinned: return` —— 钉成杆的针黑化走完就永久停住，
  直到鼠标把它拔下来。删掉：`pinned` 只决定「逻辑上是不是场景杆」，不改变视觉生命周期。
* `rendering/primitives.py::draw_needle()` 开头的 `if not live and fade <= 0.0 and not pinned: return`
  —— `fade=0`（黑化走完）就整根不画，于是「黑保持 240 tick + alpha 渐隐 80 tick」这约 8 秒被
  整段跳过，实测就是「一会儿突然消失」。改成可见性**只看 `alpha <= 0`**（`fade` 只管颜色）。
* 针 GONE 那一 tick 已经先从 `self.spears` 剔除，`_sync_spear_poles()` 的循环再也看不到它 →
  会留下**看不见却还能爬**的杆。`_sync_spear_poles()` 开头补一段「扫幽灵杆」（按 `pl.from_spear`
  反查是否还在 `self.spears`）。

验证：新增 `work/scratch/e2e_r154.py`（30 项断言：源码口径 / 匍匐行走几何 / CrawlTurn / 骨针三段
生命周期 / 幽灵杆 / `draw_needle` 像素口径）；全量 `run_all19.ps1`（含新脚本）：
`=== round done; fails=0 []`。出图 `work/scratch/p154_crawl.png` 核过：站立 → 趴下的过渡自然，
行走帧身体真的压平贴地（`dy` 由 17 收到 −1），掉头帧可见 CrawlTurn 的翻滚姿态。

### R153 · CombatTarget 接口迁移 / 杆控制器统一协议 / Spear 生命周期统一状态

文档：R150 审计里当时点名「留专轮」的三条（§7 / §9 / §13），本轮一次收完。

**① §7 hitgeom 降级链删除：每个目标自己回答「我哪里挨打」**

* 新增 `world/combat.py::CombatTarget`：`chunks()` 必答，`preferred_point()` / `hit_radius()`
  由它派生（默认＝第一个可命中点 / 最大半径）；普通「单点 + rad」对象直接继承，不写任何方法。
* `hitgeom.target_chunks / preferred_point / hit_radius` 只认 `chunks()`；旧那条
  `chunks → hit_chunks → chunk0/chunk1 → p0/p1 → x/y + seg` 降级链整条删掉 ——
  以前「命中点又飘了」得先猜这次走的是第几层。
* 各目标接接口：`SlugcatBody`（两 chunk）、`Lizard`（头 + 每节，头 owner 归一成蜥蜴自己，
  `hit_chunk is lz` 判头甲的语义不变）、`NeedleWorm`（`hit_chunks()` 改名 `chunks()`，
  吻段收细 + 獠牙尖原样）、`SeedCob`（两个挂点）；`Stone / Pearl / Fruit / BatFly / Scavenger`
  走默认实现（带上 `class X(CombatTarget)`）。
* 没实现 `chunks()` 的对象＝没有可命中点（不再猜 `chunk0`）。

**② §9 竖杆 / 横杆控制器统一协议（不合成大 Controller）**

* 新增 `world/pole_ctl.py::PoleController`：`kind / pole / update() / release() / jump_off() /
  can_handoff() / handoff() / position()`；`behavior/pole_climb.py::PoleClimber`（vertical）与
  `world/hpole.py::HPoleController`（horizontal）各自实现，物理仍完全分开。
* FSM 从「`poleclimb` / `hpole` 两个槽」收成 `pole_ctl` 一个槽；`poleclimb` / `hpole`
  变成 read-only property（按 `kind` 过滤），`_hpole_release()` 删除 ——
  释放只剩 `_pole_release()` 一条路（stun / 切态 / 死亡都走它）。
* 换杆请求从「直接挂属性」改成协议方法：`can_handoff()` 判能不能换（`no_handoff`
  的临时竖杆不允许），`handoff()` 取走即清。

**③ §13 `Spear` 生命周期从「统一读取」变成「统一状态」**

* `state / stuck / pinned / _thrown / stuck_to / stuck_local / toss_t` 这些字段现在**只**由
  `enter_free() / enter_thrown() / enter_stuck() / enter_stuck_to() / enter_gone()` 成组写；
  `unstuck()` 并入 `enter_free()`。`pole` / `held_by` 仍是杆实体 / 持有者句柄，不在这里动。
* 五个「插住」入口（`stick` / `embed_in_bar` / `embed_vertical` / `rest_on_ground` /
  `lodge_in_surface`）全部走 `enter_stuck(pinned=...)`，不再各自抄一遍九个字段。
* `weaponphys.begin_thrown` 加钩子：`Spear` 走 `enter_thrown()`，`Stone`（没有生命周期机）保持原样。
* 于是 `stuck=True + _thrown=True`、拔出来还留着 `stuck_to` 这类中间组合不再可能。

验证：新增 `work/scratch/e2e_r153.py`（66 项断言）；`e2e_r47`（假目标 `_Tgt`）与
`e2e_r151`（假目标 `TwoChunk` / 控制器槽改名）按新接口同步。
全量 `run_all19.ps1`：`=== round done; fails=0 []`。

### R152 · DodgeShot 改锁定式避让（起手定一次边，执行期不再重选）

现象：被瞄准的猫进 `DodgeShot` 后原地左右抽搐（状态面板显示「躲弹道」）。根因在执行层，不在弹道 /
物理：`_st_dodgeshot()` 每 tick 重新 `_threat_shot_at_me()` → 重新 `_dodge_side()` →
`walk_to(chunk1.x + side * SHOT_DODGE_DX)`。目标点挂在「当前位置」上，而移动本身又改变下一帧的
左右判断，于是「安全侧反转 → 目标反转 → 移动 → 安全侧又反转」自己喂自己。

* **起手锁定**：`_act_dodgeshot()` 只在进入时算一次 `(方向, 目标 x)`，写进新字段 `_dodge_dir` /
  `_dodge_target_x`；`_dodge_from` 从「面板显示用」变成真正的锁定射手。
* **`_dodge_plan(it)`**：`_dodge_side()` 给的侧别被窗口夹回原地就换另一侧；夹取只许缩短这一段
  （窗口刚收缩、身体在夹取带外时不许把目标丢到身后）；两侧都走不动 → `target_x = None`，不起手，
  不做「进了 DodgeShot 却不动」的假躲避。
* **执行期不再重选**：`_st_dodgeshot()` 只 `walk_to(锁定目标)`，不再重新找射手、不再重新算边；
  走到 `SHOT_DODGE_DONE_R` 误差内即收尾，`_dodge_left` 退化成动作上限（弹道飞过去 ≠ 中途改向）。
* 新常量 `SHOT_DODGE_MIN_DX = 27.0` / `SHOT_DODGE_DONE_R = 6.0`。

验证：新增 `work/scratch/e2e_r152.py`（27 项断言，含「身体挪了目标不跟」「第二个射手不换锁定对象」
「贴墙自动换另一侧」「身体在带外不被甩到身后」「两侧夹死不起手」「走完自动收尾进冷却」）；
`e2e_r113b.py` 原断言不变仍过；全量 `run_all19.ps1`：`=== round done; fails=0 []`。

### R151 · R150 后的收口：档位飞行模型 / 单一危险值 / 唯一逃生目标 / AimSolution / 控制器释放

文档：本轮「R150 审计整理」（15 条）。结论是「新架构已建立，旧架构残留在几个边界」，按文档给的收口顺序
做前五条，再补 §6 / §8 / §10 / §11 / §12 / §14 / §15，共收干净 13 条；没做的三条列在最后。

**① 档位即飞行模型：石头不再吃矛的平飞（文档 §1，本轮唯一实际行为矛盾）**

* 旧：`trajectory.preview()` 对所有档位都传 `thrown=True, gravity=profile.gravity`，而 `gravity_delta()`
  里写死 `if flight_far(...): return g - SPEAR_FLIGHT_LIFT` —— 石头预演吃「110px 平飞 + 半重力」，真实
  `Stone.step()` 吃满重力，预演与真值两套弹道。AI 按矛的口径算石头，正是「算能中却打不中」的来源。
* 新：`ProjectileProfile` 多两个字段 `flight_lift / flat_distance`，并带自己的 `gravity_delta()`；
  `gravity_delta(x, y, ox, oy, thrown, gravity, room_gravity, lift, flat)` 由调用方给模型；
  `preview(..., profile=profile)` 整段跟档位走。矛 = `(0.45, 110.0)`，石头 = `(0, 0)` → 满重力。
* `Spear.step` 改调 `traj.SPEAR_PROFILE.gravity_delta(...)`；豆荚预演显式传 `SPEAR_PROFILE`。
* 验证：`e2e_r151` 把 `Stone.step` 与 `preview(profile=STONE_PROFILE)` 逐帧对拍 40 帧（误差 < 1e-6），
  并断言同初速下石头比矛掉得多（不再是同一条弹道）。

**② 杆几何全部归 Pole（文档 §8）**

* `world/pole.py` 新增 `anchor() / free_end() / span_x() / span_y() / mid_x() / cross_coord() /
  axis_coord() / clamp_axis() / spans() / nearest()`。
* `fsm.py` 里 34 处 `p.ax / p.ay / p.bx / p.by` 全部改走这些接口（`_horizontal_pole_near` /
  `_pole_near_point` / 零重力抓杆整段重写）；现在 `Select-String "\.ax\b|\.ay\b|\.bx\b|\.by\b"` 在
  `fsm.py` 里是 0 条。
* 顺带删掉 `_nearby_lizard()`（确认全库无调用方的死代码）。

**③ 危险值只有 ThreatField 一个来源（文档 §3）**

* `_threat_level()` 改成先问 `ThreatField.sample(x, y, radius=恐惧半径).danger`（clamp 到 0..1）；
  半径仍由 FSM 给（恐惧圈是战术参数，不是危险模型）。
* 只有「危险表里居然没有这条威胁」（表这一 tick 还没刷新 / 单测直接调 body）时才回落旧的距离口径 ——
  否则「表是空的」会被读成「天下太平」。
* `_threat_too_close()`（贴脸反应）按文档保留，不再自称 danger 标量。

**④ 「逃去哪」只有导航层一个来源（文档 §四）**

* 删 `FSM._flee_target_x()` 与 `FLEE_GAP` —— 那是第二套横向撤退算法（`当前 x + 反方向 GAP` 再 clamp）。
* 新增 `SurfaceRoute.retreat_point(threat)`：用 `_here()`（和 `plan_escape` 同一份支撑面口径）取
  「同表面离威胁最远的那一头」，不跨缺口、不猜墙体；`Planner.retreat_point()` 转发。
* FSM 侧只剩 `_flee_plan_cached()`（带保鲜期的 A*）与 `_flee_goal_x()`（有安全节点用它，否则用
  `retreat_point`）；`_cornered_by` / `_enter_fleelizard` 的回落 / `_st_fleelizard` 的步点三处全改走它们。

**⑤ AimSolution：一次投掷一次求解（文档 §5）**

* 新 `planning/aim.py`：`AimSolution(profile, direction, origin, velocity, path, target_hit,
  friendly_blocker, requires_jump, block_ticks)` + `hit_now` / `blocked_by_friend`。
* `fsm._solve_shot(tgt, dir_x=None, force=False)` 一次算完：初速 → 弹道 → 目标命中 → 同伴遮挡
  （只看「自己到目标」那一段，目标在背后就整段不看）→ 需不需要起跳。
* `_throw_weapon_at` 只解一次，然后 `blocked_by_friend → 等 / target_hit → 投 / requires_jump → 跳`；
  `_launch_weapon(dir_x, tgt, sol=None)` 不再重算同伴避让；`_shot_would_hit` / `_shot_path_clear`
  退化成「读解」；纯别名的 `_throw_line_blocked` 删除。
* 旧实现同一帧会把同一条弹道预演 2~3 遍，现在一次。

**⑥ 友军避让几何跟档位统一（文档 §6）**

* `_shot_hits_body(pts, ob, pad, profile=None)`：投掷物半径取 `profile.radius`，补长取
  `max(pad, profile.hit_pad)`；`_shot_hits_pet(..., profile=...)` 透传，躲同伴 / 躲来袭弹道也读同一档位。
  旧实现打敌人用 projectile 半径 + pad、躲同伴用 `brad=0 + 另一个 pad`，两套口径。

**⑦ 站位状态只由 Creature 定义（文档 §10 / §11）**

* `on_vertical_pole()` / `on_horizontal_beam()` 改成 `combat_position() == "vertical" / "horizontal"`；
  动画字符串只在 `combat_position()` 里认一次。
* `blocking.is_beam()` / `at_beam_tip()` 去掉 animation fallback（`BEAM_ANIMS` 常量删除），
  `on_same_pole()` / `pole_in_the_way()` 也改走 `is_beam()`。

**⑧ 控制器释放唯一入口（文档 §12）**

* 新增 `FSM._release_controllers()`：poleclimb / hpole / climb 各自 `release()`，幂等。
* `apply_stun()` 不再自己拆「解钉 / 清 animation / 置 None」那一套；`_break_active_controllers()`
  先调它，再删掉 PoleClimb / HPole 两支 —— 外部中断只通知控制器自己 release。

**⑨ 改名（文档 §14 / §15）**

* `Board.crowd()` → `target_crowd()`（目标级拥挤）；`CrowdField` → `TrafficField`（路线级交通），
  窗口属性 `crowd_field` → `traffic_field`，`NavContext.crowd_field` → `traffic_field`。
* `Creature.muzzle()` → `throw_origin()`：它就是投掷物的生成点（`chunk0` 前上方锚点），不是手位，
  旧名字与实现错位；投掷物真的从这里生成，所以按真语义改名，而不是把「手位」塞进来让预演与生成点分裂。

**验证**

* 新增 `work/scratch/e2e_r151.py`（8 组，40 项断言）。
* 同步更新旧断言：`e2e_r149`（`muzzle` → `throw_origin`、命中分支顺序改成读 `sol.*`）、
  `e2e_r147`（`TrafficField`）、`e2e_r70`（`target_crowd`）、`e2e_r49` / `e2e_r113b`
  （`_throw_line_blocked` → `_shot_path_clear`）、`e2e_r36`（假 body 补 `combat_position` /
  `on_beam_tip`）、`e2e_r150`（修正一处空切片造成的假断言）。
* `run_all19.ps1` 全量（含新增脚本）：`=== round done; fails=0 []`。

**仍未收（文档里有、本轮没做）**

* §7 `hitgeom.target_chunks()` 的 legacy fallback 降级链：要把普通对象都补上
  `chunks() / preferred_point() / hit_radius()` 才能删 fallback，属长期迁移。
* §9 竖杆 / 横杆控制器的统一协议：`PoleClimber` 与 `HPoleController` 的方法名已高度重合，但物理本就
  分开（沿 Y 攀爬 vs 沿 X 移动 / 吊挂 / 撑起），文档也明说「不要合成一个几百行的大 Controller」，
  留作专轮。
* §13 `SpearLifecycle` 目前仍是「统一读取」而非「统一状态」（`stuck / pinned / pole / state` 各处分开写），
  文档说不用急着改，属最后一层。

### R150 · R149 后的收口：意图时机 / 唯一积分 / 武器档位 / transport 查询 / EscapeSolver / 统一杆几何

文档：本轮「R149 后收口状态」审计（16 条）。判断是 R149 方向对、进入**继续收口**而不是继续加功能，
因此本轮不加第三套逻辑，只把 R149 已有的那几套半成品收成一套。收干净 8 条，其余 8 条列在下文「仍未收」。

**① `attack_intent` 只在真的出手后记（文档 §9.1）**

* 旧：`_throw_weapon_at` 起手就 `_note_attack_intent`，`_launch_weapon` 又记一次 —— 只起跳、根本没投的
  动作也会让同伴白躲，两只猫互相让位卡住。
* 新：`_throw_weapon_at` 里那次删掉，只保留 `_launch_weapon` 里那一次（=真的投出之后）。
* 验证：`e2e_r150` 断言「够不到 → 只是起跳」时 `behavior.attack_intent is None`。

**② `trajectory.advance()` 成为唯一积分（文档 §9.2）**

* `preview` 的循环体改成 `vy += gravity_delta(...); x, y, vx, vy = advance(...)`。
* `Spear.step` 的 `self.x += self.vx` 改成 `traj.advance(self.x, self.y, self.vx, self.vy, 1.0)`
  （`apply_water` 已经乘过 `air_friction`，传 1.0 免得乘两次）。
* 现在「摩擦 / 入水 / 平飞段」只有一份；`e2e_r150` 逐帧对拍 40 帧仍一致（误差 < 1e-6）。

**③ `ProjectileProfile`：命中参数按武器取（文档 §9.3）**

* 旧：`_shot_would_hit` 写死 `SPEAR_RAD / SPEAR_HIT_PAD`，`_shot_velocity` 写死 `is_spear=True`，
  手里只有石头也按矛算。
* 新：半径 / 补长唯一真值收到 `world/weaponphys.py`（`SPEAR_RAD / SPEAR_HIT_PAD / STONE_RAD /
  STONE_HIT_PAD`）；`world/trajectory.py` 给 `ProjectileProfile` 与 `profile_for(is_spear)`；
  `spear.RAD / stone.RAD / items.SPEAR_HIT_PAD` 全部改为引用它。
* `fsm._shot_profile()` 按「双手都拿着时优先主手」选档，`_shot_velocity / _shot_arc / _shot_would_hit /
  _note_attack_intent` 全部带档位；意图字典里存 `profile`，同伴躲弹道也按同样的档位预演。

**④ `_pick_climbable_pole` 完全走 transport 查询（文档 §9.8）**

* 旧：`abs(p.bx - hx)` 只对竖杆成立，横杆取的是端点，选杆必错。
* 新：`self.planner.transport_dx(p)` 取最近；`Planner.transport_dx` 本身也收成一份统一几何
  （竖杆 / 横杆都走 `Pole.nearest_point`）。

**⑤ `EscapeSolver`：匍匐方向不再由「威胁在左还是右」决定（文档 §9.10）**

* 新增 `planning/escape.py::solve_escape(body, threat, field, step)` → `EscapePlan(movement_dir,
  posture, face)`；给了 `ThreatField` 就比左右两侧的真实危险度，「左边危险右边安全」时往右挪。
* `_st_crawlaway` 只执行 `plan.movement_dir` + `plan.face`，不再自己算 `away`。

**⑥ 杆接口统一（文档 §9.7，只统一接口、不合并物理）**

* `Pole` 新增 `geometry / length / axis / nearest_point / progress / contains / intersection /
  surface_at`。
* `Planner.transport_dx / transport_in_reach` 改读这套接口；`blocking.is_beam / at_beam_tip` 改问身体
  自己的 `combat_position()` / `on_beam_tip()`（`creature` 新增 `on_beam_tip()`），FSM 侧不再各自读
  `ax / ay / bx / by` 或 `animation` 字符串判断杆形。

**⑦ `HitResult`：接触点 + impact angle（文档 §9.6）**

* `world/hitgeom.py` 新增 `HitResult(owner, point, t, tick, normal, impact_angle)`，`sweep_hit /
  sweep_hit_predicted` 返回它；兼容旧的 `owner, point, t = hit` 解包与 `hit[1][0]` 下标。
* `tip_align(..., angle_deg=None)` 与 `Spear.pin_tip(hx, hy, angle_deg=None)` 支持用**命中瞬间的飞行角**
  摆矛尖，并把渲染角也锁到它（原版 `setRotation = throwDir`）；`items` 三个插入分支都传 `impact_angle`。
* 新增 `CombatTarget.chunks() / preferred_point() / hit_radius()` 三个正式查询（`chunks()` 优先于旧的
  降级链；`hit_chunks()` 仍兼容）。

**⑧ `SpearLifecycle`：六阶段一处归一（文档 §9.11）**

* `world/enums.py` 新增 `SpearLifecycle`（FREE / THROWN / STUCK / STUCK_TO_CREATURE / PINNED_POLE /
  CARRIED / GONE）；`Spear.lifecycle()` 只读归一 `state / _thrown / stuck / stuck_to / pinned / pole`
  六个散字段，不改任何现有字段（场景杆生命周期与骨针生命周期暂未拆开，见下）。

**工具**

* `tools/parts_audit.py` 的 `our_const()` 现在能解析「常量已指向 `weaponphys` 唯一真值」的写法
  （例如 `RAD = wp.SPEAR_RAD`），不再把迁移到唯一真值源的常量读成 None。

**测试**

* 新增 `work/scratch/e2e_r150.py`（8 组、56 条断言，全绿）；`run_all19.ps1` 已加 `e2e_r150.py`。
* 同步更新两条旧断言：`e2e_r149.py` 的 `_st_crawlaway` 朝向检查改为校验 `solve_escape` + `plan.face`。
* 全量回归 `fails=0`。

**仍未收（下一轮）**

* §9.4 / §9.5 `TargetPoint / TargetResolver + AimSolution`（四种投法枚举）：`_throw_weapon_at` 仍是
  「预演 → 起跳 → 直投」三分支，没有正式的解算器。
* §9.12 `ThreatField` → 所有 AI 只读、FSM 只判 `ThreatIntent`：FSM 仍保留 `_threat_lizard / _nearby_lizard`
  等旧威胁读取。
* §9.7 的 `PoleController`（climb / move_along / dismount / handoff / throw_position）：本轮只统一了
  `Pole` 几何接口，`PoleClimber` 与 `HPoleController` 两个控制器仍是各自的方法名（物理按文档要求不合并）。
* §9.11 场景杆生命周期与骨针生命周期仍耦合在 `pinned / pole` 上。
* §9.13 `Board.crowd` / `CrowdField` 改名 `TargetClaimCost` / `TrafficCost`（纯命名，未做）。
* §9.15 一个 tick 只有一个 `MovementController` 拥有身体运动权、`_enter_state / _exit_state` 自动释放：
  仍是分散的 `_pole_release / _hpole_release / _break_active_controllers`。

### R149 · 一套弹道 / 一套命中几何 / CombatPosition / 匍匐门禁（两套杆逻辑的收口）

文档：本轮审计（5 bug + 4 需求）。核心不是再修 5 个独立 bug，而是把「同一件事有多套判断」
收成一套：AI 弹道 vs 真实飞行、命中判定 vs AI 预演、地面投掷 vs 杆上投掷、身体朝向 vs 移动方向。

**① 一套弹道（`world/trajectory.py`，新）**

* `gravity_delta / advance / preview / flight_far`，纯函数、不引用游戏对象。
* `Spear.step()` 的重力块改调 `traj.gravity_delta`（删掉内联的 g / `_flight_far` 两分支）；
  `fsm._shot_arc()` 与 `_cob_would_hit()` 改调 `traj.preview`。调一个参数不再要改两处，
  AI 预演说能中就是真能中。

**② 一套命中几何（`world/hitgeom.py`，新）**

* `sweep_circle / seg_dist / target_chunks / sweep_hit / sweep_hit_predicted / tip_align`。
* `target_chunks` 是全局唯一的「可命中点」口径：自报 `hit_chunks()` → `chunk0/chunk1`
  → 头 + 各链节 → 单圆；本轮补上 `p0/p1` 双 chunk 分支（爆米花荚 —— 旧 `items._cob_hit`
  就是逐 p0/p1 判的，少了这一支会丢掉第二个 chunk）。
* `items._sweep_circle / _ball_hit / _cob_hit / _small_hit / _seg_dist` 全部退化成薄封装。
  蛞蝓猫分支原来只做 `_seg_dist`（只知道「碰到了」，拿不到接触点）→ 同走扫掠；
  拾荒者分支原来直接比中心点（40px/帧 一帧跨过去）→ 同走扫掠。
* `Spear.pin_tip(hx, hy)`：命中同一 tick 把矛**尖**摆到真实接触点。旧实现只把速度
  清零、位置留在这一帧飞到的终点，视觉上就是「矛插在空气里」。蜥蜴 / 拾荒者 /
  蛞蝓猫三个分支共用。

**③ CombatPosition（`core/creature.py`）**

* `SlugcatBody.combat_position()` 只回答一个：`ground / vertical / horizontal / airborne`。
  站在横杆上时 chunk 的 `on_floor` 会假真、爬竖杆时 chunk0 被钉在抓杆手上，
  只有身体状态是唯一口径。
* `muzzle(dir_x)`：出手点与 `weaponphys.throw_velocity` 的起点一致。高度对齐不再拿
  chunk0 —— 爬杆时它在抓杆手上、比胸口低十几像素，「到同一高度就投」永远不成立。
* `fsm._face_threat_tick()` 新增杆上迎战分支：手里有家伙就在杆上原地掷（横杆 / 竖杆
  同一套 `_pole_throw`）。这是「横杆、竖杆上几乎不尝试投矛」的来源。

**④ 先预演直接命中，再考虑起跳（fsm）**

* 新增 `_shot_would_hit(tgt, dir_x)`：真实弹道 + `sweep_hit_predicted`。
* `_throw_weapon_at()`：能命中就直接投；不能中、且在地面、且高度差 > `THROW_JUMP_DY`
  才起跳。旧实现只看高度差 →「明明平投就能中却先跳起来打空」。
* `_fight_climb_tick()` 的高度判据同样换成 `_shot_would_hit`。

**⑤ 匍匐（CrawlAway）门禁与朝向**

* 进匍匐要求 `on_floor() and not on_pole and _crawl_cd <= 0`，触发骰子一轮只掷一次
  （旧实现每帧重掷 → 几十帧内必然趴下 =「一靠近就后退」）。
* `_crawl_enter()` 兜底：杆上 / 空中立刻收尾（`_crawl_left = 0`、`_crawl_from = None`、
  `face_lock = 0`），状态不再停在 CrawlAway 和杆控制器抢身体（「爬杆触发匍匐卡死」）。
* `_st_crawlaway()`：`face_lock` 把身体朝向钉在威胁那一侧，移动仍旧 `walk_to` 反向。
  匍匐的正确定义是「身体朝威胁、头也看威胁、身体反向挪」；旧实现让 `walk_to` 每 tick
  把 `facing` 改成移动方向，三个朝向互相抢，才出现「身体朝威胁 / 头朝后 / 平移后退」。
* `core/creature.py` 新增 `face_lock`，在 `_movement_update()` 末尾覆盖 `facing`。

**⑥ 两套杆逻辑：结论（需求 1/3/4）**

* `world/pole.py`（几何）本来就是共享的，`Pole.kind` 只决定能力差异。
* `behavior/pole_climb.py`（竖杆控制器）与 `world/hpole.py`（横杆控制器）**物理分工不同，
  不该合并**，正是文档说的「统一接口，分开物理」。
* `planning/pole_reach.py::_PoleClimb` 不是第三套实现：它已经在驱动同一个 `PoleClimber`
  （`_ensure_climber`），只是加了「爬到指定高度」。
* `handoff` 也不是两套：竖 / 横控制器都只**产出**同一元组，FSM 只有一个 `_pole_handoff` 消费者。
* 所以「杆」这条线上真正的冗余是 **AI 的提问方式**：旧代码到处 `if pole.kind ==
  "vertical"` / `if b.on_pole`。本轮收成 `combat_position()` 一个提问。
* `_pick_climbable_pole(kinds=("vertical", "horizontal"))` 成为横竖统一的查询入口；
  两个真正只要竖杆的调用点（FLEE 上杆、`PoleClimber` 兜底）显式传 `("vertical",)`，
  免得横杆被塞进竖杆控制器。
* 结论：**bug 1/2/3 的来源不是杆的物理实现**，而是投掷 / 命中几何多头（本轮统一）；
  **bug 5 的来源是「没有唯一的身体控制权仲裁」**（本轮用 `face_lock` + 入口门禁压住）。

**⑦ 矛大师骨针（bug 4）**

* `needle_tick()` 去掉 `or self.stuck_to is not None`：扎在生物身上不再冻结整个 fade
  生命周期（旧实现白针永远不黑、黑针非得鼠标拔下来才消失）。只有真的被持有
  （手里 / 鼠标拖着 / `held_by`）才暂停。

**验证**：`work/scratch/e2e_r149.py`（弹道逐帧对拍、命中几何、薄封装、`pin_tip`、骨针
生命周期、CombatPosition、直接命中不再起跳、杆上投矛、匍匐门禁与 `face_lock`、杆查询）
+ `run_all19.ps1` 全量回归（fails=0）；离线渲染 `r149_spear_tip.png` 目视核对
「矛尖插在蜥蜴身上而不是空气里」。同步更新了两条与新口径冲突的旧断言：
`e2e_r87.py`（匍匐从「不许倒退」改成「身体朝向与视线同侧」）、`e2e_r127.py`
（扎在生物身上的针现在照样褪到 GONE）。

### R148 · LizardTongue 舌击 + 后空翻 + bodyWiggleCounter 事件

回收 R146/R147 遗留的两个「字段存在但没接线」：
反编译里 `breed.tongue / tongue_range` 早就抄进来了却从未读过，
以及后空翻一直只是「跳高一点」。

**① 舌头（文档 §六：LizardTongue / LizardSpitTracker）**

* 新增 `TONGUE_SPEED 7.5 / TONGUE_RETRACT 7.0 / TONGUE_PULL 7.0 /
  TONGUE_GRAB_R 18 / TONGUE_MOUTH_R 22 / TONGUE_CD 70 / TONGUE_W 3.2 / TONGUE_JAW 0.65`。
* `_tongue_ready()` 门禁：有舌头且有射程、没在同一趟、不在咬合前摇/保持、
  没死、没被打晕、没被拎着、没在爬杆、嘴里没叼东西。
* `_shoot_tongue(o)` 等于原版 `LashOut`：舌尖从嘴点射出，开狼、
  抬高 bodyWiggleCounter、进冷却。
* `_tongue_tick()` 状态机：`out`（射出，射程到头自动转 `back`）→ `hold`（舌尖
  碰到猎物 = 原版 `Grab`）→ 一边收舌一边 `DragChunk` 把猎物拖到嘴边
  （`_tongue_pull`，拖拽速度 = 收舌速度，两者同步不会脱节）→ 到嘴转
  `AttemptBite`（`_start_bite`）→ `back` 收回归零。拽不动的东西（石头类）舌头卷到底就放舌，
  不永远噠着，也不硬改别人的坐标。
* `_lunge()` 接线：咬不着但舌头够得到就射舌（白蜥那根 440px 长舌）。
* `lizard_gfx._draw_tongue()`：从嘴点到舌尖的渐细舌带 + 舌尖圆点，只在
  舌头在动时画（平时留在嘴里，一像素不占）。

**② 后空翻（文档 §9.4：不是「跳高一点」，是身体姿态的角动量）**

* `breed.flip_hop` 由跳跃能力派生（`charge_leap or jump_fac >= 0.9`：蓝 / 青 会，粉 / 绿
  不会），和 turn_hop 一样是独立能力，不再拿「会不会爬」凑。
* `_start_flip()` / `_step_flip()`：起跳后 `FLIP_TICKS 14` 帧里**绕质心刚体转过
  `FLIP_ARC 360°`**（节间距离守恒，驱动点一起转）；头在翻滚时跟着转。
  `FLIP_GRACE 2` 帧宽限等离地，宽限用尽还没离地就彻底作废（不留
  幽灵翻滚），落地立即作废。

**③ bodyWiggleCounter（文档 §10.5）**

* 事件抬高：发现猎物（`_adopt`，同一目标不重复抬）、起跳、射舌。
* 空闲随机抬高：`WIGGLE_IDLE_P 0.02` / tick，上限 0.25 以下一档——停着也
  不像一块死物。

**验证**：`work/scratch/e2e_r148.py`（60 项断言）+ `run_all19.ps1` 全量回归
（fails=0）；离线逐帧渲染 `r148_tongue_flip.png` 目视核对舌头伸缩与翻滚姿态。

### R147 · ThreatField / CrowdField + 动态导航代价 + EscapeGoal（贴身反应排在路线之前）

文档：《ThreatField 与动态导航代价（调整版）》。核心不是「离威胁多远」一个标量，
而是给整张导航图加一层**会随时间变化的世界危险场**：威胁带速度、带它所在的杆/面，
代价按拓扑加权；逃跑不再是 FSM 给一个 x，而是 Planner 在导航节点里挑安全区，
交给 RouteExecutor 执行。

**① `planning/threat.py`（新）**

* `Threat`（actor / x / y / vx / vy / strength / kind / pole / surface）、
  `ThreatSample`（danger / nearest / time_to_contact / same_pole / same_surface）、
  `ThreatField`。
* `update(win, geom=None)` 每 tick 采一次：活蜥蜩、愤怒的面条蝇成体、敌对拾荒者。
* `sample(x, y, pole=, surface=)`：主威胁取 max，其余按 `_EXTRA_W=0.25` 少量叠加；
  拓扑乘数同杆 5.0 / 同面 1.8 / 同区域 1.2 / 隔墙 0.3。
* `predicted_sample()`：按 (0, 20, 40) tick 三个预测视界算「它冲过来会怎样」。
* `eta()`（`THREAT_ETA_MIN_SPEED` 兜底）、`edge_cost()`（沿边采 3~5 点取 max ×180，
  同杆软惩罚 +800 不禁止）、`danger_at()`、`threat_of()`、`pole_surface_at()`。
* 模块级 `same_terrain()` / `hostile_needleworm()` / `hostile_scavenger()`，
  `_SCREEN_FLOOR` 给地板一个稳定身份。

**② `planning/crowd.py`（新）**

`CrowdField`：`point_cost()` 半径 180、`exp(-d/55)`；`pole_riders()`；`edge_cost()`
采样 Σpoint_cost×25 + 杆占用×260。

**③ 导航图吃动态代价**

* `NavigationEdge` 加 `occupancy_cost`（**静态**占用；每 tick 变的拥挤不写回缓存边）。
* 新增 `NavContext(threat_field, crowd_field, me, body, pos)` 与
  `dynamic_edge_cost(e, ctx) = occupancy_cost + threat.edge_cost + crowd.edge_cost`。
* `NavGraph` 的 `_run / _ensure / path / astar / reachable` 全部接 `context`，
  代价从 `e.time` 变成 `e.time + dynamic_edge_cost(...)`；带 context 的查询每 tick
  现算，**不缓存**（威胁在动，缓存等于把危险记死）。
* `planning/surface.py::route_to(..., context=)`、`world/terrain.py::_run` 一路转发。

**④ EscapeGoal：逃跑变成一条导航目标**

* `planning/goal.py` 加 `EscapeGoal`（threat / min_safety=0.75 / min_distance=180）。
* `SurfaceGraph.escape_route()`：遍历节点 → 安全度 `exp(-danger) >= 0.75` 且离威胁
  `>= 180` 且 `in _returnable` → 评分 `cost + danger*500 + 死胡同300 + 拥挤*260`；
  一个都挑不出来就 `_panic_route()`（可达且最远）。
* `RouteExecutor` 加 `route_fn` / `plan`，新增 `refresh()`（只有没有 leg 在跑才换路线）。

**⑤ 世界层接线**

`window.py` 的 `__init__` 建 `threat_field` / `crowd_field`；`_do_tick()` 在
`for pet in self.pets: pet.step()` **之前** `update()` 两个场 —— 世界一份，不是每只猫一份。

**⑥ FSM：逃命走路线，但贴身反应永远优先**

第一版把「有没有逃生路线」摆在最前面，路线一有就把三条贴身反应全吃掉，
表现为：被逼到墙角不再跳过威胁、在它背后不再匈匈、杆上/空中的处置被绕路，
共 7 个旧回归（r29 / r68 / r78 / r87 / e2e_wants / e2e_r125）一起红。改成分层：

1. 退无可退（贴墙 / 被逼退够远够久）→ 当场 `threat_jump` 跳过它，**路线作废**；
2. 近处有竖杆 → 爬上去；
3. 只在真的在它背后 → 匈匈潜行；
4. 都不适用 → Planner `escape_route()` 找安全区（`_flee_plan` 保鲜 16 tick）→
   `RouteExecutor`；
5. 连路线都给不出来 → 旧的横向撤退。

`_st_fleelizard()` 里也补了同一层：执行器在跑的时候仍然先判「退无可退 → 跳」，
空中则整段交给物理（`walk_target_x = None`，路线留着落地接着走）。
`_safe_from()` 改成**时间比较**（`tf.eta(t, me) > dist(me, safe)/4.2 + 12` 且
`danger_at(me) <= 0.22`）；但危险表里查不到这只威胁时仍然回落旧的距离口径 ——
不然「表这一 tick 还没刷新」会被读成「天下太平」，猫当场退出逃跑态。

**⑦ `_face_threat_tick()`：杆上/空中不再直接退出决策**

旧版 `if not b.on_floor(): return False` 就是「杆上不躲」的来源。现在杆上/空中只处理
贴脸一档（`_threat_too_close()`：水平 76px，或同一根杆上纵向 150px），中距离的
迎战 / 捡家伙 / 救人留到落地再走完整决策。

**⑧ 回归**

新增 `work/scratch/e2e_r147.py`（世界层接线 / ThreatField 拓扑与预测 / 动态代价真的进了
Dijkstra 与 A* / CrowdField / EscapeGoal 与安全节点 / 安全判定是时间不是横向距离 /
贴身反应优先于路线 / 结构断言），并入 `run_all19.ps1`；全量 148 个脚本
`fails=0 []`。

### R146 · 物同帧贴手（去自造偏移）+ 线/矛真实渐隐 + 矛大师爆米花规则

用户实测：**「依旧大量出现物体悬浮、错位」**、要求去掉「重置窗口地形」按钮、
**「矛大师的线要在两秒后渐隐消失」**（并指出「矛本身的渐隐消失没有真实实现：
视觉上一会儿突然消失了」）、以及 **「矛大师不能吃爆米花，但活针扎未开荚的
爆米花 +5 饱食度、扎已开荚的 +1」**。

**① 物体悬浮 / 错位**

两条自造的「物离开手」全删，并把「物跟手」收成**同一帧**：

* R142 把持物的手推开 `POLE_CARRY_DX=7px`（手浮在杆旁）→ R145 又把这 7px 加到
  **物**上（矛浮在杆旁）。原版根本没有这个偏移 —— `Player.cs:5989` 就是
  `grabbedChunk.MoveFromOutsideMyUpdate(eu, hands[i].pos)`，物直接摆在手上。
  `_pole_item_offset()` / `POLE_CARRY_DX` 连常量一起删；三处持物（矛 / 石头 /
  果子）统一 `x, y = cx, cy`，手贴杆（`SlugcatHand.cs:201`，MiddleOfTile ± 1）。
* **差一帧**：`b.step()` 跑在 `graphics.update()` 之前，里面那三次
  `_apply_carry_*` 读到的 `hand_pos` 还是上一帧的 → 物恒定慢一帧（手一动就看
  得见「物浮在手边 / 滞后」）。新增 `SlugcatBody.sync_carried_to_hands()`，
  在 `petunit.step` 的 `g.update()` 之后用同一套逻辑再对齐一次：物和手落在
  同一帧（`hand.lx/x` 与 `sp.last_x/x` 现在是同一对坐标）。

**② 去掉「重置窗口地形」按钮**

`ui/tabbar.py` 的按钮 + `_reset_window()` handler + 三条 i18n
（`btn_reset_window` / `tip_reset_window` / `toast_window_reset`）一起删。
`reset_window_geometry()` 本体保留 —— 「清除可交互实体」之后那次自动重跑还在。

**③ 矛大师的有机细线：2 秒后渐隐**

`NeedleThread` 加 `age` / `alpha`：拉出后完整显示 `THREAD_HOLD_TICKS=80`
（定步长 40fps × 2s），再用 `THREAD_FADE_TICKS=40`（1s）把 alpha 褪到 0 并置
`dead`；`draw()` 每段的 alpha 乘上它。另外 `Spear.needle_thread_done` 记住
「这条线的寿命已经用完」，免得 `_needle_thread_tick` 下一 tick 又给同一根针重拉
一条（被顶替的旧针也一并标记）。

**④ 矛本身的渐隐：白 → 黑 → 黑保持 → 整体渐隐 → GONE**

反编译 `Spear.cs:1333-1356` 只按 `fadecounter/400` 把颜色从白 Lerp 到黑，
**没有 alpha**；旧实现是黑到 `fade==0` 的那一 tick 直接 GONE（「一会儿突然
消失」）。`needle_tick()` 重排成三段状态机（黑化 → 黑保持 `NEEDLE_BLACK_HOLD`
→ `NEEDLE_ALPHA_FADE=80` 把 `needle_alpha` 从 1 褪到 0），褪尽才真消失；
钉成杆的针走完黑化就停住，仍留作场景杆。`primitives.blit()` 新增 `opacity`，
`draw_needle()` 新增 `alpha`（alpha=0 一像素都不画）。

**⑤ 矛大师与爆米花**

* 矛大师**没嘴**：`diet = DIET_SPECIAL` → 爆米花（plant）不可食，
  `_nearest_cob(feedable=True)` 与 `_st_eatcob` 的啃食分支都按 `_can_eat()` 拦住
  （原版 `SeedCob.cs:335` 也把 Spear 排除在 `handOnExternalFoodSource` 之外）。
* 活针吸食（原版 `Spear.cs:1096-1108`）：`_spear_needle_feed_cob()` ——
  未开荚 `AddFood(5)` + `Open()`，已开荚 +1（用户口径）；一根针只喂一口
  （喂完 `Spear_NeedleDisconnect`）。普通矛照旧只开荚、不喂食。

回归：`e2e_r146.py`（新增）+ `e2e_r91/94/127/144` 口径同步；全量 `fails=0`。

### R145 · 持矛朝向 / 爬杆手位回归原版（反编译对拍）

用户实测：**「矛在右侧、猫向左走，矛就左右翻转」**、**「爬杆子手要贴着杆子」**，
并要求「底层逻辑有隐患，反编译看看」。查下来两处都是自造角度/自造偏移，不是参数没调好。

**① 持矛朝向：`facing * 25` 是自造的 → 换成原版 `spearDir`**

旧实现 `spear_hold_angle()` = `fdir * (25 + wob)`，`fdir` 直接取 `facing`。
`facing` 是**瞬时**的：猫一走反向，那一帧整根矛镜像 50° —— 用户看到的「左右翻转」。
原版根本不是这么算的（`Player.cs:6006-6034 GetHeldItemDirection`）：

```
v = DirVec(mainBodyChunk.pos, grasps[hand].grabbed.bodyChunks[0].pos) * (hand == 0 ? -1 : +1)
if (animation != HangFromBeam) v = PerpendicularVector(v)          // (-v.y, v.x)
if (bodyMode == Crawl)  v = DirVec(bodyChunks[1].pos, Lerp(hand.pos, bodyChunks[0].pos, 0.8))
elif (animation == ClimbOnBeam) { v.y = Abs(v.y); v = Slerp(v, DirVec(body1.pos, body0.pos), 0.75) }
elif (grabbed is Spear)
    v = Slerp(v, DegToVec((80 + Cos((animationFrame + (leftFoot ? 9 : 3)) / 12 * 2π) * 4 * spearDir)
                          * spearDir), Abs(spearDir))
```

要点（都已落地）：

* **朝向由 `spearDir` 决定，不看 `facing`**。`PlayerGraphics.cs:1987-1998`：
  `bodyMode == Stand && input.x != 0` 时每 tick ±0.1（限幅 ±1），否则朝 0 每 tick 退 0.05。
  于是反向走路是**转过去**的（+80° → 0° → −80°），不是瞬间翻面。
* **双持两支永远严格平行**：那一档的目标角只跟 `spearDir` 有关，摆动相位
  `(animationFrame + (leftFoot ? 9 : 3)) / 12 * 2π` 里**两只手共用同一个 `leftFoot`**。
  旧版按手错开 0.75/0.25 是自造的。
* **静止时两支各按自己那只手的 `Perp`**（右手 +30.96°、左手 −30.96°）。
  这不是「外八字 bug」，是 `PerpendicularVector` 那一行的必然结果，和参考图一致。
* 物永远读那只手的 `hand_pos`（= `Player.cs:5988` 把 grabbed chunk 挪到 `hands[i].pos`）。

**② 爬杆手位：`POLE_CARRY_DX` 推手 → 手贴杆，偏移改由「物」承担**

R142 把「别让矛压在杆线上」的 7px 偏移加在**手**上，结果手浮在杆旁边。
原版 `SlugcatHand.cs:193-215` 的手是**贴杆**的：

* `ClimbOnBeam`：`absoluteHuntPos = (MiddleOfTile(body0.pos).x, body0.pos.y)`，
  `y += (cond ? -3 : 3) + 6f`，`x += ±flipDirection` —— 行竖杆上只有 **±1px**。
* `HangFromBeam / GetUpOnBeam`：`y = MiddleOfTile(body0.pos).y - 1` —— 手抓在杆身上。

现在 `rendering/graphics.py::_beam_hand_target` 不再推手，偏移交给
`core/creature.py::_pole_item_offset()`：竖杆 → 物挪到杆侧 `∓x`，吊杆 → 物挪到杆身下 `+y`。
`graphics.py` 里那个已经没人用的 `POLE_CARRY_DX` import 一并删掉。

**③ 回归口径同步**

`e2e_r39 / r114 / r141 / r142 / r144` 里 15 条检查编码的是旧口径（「双持同角」「竖杆矛角恒 0」
「持物的手从杆线上伸出去」），按原版口径改写：静止镜像 ±30.96°、`spearDir=±1` 时严格平行、
竖杆 `|角−杆轴| < 26°`、手贴杆且偏移由物承担。`fails=0`。

**验证**：`run_all19.ps1` → `=== round done; fails=0 []`；
`r145_hands.py` 出图目视：`E` 手贴杆（x=149/151，杆 x=150）、`C` 朝左走矛 −80°（转过去，不翻面）。

### R144 · Wall / Pole / Background 三方拆分 + 窗口重置 + 持物手收敛

R143 文档末尾那段「追加审计：三分法」当时被判定与 R135 已交付的 `WINDOW_EDGE` 语义正面冲突，
留给了单独一轮。本轮就是那一轮：把它做完，并顺手收掉用户实测的三件事（窗口重置、手、双持基准）。

**① Wall / Pole / Background 彻底分家**

R135 起 `WINDOW_EDGE` 是「一个身份 = 碰撞体 + 可攀爬竖线 + 顶端可站」，结果就是**墙被当成杆**：
`terrain.vpoles()` 把 `win.wall_surfaces` 整体并进「竖杆」，导航层再按 `kind="pole"` 发出去。
只删一个 `wall_surfaces` 不解决问题（`TerrainGraph` 里 `can=False` 的竖线节点依然 `stand=True`）。

现在竖线是**三类互不重叠**的地形，各有各的能力位：

| 类型 | `kind` | 碰撞 | 可站 | 攀爬能力位 | 谁有 |
| --- | --- | --- | --- | --- | --- |
| 真竖杆 | `pole` | 有 | 端点可站 | `climb_pole` | 粉 / 蓝 / 黄 / 白 / 红 / 黑 / 蝾螈 / 青 / 等 |
| 实体墙（庇护所墙条） | `wall` / `shelter_wall` | 有 | 顶面可站 | `climb_wall` | 蓝 / 白 / 电鳗 |
| 背景区域（别的窗口露出来的竖边） | `background` | **无** | **不可站** | `climb_background` | 会爬墙的品种 |

- `planning/navgeom.py`：`WINDOW_EDGE` 常量留名（兼容旧引用）但**不再产出任何地形**；
  新增 `BACKGROUND` / `CLIMB_BACKGROUND`，`VERTICAL_KINDS` 换血；窗口左右竖边整段删除
  —— 屏幕边框本来就由 `chunkphys.aabb_wall_collide` / `_integrate` 管，不是地形；
  ⑦ 段落里那条「把背景当 obstacle」的旧逻辑一并删掉，背景从碰撞层消失。
- `planning/navgraph.py`：`Capabilities` 加 `climb_background`（默认跟 `climb_wall` 走，因为原版
  就是 WallClimber 干的活），`climb_edge` 恒 False 废弃；`allows_climb("background")` 认它。
- `world/terrain.py`：新增 `backgrounds()`；`walls()` 只回实体墙；`window_edges()` 恒空；
  `_build_graph()` 的 `stand=` 从 `bool(s.stand and can)` 改成 `bool(can)` —— 背景按三分法本身
  不是可站面，但会 Background Climb 的品种依然要占它的两端，否则目标落在背景上算不到节点。
- `world/lizard.py`：`_CLIMB_MODES` 换成 `climb_background`；`tq.walls()` 从三条碰撞循环里
  **全部删除**（背景不是实体，留着「背景被当墙」会以碰撞形式长回来；庇护所墙体走
  `_collide_solids`）；`_climb_step` 里 `wall` 与 `background` 都要求 `climb_wall and wall_attach`。

**② 窗口重置**

旧 `_refresh_platforms()` 有个死角：开关一关就直接 `return`，场上那份过期窗口地形（平台 +
墙段）**永远留着**，导航快照又只认当时算出的那一份 —— 用户实测「清掉重画一下就好」就是这个。

- `window.py`：`_sync_window_terrain()` 成为窗口几何的**唯一生成点**（顶边 → `chunkphys.set_platforms`；
  竖边 → `walls` / `wall_surfaces`）。用 `_win_tops` / `_win_wall_rects` 记录「我们自己放上去的
  那一份」，区分测试夹具 / 鼠标虚杆注入的平台与墙段 —— 关开关只清自己那份。
- `reset_window_geometry()`：显式「窗口重置」入口，`force=True` 时连注进来的旧地形一起清。
  工具栏新增「重置窗口地形」按钮，「清除可交互实体」之后也自动跑一次。
- `_drop_nav_caches()`：不只推版本号，还把 `_navgeom_cache` / `_terrain_graphs` / `_nav_sig`
  真正丢掉（旧实现只改 `_nav_version`，可这几个缓存根本不看版本号）。
- 这些属性在 `__init__` 里就给了初值，且挪到第一次 `_refresh_platforms()` 之前，
  免得初始化那一帧把 `walls` 又覆盖回空。

**③ 持物手：物跟手，手 aim 到携带点**

根因是**自我反馈**：`_apply_carry*` 调的是
`self._aim_hand(side, cx if aimed else None, cy if aimed else None)`，
而 `cx, cy` 来自 `_carry_anchor()` —— 那是**物自己当前的位置**。于是「手被瞄准到它现在所在的地方」，
永远走不到身侧携带点，物每帧只挪 0.1px。用户实测的「矛浮在手前面 / 没在手上」就是它。

- 新增 `_aim_carry(side, aimed)`：`aimed=True` 时瞄准 `_carry_pos(side)`（手**该去哪**），
  三处持物（果 / 石 / 矛）统一走它；`_carry_anchor` 维持「物永远 = `hand_world(side)`」。
- 双持基准：`DUAL_SPEAR_SPLAY` / `DUAL_SPEAR_BASE_K` 归零（常量留名供旧测试 import，注释写明废弃），
  `spear_hold_angle()` 的两支矛**同角度同方向**（平行），摆动只是在基准上叠一层相位差小幅摆动
  —— 对齐用户给的四格参考图（双持基准不是外八字，摆动是叠加量）。

**回归**：`e2e_r144.py` 新增（三分法 23 项 + 窗口重置 11 项 + 手/双持 8 项，全绿）；
`run_all19.ps1` 全量 19 联跑 `fails=0`。视觉核对出图见
`work/scratch/r144_{A_stand1,B_stand2,C_vpole2,D_hpole1}.png`。

### R143 · 收口：行为→路线哲学、Jump 归位统一图、target-drift、导航黑名单、真伏击 / 包夹

外部审计（用户贴的整理稿）结论是「R135–R137 的统一导航已经成立，别再大改寻路」，并给出
**下一轮只做这五件事**。本轮把这五件全部落地，一行不留。

文档末尾还有一段「追加审计：Wall / Pole / Background 三分法」，**本轮没做**：它要求把
`WINDOW_EDGE` 从基础 Surface 类型里拿掉、把背景墙拆成 `BackgroundRegion`，这与 R135 已交付的
设计正面冲突 —— `planning/navgeom.py` 的模块注释明确写着 `WINDOW_EDGE` 的语义就是「一个身份 =
碰撞体 + 可攀爬竖线 + 顶端可站」。那是一次真正的几何重构，不该塞进收口轮，留给单独一轮。

**① 行为各自指定路线类型（文档 §5）**

`route()` 本来就支持 `SAFE / RETURNABLE / ONE_WAY / RISKY / DEAD_END`，但上层从来不传 ——
`lizard_ai._terrain_route()` 一律默认 `RETURNABLE`，「五种路线哲学」等于不存在。

- `world/terrain.py::route(..., kind=)`：`kind` 现在可以给**一串**（从严到松），取第一个成立的。
  于是「我要 SAFE，但只有 RETURN 可用」会降级成 RETURN，而不是直接判无路线。
- `lizard_ai.route_kinds(intent, prefs)`：意图 → 路线类型链。
  Hunt 看性格（伏击型 `RETURNABLE` 优先，冲刺型 `ONE_WAY` 优先）／Carry `SAFE→RETURN`／
  Flee `SAFE→RETURN→ONE_WAY`／Investigate `RETURNABLE`／Pack `ONE_WAY`。
- 落点：`_terrain_route(..., kind=)`、`_vertical_detour(..., kind=)`、`plan_approach(..., route_kind=)`；
  Hunt（`_plan_for`）、Investigate、Carry（去巢穴）、Flee（找逃生点）、Pack（去包夹位）各自传入自己的链。
  路线的实际档次写在 `plan.reason` 里（`navgraph:one_way` / `navgraph:safe` …），测试直接钉它。

**② Jump 成为可比较的 NavigationEdge（文档 §6）**

旧顺序是「先自己枚举起跳弧，失败了才问图」—— 两套 planner 打架。`plan_approach()` 现在是：

1. 同层 → 直线扑（原版也是直线扑）；
2. **统一导航图先说**：`_terrain_route()` 给 walk / climb / jump / drop / hop 的 MovementConnection；
3. 图给的那条 **jump 边**再交给 `sim_arc()` 细化起跳点（`_launch_search(cx=边起点, span=半个搜索窗)`）；
4. 图里没有连接时，才退回本地弧线搜索（`arc:launch`，Jump Executor 的兜底）。

顺带把起跳点搜索抽成 `_launch_search()`，它只回答「这一跳从哪儿起跳」。

**③ 移动目标 target-drift（文档 §12）**

`ApproachPlan` 增加 `anchor`（规划时目标在哪）与 `drifted(tx, ty)`（阈值 `TARGET_DRIFT = 24px`）。
`_terrain_route` / `plan_approach` 造的计划都带上猎物当时的坐标；`_route_tick`、`_approach_tick`、
`_vertical_detour` 在目标漂走时**立刻重规划**，不再硬等 `ROUTE_TTL`。

**④ StuckDetector 分两种卡住 + 导航黑名单（文档 §13）**

- 区分 `STUCK_PHYSICS`（路线对、位移被墙 / 碰撞吞掉 → 原地小跳脱困，**不丢路线**）与
  `STUCK_NAVIGATION`（同一条边反复把人带到同一个死点 → 记进黑名单）。
- 新增 `block() / blocked() / blocked_keys()`；黑名单是**世界知识**：`reset()` 不清它，
  `BLACKLIST_TTL = 240` 过期。
- `planning/navgraph.py`：`NavGraph.astar/path/_run` 接受 `avoid`（节点下标集），Dijkstra 的缓存键也带上它
  （否则「先问一次、再带黑名单问」会复用旧结果）；`TerrainGraph.path_edges(..., avoid=)`；
  `TerrainQuery.route(..., avoid=)` 用 `anchor_key()` 把量化锚点键翻成节点下标（源点永不禁）。
- `lizard._route_tick`：等级 1 按类型分流，等级 2 丢路线；黑名单经 `self._stuck.blocked_keys(tick)`
  传给每一次寻路（Hunt / Investigate / Carry / Flee / Pack 全走同一条路）。

**⑤ 真正的白蜥伏击 + 黄蜥包围（文档 §14/§15）**

两者都从统一地形里挑点，不再是「目标坐标 + X 偏移」：

- `stand_anchors(terrain, caps, cx, cy, r)`：可站面上采样出来的落点候选（`NavGeometry.floors`）。
- `pack_slots(...)`：猎物的前 / 后 / 左 / 右四个落点（平地退化时沿面补齐，绝不挤成一列）；
  `lizard._pack_seat()` 用**路线代价**挑最划算的那个（`PACK_SEAT_TICKS = 30` 缓存一轮），
  于是每只黄蜥各自选位 —— 才是围过去。旧 `flank_offset()` 保留（兼容旧测试）但行为层不再调用。
- `ambush_point(...)`：猎物去路的侧后方（视野锥外）、有遮挡加分、离猎物约一个扑咬距离、离自己近 ——
  白蜥的 `lurk` 从「决定不追」变成「挪到伏击点等」，`_lurk_idle()` 负责走过去。另外 `act()` 里
  `st == "Lurk"` **不再**要求 `o is None`：以前带目标的 Lurk 会掉进 `_lunge_toward` 直接冲锋，
  伏击意图等于没有。
- Flee 升级：威胁不在同一层时，从可站面里挑「离威胁最远」的落点、走 SAFE 路线过去
  （`_flee_seat`，最多试 `FLEE_SEAT_TRIES = 3` 个）；逃跑路线不含跳（Flee 没有跳跃执行器）。
- Carry 升级：巢穴不在同一层时走 `SAFE` 路线（`no_jump=True`），不再对着 `den.x` 一路撞。
- `_climb_obs(st, o)`：Flee / Carry 这类「非追猎」状态只有在**自己的正式路线含爬段**时才把观察交给
  攀爬层，避免它们临时抓一根竖线。

**性能**：30 只蜥蜴 300 tick 实测 `7.04 ms/tick`（改前 `7.43 ms/tick`）—— 图本来就有缓存，
每 tick 多一次 A* 没有变成热点。

**测试**：新增 `work/scratch/e2e_r143.py`（33 项全绿）—— 路线类型链（合成图验证 SAFE 被高风险边否掉、
链式降级、顺序有意义）、Jump 归位（合成图给 jump 边 → 计划来自 navgraph；无图 → `arc:launch`）、
target-drift（阈值 / 锚点透传 / 行为级重规划）、StuckDetector 分类与黑名单（`avoid` 穿透
astar / path / route 与 Dijkstra 缓存键）、伏击点 / 包夹位（只来自可站面、四个互不相同、锥外、
无地形退化）、白蜥伏击待机真的朝伏击点挪、黄蜥包夹位来自路线代价、Flee 走 SAFE 路线。
`run_all19.ps1` 已登记（128 个脚本，`fails=0`）。

### R142 · 杆上持物：物永远贴手，偏移改由手承担

用户实测截图（竖杆）：手里的矛浮在杆旁、没在手上。—— 这和 R141 那两张实测图（横杆）是同一个错误。

**根因：上一版把偏移加在「物」上，手还在杆上**

`core/creature.py::_carry_anchor()` 原来返回「手位 + 偏移」（竖杆横向 ±7px / 横杆向上 7px），而那只手仍然贴在杆上/杆身上。于是物从手里脱开漂在旁边（用户截图里的 7px 缝；横杆上则是漂在手上方）。上一版只想到「别把物画进杆里」，却把「物贴手」这条更硬的规则破坏了。

**修法：物 == 手；拿着东西的那只手从杆上伸出去**

- `core/gfxmath.py`：常量 `POLE_CARRY_DX = 7.0` 搬到这里（渲染层也要读；放在 core/creature 会形成 rendering → core.creature 的反向依赖）；`core/creature.py` 改成从这里 import（对外名字不变）。
- `core/creature.py::_carry_anchor()`：**删掉两个偏移分支**，直接返回那只手的实际位置。
- `rendering/graphics.py::_beam_hand_target()`：
  - `ClimbOnBeam`（竖杆）：拿着东西的手 `hx ± POLE_CARRY_DX`（左手向左、右手向右，即原来物所在的位置），空手不动。
  - `HangFromBeam` / `GetUpOnBeam`（手就在杆身上）：拿着东西的手 `hy -= POLE_CARRY_DX`（向上撑），空手不动。
  - 新增 `_hand_carrying(side)` 读 `body.hand_items()`，判断这只手拿了没有。
- 结果：物不再自己算第二套坐标，手到哪里物到哪里；「不压杆」改由手臂伸出去完成（与参考图里「手拿着东西伸到杆外」一致）。

**A/B 目视核对**（`work/scratch/_vis142.py` → `work/scratch/r142_pole.png`，上行=旧 R141、下行=新 R142；五格：竖杆+矛 / 竖杆+石头 / 竖杆双针 / 站横杆+矛 / 吊横杆+矛）

| 场景（实测坐标） | 旧 R141 | 新 R142 |
|---|---|---|
| 竖杆 手右 | (199.0, 185.1) | (206.0, 185.1) |
| 竖杆 矛心 | (206.0, 183.5) | (206.0, 183.5) |
| —— 缝 | **7.0 px** | **0.0 px** |
| 站横杆 手 / 矛 | 手 (220,197) / 矛 (220,190) | 手 (220,197) / 矛 (220,197) |
| 吊横杆 手 / 矛 | 手 (208.7,214.9) / 矛 (208.7,207.9) | 手 (210,212) / 矛 (210,212) |

物的画面位置几乎不变（仍在杆侧 / 杆上方），变的是**手过去了**——所以腾出来的那只手现在真的拿着它。

**测试**：新增 `work/scratch/e2e_r142.py`（15 项，全绿）—— `_hand_carrying` 空/满手；竖杆手位（拿着就伸出 7px、空手就收回杆线，左右互换后同样成立）；吊杆手位；站杆顶不受影响；实机两格（竖杆/横杆上物与手 <0.5px 且手确实离开了杆线）；源码级（`_carry_anchor` 不再自己挪物）。`run_all19.ps1` 已登记（127 个脚本）。

**改既有守护**：`e2e_r140b.py` §3 与 `e2e_r141.py` §2/§5 原来钉的是「物自己偏出去」——那正是本轮要修的行为，已改成新口径（物 == 手）。

**回归**：`run_all19.ps1` **127 个脚本 fails=0 []**；`tools/parts_audit.py --check` exit=0；`tools/sprite_variants.py` 正常。

### R141 · 横杆持物订正（两手张开 + 物不压杆 + 矛不横放）

用户反馈「横杆持物还是做错了」，附两张玩家实机截图（站在横杆顶：两臂向两侧张开、手里的矛是**正常斜持角**而不是横躺在杆上；竖杆上托石头：石头偏出杆线、不压杆身）。根因是两处硬编码：

**① 两只手被拉到身体中线（`rendering/graphics.py::_beam_hand_target`）**

旧版 `StandOnBeam` 有一段「平衡样态混合」`if anim == "StandOnBeam" and self.disbalance < 40.0:`（s = 1 时把 `relx` 归零、`rely_up` 拉到 15px）。但 **`self.disbalance` 全仓库只有 `graphics.py` 里的初始值 `0.0`，从来没有地方写过它** —— 所以 `s = (40-0)/40 = 1.0`，分支**永远生效**：站杆顶时两只手（以及手里的东西）永远堆在身体中线上方，看上去就像没有输出「两臂张开」的姿态。现在删掉该分支，只保留参考图那一档：`relx = -20 + 40*j`、`rely_up = -4 - 6*sway*∓1`、`speed = 5.0 / quickness = 0.2`。

**② 横杆上的矛被强行横放（`core/creature.py::spear_hold_angle`）**

旧版 `if self.on_pole:` 里有一条 `if self.animation in ("StandOnBeam", "HangFromBeam", "GetUpOnBeam"): return 90.0 if fdir > 0 else 270.0` —— 矛被摆成**沿横杆方向**，等于躺进横杆里。参考图里是**正常持矛角（25° 前上）**。现在改成 `if self.on_pole and not self.on_horizontal_beam(): return 0.0`（只给竖杆留「顺体轴朝上」），横杆走普通 `fdir*(base+wob)+splay` 链路 —— 与站立时逐位相同，且双持时仍然走外八字。

**③ 新增横杆姿态判定 + 持物上抬（`core/creature.py`）**

- 新增 `on_horizontal_beam()` = `on_pole and animation in ("StandOnBeam", "HangFromBeam", "GetUpOnBeam")`，与 `on_vertical_pole()`（`ClimbOnBeam` / `BeamTip`）互斥。
- `_carry_anchor()` 新增一档：横杆上物偏到手**上方** `POLE_CARRY_DX = 7px`（`HangFromBeam` / `GetUpOnBeam` 的手本来就在杆线上，不偏就压杆）；竖杆仍走横向 ±7px，两者不共存。

**A/B 目视核对（`work/scratch/_vis141b.py` → `work/scratch/r141_beam.png`，上行=旧（R140）、下行=新（R141），五格：站杆顶 / 站杆顶+矛 / 吊杆+矛 / 撑上杆+石头 / 竖杆+石头）**

| 场景 | 旧（R140） | 新（R141） |
|---|---|---|
| 站杆顶 两手 x | `(200, 200)`（中线重合） | `(180, 220)`（分居两侧） |
| 站杆顶+矛 矛角 | **90.0°**（沿杆横放） | **25.0°**（正常持矛角） |
| 吊杆+矛 矛角 | 90.0° | 25.0° |
| 矛与手的位置关系 | 矛心 = 手心（压杆） | 矛心 = 手心 **上方 7px** |
| 竖杆+石头 | 物在手右 7px | **逐位不变**（R140 不回退） |

**测试：新增 `work/scratch/e2e_r141.py`**（25 项，全绿）—— `on_horizontal_beam()` 对三种横杆动画为 True、对 `ClimbOnBeam`/`BeamTip`/`on_pole=False` 为 False；横杆时 `_carry_anchor` 返回 `(hand.x, hand.y - POLE_CARRY_DX)` 且 `aimed=False`；横杆矛角 == 站立矛角且 ≠ 90/270；竖杆矛角仍为 0；`_beam_hand_target(0/1, "StandOnBeam")` 分居身体两侧且间距 > 24px；竖杆横向 ±7px 回归；源码级守护（两条旧分支彻底删掉）。`run_all19.ps1` 已登记（126 个脚本）。

**回归**：`run_all19.ps1` **126 个脚本 fails=0 []**；`tools/parts_audit.py --check` exit=0；`tools/sprite_variants.py` 正常。

### R140 · 面板超长/身体拓扑/动作序列/面条蝇三连修 + 手部动画与持矛角度订正

本轮两批需求一起交付。前一批是上一轮遗留的三件大事（面条蝇三连修、身体拓扑、动作序列），后一批是手部动画与持矛姿态。

**① 面条蝇三连修（`rendering/primitives.py` / `world/needleworm.py` / `world/items.py`）**

- **翅膀动画丢失**：R138 §14.1 的合批优化把每组颜色**取均值塌成一个 stop**，翅的「根→尖」渐变被抹平。`ribbon_many` 现在按每条在合批轴线上的投影区间铺开**全部**颜色点（仍只有一个 `QLinearGradient` + 一次 `drawPath`）。
- **尸体不动**：`_step_dead` 从不调 `_step_chain`，`seg` 永远停在死亡那一帧。新增 `_step_dead_chain()`（Verlet 摆链：重力 + 阻力 + 父节速度传递 + 绳长约束 + 地板）。坑：纯竖直摆链是**退化稳定平衡**（绳长约束吃掉向下位移 → 尸体倒立在鼻尖上），靠 `DEAD_CHAIN_TOPPLE` 横向力矩破解，且只在 `|dx| < 0.45*|dy|` 时加（躺平后停手，免得在地上自己滑）。
- **命中 / 拖动 / 删除**：`items._needleworm_at` 改为遍历**整条 `nw.seg`**（只跳 EATEN/GONE）；`_erase_dist` 走整条体节链；`_begin/_step_needleworm_drag` 调 `nw.snap_chain()`（刚体跟手）；池过滤改成 `not in (EATEN, GONE)`（摔出窗外的尸体真的出池）。

**② §9.1 身体拓扑（`world/lizard_gfx.py`）**：新增 `_chunked_path()`——每个 body chunk 一圈**自己的圆截面** + 节间梯形连接面，替代「一条整体平滑软管」；`_draw_body` 填充走分块路径、描边仍走 `_strip_path()`（轮廓一笔连贯不留接缝）。圆截面不能加体轴拉长（会让包围盒外扩像胖一圈），用 `hw` 原值 + 梯形面填缝。

**③ §9/§10 动作序列（`world/lizard.py`）**

- Attack 四阶段 `Prepare → Lunge → Bite → Recover`：`_step_attack_pose()` **逐 chunk 单独写速度**（前节前压、中后节反向/压缩），`_intent()` 把阶段映射成 `body_compress` / `body_raise`。
- `_leap()` 加 PrepareToJump 分节点冲量（`seg[1].vy += vy*BODY_JUMP_MID`、`seg[2].vy -= vy*BODY_JUMP_REAR`）。
- `_step_chain` 末尾加 bodyWiggleCounter 扰动 + 衰减；`hear_noise()` 抬高 wiggle。
- `_step_head_point` 末尾加**物理扭头**：驱动量取 AI 的注视角 `head_angle`（不取头弹簧位移——里面混着重力下垂和咬合冲量，拿它当弯曲源会反过来吃掉动作），只在 `look_at is not None` 时生效。

**④ 吃东西只动拿食物的那只手（`core/creature.py::_carry_pos`）**：`eat_raise` 以前对所有手一视同仁，双持（另一只手还握着矛/石头）吃东西时另一只手也被一起拽到胸前。现在 `s = (1.0 - eat_raise) if side == hand_of["fruit"] else 1.0`——只有食物手抬到嘴边，另一只手（及其手里的东西）原地不动。

**⑤ 双持矛外八字 + 杆上持物偏移（`core/creature.py`）**

- `spear_hold_angle(tilt, side, dual)`：双持（只要 `len(hand_spears) >= 2`，猎手双矛与**矛大师的白针走同一条路**）时两支矛向外撒 `DUAL_SPEAR_SPLAY = 40°`，且前倾剔弱到 `DUAL_SPEAR_BASE_K = 0.35`（参考图里两支矛是围着**竖直方向**对称的，不降的话左手那支几乎竖直，不像外八字）。撒开量乘不乘 `fdir`——不乘，于是照片翻过来时整体**镜像**（只持一支时还是原来的 25°，不受影响）。
- 新增 `on_vertical_pole()`（`on_pole and animation in ("ClimbOnBeam", "BeamTip")`）：抱竖杆时 `_carry_anchor` 把物横向偏出杆线 `POLE_CARRY_DX = 7px`（左手向屏幕左、右手向屏幕右）——不偏的话矛/石头正好压在杆线上，看上去像插进杆里（用户参考图：杆上持物画在杆侧面）。横杆/`HangFromBeam` 不走这一档。

**⑥ 手势的手部处理（`behavior/fsm.py` + `rendering/graphics.py`）**

- 伸手比划优先用**空手**：`_point_at_cursor` / `_aim_target` / `_drag_reach_tick`（被鼠标拗着伸手抱杆）/ `_social_stroke` / `_social_wake` 五处都改走 `body.free_hand(hint=...)`——拿着东西的手不再被抽去指指点点（两手都占才退回最近的手；`_drag_reach_tick` 两手都占时宁可不伸手）。
- `graphics._update_hands` 每帧回写 `body.hand_anim_driven[side]`；`_carry_anchor` 读它：**被手势驱动的手，持物跟着手走**（不再留在身侧锚点——否则手伸出去了、矛还在腰边）。这把 R139 的「一只手 = 一个状态」从攀爬动画扩到了手势动画。

**⑦ 矛大师的细线：尾巴根红 → 针端黄（`world/needlethread.py`）**：原版 `ApplyPalette` 的 `threadCol` 是一色米黄；按用户口径改成沿线长渐变（`_shade(i)`，首端 `(226,58,44)` → 末端 `(248,222,82)`），宽度/alpha 仍走原版 `InverseLerp(0,0.3,life)`。

**证据**（离屏渲染，`work/scratch/_vis140b.py` / `_vis140eat.py`）：`r140b_vis.png`（双持外八字·竖杆持物·细线尾红针黄）、`r140b_eat.png`（左：双持站立；右：吃饭时只有食物手抬到嘴边、矛手原地）；双持实测角 `(-31.2°, +48.8°)`，抱竖杆时 `_carry_anchor("l") = 手位 − 7px`。面条蝇证据图 `nw140_wings_ab.png` / `lz140_ab.png`。

**测试**：`work/scratch/e2e_r140.py`（8 组 30+ 断言）+ `work/scratch/e2e_r140b.py`（6 组 30 项），都已登记进 `run_all19.ps1`。

**回归**：`run_all19.ps1` **125 个脚本 fails=0 []**；`tools/parts_audit.py --check` exit=0；`tools/sprite_variants.py` 正常。

### R139 · 持物绑定到实际手位（一只手 = 一个状态 = 一套手臂 = 一个物品）

**问题**：手的位置有两套在打架。`rendering/graphics.py::_update_hands()` 按攀爬动画算真实手位（写回 `body.hand_pos`），`core/creature.py::_carry_anchor()` 又按身体偏移另算一套持物位置。于是爬杆时矛浮在身体旁边、和攀爬手脱节；更糟的是 `_apply_carry_stone` / `_apply_carry_spear` 在「有杆」时**整条跳过** `_aim_hand`，把上一帧的 `arm_aim` 留在原地 —— 而 `_update_hands` 的优先级是 `hand_aim > arm_aim > 内部姿态`，`arm_aim` 会盖掉攀爬姿态，把那只手从杆上拽回身侧持物点，于是同一只手既有一只伸向身侧的持物臂、又有一条杆上的抓握手（用户报的「多出两只手」）。

**修法**：把「手」收成两个独立状态槽位，动画决定手的实际位置，持物只读取对应手的位置。

- `behavior/anim_intent.py` 新增 `BEAM_LIMB_ANIMS`（`ClimbOnBeam / BeamTip / StandOnBeam / HangFromBeam / GetUpOnBeam`）作为**唯一真值源**。原先这份元组在 `graphics.py` 里抄了两遍（`_update_hands` 和 `_update_legs`），现在两处 + `creature.hands_on_anim()` 共读一份，顺手删掉一份重复。
- `creature.hands_on_anim()`：`bodyMode == "ClimbingOnBeam" and animation in BEAM_LIMB_ANIMS`。注意它**不等于**旧的 `_holding_on_pole()` —— 扶墙下滑的 `WallClimb` 也把 `bodyMode` 写成 `ClimbingOnBeam`，但手并没有被 beam 姿态接管，旧口径把这一档也算进「有杆」，属于误伤。旧名 `_holding_on_pole` 已删除（全仓库无调用方），不再留两个名字指一件事。
- `creature._carry_anchor(side)` → `(x, y, aimed)` 唯一真值源：动画接管时返回 `hand_world(side)`（即 `hand_pos`）+ `aimed=False`；`hand_pos` 还没写过（没跑过渲染帧）时退回身体锚点但**仍然** `aimed=False`，绝不抢那只手。其余状态照旧返回身体偏移锚点 + `aimed=True`（手跟物），这一档与旧版逐位相同。
- `_apply_carry_stone` / `_apply_carry_spear` 不再「有杆就整条跳过」，统一走 `_aim_hand(side, cx if aimed else None, ...)` —— `aimed=False` 会把 `arm_aim` 清掉，从根上消灭「残留瞄准把攀爬手拽走」。
- 新增 `creature.release_hands_to_anim()`：进 `PoleClimb` / `HPole` / `CeilingHang` 时显式把双手交还动画（清 `arm_aim`）。三处 `_*_enter()` 都已接上。
- `_sleep_drop_hands()` 原来只 `release_spear()`（放主手那支），双手各一支的猎手 / 矛大师会漏掉副手 → 改成遍历 `hand_spears` 逐手放掉；背上的矛不受影响。

**证据（A/B 实机渲染，`work/scratch/_shot139d.py`）**：复刻旧口径 vs 新口径，同一根竖杆、同一只拿矛的手 ——

| | `|矛 − 手|` |
|---|---|
| 旧版（物留身体锚点） | **17.5 px**（矛浮在杆旁边） |
| 新版（物跟实际手） | **0.0 px** |

目视拼图 `work/scratch/shot139_ab.png`（左旧右新）、单张放大 `shot139_pole.png` / `shot139_dual.png`：新版是「一只抓握手按在杆上、矛挂在这只手上」，不再有身侧浮空的矛。注意 A/B 里的旧版只复刻了「物留锚点」那一半；真实旧版还会被残留 `arm_aim` 把手也拽过去，比截图更糟。

**测试**：新增 `work/scratch/e2e_r139.py`（40 项，全绿）—— 动画集判定（含 `WallClimb` 边界）、`creature`/`graphics` 共读一份、`graphics` 不再硬编码元组；果子/石头/矛三种物品「站着物在携带点 + arm_aim=携带点」「爬杆物在手位 + arm_aim 清空」「`hand_pos` 未知时暂留携带点但不抢手」「手位与身侧锚点确实是两处（用例有效）」；双手各一支各跟各的手 + `hand_pos` 只有 l/r 两槽；`release_hands_to_anim` 与三处 `_*_enter()`；入睡释放两手 + 背矛保留；绘制层「站着 2 条手臂 / 爬杆 0 条手臂 + 正好 2 条抓握精灵」。`run_all19.ps1` 已登记（123 个脚本）。

**改既有守护**：`e2e_r49.py` §3 原来钉的是 b625b76 的口径「爬杆时物留在稳定携带点、不吃 `hand_pos`」—— 那正是本轮要修的行为，已按新规格重写（物跟手 + 清 `arm_aim` + `hand_pos` 未知时的兜底）。

**回归**：`run_all19.ps1` **123 个脚本 fails=0 []**；`tools/parts_audit.py --check` exit=0；`tools/sprite_variants.py` 正常。

**未做**：§9.1 `_strip_path()` 拓扑、§9/§10 动作序列（`PrepareToLounge` 式分节点冲量、Attack 四阶段姿态）；驯服社交 / 黄蜥 Pack / AttemptBite→Grasp→Carry 分层（用户明确暂缓）。

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
