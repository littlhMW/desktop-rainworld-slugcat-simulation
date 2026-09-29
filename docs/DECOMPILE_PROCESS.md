# 反编译流程（部件 / 位置 / 大小 / 骨骼 / 图层 / 翻转 / 使用逻辑 / 精灵）

移植原版生物或物件**一律按本流程走**（不靠截图猜、不凭印象写）。每一步都有出处：
原版源码 + 图集 JSON，两者都对得上才算移植完成。

## 0. 前置

| 东西 | 位置 | 说明 |
| --- | --- | --- |
| 反编译源码 | `work/scratch/decomp_full`（`RW_DECOMP` 环境变量可覆盖） | 反编译的是 **Rain World 本体** |
| 图集 | `~/.slugcatpet/assets`（`SLUGCATPET_ASSETS` 可覆盖） | `rainWorld` / `rainworldmsc` / UI，由用户自己的正版游戏导入 |
| 工具 | `tools/parts_table.py`、`tools/parts_audit.py`、`tools/sprite_variants.py` | 见 `tools/README.md` |

## 1. 定位要读的类（顺序固定）

1. `XGraphics.cs` —— 部件（精灵、图层、锚点、角度、颜色、多变体）
2. `X.cs` —— 本体（BodyChunk 半径/质量/连接、物理常量、每 tick 状态量、交互钩子）
3. `XAI.cs` —— 行为（`Behavior` 枚举、`DetermineBehavior` 优先级、目标选择）
4. `X` 里的 `IndividualVariations` / `GraphicsModule.ctor` —— 每只个体的随外形
5. `StaticWorld.cs` 的 `XTemplate` —— 与其他物种的关系表（Eats / Attacks / Afraid / Ignores）

## 2. 图层 = `InitiateSprites`

`sLeaser.sprites[i] = new FSprite("Name")`：**下标 i 就是绘制顺序**（同容器内后画盖前画）。
`AddToContainer` 决定跨容器顺序（背景/前景层）。

→ 我们的绘制调用顺序必须逐条对应这个下标序。

## 3. 位置 / 角度 / 缩放 / 翻转 = `DrawSprites`

逐帧给 `sprites[i]` 赋 `x/y/rotation/scaleX/scaleY/isVisible/color`，全部照抄：

* `rotation`：Futile/Flash 口径（屏幕上**顺时针为正**），与本仓库 `_ang_from_up()` 同号 → **照抄，不取反**。
* `scaleX = -1`：局部水平镜像 → 我们的 `blit(..., sx=-1)`。
* 循环里 `sprites[SpriteBodyStart + i]` 这类批量赋值：先把 `SpriteXxxStart/End` 助手展开成常量，再代入循环变量。
* `isVisible`、`bites` 之类的**可见性开关必须一起抄**（例：蝙蝠 `sprites[1].isVisible = bites == 3`）。

## 4. 锚点换算（最容易错的一条）

FSprite 顶点：`_textureRect.y = -anchorY * height`（Unity y↑，`FSprite.cs:182-183`）。
换算到我们的 Qt（y↓，`blit` 的 `ay` 从贴图**顶边**量）：

    ay = 1 - anchorY          # anchorX 不变（x 轴同向）

| 原版 | 我们 | 含义 |
| --- | --- | --- |
| `anchorY = 0` | `ay = 1.0` | 贴图整块在锚点**上方**（翅根、花瓣、蜥蜴头…） |
| `anchorY = 0.5`（FSprite 默认） | `ay = 0.5` | 居中 |
| `anchorY = 0.7` | `ay = 0.30` | 例如蜥蜴 5 片共用头锚 |

尺寸一律用 `sourceSize`（未裁剪画布）；被 trim 掉的空白由 `spriteSourceSize` 还原（`Atlas.sprite(padded=True)` 已处理）。

## 5. 颜色 = `ApplyPalette`

`ApplyPalette` 里 `sprites[i].color = palette.xxx` 决定哪些部件吃调色板、哪些保持默认白
（例：蝙蝠 0..2 吃 `blackColor`，眼睛 3 保持白）。到我们这边就是 `blit(..., color)` 的 tint。

## 6. 精灵与多变体

`"Name" + num` 的拼接要在源码里找出 num 的**取值域**（角度分区表、深度分档、左右侧别）：

