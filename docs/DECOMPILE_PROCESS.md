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
