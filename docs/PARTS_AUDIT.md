# 已移植对象：尺寸/位置/图层审计

审计对象：蜥蜴 / 拾荒者 / 珍珠 / 矛 / 爆米花 / 蝠蝇 / 禅乌贼 / 蛞蝓猫(手·尾) / 爆炸特效。
原版数值一律取自反编译（`work/scratch/decomp_full`），贴图数值取自图集 JSON；
机械参考表见 `docs/PARTS_REFERENCE.md`（由 `tools/parts_audit.py` 生成）。

## 一、自动对拍（数值级）

| 项目 | 原版 | 我们的常量 | 结论 |
| --- | --- | --- | --- |
| 矛 chunk0.rad | 5.0 | `RAD = 5` | ✅ 一致 |
| 矛 chunk0.mass | 0.07 | `MASS = 0.07` | ✅ 一致 |
| 珍珠 chunk0.rad | 5.0 | `RAD = 5` | ✅ 一致 |
| 珍珠 chunk0.mass | 0.07 | `MASS = 0.07` | ✅ 一致 |
| 禅乌贼 chunk0.rad | 7.5 | `RAD = 7.5` | ✅ 一致 |
| 禅乌贼 两截间距 | 14.0 | `CHUNK_GAP = 14` | ✅ 一致 |
| 面条蝇 躯干半径下限 | 2.0 | `CHUNK_RAD_MIN = 2` | ✅ 一致 |
| 面条蝇 躯干半径上限 | 5.0 | `CHUNK_RAD_MAX = 5` | ✅ 一致 |
| 拾荒者 chunk1.rad(髋) | 7.0 | `BODY_RAD = 7` | ✅ 一致 |
| 拾荒者 chunk2.rad(头) | 5.0 | `HEAD_RAD = 5` | ✅ 一致 |

## 二、人工核对结论（不一致清单）

| 结论 | 对象 | 原版 | 我们的现状 |
| --- | --- | --- | --- |
| ✅ | 矛 | chunk0 rad 5 / mass 0.07（Spear.cs:286） | 同值；杆长 53px 取 SmallSpear 贴图 |
| ✅ | 珍珠 | chunk0 rad 5 / mass 0.07（DataPearl.cs:184） | 同值；bounce 0.4 / surfaceFriction 0.4 同值 |
| ✅ | 禅乌贼 | chunk0 rad 7.5、两截间距 14（Cicada.cs:131） | 同值；触须 ConnectToPoint 24/19×tentacleLength 同值 |
| ✅ | 面条蝇 | 躯干半径 Lerp(2,5,t)*num、质量 Lerp(0.05,0.15,t)*num（NeedleWorm.cs:85） | 同值（CHUNK_RAD_MIN/MAX、CHUNK_MASS_MIN/MAX）；幼体 ×0.7 同原版 |
| ⚠️ | 面条蝇 | 身体是 TriangleMesh 程序化网格（无贴图） | 我们同样程序化画：躯干/尾用中轴带 + 高光带，眼/翅复用 JetFishEyeB、CentipedeWing；
翅膀尺寸是我们的观感微调（×0.55），不是原版顶点数据 |
| ⚠️ | 禅乌贼 | chunk1 rad 7.0（第二截） | 我们只有主 chunk（7.5）+ 14px 偏移，第二截没有独立半径：贴墙/压地时比原版略薄，不影响观感 |
| ⚠️ | 拾荒者 | 身体是 3 截：胸 9.5 / 髋 7.0 / 头 5.0（Scavenger.cs:1611 起）+ 截间连接 | 我们仍按 1 截 rad 7.0（髋）跑物理：三个半径常量现在都与原版一致（BODY_RAD 7 / HEAD_RAD 5），但**没有第二、三截的质点**，所以贴墙/被矛插时的接触点比原版粗一档；要彻底对齐需要把拾荒者改成三质点身体 |
| ⚠️ | 拾荒者 | ScavengerGraphics 的精灵表（面具/尖刺/腿/眼） | 我们的画法是自己拼的色块，不是逐件对表：面具/腿的**图层顺序与尺寸**只能算「像」，参考表在 docs/PARTS_REFERENCE.md 的 ScavengerGraphics 一节 |
| ✅ | 蛞蝓猫尾巴 | TailSegment rad 6/4/2.5、conn 4/7/7（PlayerGraphics.cs:1770 起） | 同值（core/tail.py） |
| ✅ | 蛞蝓猫手 | SlugcatHand rad 3 / sfFric 0.8 / aFric 1.0 / huntSpeed 7 / quickness 0.5，ConnectToPoint 20（SlugcatHand.cs:17） | huntSpeed 7、quickness 0.5、拴绳 20 同值；手走的就是 Limb 的「速度朝目标插值 → 够近吸附 → 拴绳约束」模型 |
| ⚠️ | 蛞蝓猫手 | Limb.pushOutOfTerrain（手不许插进地形） | 我们的手没有地形推挤：贴墙/贴地时手会画进墙里 |
| ✅ | 蜥蜴 | LizardBreeds 步态 9 参数 / LizardLimb 迈步模型 | 第 33 轮已逐品种照抄（见 README 第 33 轮） |
| ⚠️ | 蜥蜴 | LizardGraphics 的体节圆/背刺/头片图层 | 体节圆与四肢是我们按同一套参数重画的，件数与下标顺序不完全等同原版（原版用 sprite 下标循环），参考表见 PARTS_REFERENCE.md |
| ✅ | 爆米花 | SeedCob 图层：茎→豆荚→种子(按层)→外壳→叶片；外壳在所有种子之上 | 第 32 轮已按表对齐（tools/README 有结论） |
| ✅ | 爆炸特效 | ExplosionLight 的半径/时长 | 第 30 轮按原版数值对齐 |

