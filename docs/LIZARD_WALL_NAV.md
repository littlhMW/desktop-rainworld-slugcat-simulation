# 蜥蜴背景墙导航：反编译口径 + 桌宠映射

本文回答「背景墙爬行」的 20 个问题，逐条给出
`[source class] [source method] [field/property] [condition] [transition] [formula] [constant] [unresolved]`。
反编译产物位于 `work/scratch/decomp_full/`（Rain World 1.9 `Assembly-CSharp`，
`AItile.cs / AImapper.cs / AImap.cs / MovementConnection.cs / LizardPather.cs /
LizardBreedParams.cs / Lizard.cs / LizardAI.cs / LizardLimb.cs / PathFinder.cs / CreatureTemplate.cs`）。
源码中没有确认的一律标 `UNRESOLVED`，不做行为猜测。

桌宠对应实现：`slugcatpet/world/walls.py`（`WallSurface` / `build_wall_surfaces`）
与 `slugcatpet/world/lizard.py`（`_climb_plan` / `_step_wall`、`LizardBreed.climb_wall / climb_pole`）。

## 一、原版怎么表示地形可通行性

### 1.1 `AItile.Accessibility` 枚举

`[AItile] [AItile.Accessibility] [enum] [constant]`

```
OffScreen, Floor, CurvedFloor, Corridor, Climb, Wall, Ceiling, Air, Solid, Sand
```

- `[AItile] [AItile] [field walkable] [formula] = acc != Air && acc != Solid`（AItile.cs:38）
- `[AItile] [AItile] [fields] narrowSpace / floorAltitude / smoothedFloorAltitude / visibility / fallRiskTile / incomingPaths / outgoingPaths`
- `[AItile] [AItile.DeepWater/WaterSurface/AnyWater] [condition] waterInt == 1 / 2 / != 0`

要点：**墙（`Wall`）和攀爬（`Climb`）是两种不同的 accessibility**。
`Wall` = 贴在实体侧面的墙面；`Climb` = 竖直杆 / 横梁（beam）。
爬墙能力看 `LizardBreedParams.WallClimber`，爬杆是另一套（`verticalBeam/horizontalBeam` 标 `Climb`）。

### 1.2 `AImapper.FindAccessibilityOfCurrentTile` 判定顺序（AImapper.cs:188-229）

`[AImapper] [FindAccessibilityOfCurrentTile] [map.map[x, y].acc] [condition] [transition]`

按顺序（先命中先返回）：

1. `room.terrain.ObstructsTile(x, y)` → 用 `terrain.TileAccessibility(x, y)`（:190-193）
2. 本格 `Terrain != TerrainType.Solid` 才继续：
   - `terrain.ObstructsTile(x, y - 1)` → 用 terrain 的 acc（:199-203）
   - 正下一格 `Solid`/`Floor`，或「左下 `Solid` 且正下非 `Solid`」「右下 `Solid` 且正下非 `Solid`」 → **Floor**（:204-208）
   - 左右邻都是 `Solid` → **Corridor**（:209-213）
   - `tile.verticalBeam || tile.horizontalBeam` → **Climb**（:214-218）
   - `tile.wallbehind`，或左右邻 `Solid`，或「左下 `Solid` 且正下非 `Solid`」「右下 `Solid` 且正下非 `Solid`」 → **Wall**（:219-223）
   - 正上一格 `Solid` → **Ceiling**（:224-228）
   - 否则 **Air**（:197）

桌宠映射：`wallbehind` ↔「别人窗口露出来的侧边」；`Solid` ↔ 窗口/墙体矩形；`Floor` ↔ 窗口顶边/桌面底。

### 1.3 Floor → Climb / Wall 的连接（AImapper.cs:281-329、586-604）

`[AImapper] [FindAccessibilityOfCurrentTile] [outgoingPaths.Add] [MovementConnection] [condition]`

起始 `intVector2 = (0, -1)`（:280）向下扫描：

- `acc == Floor|CurvedFloor` 且其上一格 `Solid|Floor|terrain obstructs` → `DropToFloor`（:287-294）
- `acc == Climb` 且其上一格 acc 更大 → `DropToClimb`（:295-298）
- `room.GetTile(...).WaterSurface` → `DropToWater`（:300-304）
- 下落高度 `num >= 4` 时，对左右各 ±1 再做一次斜向 `DropToFloor` / `DropToClimb`（:307-328）
- `IsThereAStraightDropBetweenTiles`（:586-604）同样只认 `Floor` 与 `Climb` 两个终点类型