1. `tools/parts_table.py <Class>` 列候选帧 → 每个候选帧的真实尺寸；
2. 确认取值域里**每个值都真的会被请求**：`tools/sprite_variants.py` 强制扫一遍并统计缺帧；
3. 缺帧 = 画面缺件（`AtlasSet.find_atlas` 静默跳过），不允许留着。

## 7. 骨骼 / 物理

* `Limb`：`new Limb(this, anchor, connectedChunks, numberOfSegments, rad, ...)`，字段
  `position / direction / vel / connectToPointMode / findGrip / ...`；`Limb.Update()` 的
  顺序（FindGrip → 惯性 → ConnectToPoint → 碰撞）照抄。
* `BodyChunk(owner, index, pos, rad, mass)` + `bodyChunkConnections` 的 tether/elastic 常数。
* `TailSegment` / `GenericBodyPart`（如蝙蝠 `lowerBody`）同样逐行搬。
* 物理常量（`airFriction / bounce / gravity / waterFriction / buoyancy / surfaceFriction`）
  抄进 `world/*.py` 顶部常量区，并注明源码行号。
* **例外**：像素比例要按实际画面换算。原版 1 tile = 20px，我们的窗口尺寸与它不同时，
  跳跃高度/距离/速度按比例调整，不能直接照抄像素数（`world/lizard.py` 的 `BODY_SCALE` 就是这个换算）。

## 8. 使用逻辑 / AI / 交互

* `StaticWorld` 的 `CreatureTemplate` 关系值 → 我们的 `lizard_rel` / `hostile_to` / 好感表。
* `XAI.Update` 的 `Behavior` 与 `DetermineBehavior` 优先级 → 我们的状态机分支与优先级。
* AI 分层照 `LizardAI`：`PreyTracker` / `AgressionTracker` / `ThreatTracker` / `NoiseTracker` /
  `LurkTracker` / `PackTracker` / `InjuryTracker` 各自独立收集信息 → `lizard_ai.py` 的
  `Memory` / `PreyTracker` / `SocialMemory` / `PackAlert` / `Observation`；
  `LizardAI.VisualScore` 的视野锥 + `Community` 视线 → `Observation.los` 与 `los_blocked`。
* `SocialEvent` / `RelationshipTracker` / `tempLike` / `like` 的加减量与衰减 →
  `behavior/events.py`（事实总线：谁对谁做了什么）+ `behavior/relationship.py`
  （静态基线 + 个体记忆 + 近期事件 → 实时关系，按 DECAY 表随时间回基线）；
  反应系数照 `LizardAI` / `ScavengerAI` 的 Utility 权重落到 `behavior/social_response.py`。
* `LizardAI.DetermineBehavior` 的 Utility 与 `LizardAI` 的移动规划 → 我们的行为状态机；
  `PathFinder` / `Pather` 的代价 → `planning/route.py` 的六轴（时间 / 体力 / 风险 /
  噪音 / 精度 / 后摇）与 `planning/hop_reach.py` 的落点安全边距。
* 交互站位（原版 `Creature.DangerPos` / 各类 `XAI` 的接近点选择）→ `behavior/pose.py`
  的 Interaction Pose：目标 + 动作 + 位形槽 → 站位点与朝向。
* 交互钩子：`LickedByPlayer`、`BitByPlayer`、`Violence`、`Collide` → 我们对应的
  `on_licked` / `bite` / `hurt` / 碰撞处理。
* 每段照抄的代码都在注释里写 `文件名.cs:行号`。

## 9. 每次移植都要跑的验收

```powershell
D:\spenv\Scripts\python.exe -X utf8 tools/parts_table.py <Class...>   # 部件表，人工核对
D:\spenv\Scripts\python.exe -X utf8 tools/parts_audit.py --check      # 尺寸/图层/物理常量对拍，非 0 退出=有偏差
D:\spenv\Scripts\python.exe -X utf8 tools/sprite_variants.py          # 多变体切换 + 零缺帧
```

再补一条 `work/scratch/e2e_rNN.py`（断言图层序、锚点 `ay`、角度/缩放公式、行为分支），
登记进 `work/scratch/run_all19.ps1`，跑出 `fails=0`。

## 10. 记录

新核对的结论追加到 `docs/PARTS_REFERENCE.md`（机械表）与 `docs/PARTS_AUDIT.md`（不一致清单），
README 只留最终结果。

## 10.5 一键生成（RainWorldExtractor v2）