## 三、已知的系统性偏差

- **图层顺序**：能机械抓的都在 `PARTS_REFERENCE.md`；我们的绘制函数多数是「按同一套参数重画」，
  不是逐 `sLeaser.sprites[]` 下标照搬，所以「件数/顺序」只在标了 ✅ 的对象上做过对齐。
- **循环下标**：原版大量用 `sprites[SpriteXxxStart + n]` 批量赋值，工具只能给出行，
  需要人工代入循环变量（工具 `tools/README.md` 有说明）。
- **Mesh 类精灵**（禅乌贼触须/蛞蝓猫尾巴）没有 atlas 尺寸，形状由顶点代码决定，
  审计按「公式是否照抄」判定，而不是按像素尺寸。

## 四、多角度 / 多变体精灵切换（按情况换贴图）

原版「同一部件换贴图」分两类：**按角度分行**（头片、躯干片）与**按距离 / 侧别取档**（腿、手、翅）。
桌宠只取一档就会「停在某一帧」。逐对象核对结果（原版出处 = 反编译；机械复核 = `tools/sprite_variants.py`）：

| 对象 | 原版切换规则 | 出处 | 我们 | 结论 |
| --- | --- | --- | --- | --- |
| 蜥蜴头 5 片 | 行号 `num14 = 3 - int(|headDepthRotation|*3.9)`：|num|≈1 → 行 0（正侧），|num|→0 → 行 3（正对镜头）；`scaleX = Sign(num)` | `LizardGraphics.cs:1907-1921` | `world/lizard_gfx.py`（`head_row` + `_draw_head`） | ✅ 跑动中 0..3 行全部出现 |
| 蜥蜴腿 | `val = clamp(int(dist/(4·limbSize))+1, 1, 9) + 9·(2-clamp(int(|flip|·3),0,2))`，后腿再 +27 ⇒ `LizardArm_01..54` | `LizardGraphics.cs:1778-1808` | `lizard_gfx.py` 四肢 | ✅ 单次跑动取到 20+ 档 |
| 蝉乌贼 | `Cicada{0..8}{body,head,shield,eyes1,eyes2}`，`num3 = IntClamp(8 - int(|num2|/180·9), 0, 8)`、`num4 = (8-num3)·Sign(num2)·22.5` | `CicadaGraphics.cs:453-467` | `world/squidcada_gfx.py` | ✅ 0..8 行全部出现 |
| 蛞蝓猫头 | `HeadA/B/C` 各 18 行，`num7 = round(|头角|/360·34)`；睡觉 7→4、匍匐 7、站立走动 6 | `PlayerGraphics.cs:2936-2955` | `rendering/graphics_draw.py` `_head_frame_index` | ✅ |
| 蛞蝓猫脸 | `FaceA..D` 各 9 行（`|角|/22.5`）+ `FaceDead` / `FaceStunned` | `PlayerGraphics.cs:2946-3013` | `_face_angle_index` / `_draw_face` | ✅ |
| 蛞蝓猫腿 | `LegsA` / `LegsACrawling` / `LegsAAir` / `LegsAOnPole` / `LegsAPole` / `LegsAVerticalPole` / `LegsAWall`，各 31 档 | `PlayerGraphics.cs:3050-3110` | `_draw_legs` | ✅（`LegsAClimbing` 只用于管道爬行，本桌宠没有管道 → 不适用） |
| 蛞蝓猫手 | `PlayerArm0..12`，按 `dist/2` 取档 | `PlayerGraphics.cs:3144` | `_draw_hands` | ✅ 0..12 全档 |
| 蝙蝠 | 4 片：`FlyBody` / `FlyWing`×2（`anchorY=0`）/ `FlyEyes`；翅 `rotation = ±(40+150a) + num`、`scaleX` 按扑翅收窄；`bites` 决定翅的可见性 | `FlyGraphics.cs:163-205` | `world/items.py` `_draw_one_batfly` | ✅ 本轮改为原版精灵（原先手绘矢量近似） |
| 面条蝇 | 无分行贴图；翅 `WingSprite((l==0) != (zrot.x>0))`、獠牙按 `zx` 侧别 | `NeedleWormGraphics.cs:423-453` | `world/needleworm_gfx.py` | ✅ |
| 拾荒者 | 无分行贴图（头是 `Circle20` + 三角网格）；仅手掌 `ScavengerHandA/B` 按 `reachedSnapPosition` 切换 | `ScavengerGraphics.cs:507/607` | `rendering/primitives.py` `_scav_hand` | ✅ A/B 都在用 |
| 泡泡 | `Bubble.cs` 写死 `LizardBubble5`（贴图集里的 0..7 只给别的特效） | `Bubble.cs:175` | `window.py` | ✅ 与原版同值 |