`[MovementConnection] [MovementConnection.MovementType] [enum] [constant]`：
`Standard, ReachOverGap, ReachUp, DoubleReachUp, ReachDown, SemiDiagonalReach, DropToFloor,
DropToClimb, DropToWater, LizardTurn, OpenDiagonal, Slope, CeilingSlope, ShortCut,
NPCTransportation, BigCreatureShortCutSqueeze, OutsideRoom, SideHighway, SkyHighway,
SeaHighway, RegionTransportation, BetweenRooms, OffScreenMovement, OffScreenUnallowed`

**没有独立的 `Climb` / `Wall` MovementType**：上下墙走 `Standard` / `ReachUp` / `ReachDown` / `DropToClimb`。

### 1.4 「这只生物能不能走这条连接」

`[AImap] [IsConnectionAllowedForCreature] [legality] [condition]`（AImap.cs:59-77）

- 先 `IsConnectionForceAllowedForCreature`（:61-64）
- 要求 `WorldCoordinateAccessibleToCreature(start)` 且 `(dest)` 且 `crit.ConnectionResistance(type).Allowed`（:65-68）
- `ReachUp` 且两端都是 `Floor` 时还有额外相邻格检查（:69-81）

`[AImap] [WorldCoordinateAccessibleToCreature] [formula]`（AImap.cs:340-362）：

- 正常重力：`crit.AccessibilityResistance(aItile.acc).Allowed`（:354-361）
- 零重力（`room.gravity <= Lizard.zeroGravityMovementThreshold`）且祖先为蜥蜴：
  改用 **BlueLizard** 的抵抗表 `StaticWorld.GetCreatureTemplate(BlueLizard).AccessibilityResistance(acc).Allowed`（:342-353）

桌宠映射：能力差异是「生物模板的抵抗表 + `ConnectionResistance`」，不是给某只蜥蜴临时开的特例。

## 二、20 问逐条

| # | 问题 | 结论 | 出处 |
|---|---|---|---|
| 1 | `LizardPather` 如何判断 tile 能否爬墙 | 它不自己判断；`FollowPath` 只枚举 `outgoingPaths` 并按 `CheckConnectionCost` 过滤，可爬性由 AImap 的 acc + 抵抗表决定 | `[LizardPather] [FollowPath]`；`[AImap] [IsConnectionAllowedForCreature]` |
| 2 | 哪个字段表示墙 / 后墙 / 地面 / 杆 | tile 层 `Room.Tile.wallbehind / verticalBeam / horizontalBeam / Terrain`；AI 层 `AItile.acc`（Wall / Climb / Floor / Ceiling） | `[AItile] [acc]`；`[Room.Tile] [wallbehind/verticalBeam/horizontalBeam/Terrain]` |
| 3 | Wall / BackWall / Climb 对应的 TerrainType | `Room.Tile.TerrainType` 里没有 Wall / BackWall；墙来自 `wallbehind` 标志与相邻 `Solid`，杆来自 beam 标志。完整枚举未逐项核对 | `[Room.Tile] [TerrainType]`；**部分 UNRESOLVED** |
| 4 | Floor → Wall 的 MovementConnection 怎么生成 | Floor 的 outgoing 是 `DropToFloor / DropToClimb / DropToWater`；到 Wall 走邻格 `Standard` / `Reach*`（横向 / 斜向扫描）。**没有 DropToWall** | `[AImapper] [FindAccessibilityOfCurrentTile]`（:281-329） |
| 5 | Wall → Wall 怎么连 | 相邻 Wall tile 之间按四向 / 斜向的 `Standard` / `SemiDiagonalReach` 连接（沿用通用 tile 连接扫描） | **部分 UNRESOLVED**（逐向分支未逐行定位） |
| 6 | Wall → Floor | 反向 `DropToFloor` / `Standard` | `[AImapper]` |
| 7 | 墙顶如何接到其他地形 | 墙顶格若满足 Floor 条件就标 `Floor`，随后走标准地面连接 | `[AImapper] [FindAccessibilityOfCurrentTile]`（:204-208） |
| 8 | 墙底如何回到地面 | 同上：底部邻格标 `Floor` → `Standard` / `ReachDown` | `[AImapper]` |
| 9 | 蜥蜴何时选择 Climb | 路径器在 `outgoingPaths` 里按代价 / 合法度挑；AI 侧只看 `acc >= Climb` 决定叼 / 吐舌等 | `[LizardAI] [wantToSpit]`（:350）；`[LizardPather] [FollowPath]` |
| 10 | 蜥蜴何时停止 Climb | 到目标 / 到 `Floor` / 连接不可用（`possibleToGetBackFrom == false` 且不允许 `walkPastPointOfNoReturn` 时被标 `Unallowed`） | `[LizardPather] [FollowPath]`（:41-49） |
| 11 | 如何从普通移动进入贴墙 | 走 `DropToClimb` 或邻格 `Standard` 过渡 | `[AImapper]`（:295-298） |
| 12 | 如何从墙回到普通移动 | 走 `DropToFloor` / `Standard` | `[AImapper]`（:287-294） |
| 13 | 爬墙速度由哪个字段决定 | `[LizardBreedParams] [terrainSpeeds]`（按 acc 索引，`TerrainSpeed(acc)` 返回 `SpeedMultiplier`）、`baseSpeed`、`baseSpeedMultiplier`；具体数值表在 `LizardBreeds` | `[LizardBreedParams] [TerrainSpeed]` |
| 14 | 墙面移动是否用 bodyChunks / BodyChunkConnection | 脚部 IK：`LizardLimb` 用 `FindGrip(..., (owner as LizardGraphics).lizard.IsWallClimber)` 决定抓地方式 | `[LizardLimb] [FindGrip]`（:131） |
| 15 | 是否有特殊 WallClimber / wallJump 状态 | `Lizard.IsWallClimber` 是**属性**（能力查询），不是状态机状态；没有独立 `wallJump` 状态字段 | `[Lizard] [IsWallClimber]`（:410-420） |
| 16 | 哪些品种 `WallClimber = true` | `LizardBreedParams.WallClimber`：`BlueLizard`、`WhiteLizard`、`DlcEelLizard` | `[LizardBreedParams] [WallClimber]`（:196-210） |
| 17 | 蓝 / 白 / 绿 wall capability 差异 | 蓝 / 白 `WallClimber = true`，绿 `= false`；蓝蜥另有 AI 代价偏好：走 `Climb` / `Wall` 时 `num *= 0.5`（更愿意贴墙 / 爬杆） | `[LizardBreedParams]`；`[LizardAI]`（:1583-1591） |
| 18 | accessibility mapping 如何建立 | 逐格 `FindAccessibilityOfCurrentTile` 建 acc → 建 connections → `PathFinder` 计算 `reachable` / `possibleToGetBackFrom`（可达 & 可返回） | `[AImapper]`；`[PathFinder]` |
| 19 | Respawn 时是否重算可访问区域 | 未在本次产物中定位到 `Respawn → AImap` 重算的确切调用 | **UNRESOLVED** |
| 20 | AImap 中 wall tile 的连通关系如何缓存 | tile 持有 `incomingPaths` / `outgoingPaths` 列表，连接在建图时一次性生成并挂在 tile 上 | `[AItile] [incomingPaths/outgoingPaths]` |