上面第 2~7 节用手做一遍很慢，`python -m slugcatpet.gameassets dump` 会把同一套规则自动跑成一份可查询的资料库（默认 `~/.slugcatpet/rainworld_dump/`）：

| 目录 | 回答什么问题 |
| --- | --- |
| `assets/` | 游戏里有哪些 `Texture2D` / `Sprite` / `TextAsset` / `Material` / `Shader` / `MonoBehaviour` / `MonoScript` |
| `atlases/` `sprites/` | 某个精灵的 `frame` / `source_size` / `source_rect` / `rotated` / `trimmed` / `pivot` / `bounds` / `anchor` |
| `creatures/` | 某只生物的精灵下标（= 图层序）、容器、元件名、`x/y/rotation/scale/anchor/element`、翻转、调色板、依赖哪节身体 |
| `rigs/player.json` | 身体节半径 / 质量、头 / 腿 / 手的 BodyPart、4 节尾巴（按种族分支）、尾巴三角网格表、游戏写死的锚点 |
| `animations/` | 帧族与帧数、每帧 tick 数、是否循环、触发条件；含 `InitCachedSpriteNames()` 自报的帧名与帧数 |
| `logic/` | 每个方法写哪些精灵的哪些属性，依赖什么运行时量 |
| `layers.json` | `RoomCamera.SpriteLayerIndex` 的 FContainer 层序 + 同容器内绘制顺序 |
| `reports/` | 代码引用了但图集没有的元件、工程占位、运行时拼接前缀；可搜索的精灵表；帧族总览图；骨架自检图 |

锚点口径仍是第 4 节的 `qt_ay = 1 - anchorY`：`BodyA` 的 `anchorY = 0.7894737f` → `qt_ay = 0.2105263`，`LegsA0` 的 `0.25f` → `0.75`，`PlayerArm0` 的 `anchorX = 0.9f` 不换算。

## 11. 蛞蝓猫外观参数（`CatDef.visual`）

`PlayerGraphics.DrawSprites` 里按种族写死的缩放/偏移，一律落到 `CatDef.visual` 的键上，
由 `rendering/graphics.py` 读取、`rendering/graphics_draw.py` 乘进对应的 `blit`，
不要在绘制函数里写 `if cat == ...`。

| 键 | 含义 | 反编译出处 |
| --- | --- | --- |
| `body_sx` | 体 sprite（`BodyA`）的 scaleX 倍率 | `PlayerGraphics.cs:2872/2876/2884` |
| `hips_sx` | 臀 sprite（`HipsA`）的 scaleX 倍率 | `PlayerGraphics.cs:2892/2896/2904` |
| `head_sx` | 头 sprite 的 scaleX 倍率 | `PlayerGraphics.cs:3037/3041` |
| `arm_offset_fac` | 手肩点横向偏移倍率 | `PlayerGraphics.cs:3143` |
| `tail_speckles` | 画尾上 5×3 斑点 + 尾针精灵 | `PlayerGraphics.cs:947-1113` |
| `pup_wide` | 幼崽：`0.95 + 0.1*Wideness` 同一个倍率给体/臀/头 | `PlayerGraphics.cs:2880/2900/3041` |

各族当前取值（数值全部来自上表行号，不许凭感觉调）：

| 种族 | 取值 |
| --- | --- |
| 饕餮 Gourmand | `body_sx=1.4, hips_sx=1.6`（更圆） |
| 矛大师 Spearmaster | `body_sx=0.76, hips_sx=0.76, head_sx=0.85, arm_offset_fac=0.6, tail_speckles=True` |
| 幼崽 Slugpup | `pup_wide=True`（体/臀/头同倍率，个体 Wideness 固定） |
| 圣徒 Saint | 头族 `HeadB`（`PlayerGraphics.cs:3027`）、常态闭眼族 `FaceB` |
| 工匠 Artificer | 脸族 `FaceC`/`FaceD`（`PlayerGraphics.cs:4293`） |
| 其余 | 默认 `HeadA` + `FaceA`/`FaceB`，倍率全 1.0 |

尾针的动画流程也照抄原版，拆成两段（`Player.cs:9995-10036`）：
`spearProg` 先从 0 长到 0.11 → 每 tick `lerp(prog, 1, 0.05)`；中途被打断按 0.05 缩回，
低于 0.025 归零；`spearProg` 到 1 才真正生成矛并入手，随后进 `TAIL_NEEDLE_CD` 冷却。
斑点绘制用 `SpinePosition(s)` 沿尾段取样（`PlayerGraphics.cs:4429`），
落点那一格与四邻随 `spearProg` 放大，针精灵长度 = `spearProg * 0.5`。

