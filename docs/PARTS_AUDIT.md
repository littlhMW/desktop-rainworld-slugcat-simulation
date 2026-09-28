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