## 三、UNRESOLVED 汇总

- `Wall → Wall` / `Wall → Pole` 的逐向连接分支（未逐行定位）。
- Respawn 是否触发 AImap 重算。
- `Room.Tile.TerrainType` 的完整成员（已确认不含 `Wall` / `BackWall`，但未逐项核对）。
- 爬墙时的具体速度公式（`terrainSpeeds` 的逐品种取值来自 `LizardBreeds`，未逐品种取值）。

## 四、桌宠映射

```
DesktopGeometry（枚举屏幕上的窗口矩形）
        │
        ├── FloorSurface    <- 窗口顶边 / 桌面底
        ├── WallSurface     <- 非全屏窗口某一侧「露出来的」竖边（walls.py）
        └── PoleSurface     <- 竖杆 / 横杆
                │
                ↓
        LizardNav（_climb_plan 选墙 + _step_wall 执行）
                │
        ┌───────┼────────┐
        ↓       ↓        ↓
      Floor    Wall     Pole
```

- `walls.py [build_wall_surfaces]`：把窗口矩形按 Z 序切成**可见**墙段（被前窗挡住的段不算墙），
  对应原版 `wallbehind` 只在「真的露出来」时成立。
- `lizard.py [LizardBreed.climb_wall]`：对应 `LizardBreedParams.WallClimber`，只给 blue / white / eel。
- `lizard.py [LizardBreed.climb_pole]`：对应杆 / 梁（原版 `Climb` acc）能力，与爬墙分开。
- `lizard.py [_climb_plan]`：对应「从 Floor 找一条到 Wall 的连接」：先走（`CLIMB_WALK_R`）→
  进入 `CLIMB_GRIP_R` 才附着 → `_step_wall` 弹簧吸附（对应脚 IK 的 `FindGrip`）→ 到墙头 / 墙底脱墙。

## 五、与原版仍存在的简化

- 桌宠没有 tile 网格，`WallSurface` 是「一条竖边 + 若干可见段」的连续几何，不是逐格 acc。
- 没有 `possibleToGetBackFrom` 的可返回性检查；桌宠用「墙底是否落在我这一层」近似（`WallSurface.covers`）。
- `_step_wall` 用弹簧吸附（`CLIMB_GRIP_SPRING` / `CLIMB_GRIP_DAMP`）代替真实 `LizardLimb.FindGrip` 的脚部物理。
- 能力位的 `wall_jump`（cyan 蓄力弹射）在源码里没有对应的独立 MovementType，标为桌宠自定扩展。