复核方式：`python tools/sprite_variants.py` —— 拦截图集查找（`AtlasSet.find_atlas` 缺帧静默跳过、
`Atlas.sprite` 直取会 KeyError），把所有生物放进场景跑 900 tick（并强制扫描蜥蜴头深度 −1..+1、
蝉乌贼 z 轴 −180..180），报「请求了但图集没有的帧」与各族实际取到的变体号。
当前结果：213 帧、缺帧 0。

## 2026-10 大改复核

- ✅ 幼崽尺寸、体色/眼色随机范围、个体移动参数已按 `Player.cs` / `PlayerGraphics.cs` 对拍；`parts_audit.py --check` 通过。
- ✅ 杆导航不再把竖杆加入实体障碍，蜥蜴地面移动不会被杆阻挡；连续攀爬和背景墙路线已覆盖。
- ✅ 蛞蝇猫威胁冷却、匍匐速度、逃生分流与杆占用已通过 `run_all19.ps1`（fails=0）。

## 2026-10 音频与交互复核

- ✅ Push To Meow 长/短叫独立播放器，抓取与甩动事件，闭眼反馈。
- ✅ Rain World 雨循环和蜥蜴咬合音效入口，世界音效独立音量。
- ✅ 高处落地掉落物品并直接匍匐；放置释放坐标与预览一致。