## 12. 矛大师的有机细线（`Spear.Umbilical`）

wiki 的说法是「掷出白色的矛针后可以看到一条长的有机线连接矛和矛大师，前提是矛命中了活物」。
反编译里这不是贴图，而是一个独立的房间对象，所以不看 `PlayerGraphics`，看 `Spear.cs`：

| 事实 | 出处 |
| --- | --- |
| 出手：`Weapon.Thrown` 时 `if (Spear_NeedleCanFeed()) room.AddObject(new Umbilical(room, this, thrownBy as Player, firstChunk.vel))` | `Spear.cs:714` |
| 形状：`points` 是 10~19 个自由点，相邻点最小间距 6，末端跟随 `maggot.bodyChunks[0].pos - maggot.rotation * 25` | `Umbilical` 构造 |
| 两端：`points[0]` 每 tick 重新钉到 `PlayerGraphics.tail[0].pos`，末点钉在针尾 | `Umbilical.Update` |
| 寿命：`(2, Lerp(150, 200, rand^0.3))`，重力 `vy -= Lerp(0.1, 0.6, life)`，宽度 `0.5 * InverseLerp(0, 0.3, life)`，颜色 `Lerp((0.95,0.8,0.55), fog, 0.2)`；寿命尽 `Destroy()` | `Umbilical.Update` |
| 断开：`Mode.Free`(:464)、`Mode.StuckInWall`(:668)、真的喂成功(:1081)、戳到异物(:1145) 全部 `Spear_NeedleDisconnect()` | `Spear.cs` |
| 拔出动画：`spearProg > 0.6` 头抖，`> 0.95` 封满，`== 1` 时先溅 4 个 `WaterDrip`（尾中点、朝髋、速度 2~6）+ 5 个 `Spark`（散开 40px、速度 4~30、寿命 18）再把针交到手 | `Player.cs:10013-10036` |
| 使劲脸：`spearProg > 0.1` → `blink = 5`（本该闭眼的帧，看起来像咬紧牙往外拽） | `PlayerGraphics.cs:4331-4334` |

桌宠里的对应实现（`world/needlethread.py` + `world/items.py`）：

- `NeedleThread.__init__(tail_xy, vx, vy, rng)` 用与 `Umbilical` 同分布的 10~19 点起步，速度按出手速度铺开。
- `update(head_xy, tail_xy)` 每 tick：首点重钉到尾根、末点钉到 `spear.butt()`、其余点受 `Lerp(0.1, 0.6, life)` 的等效重力与最小间距 6 约束；`life` 到 1 即 `dead`。
- `_needle_thread_tick()` 在 `_tick_spears()` 里跑：针没了 / `needle_live` 变假（喂过、扎墙、落地）就置 `dead`；新掷出的活针补一条，随机流用 `random.Random(id(spear) * 7919 + 13)`，**不去扰动矛自己的 spin 随机数**。
- 断开时机按用户口径改写：原版那四处 `Spear_NeedleDisconnect()` 里的「喂成功 / 扎墙 / 落地」都不再断线，只有 **① 这根针实体被删掉**、**② 下一根活针掷出** 才断（同一时刻只跟最新那根活针）；掷出者不在了就把线头冻在最后一个尾根位置。
- 寿命只用来把重力 `Lerp(0.1,0.6)` 与宽度带到稳态（夹在 `LIFE_HOLD = 1.0`），所以线不会自己淡没。
- 拔出动画：`tail_needle_prog > 0.1` 时 `blink` 顶到 5（使劲脸），`> 0.6` 头随进度抖，封满那一 tick 在尾中点溅 4 水珠 + 5 白火花（`_tail_needle_burst()`，随机流独立于行为流）。
- 绘制：`window._paint_world` 在 `_draw_back_spears` / `_draw_low_spears` 之后、`pet.gfx.draw_sprites` 之前调用，所以细线永远压在猫与生物之下；`QPen` 圆头逐段连。

验收：`work/scratch/e2e_r91.py` 断言点数落在 10~19、首末点分别钉在尾根与针尾、`needle_live` 变假时线消失、没掷针时不冒线、绘制顺序在源码里的位置。
