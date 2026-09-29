Windows 桌面宠物：让 Rain World 的蛞蝓猫住在你的屏幕上。exe 见 release 压缩包。

本项目 fork 自 [lingxiaojun/slugcatpet](https://github.com/lingxiaojun/slugcatpet)（原仓库地址：https://github.com/lingxiaojun/slugcatpet），在此之上修复了脸部表情问题，并加入了蜥蜴、蝉乌贼、拾荒者、珍珠、矛等可放置生物与物件。

RainWorld里控制蛞蝓猫各个bodychunk拼接和行动的质点系统是C#写的，反编译后参考常量和主要函数就能足够相似的模拟。但粒子shader等效果难以复现原游戏渲染，又为了提升桌宠性能，所以我做了大量简化。

## 运行要求

- Windows 10 / 11
- Python 3.10+
- 初始化时需要已下载 Rain World，需要包含 Downpour (More Slugcats) DLC。

## 安装与运行

```powershell
pip install PySide6 UnityPy numpy Pillow
python run_slugcatpet.py
```

首次启动会引导你选择本机的 Rain World 安装目录，从中一次性提取精灵图集到 `~/.slugcatpet/assets`，仅存放在你本机、仅供本程序使用。

## 玩法

展开侧边工具栏可以把东西放到屏幕上：藤蔓、水果、石子、灯笼、黏菌、蝠蝇、蜥蜴、蝉乌贼、面条蝇、拾荒者、珍珠、矛。

所有物件都没有数量上限，想放多少放多少。

- 点工具栏里的图标，鼠标变十字后，在屏幕上点一下即可放下该物件；按 Esc 或右键取消放置。
- **蜥蜴**品种按放置顺序轮换（粉 / 绿 / 蓝 / 黄 / 白 / 红 / 黑 / 蝾螈 / 青），个体颜色、尾色与背刺随机；绿 / 粉 / 白三个品种按原版外观还原。
- 放下的蜥蜴会自己爬行。蛞蝓猫靠近时会扑上去咬一口，被咬到的猫会眩晕一小会儿。
- **蝉乌贼**悬停飞行，被靠近就扑翅逃跑；力竭落地后可以被蛞蝓猫叼起来。
- **面条蝇**出生年龄随机（**幼体 / 成体**，随机不再出卵）：幼体和成体在空中扇翅游走、体型和颜色每只都不同；幼体 5 口可吃、被抓住就惨叫，**惨叫会把最近的成体惹成死敌并去追离幼体最近的生物**（抓着幼体丢向别人就能把仇恨转走）；成体会用獠牙戳人（晕 + 掉东西）和突刺（致命），还能闪过扔过来的矛和石头，同族之间见着就互刺。**被激怒的成体算威胁**：蛞蝓猫会躲它、会持械、也会投矛打它。
- **驯服蜥蜴**：场上有没被驯服的蜥蜴时，蛞蝓猫会去抓落地的蝉乌贼，送到蜥蜴嘴边。这是原版机制（`FriendTracker.GiftRecieved`）——活礼 +0.6、死礼 +1.2，好感超过 0.5 的蜥蜴从此认主，只跟着猫走、不再咬人。
- **拾荒者**持矛在屏幕上巡走，看到蜥蜴或猫靠近会站定瞄准，然后把矛掷出去，掷完就跑。
- **珍珠**很弹，掉在地上会蹦几下；**矛**可以插在地上，也可以被拖起来丢出去。
- 用鼠标按住任何物件都可以拖着它走，松手就放开；丢进水里、半空中都可以。
- 工具栏最右的禁止图标一键清空场上所有物件。
- 别的窗口的**顶边当一块平地**（单向平台）：猫和果子、石子们从上方落下会站在人家窗口顶上，但窗口本体不挡路（猫仍然能从窗口前面走过去）。想关掉就在启动参数里把 `window_platforms` 设成 `false`。
- **墙和杆是两回事**：墙最多只能攀爬一只蛞蝓猫的高度，够到墙头就抓沿，抓不住就贴墙缓慢滑下或蹬墙跳。
- **屏幕顶边只有圣徒能吊**：只有圣徒的舌头能粘住屏幕顶边悬挂，其他猫到了顶边只能站着或者掉下来。
- **杆上跳跃**：在竖杆、横杆上都能起跳，跳出去后可以抓住附近的另一根杆，或者顺手摘掉悬着的果子。
- **扎住的矛变成杆**：矛几乎是垂直地钉进墙或者地面时，会判定成一根对应长度的杆（横着扎进墙就是横杆），谁都能爬，但钉进去的那根谁也拔不出来——想拿回来只能用鼠标把它拖出来。
- **杆上 / 空中投矛**：挂在杆上、或者跳到半空中都能把手里的矛、石头扔出去（原版 `Player.ThrowObject` 不挑姿势）。
- **被挡路**：平地上被同伴挡住会先尝试跳过去，跳不过才会指指点点；脾气不好的猫才会一上来就指。
- **遮挡处的地面**：被前面的窗口挡住的后面窗口顶边，只有露出来的那一小段能当地板踩。
- **睡眠**：上床前要磨蹭很久（睡意从 0 缓慢涨到 100），睡着后会睡很长一段随机时间才自然醒。
- **移动数值对齐原版**：跳跃初速 8/7、按住续力、蹬墙跳 8/7 + 6/5、跑步 4.2、匍匐 4 全部照 `Player.cs` 取值，站立跳约 44px、跑跳约 83px。

**蜥蜴渲染对齐原版（第 38 轮）**：

- **头部 5 片按反编译重写**：原版没有独立朝向，镜像只看 `Sign(headDepthRotation)`（朝右 = -1，来自 `LizardGraphics.Update` 里腿翻转累加出的 `depthRotation`），而且 `FSprite.rotation` 的矩阵（`FNode.UpdateMatrix` × `FMatrix.SetScaleThenRotate`）跟 Qt 的顺时针 `rotate` 同号 —— 所以既不要再 +180、也不要垂直翻转。之前「朝左 + 张嘴」时上下颚会朝相反方向转（对称轴整个是错的），现在左/右 × 闭/张四种组合都用数值对照过原版矩阵，位移还走 `PerpendicularVector(颈-头)`。
- **腿**：翻转符号按原版 `Custom.DistanceToLine(脚, 挂点, 挂点.rotationChunk)` 求、前腿整体取反（`LizardGraphics.cs:1209-1215`）——站立时四条腿同号，**远近腿不是镜像关系**；贴图锚点是中心、位置钉在脚上、旋转 = `aim(脚→髋) - 90`、按髋脚距离在 `LizardArm_01..09`（后腿 `28..36`）里选帧，远侧腿的色层压到 0.3，全部照 `DrawSprites` 逐行对齐。
- **拖动时的身长**：原版躯干是 `BodyChunkConnection(Normal, elasticity 0.95)` 的近刚性绳，之前拖快时整条会被抻长。现在躯干刚度 0.8、头挂点 `12*headSize`（`LizardGraphics.cs:1291`）、头点每帧最多跟 24px，并给链节加了长度夹取，拖再快身体也保持原长、整条跟着走。

**横杆=地面 · 空中抓杆 · 飞虫入视野（第 39 轮）**：

- **横杆顶上就是地面**：站在横杆上时，找食、歇、跳着去摘果等判断和平地完全一样，只是换成横杆的动画；待够久了也会主动下杆去拿吃的。
- **带方向跳杆 + 空中抓杆**：竖杆杆顶、横杆上、空中都能朝另一根杆起跳，跳出去后在空中伸手抓住目标杆再接着爬（`planning/pole_hop.py`，弧线用反编译里 beam jump 的实测落地弧 `get_pole_jump_arc` 采样，不用平地起跳弧）。
- **杆上投矛**：挂着、蹲着杆顶都能把手里的矛/石头扔出去。
- **不再死赖在杆头**：杆顶最多赖 `POLE_TIP_LOITER_MAX` 帧就会自己跳杆或者下杆，杆头不再一只只堆着。
- **飞虫进寻路**：蝙蝠、禅乌贼、幼面条蝇也进可达性判断（`planning/fly_reach.py` 的 `in_reach`），近距离直接抓、远距离先规划一条够得到的路线再跳/走过去抓（空中贴手也能抓）。
- **饿到一半抓幼体**：饱食度掉到一半以下时，幼年面条蝇也进猎物名单。
- **社交不强制**：社交对象跑出 `SOCIAL_ABANDON_R` 或者死掉就直接放弃（道谢、抚摸、指指点点都一样）。
- **矛朝向修根因**：手里/背上的矛的朝向改用 `facing` 决定，不再拿两个躯干 chunk 的差去算，随机抖动时矛不再跟着乱转。

**威胁圈 · 蜥蜴物理与外观对齐反编译（第 42 轮）**：

- **恐惧圈 = 1/3 桌面宽**（`THREAT_WIN_FRAC`，小窗口有 90px 下限，不写死）：这个圈里有活蜥蜴时恐惧优先级最高 —— 睡着会被立刻叫醒，圈里还有活威胁就睡不着（`_sleep_roll` 恒 False）；勇敢的才敢迎战、善良的才敢先去救人，蜥蜴贴到 `FEAR_TOO_CLOSE_R` 一律逃。
- **有威胁先上高处**：圈里出现威胁、身边就是墙或者附近有竖杆时，先爬墙 / 上杆（`FLEE_CLIMB_P`），没得爬才掉头跑。
- **倾向握家伙**：威胁圈内空手时会专门跑去捡附近的矛/石头再迎上去（`ARM_SEEK_R`/`ARM_COOLDOWN`）。
- **圣徒会主动超度威胁**：业力与饱食都够时，圈内出现活威胁直接进 `Ascension`。
- **匍匐潜行真的有用**：蜥蜴选目标时匍匐的猫权重除以 `CROUCH_TARGET_MULT`（之前方向反了，趴下反而更招咬）。
- **躯干/尾 = 原版 BodyChunk + BodyChunkConnection**：3 节躯干按 `Lizard.cs:680-687` 的半径/连接长度/弹性串起来，杆长约束只消径向误差（切向动量保留），转身、被拖、叼猫时身体不再抻长也不再折成竖条。
- **头色按原版 `HeadColor` 呼吸闪烁**：在 `palette.blackColor`（宠物里取深色躯干色）与 `effectColor` 之间按 blink 相位搏动；白蜥这类整只个体色的品种深相位取近黑。
- **腿翻转公式抽出成 `_leg_flip_num`**（原版 `Custom.DistanceToLine(脚, 挂点, 挂点.rotationChunk)` × 前腿取反）：站立时四腿同号，一条腿抬到体轴另一侧才变号，和 `LizardGraphics.cs:1209-1215` 一致。
- **端着礼物的猫不会被咬**：手里是能驯服蜥蜴的食物时，蜥蜴靠近只吃食不咬人（原版 `FriendTracker.GiftRecieved`）。

**四槽位与复活认领（第 43 轮）**：

- **四个槽位**：右手（主手）、左手（副手）、背部（只有猎手系用、只放矛，原版 `Player.spearOnBack`）、胃（暂时闲置）。`SlugcatBody.pick_hand(kind)` 是唯一选手指南：右手空就用右手，右手被占才落到左手，两手都占就顶掉 `ITEM_PRIO` 最低的那件（同优先级先顶右手），顶不动就抓不起来（纯查询，不改状态）。取果、取矛、取石、空中抓飞虫、杆上摘果、被鼠标拖着时的抓取全走它，不再按「目标在哪边就用哪只手」挑手。
- **双手都拿着投掷物时先扔右手那件**（`_launch_weapon`），另一件仍在左手里。
- **猎手：附近没家伙就把背上的矛抽到主手**（`_weapon_ready`，原版 `CanRetrieveSpearFromBack`）；抽的时候手上腾不出位置就还背回去，不会把矛弄丢。
- **一只死猫同时只由一只猫去救**：`_revive_claimed_by` 不建登记表，直接看谁的状态是「Socialize + revive + 目标就是它」——救活、放弃、或救护者自己倒下都会离开 Socialize，认领自动失效，死猫重新可救。
- **蝙蝠 / 禅乌贼的 `hurt` 补上 `by`/`lethal` 形参**（与面条蝇统一签名）：投掷矛 / 石头命中飞虫走同一段命中循环，之前会直接 TypeError。

**杆上行为 · 面条蝇 · 睡眠结算（第 44 轮）**：

- **杆上（横杆 / 竖杆）等同地面**：摘果、投矛、捡地上的矛 / 石头、徒手抓飞虫全部通用。
- **够取改用手位判距**（`_hand_reach_dist`）：取躯干两节＋两只手的真实位置里最近的那个。原先只量 `chunk0`，而杆上站立时手比 `chunk0` 低十几像素 → 明明抓得到却判成「够不到」，猫上杆走到位后原地发呆。
- **够不到就放弃**：`HPOLE_GOAL_TIMEOUT`（150 tick）到点清掉目标并松杆离开；`_hpole_goal_clear` 同时清掉控制器里的停位 —— 否则 `StandOnBeam` 的 200 tick 超时永不触发，猫会一直站在杆面上直到掉下去。
- **杆上伸手捡东西 / 抓飞虫**（`_pole_reach_pickups`）：有威胁又肯用矛时捡够得到的矛 / 石头；饿时徒手抓住飞到杆边的蝙蝠 / 乌贼 / 幼面条蝇（抓到就松杆落到 `CatchFly`）。
- **竖杆也能「跳一下够」**：`_pole_jump_grab` 从 `_hpole_goal_jump` 抽出来，横杆竖杆共用（原版杆上跳抓）。
- **面条蝇随机年龄去掉卵**：`AGE_ROLL` 只留幼体 0.55 / 成体 0.45（卵是物件不是面条蝇，随机生成不再出）。
- **面条蝇翅膀贴图照原版重排**：原先固定画成「身后一对 + 身前一对」、朝向恒为竖直，看着像交叉骨架。现在按 `DrawSprites` 的 `WingSprite(num8, m)` 取 `num8 = ((l == 0) != (zrot.x > 0))`——哪一侧翻到上层由朝向决定，图层 0 在下、1 在上，腿排在最上层；朝向补上 `Update` 里 `vector6` 那一推（身体切线 ±45° 且强制朝上，再按 `|vector.y|` 混到朝上），翅才是原版那种斜后方张开的样子。幼体照原版 `isVisible`：被啃到 `bites <= 4` 就不显翅。
- **愤怒的面条蝇成体算威胁**：`_hostile_fly` 走原版 `BigNeedleWormAI` 的 `hostile_to`（拿着它的幼体 / `tempLike < -0.25`）；`_threat_lizard`、`_nearby_lizard`、杆上投矛目标 `_nearest_throw_target` 都认它 → 会躲、会持械、会投矛打。猎食 / 矛杀名单本来就有蝙蝠、乌贼、幼面条蝇与成体。
- **入睡即结算**：进 `Sleep` 态那一刻就扣掉睡眠饱食度（`food_hibernate` 格）并且业力 +1；睡醒只补体力，不再重复结算。

**面条蝇体色对齐原版调色板（第 45 轮）**：

- **幼体 / 成体各 50%**：`AGE_ROLL` = `((small, 0.5), (big, 0.5))`。
- **体色逐档对上 wiki 调色板图**（[Adult Noodlefly](https://rainworld.miraheze.org/wiki/Adult_Noodlefly) / [Infant Noodlefly](https://rainworld.miraheze.org/wiki/Infant_Noodlefly) 的 palette 图，原图注明「每块颜色的**面积正比于出现概率**」）：
  - 主体（成体 `lightness = 0.4`，概率 16/17·2/3）：`#440718`，色相随 `hue = WrappedRandomVariation(0.5, 0.08, 0.2)` 从紫 `#44071B` 扫到红 `#440713`。
  - 暗档（1/3）：`lightness = 0.4·rand⁵`，一路压到纯 `palette.blackColor`，即 wiki 图顶那条黑带 `#1B0A20`。
  - 亮档（1/17）：`lightness = 1 − 0.6·rand⁵`，底部那条粉白带。
- **灰 / 白 / 黑那一档补上了（关键）**：原版 `Custom.HSL2RGB` 的 `switch` 只写了 `case 0..5`，`(int)(h*6)` 落到 6 以上时一个分支都不匹配，直接返回 `r = g = b = l` 的**灰**。面条蝇 `num = hue + 0.478` 有 **15.3%** 的个体 > 1 → 这些个体在原版里就是灰的。之前我们对 hue 取过 `% 1.0`（错），把这 15% 全画成了饱和红。现在按原版不取模：成体灰个体 = `#29222C`，与 wiki 图右侧那根灰柱**逐像素同值**（灰柱宽度 15% ↔ 灰个体占比 15.3%）。
- 复核脚本 `work/scratch/pal_audit.py`：按同一套个体随机采样 4 万只，画成 wiki 那种「行高 ∝ 明度概率、列宽 ∝ 色相概率」的调色板图 → `outputs/noodlefly_palette_vs_wiki.png`（左 wiki / 右本作）。抽查：主体 `#440719` vs wiki `#440718`、灰柱 `#29222C` vs `#29222C`、顶黑 `#1B091F` vs `#1B0A20`。

**面条蝇的腿 / 獠牙 / 翅膀照原版修正（第 46 轮）**（对照你给的 [Noodlefly_kiss.gif](https://static.wikitide.net/rainworldwiki/3/3b/Noodlefly_kiss.gif) 与反编译 `NeedleWormGraphics.cs`）：

- **腿（原版就叫 legs，画出来正是你说的「胡须」）原本挂在了吻部上 → 挂回躯干**：原版 `LegConPos` 用 `OnBodyPos(0.03 / 0.066 / 0.1)`，而 `OnBodyPos` 里的 `TotalSegments` **不含 snout**（成体是 15 节躯干，`NeedleWorm.cs:70,983`），所以三对腿全长在躯干最前面 1~1.4 节、紧贴头部后侧。我们换算到自己的 `seg` 数组时漏了 `+snout_n` 这个偏移，腿被挂到吻部最前端 —— 看上去就是脸上一撮须子。
- **腿的形状一起改了**：原版是一条 4 顶点的小蹼 —— 根在体侧，尖被 `ConnectToPoint(…, 11/16·legsFac)` 的连接半径拉住，同时吃重力（`vel.y -= 0.9`）和 `LegConDir * 0.55` 往外拽，所以是**挂在体侧外下方的小短腿**（长 11~16·`legsFac`、中点全宽约 4.4·`legsFac`），尖端染 `detailsColor`。之前画成 2.6 宽的细绦，才像胡须。
- **獠牙起点整体前移了一段 → 挪回口腔根部**：原版 `FangMesh` 的第 0 组顶点就落在 `vector5`（口/吻根部）上；我们的循环是先前进再记点，整根獠牙凭空往前挪了 `fangLength / 3.5`（≈14 px），看着就是「针飘在嘴前面」。现在根点先入表、再逐段前伸（5 段 = 6 个节点）。
- **獠牙图层**：照 `InitiateSprites` 的精灵序，`FangMesh = 5 < BodyMesh = 6` —— 獠牙画在**身体之下**（从嘴里伸出来的样子）。我们原先画在身体之后，整根浮在脸上。
- **獠牙半宽**：原版 `num14 = Lerp(0.6 + 0.6·fangBlack, 0.5, num13)` 本身就是半宽（根 1.2、尖 0.5），我们额外乘了 0.5，针细了一半。
- **獠牙摆动补上 `zRot.x`**：`DrawSprites` 里那一项末尾是 `* vector2.x`；少了它獠牙不会随左右朝向摆动（`fangOut = 1` 时 `Sin(num10·π) = 0`，原版本来也就是直的）。
- **翅膀宽度照原版 `CentipedeWing` 贴图**：翅是 `CustomFSprite("CentipedeWing")` —— 一张 8×52 的白色叶片贴图，贴到「根 / 尖各半宽 `2*wingsSize`」的四边形上（`NeedleWormGraphics.cs:565`）。CustomFSprite 的 uv 序是 0=左上 1=右上 2=右下 3=左下，而翅的顶点 0/1 在尖、2/3 在根 ⇒ **贴图上缘 = 翅尖**。贴图逐行宽 2,4,6,6,8×20,6×8,4×9,2×11，换成「根→尖」的半宽比就是 **0.25 / 0.5 / 0.75 / 1.0 / 0.75 / 0.25**（外侧半段最宽，像蝉翅）。我们原来固定画成 2.4→1.2 的锥条，两端都不对。
- 复核：`work/scratch/e2e_r46.py`（24 项；用 `ribbon` 探针直接量每条折线的端点、半宽与绘制顺序）与 `outputs/noodlefly_parts_r46.png`（左 = wiki kiss 动图里的原版成体，右 = 本作：成体闭口 / 成体张口 / 幼体）。

**面条蝇躯干半径 / 圣徒敲爆米花 / 爬杆投矛 / 圣徒吃荤眩晕（第 47 轮）**：

- **面条蝇躯干半径照 `GraphSegmentRad` 重算**（`NeedleWormGraphics.cs:709-720`）：吻段不再是常量 1.0，而是 `1 + pow(InverseLerp(0, 0.5, fangOut), 0.6) * 1.5`（开口时整段吻变粗，闭口 1.0）；尾段不再是线性收到 0.9，而是按 `LerpMap(i - snout - ...)` 带 `(1.4 - 1.35*thinTail) * Lerp(1.8, 0.2, fatness)` 指数收细（`thinTail = 1` 时尾梢 0.707，比原来细）；整段再乘 `num3` —— 成体躯干首尾拉开 50→80px 时 1→0.85 整体收细（幼体恒 1.0）。只改渲染半径，物理半径没动。
- **圣徒肯拿矛敲爆米花**：`SeedCob.HitByWeapon` 只认 `Spear`，所以「敲开豆荚」必须用矛；而圣徒的 `_spear_willing()` 是 False（不用矛打猎）。现在「为了吃」单独走 `_cob_spear_willing()`（素食 / 特殊食谱也愿意），既不去打猎也能把豆荚敲开。
- **掷矛站位不再停在空档里**：豆荚两个 chunk 是斜的，`_cob_would_hit` 的预演在同一个高度上是一段一段的「能中 / 不能中」区间。原来「离理想站位 60px 就停下」会让猫正好停在不能中的区间里、站着把预算耗完才放弃 —— 表现就是「圣徒敲不动爆米花」。现在：① 先看**现在这位置**掷不掷得中，能中立刻出手；② 掷不中就走到底下的站位（收尾公差 4px）再掷。
- **轻抛也要 `firstFrameTraceFromPos`**：圣徒投矛走的是 `Player.TossObject`（不是 `Weapon.Thrown`），原来没记 `firstFrameTraceFromPos`，真实第一帧的扫掠线段比预演的短一截 —— 预演说能中、真掷出去却穿过豆荚。现在轻抛也标 `_f1`（第一帧从出手前位置起算），预演和实弹完全一致。
- **掷矛方向朝豆荚本体**：原来拿「站位点」定左右，站在豆荚正下方时站位点会落到身体这一侧，矛就直接往反方向飞。现在朝两个 chunk 的中点掷。
- **爬竖杆到猎物同高再投矛**：目标比猫高 40px 以上、猫在地上又找得到竖杆时，它会挑一根（杆顶高于目标、路线代价最小）爬上去，爬到 `|自己高度 - 猎物高度| <= THROW_JUMP_DY` 再水平投矛，只出手一次；没有竖杆就照旧跳着打。
- **圣徒吃荤会眩晕**：对照 `Player.SaintStagger`（`Stun(time / 5)`，肉食的 `staggerTime` 220~800），素食 / 特殊食谱（圣徒）吃到 `is_meat` 的东西会 `Stun(44)`，走 Stunned 态并掉下手上的东西；吃果子不晕，杂食猫（白猫）吃荤也不晕。
- 复核：`work/scratch/e2e_r47.py`（23 项：躯干/吻/尾 20 段逐段对拍、矮豆荚两侧都能敲开、爬杆同高投矛、吃荤眩晕）。

**面条蝇攻击欲望 / 禅乌贼 / 蜥蜴 AI / 猫的攻击欲望 / 尸体与橡皮（第 48 轮）**：

- **成体面条蝇真的会追猫了**：静态关系 `BigNeedleWorm → Slugcat = Eats 0.25`，但 `AI.cs UncomfortableToAfraidRelationshipModifier` 会在 `Lerp(150, 450, nervous)` 以内把 `Attacks` 改判成 `Afraid`。之前只落地了「拿着幼体 → Attacks 1.0」那一条（`BigNeedleWormAI.cs:333-413`），于是成体几乎从不出手。现在按 `nervous` 性格插出畏惧距离：比它远就把猫当猎物主动扑，一进圈立刻掉头跑；尸体既不追也不躲。恐惧距离随每只个体的性格不同（`nervous` 0~1 → 150~450px）。
- **面条蝇的准度**（`BigNeedleWormAI.cs:325-349`）：进攻点不再是「偏差 >60px 才重挑」，而是每 tick 在「当前进攻点 / 目标点」周围撒一个 300px 内的候选点，`AttackPosScore` 更低就换过去；提前量用 `LerpMap(到进攻点的距离, 80, 400, 0, 30, 0.35)` 放大目标速度估计（每 tick 先衰减 1%，:154）；体轴朝向改取「体节中点 → 头」（:520，取错源会让蓄力条件几乎永远不成立）；贴住阈值 60 → 40（:533）。
- **禅乌贼整条链路重写**（`Cicada.cs` / `CicadaAI.cs` / `CicadaGraphics.cs`）：体力按 1/70 每 tick 回升（原来几乎飞不动）；冲撞是 21 帧蓄势 → 21..38 直线突进（`CHARGE_THRUST = 4`/tick）→ 收招归零；触须 4 节半宽 `(1.6, 1.2, 0.9, 0.8)`，根部照 `CicadaGraphics.cs:553-555` 随 `lookDir` 偏移（`+lookDir*6` 与 `2*|p.x|*(1-|lookDir|)` 一起算，净位移 4px）；翅膀按 `|p.x|` 折算成「整片画 / 不画」，不留半透明毛边；**被吃**改成逐 tick 递减 `eaten`、归零才消失（把原仓库「吃东西有渐变外观」这一套还原到乌贼上）。
- **蜥蜴 AI 照 `LizardAI.DetermineBehavior` 重排优先级**：Flee > 叼尸体 > Injured > Anger/Fight > casual 撕咬 > Hunt > InvestigateSound > Pack > wander。
  - 品种关系表逐条照抄 `StaticWorld.cs:3691-3726`（绿→蓝 `Eats 0.25`、蓝→绿 `Afraid 0.25`、红→红 `Attacks 1.0`、黄→黄 `Pack 0.2`……），基表 `StaticWorld.cs:3668-3689`（→拾荒者 `Eats 0.8`、→蝉乌贼 `Eats 0.05`、→成体面条蝇 `Eats 0.25`）。
  - 视野锥按 `LizardBreeds.cs` 的 `perfectVisionAngle / periferalVisionAngle = Lerp(1, -1, t)`，锥外只留 40% 视野。
  - 侵略追踪器 `AgressionTracker`（`angerSpeedUp/Down = 0.001`，`Utility = InverseLerp(0.35, 1, anger)`）越过 0.35 转 Fighting，会真的互相撕咬掉血（`_lizard_bite` 现在也认拾荒者）；残血 `LizardInjuryTracker` 退向角落躲起来；`LurkTracker` 让白蜥 / 蝾螈原地潜伏 ×4；地面/地形被砸出的响声 320px 内会去查（砸中地面能引开蜥蜴）；黄蜥 `Pack` 结伴。
- **蛞蝓猫的攻击欲望**：`FIGHT_UNARMED_R = 150` / `FIGHT_UNARMED_BRAVE = 0.70`（空手也敢主动扑上去的距离与胆量阈值）；敌对**拾荒者**（没交易过、`like` 低）进投掷目标列表——珍珠交易过的友好拾荒者不算。圣徒仍不肯为打猎用矛。
- **尸体**：拖动非蛞蝓猫的尸体（含拾荒者）丢出窗口外就当场清除；活着的对象不会被误清。
- **删除模式**：工具栏新增橡皮按钮，进去以后点谁删谁——13 类物件/生物（果子、石头、黏菌、蝠蝇、蜥蜴、蝉乌贼、面条蝇、珍珠、矛、拾荒者、豆荚、种子、杆）都能单点删除，蛞蝓猫不在此模式下被删；Esc / 右键退出。
- 复核：`work/scratch/e2e_r48.py`（29 项：面条蝇远近关系与出手、乌贼蓄势三段 / 推力 / 体力 / 触须偏移 / 被吃、蜥蜴关系表与视野锥与受伤与响声与同类互咬、投掷目标与友好拾荒者、尸体出屏、删除模式含鼠标事件）。

**挡路与掩护 / 手部携带 / 边缘卡死 / 隐形窗口 / 小生物命中 / 邻杆小跳（第 49 轮）**：

- **投掷前先看视线**：`_launch_weapon` 出手前用 `_throw_line_blocked` 扫「自己 → 目标」这条线段（粗细 14px、最远 320px），扫到任何同伴的身体段就不扔了 —— 原版投掷前会避让同伴（`ScavengerAI` 的投掷判定 + `Weapon.Thrown` 的碰撞），不然一矛扎在同伴背上。爆米花、果子的投掷判定不受影响。
- **有威胁就躲到拿矛的同伴背后**：新状态 `CoverAlly`。场上有威胁、自己手上没家伙时，猫会挑一只**握着矛**的同伴（`_armed_peer`，按距离与性格排序），绕到它身后 `COVER_BACK_OFF=26px` 处跟着走（保持 `COVER_MIN_GAP=70px` 不贴脸）；自己捡到矛/石头就立刻退出掩护去迎战，威胁进到 `FEAR_TOO_CLOSE_R` 则直接逃跑。找不到持械同伴、或试了 `T_COVER_RETRY` 帧还不成，就退回原来的害怕逻辑。
- **有威胁时被挡路：一律先跳**：`_scan_blocking` 里「先指指点点再跳」只留给没威胁的场合；场上有威胁时不管什么性格都先跳过挡路的同伴（`_threat_present()`），不会站在蜥蜴面前对同伴指指点点。
- **左手拿着东西爬杆不再穿模**：抓杆时手是**抓在杆上**的，物品要跟着手走。新增 `SlugcatBody.hand_pos`（`graphics._update_hands` 每帧写回真实手位）与 `_carry_anchor(side)`：`bodyMode == "ClimbingOnBeam"` 时携带点直接取手位，并且**不写** `arm_aim`（原版爬杆时 `SlugcatHand` 把手臂交给杆子，不进 `HuntRelativePosition`）。照 `Player.cs:5984-5990`（物品跟手）+ `SlugcatHand.cs:41-74 / 190-256`。
- **不再卡死在屏幕左右边缘**：贴墙滑降原来写成 `vy = climb - g`，每帧又被重力扣一次，净下滑只剩 0.14px/帧（要 20 秒才从墙头滑到底，看上去就是「卡死在边上」）；现在直接给 `vy = WALL_LEDGE_SLIDE + g`，一帧就是该有的下滑速度。爬墙另加 `WALL_APPROACH_TIMEOUT`：够不到墙头、也上不去时按距离给宽限，超时就松手落地，不再永远贴着墙重复爬墙动作。
- **隐形窗口**：枚举他窗口当平台时原来只按 `own` 集合排掉自己，但自家 QToolTip / 托盘提示 / Qt 内部隐藏窗拿不到 winId，于是被当成一块「看不见的地板」。现在 `_visit` 用 `GetWindowThreadProcessId` 跳过**本进程所有**窗口，另外跳过带 `WS_EX_TRANSPARENT` 的点击穿透窗口。
- **矛戳面条蝇不再穿过去**：原来只在矛尖**当前点**判命中，面条蝇 40px/帧地飞，矛几乎必然从它身上穿过。新增 `_small_hit`：有体节链的（面条蝇）逐节扫掠，圆身小生物（蝠蝇 / 蝉乌贼）用「上一帧 → 本帧」线段做圆判定，一矛就能带走。
- **杆顶跳邻杆改成小跳弧**（顺手修掉的旧 bug）：杆顶「跳过去抓另一根杆」用的是全力 `pole_jump`（横速≈6px/tick，一条弧飞 300+px），40px 外的同高邻杆会被**从头顶掠过**再落到远处地面 —— 调参里的 `POLE_HOP_VX/VY` 从来没被用上。现在 `SlugcatBody.pole_hop` 用小冲量（4.0 / 4.2），规划弧换成同源的 `jump_arc.get_pole_hop_arc`，跳 40px 一次到位（`work/scratch/e2e_pole.py` 第 5 节从「靠乱走碰到」变成真的跳过去）。
- 复核：`work/scratch/e2e_r49.py`（19 项：同伴挡线不投掷、掩护走位与拿到矛后退出、有威胁先跳、左手持物爬杆的手位、贴墙滑降速度、爬墙超时、本进程与透明窗口被排除、小生物扫掠命中、杆顶小跳命中）。

**社交动作**（第六类欲望「社交」攒满后凑到同伴身边做；动作词表见 `slugcatpet/behavior/social.py`）：

| 动作 | 手势 | 含义 |
| --- | --- | --- |
| 指向 | 伸出手指对象，举着不放 | 指向 / 想要 / 注意 |
| 指指点点 | 伸出收回手快速循环 1~5 次 | 指责 / 强调 |
| 抚摸 | 伸出手，在对象上画折返 2~5 次的横线 | 喜欢 / 安抚 |
| 拍拍 | 伸出手，在对象上画折返 2~5 次的竖线 | 喜欢 / 安抚 |
| 复活 | 伸出手用力按压目标（身体也一起用力向下）4~8 次 | 复活中，按完对象复活 |
| 匍匐 | 趴下 | 让路 / 抱歉 / 害怕 |
| 匍匐指指点点 | 匍匐着指指点点 | 仇恨 / 预备攻击 / 狩猎目标 / 帮我打这个 |
| 匍匐指向 | 匍匐着指向 | 恐惧这个对象 / 小心这个对象 |
| 匍匐行走 | 匍匐着潜行挪动 | 害怕强敌，正在潜行 |

性格决定抽得到哪些：`crawl_like` 低的猫（不肯趴）抽不到匍匐族，`point_like` 低（性格好）少指指点点，`sociability` 高更喜欢抚摸/拍拍；记恨的对象会加权匍匐指指点点。

同一套词表也管**平时**（没攒满社交欲望时）的随手小动作——所有伸手比划的地方都走同一个「起手 / 推进 / 收势」接口，不再各写各的：

| 情景 | 抽到的动作 |
| --- | --- |
| 家闲态附近有同伴 / 鼠标在附近停够久 | 按性格随手抽一个（指向/指指点点/抚摸/拍拍/匍匐族），一小段后自己收势 |
| 被别的猫挡路（跳不过去） | 指指点点；暴躁又爱趴的猫改用匍匐指指点点 |
| 杆上被同伴挡住 | 按性格分流：好性格松手让路、中性停住等待（交叉处有横杆就先挪过去）、坏性格死磕到底；挤位赛随机只留一只，坏性格被挤掉落地后回头指指点点 |
| 被抢了果子 | 过去扒拉指指点点那个小偷（`protest` 是 `scold` 的旧键别名） |
| 追鼠标 / 睡醒 | 指向鼠标；性格不好的猫改成指指点点鼠标 |
| 空手反击蜥蜴 | 贴上去扒拉着指指点点 |
| 被同伴指指点点 | 性格不好就回头指回去，其余有概率转身匍匐 |
| 被顶后让完路 | 小概率回头对顶人者做个动作 |
| 被鼠标抓着挣扎 | 伸手扒鼠标 |
| 复活同伴 | 按压 4~8 下（`PressGesture`），按完对方复活 |
- 手里或脚边有矛/石头时，蛞蝓猫会主动迎战蜥蜴：捡起家伙、拉开距离、预判弹道扔出去。在杆上也能把手里的东西吃完。
- 拖拽**爆米花**只会把豆荚拉开（植株不会挪位置，松手弹回），豆荚有弹性，也会和地面/窗口碰撞。
- 蛞蝓猫**手里拿着东西**时，用鼠标抓着它**剧烈左右摇晃**，东西会被甩掉（先掉石头、再掉果子，最后才是矛），甩出去的物件带着摆动速度飞出去。
- **被鼠标抓着的时候**：靠近杆子或地上的东西会自己伸手去够——松手就抓牢，竖杆爬上去、横杆（含钉成杆的矛）就地挂住；抓住的食物拖远也不撒手。
- **被指向 / 被指指点点**：鼠标只要在猫附近**待够一段时间**就会招来指向和指指点点，**不需要把鼠标停住不动**；挪远了就重新计时。
- **所有猫都死掉**时会一起走一遍转生：先守灵片刻（这段时间同伴仍能扒拉救回），随后尸身升起白色灵光，全体在屏幕顶部中央转世复活。
- **体力经济（已撤回自创机制）**：自创的「兜底扣体力 + 回体力烧饱食度 + 没吃没体力就睡掉一级业力」整套已删除，回到原仓库口径——只有剧烈（1/1200）和轻度（1/4800）两档行动耗体力，发呆 1/1600、趴下 1/800 缓慢回，**不跟饱食度挂钩**。睡觉照旧「涨一级业力 + 扣一格饱食度 + 体力回满」。
- **投矛打爆米花**：矛的判定改成按本帧扫掠线段比豆荚（原版 `Weapon.cs` 逐 chunk 命中判定，判半径还带玩家投掷的 +5），不会再一帧跨过整个豆荚而漏判；打中的矛**会插在豆荚上**跟着豆荚晃，想拿回来可以捡（插在生物身上的仍然拔不动）。
- **活泼度**：发呆驻留时间缩短、发呆权重下调、爬杆/爬墙/追鼠标/小动作的兴趣回升都调快了，玩耍的体力门也放宽了，猫整体更爱动。
- **猎手背上的备用矛**画在猫身后（原来压在猫身上）。
- **状态面板**底板修好了（普通 QWidget 要开 `WA_StyledBackground` 才会画 QSS 底色，之前是透的）。
- **跳跃高度已核对**：我们的物理 1 逻辑单位 = 原版 1 像素（身体 17），实测站立跳峰高 43.7，与按 `Player.cs` 常数独立复刻的结果（44.0）一致；相对画出来的猫高（约 37）是 1.18 倍，和原版观感一致，所以这里不需要按画面再缩放。
- **打不中爆米花修好了（第 28 轮）**：一是「一帧插墙」——矛在飞过豆荚的同一帧撞到窗口侧墙时，会被拽回插墙姿势，命中判定就看不到那一段飞行了；现在扫掠线段用的是**撞墙之前真正飞到的位置**（`_seg_end`，对照 `Weapon.Update` 先判命中、后 StuckInWall 的顺序）。二是预演弹道——蛞蝓猫掷矛前会按 `Spear.step` 逐帧预演一遍，预演说能中才出手。三是**顺植株爬**——豆荚挂得比掷矛线高、跳也够不着时，猫会顺着爆米花植株爬上去，爬到和豆荚同高再插一矛（这截「植株杆」是虚拟的，不画出来、不挡路，也**不许在交点换到别的杆上**）。实测：40 个豆荚种子全中、17 个不同位置全中，且矛都插在豆荚上。
- **体力口径回滚（第 32 轮）**：上一轮自创的「1.5 倍消耗 + 兜底 1/2000 + 代谢烧饱食度」全部撤回原仓库数值（剧烈 1/1200、轻度 1/4800、发呆 1/1600、趴下 1/800），也没有「没体力才去睡」的额外门槛了。**吃饱之后**，猫会把捕猎也算进娱乐项目：饱着也会拿石头/矛去追蝙蝠、禅乌贼。
- **状态面板底色（第 28 轮再修）**：上一版只修了面板本体，行区所在的滚动视口还在用调色板默认浅灰铺满，看起来像一条浅灰带；现在视口/行容器都设成透明，整块面板是同一种深色。
- **杆子更细（第 32 轮）**：杆子半径 2.0 → 1.4 逻辑单位，视觉和碰撞都一起收细。
- **尸体可以扔出屏幕（第 32 轮）**：非蛞蝓猫的尸体（蜥蜴/禅乌贼/蝠蝇）被拖到窗口外松手，或自己飞出去，就会直接清除；活着的东西照旧会被边框挡住。
- **屏幕顶边谁都不能挂（第 32 轮）**：以前是「爪子抓住了顶边就算攀附」，现在顶边对爪子一律不算可抓边——能吊住屏幕顶边的**只有圣徒的舌头**。
- **蝠蝇爱贴低空（第 32 轮）**：75% 的巡飞目标点落在下半屏，且到达后在低空**原地悬停更久**（约 7 秒）才换下一个点。
- **鼠标更容易被注意到（第 32 轮）**：被注意半径 150 → 260，追鼠标的兴趣半径 320 → 520，鼠标稍微晃远一点也不会立刻被忘掉。
- **猎手出生自带一支矛（第 32 轮）**：猎手（含其变体）一出生背上就插着一支备用矛；背上只能挂一支，换矛时旧的那支会被正确放回地面。
- **不动的矛不伤人（第 32 轮）**：伤害只算「正在飞行 / 刚掷出」的矛——插在地上、躺在角落、被别人捡在手上的矛不再蹭伤路过的猫。
- **蜥蜴步态照原版复刻（第 33 轮）**：九个步态参数（步幅阈值、抬脚高度、落脚下沉、腿速、腿灵活度、腿平滑、前后腿错位、上下颠、冲刺倾向）直接照抄原版 `LizardBreeds.cs`：绿蜥大跨步拖腿、粉蜥对称步、蓝蜥小碎步、白蜥慢速试探；腿按原版 `LizardLimb` 模型走（脚踩住 → 被身体拖到身后 → 抬脚迈到身前），躯干随步伐上下颠（原版 `frontBob`/`hindBob`）。
- **白蜥头会黑白呼吸（第 33 轮）**：原版 `LizardGraphics.HeadColor` 是 `HeadColor1/2` 之间按 blink 呼吸；之前只给彩色品种做了，白蜥的头一直死白。现在白蜥头在黑↔白之间呼吸闪烁，体色仍是纯白（`DynamicBodyColor`）。
- **叼猫（第 33 轮）**：蜥蜴会把死掉/昏迷的蛞蝓猫叼在嘴前（速度降到 55%），一路搬到屏幕两侧角落放下，再咬到死。优先级：**叼死猫/昏迷猫到角落 → 咬死昏迷的猫 → 追最近的活猫 → 其余还没晕/死的猫**。中途被石头砸晕、被矛打、自己死、目标醒来都会松口。
- **被石头砸晕（第 33 轮）**：石头命中按原版 `turnedByRock` 判定眩晕时长（绿蜥最耐砸），晕了立刻松口并丢掉当前目标。
- **复活要两只手（第 33 轮）**：以前只看「身体离目标够近」；现在两手要分别贴到目标身上、胳膊确实伸出去（`REVIVE_ARM_MIN`）才算在复活。
- **冲刺倾向（第 33 轮）**：锁定新目标时按品种 `lounge_tendency` 掷一次骰子——粉蜥 0.05 慢慢蹭过来、蓝蜥 0.01、绿蜥 1.0 必定全速直冲。
- **部件审计（第 34 轮）**：新增 `tools/parts_audit.py`，把「已移植对象的尺寸/位置/图层」变成可复现的检查：它会调 `tools/parts_table.py` 从反编译源码抓出每个实体的原版精灵表（层级/元件/原始像素/变换），生成 `docs/PARTS_REFERENCE.md`；同时把原版 `BodyChunk` 的半径/质量、`BodyChunkConnection` 间距跟我们的常量逐条对拍，把结论写进 `docs/PARTS_AUDIT.md`（`--check` 可当测试跑）。当前对拍 8 项全绿；人工核对的不一致清单也在这份文档里（拾荒者仍是单质点身体、禅乌贼第二截没有独立半径、蛞蝓猫的手没有地形推挤）。
- **摇醒睡着的同伴（第 34 轮）**：词表新增第 10 个社交动作「摇醒」（抓着对方左右晃 2~4 下，晃完对方就醒）。社交欲望攒满、而身边这位同伴正在睡时按 `wake_like` 掷骰改成摇醒——溪流（1.0）几乎必摇，黄猫 0.8，普通猫 0.55。
- **猫的性格差异（第 34 轮）**：性格层新增 `hurry / wake_like / apologize / spear_like / pearl_like` 五个轴。黄猫社交欲望拉到满、偏好友好；溪流社交 0.45→0.85、特别爱摇醒、喜欢珍珠；圣徒宽容 0.70→0.95 且**不喜欢用矛**（不肯为开爆米花去捡矛、不爱玩矛、几乎不捡矛）；工匠暴躁执拗**永不认错**；猎手赶时间（被挡时先跳走、回头再指指点点）且**特别容易着急补矛**（背矛搜索半径 ×1.25、没矛时冷却减半）。
- **食性与打猎（第 34 轮）**：吃素的猫（圣徒）不再去打蝙蝠/禅乌贼，捕猎冷却按食性缩放（荤 0.6× / 杂 1.0× / 素 1.4×）——猎手最愿意接着打。
- **溪流喜欢珍珠（第 34 轮）**：`pearl_like > 1` 的猫把珍珠排在果子前面；拿到珍珠又没拾荒者可交易时不再撒手，而是**端在手里把玩**再放下；闲下来也有概率专门去把地上的珍珠叼起来拿着。
- **工匠爆炸会吓人（第 34 轮）**：自爆的冲击先给附近同伴一次 `startle`——睡着的**被炸醒**，醒着的按性格（point_like × temper）回头指指点点，然后才吃那一记眩晕。工匠自己不吃这套。
- **面条蝇（第 35 轮）**：工具栏新增「放面条蝇」，出生年龄随机（第 44 轮起去掉卵，第 45 轮起幼体 / 成体各 50%）。数值照抄原版 `NeedleWorm.cs` / `NeedleWormGraphics.cs` / `SmallNeedleWorm.cs` / `BigNeedleWorm.cs`：幼体 3 躯干 + 4 尾、成体 5 躯干 + 10 尾、吻段 3/5 节，`chunkRad = Lerp(2,5,t)*num`（幼体 ×0.7），空中摩擦 0.999、重力 0.9、弹跳 0.3；个体随机（`wingsSize` / `fatness` / `snoutLength` / `hue = WrappedRandomVariation(0.5,0.08,0.2)` / `lightness` / `hueDiv`）与配色 `HSL2RGB(hue + 0.478, ...)` 逐项照抄，所以每只的面条蝇颜色和胖瘦都不一样。幼体（`SmallNeedleWorm`）5 口可吃、被抓会惨叫并激怒最近的成体；成体有獠牙戳（`Violence(Stab, 0.05, 30)`）与突刺（`Violence(Stab, 1.22, 60)`）两段攻击。伤害抗性也照原版（成体 0.4 / 幼体 0.2）。蛞蝓猫能徒手抓、能叼、能驯服蜥蜴时拿去当礼物（原版 `Eats 0.25/0.3`，比蝉乌贼更可口），蜥蜴会吃、石头能砸、矛能一矛带走、圣徒能超度。
- **白蜥随机体色（第 35 轮）**：白蜥改成"随机生成颜色版本"——每只出生时按 `HSL2RGB(随机色相, 0.45, ClampedRandomVariation(0.86, 0.10, k))` 抽一个**淡彩色**（低饱和 + 高亮度），头部照旧在原版 `HeadColor1/HeadColor2` 之间黑白呼吸（现在是在「黑 ↔ 个体淡彩色」之间呼吸）。
- **蜥蜴头的四个方向（第 35 轮）**：原版 `LizardGraphics.DrawSprites` 里头的贴图行号是 `num14 = 3 - (int)(|headDepthRotation| * 3.9)`，四行分别对应**正侧面 / 斜侧面 / 斜正面 / 正对镜头**，行内再按品种取 `LizardHead{行}.{headGraphics[3]}`（Jaw / LowerTeeth / UpperTeeth / Eyes 同理）。之前这一行恒为 0，所以蜥蜴永远只用最侧面的那张头图，一转身头就"不跟着转"。现在按 `headDepthRotation` 的插值实时选行，上下前后都能取到对应精灵。
- **蜥蜴转身支起上半身（第 35 轮）**：`depthRotation` 平时锁在 ±1（朝左/朝右），转身时从 -1 扫到 +1，中途 |depth|→0（正对镜头），头**顺着这条扫描线从一侧抬起来绕过身体转到另一侧**；转身期间驱动机的落地高度抬高 `turn_lift = TURN_LIFT * (1 - |depth|)`，也就是"支起上半身再转头"，转完自动落回。
- **横杆四态（第 36 轮）**：横杆照原版 `Player.cs` 补齐**停歇 / 悬挂 / 站立 / 跳跃**四种状态。吊在杆下不再定格：`HangFromBeam` 沿杆横向攀行时 `animationFrame` 走 1..20 一圈（原版 7644-7660），停下时往回收到中性帧 10（之前整段攀行是死的、站着也永远只推进 `StandOnBeam` 的第 0 帧）；站杆面走两步会随机停一会儿（`_phase_stand` 的 `_pause`），站够 200 tick 后照原版 `StandOnBeam canJump = 5` **起跳离开**（一半概率向前上跳出、一半直接跳下），不再是直挺挺掉下去。
- **横杆不再自动跑去爬竖杆（第 36 轮）**：换杆改成"经过交点时掷一次骰子"（`CROSS_SWITCH_PROB = 0.25`，一个交点只掷一次，离开交点重新武装），删掉了"站在杆面上主动走向交点换竖杆"的意图——那正是"横杆上的猫总往竖杆顶跑"的根因。走上交叉点时若骰中才换到竖杆。
- **横杆走带夹在窗口内（第 36 轮）**：杆子伸出窗外时，可走带会跟着窗口边界内缩（`_walk_band`）。之前下身 chunk 会被窗口边界夹住、上身还在往前挪，连接约束拉满后起身（`GetUpOnBeam`）会看到下身瞬移。
- **杆上阻塞按性格分流（第 36 轮）**：竖杆和横杆都走同一套（`behavior/blocking.py` 的 `pole_push_role` / `pole_in_the_way`）。**杆头只容一只猫**（两只都在杆顶时按"谁先站上去"定先后）；顶部被底部挤——好性格松手/跳下来，中性先尝试挪到交叉的横杆上、挪不了就停住等待，最坏性格坚持不动、把下面那只挤掉；底部挤上面——好性格松手/下滑，中性停下等待，坏性格一直往上挤。多方"坚持挤"时由窗口统一仲裁（`pole_contest_winner`，同一场冲突两端拿到同一个胜者），**只随机留一只登顶、其余掉下去**；坏性格被挤掉会带着冲量摔出去，落地后回头对挤赢的那只**指指点点**。钉住期间角色是冻结的——横杆上"沿杆方向"靠速度判定，会随平衡摆动来回翻，每 tick 重算会让判定在 0 与非 0 之间抖，谁也分不出胜负。
- **珍珠持有链（第 36 轮）**：溪流找珍珠的搜索半径 170 → 520（隔着大半个窗口也会专程去叼），把玩时长 15 秒 → 4 秒，**放下的那一刻进 900 tick 冷却**。之前"把玩"计时用的是取物器内部计时、结束即 `release`，而外面的珍珠搜索计时刚好也归零，于是放下→原地又叼起来→再放下，猫会**永远卡在取物态**（既不吃饭也不干别的），看起来就像"没有正常拥有珍珠"。
- **面条蝇重做（第 37 轮）**：照 `Infant Noodlefly` / `Adult Noodlefly` 两页 wiki 与反编译把面条蝇整条链路重写。
  - **幼体**（`SmallNeedleWorm.cs`）：`bites = 5`、`FoodPoints = 2`，被啃/被蜥蜴咬都是一口一口（第 5 口才消失）；被抓住或被抓死都会**惨叫**——惨叫链把母亲的 `tempLike`/`like` 直接拉到 **-1**，并让母亲去追**离幼体最近的生物**（不是抓它的人，所以抓着幼体丢给别人可以把仇恨转出去）；惨叫中是每帧 +1/190，超过 0.2 就死；**圣徒抓幼体不会叫**（原版 `grabber is Player && SlugCatClass == Saint` 的特判）；幼体会挂在母亲尾巴第 30px 处（0.95/0.05 分力），母亲被打断时改由自己每 17 帧掷骰找尾节空位；**卵孵出的幼体先跟着蛞蝓猫**，遇到成体再改跟成体。
  - **成体**（`BigNeedleWorm.cs`）：关系用 `tempLike`——每帧朝 `like` 慢慢回升（0.0005/帧），投掷物**掠过 120px 记一次 AttackAttempt**、命中记 Attack，攻击事件按原版五种 ID 扣分（`0.1/0.2/0.4/0.6/0.9`，打到别人身上 / 打死了 / 打的是自己各自再除 2、除 3、除 2），低于 **-0.25** 就从"怕"翻成**敌意**开始追杀；**拿着幼体的猫直接算死敌**；**同族永远敌对（0.9）**，两只成体可以对刺同归于尽；**成体打不到幼体**（`HitThisObject`）。
  - **两段攻击**：戳（0.05 伤害 / 30 帧眩晕，会打掉猫手上的东西）与突刺（1.22 伤害 / 60 帧眩晕，按原版口径 ≥ 蛞蝓猫即死阈值 1 所以必死）；突刺是 6 帧的蓄力挑刺，撞地形时按入射角分流——**顶进去就卡住**（`Stun(60)` + `stuckTime` 0.0125/帧，晕着的时候涨得极慢，合计约 3~4 秒拔不出来），擦着地面滑过只是"瘸" 30 帧。
  - **闪避**：任何朝它飞来的矛/石头都会触发一次侧移（12 的速度加到最近那节上，10 帧冷却），所以远距离很难打中；成体的血只有 0.4，一矛就是一条。
  - **接线**：成体每次刺/戳到猫都由窗口结算（刺死 / 戳晕 + 掉手上东西），卵到了时间就孵，幼体被吃掉改成逐口啃。
- **测试可复现**：debug 模式下首次开窗会 `random.seed(...)`，整套行为链变得可复现（`work/scratch/run_all19.ps1` 现在 40 个脚本、连跑多次 `fails=0`）。

## 素材与版权说明

- 本仓库不包含任何 Rain World 游戏素材。全部游戏图像在你本机、从你自己的正版安装中提取。
- 此项目为粉丝项目，Rain World 及相关名称、美术均归其权利人所有。
- 本仓库代码以 MIT 许可发布（见 [LICENSE](LICENSE)）；该许可仅覆盖本仓库代码，不授予任何游戏素材相关权利。

---

A Windows desktop pet that puts Rain World's slugcats on your screen. The .exe is in the release zip.

The mass-point system in Rain World that controls the connection and movement of the slugcat's various body chunks is written in C#. After decompiling it, I referred to its constants and main functions, which was enough to create a sufficiently similar simulation. However, effects like particle shaders are hard to replicate to match the original game's rendering, and to boost the desktop pet's performance, I made extensive simplifications.

## Requirements

- Windows 10 / 11
- Python 3.10+
- Rain World installed, including the Downpour (More Slugcats) DLC.

## Install and run

```powershell
pip install PySide6 UnityPy numpy Pillow
python run_slugcatpet.py
```

On first launch you pick your Rain World install folder. Sprite atlases are extracted once to `~/.slugcatpet/assets`, kept on your machine and used only by this program.

## How to play

Open the side toolbar to drop things onto your screen: poles, fruit, rocks, a lantern, a slimemold, batflies, lizards, squidcadas, scavengers, pearls and spears.

Nothing has a count limit any more - place as many as you like.

- Click a toolbar icon, then click anywhere on screen to place it; Esc or right-click cancels placement.
- **Lizards** cycle through breeds in placement order (pink / green / blue / yellow / white / red / black / salamander / cyan); body tint, tail tint and back spikes are randomized. The green, pink and white breeds follow their in-game look.
- A placed lizard crawls around on its own. When a slugcat comes close it lunges and bites, stunning the cat for a moment.
- **Squidcadas** hover and fly; get close and they flap away, and once exhausted they land and can be picked up by a slugcat.
- **Taming lizards**: when an untamed lizard is around, the slugcat fetches a landed squidcada and carries it to the lizard's mouth. This is the original mechanic (`FriendTracker.GiftRecieved`): +0.6 like for a live gift, +1.2 for a corpse, and past 0.5 like the lizard bonds and follows the cat instead of biting.
- **Scavengers** patrol with a spear; when a lizard or slugcat comes near they stop, aim, throw the spear and then flee.
- **Pearls** are very bouncy - drop one and it bounces a few times. **Spears** can stick into the ground and be dragged or thrown.
- Hold the mouse on anything to drag it around; release to let go. It works in water and in zero-g too.
- The crossed-out icon at the end of the toolbar clears everything on the field.
- The **top edge of any other window is solid ground** (a one-way platform): the cat, fruit and rocks land on other windows' title bars when they fall from above, but window bodies never block the way (the cat can still walk in front of them). Turn it off with `window_platforms: false`.
- **Walls are not poles**: a wall can be climbed for at most one slugcat height, then the cat grabs the ledge, slides slowly back down, or wall-jumps off.
- **Only the Saint can hang from the screen's top edge**: the Saint's tongue is the only thing that sticks up there; every other cat just stands on the rim or falls off.
- **Pole jumps**: the cat can jump off a vertical or horizontal pole and grab a nearby pole, or snatch a hanging fruit on the way.
- **Stuck spears become poles**: a spear that lands near-vertical in a wall or the ground turns into a pole of the matching length (horizontal into a wall, vertical into the floor). Anyone can climb it, but a lodged spear can no longer be picked up - drag it out with the mouse to recover it.
- **Throwing while on a pole or mid-air**: the cat can throw the spear or rock in its hand from a pole or while airborne (the original `Player.ThrowObject` ignores your stance).
- **Getting blocked**: on flat ground a companion in the way is jumped over first, and only if that fails does the cat point and scold; short-tempered cats scold straight away.
- **Occluded ground**: where a window in front covers another window's top edge, only the visible sliver counts as a floor.
- **Sleeping**: cats take a long time to get sleepy (the urge creeps from 0 up to 100) and then sleep for a long, random while before waking up.
- **Movement numbers match the original**: jump 8/7, hold-to-boost, wall-jump 8/7 + 6/5, run 4.2 and crawl 4 are taken straight from `Player.cs`, giving a standing jump of about 44px and a running jump of about 83px.

**Threat circle, lizard physics and looks aligned with the decompile (round 42)**:

- **The fear circle is one third of the desktop wide** (`THREAT_WIN_FRAC`, floored at 90px): a live lizard inside it always wins the priority check - a sleeping cat is woken at once and cannot fall asleep again while the threat is there. Only brave cats fight back and only kind ones stop to rescue first; a lizard closer than `FEAR_TOO_CLOSE_R` is always fled from.
- **Climb first when threatened**: with a threat in the circle the cat climbs the nearest wall or vertical pole (`FLEE_CLIMB_P`) before falling back to running away.
- **Arm yourself**: an empty-handed cat inside the circle walks over to a nearby spear or rock (`ARM_SEEK_R`/`ARM_COOLDOWN`) before facing the lizard.
- **Crouching really hides you**: a crouching cat's target weight is divided by `CROUCH_TARGET_MULT` (the old multiplier was inverted, so crawling made you more likely to be bitten).
- **Body and tail are the original `BodyChunk` + `BodyChunkConnection`**: three chunks with the radii, connection lengths and elasticity from `Lizard.cs:680-687`; the length constraint only removes radial error, so the chain no longer stretches when dragged and never folds into a vertical bar.
- **Head colour breathes like the original `HeadColor`**, pulsing between `palette.blackColor` (approximated by the dark body colour) and `effectColor`.
- **Leg flip extracted into `_leg_flip_num`** (the original `Custom.DistanceToLine(foot, hip, hip.rotationChunk)` with the front-leg sign flip): all four legs agree when standing and only a leg lifted across the body axis changes sign.
- **A cat holding a gift is never bitten**: with tame food in hand the lizard eats instead of biting (the original `FriendTracker.GiftRecieved`).

**Four slots and revive claims (round 43)**:

- **Four slots**: right hand (primary), left hand (secondary), back (hunter line only, spears only - the original `Player.spearOnBack`) and stomach (unused for now). `SlugcatBody.pick_hand(kind)` is the single place that picks a hand: the right hand when free, otherwise the left, otherwise the lowest-`ITEM_PRIO` item is dropped (the right hand wins ties), and when nothing can be dropped the grab just fails. It is a pure query, and every pickup - fruit, spear, rock, catching a fly mid-air, picking fruit off a pole, grabbing while dragged by the mouse - goes through it instead of choosing a hand by which side the target is on.
- **With a throwable in each hand the right hand's item is thrown first** (`_launch_weapon`); the other stays in the left hand.
- **A hunter with no weapon nearby draws the spear off its back** (`_weapon_ready`, the original `CanRetrieveSpearFromBack`); if no hand can take it the spear goes back on the back instead of being lost.
- **One reviver per corpse**: `_revive_claimed_by` keeps no registry - it just looks for a peer in "Socialize + revive + this target". Being revived, giving up, or the reviver dying all leave Socialize, so the claim lapses and the corpse becomes claimable again.
- **`hurt` on bats and squidcadas now takes `by`/`lethal`** like the noodlefly, matching the shared projectile-hit loop; thrown spears and rocks used to raise a TypeError here.

**Pole behaviour, noodleflies and sleep (round 44)**:

- **A pole (horizontal or vertical) is just ground**: picking fruit, throwing a spear, picking up a spear or rock and bare-hand catching a fly all work on it.
- **Reach is measured from the hands** (`_hand_reach_dist`): the closest of the two body chunks and the two real hand positions. The old test only measured `chunk0`, which sits a dozen pixels above the hands when standing on a beam - so a grabbable fruit was judged out of reach and the cat idled on the beam.
- **Unreachable goals are abandoned**: `HPOLE_GOAL_TIMEOUT` (150 ticks) clears the goal and lets go of the beam; `_hpole_goal_clear` also clears the controller's stop position, otherwise `StandOnBeam`'s 200-tick timeout never fires and the cat stands there until it falls off.
- **Reaching from a pole** (`_pole_reach_pickups`): with a threat around, a spear-willing cat picks up a spear or rock in reach; a hungry cat bare-hand catches a batfly / squidcada / infant noodlefly that flies within reach (grabbing it drops the pole into `CatchFly`).
- **Vertical poles can also "jump up and grab"**: `_pole_jump_grab` was pulled out of `_hpole_goal_jump` and is shared by both pole kinds (the original beam jump grab).
- **Noodleflies no longer roll an egg age**: `AGE_ROLL` has no egg any more (an egg is an object, not a noodlefly); round 45 makes it a flat 50/50 infant / adult.
- **Noodlefly wings redrawn from the original**: they used to be a fixed "pair behind plus pair in front" drawn straight up, which read as a crossed skeleton. Now `WingSprite(num8, m)` with `num8 = ((l == 0) != (zrot.x > 0))` decides which side flips to the upper layer (layer 0 below, layer 1 above, legs topmost), and the direction applies `Update`'s `vector6` push (segment tangent +/-45 degrees forced upwards, blended by `|vector.y|`), so the wings sweep back the way they do in game. Infants keep the original `isVisible`: no wings once bitten down to `bites <= 4`.
- **An enraged adult noodlefly counts as a threat**: `_hostile_fly` follows the original `BigNeedleWormAI` `hostile_to` (holding its infant / `tempLike < -0.25`); `_threat_lizard`, `_nearby_lizard` and the on-pole throw target `_nearest_throw_target` all pick it up - so cats flee it, arm themselves and throw spears at it. The hunt / spear-kill list already covered bats, squidcadas and both noodlefly ages.
- **Sleep settles the moment the cat falls asleep**: entering `Sleep` immediately spends the hibernation food (`food_hibernate` pips) and gives +1 karma; waking only restores energy, with no double settlement.

**Noodlefly body colour matched to the original palette (round 45)**:

- **50/50 infant / adult**: `AGE_ROLL` is a flat `((small, 0.5), (big, 0.5))`.
- **Colour matched band by band to the wiki palette charts** ([Adult](https://rainworld.miraheze.org/wiki/Adult_Noodlefly) / [Infant](https://rainworld.miraheze.org/wiki/Infant_Noodlefly); the charts state that every colour's **area is proportional to how likely it is**):
  - Body (adult `lightness = 0.4`, probability 16/17·2/3): `#440718`, sweeping with `hue = WrappedRandomVariation(0.5, 0.08, 0.2)` from purple `#44071B` to red `#440713`.
  - Dark band (1/3): `lightness = 0.4·rand^5`, running all the way down to plain `palette.blackColor`, i.e. the black band at the top of the wiki chart (`#1B0A20`).
  - Light band (1/17): `lightness = 1 − 0.6·rand^5`, the pink-white strip along the bottom.
- **The grey / white / black band is the fix that mattered**: the original `Custom.HSL2RGB` only writes `case 0..5`, so when `(int)(h*6)` lands on 6 or more no branch matches and it returns the flat `r = g = b = l` **grey**. A noodlefly's `num = hue + 0.478` exceeds 1 for **15.3%** of individuals, so in game those really are grey. We had been taking `h % 1.0` (wrong), which painted all 15% as saturated red. Now, as in the original: a grey adult comes out `#29222C`, **pixel-identical** to the grey column on the right of the wiki chart (column width 15% vs 15.3% of individuals).
- Recheck script `work/scratch/pal_audit.py`: samples 40k individuals through the same individual-randomisation and draws a wiki-style chart (row height proportional to lightness probability, column width to hue probability) into `outputs/noodlefly_palette_vs_wiki.png` (wiki left, ours right). Spot checks: body `#440719` vs wiki `#440718`, grey column `#29222C` vs `#29222C`, top black `#1B091F` vs `#1B0A20`.

**Noodlefly legs / needle / wings fixed against the original (round 46)** (checked against the [Noodlefly_kiss.gif](https://static.wikitide.net/rainworldwiki/3/3b/Noodlefly_kiss.gif) you gave and the decompiled `NeedleWormGraphics.cs`):

- **The legs (the original calls them legs — they are the "whiskers" you meant) were attached to the snout; they are back on the torso now**: the original `LegConPos` sits on `OnBodyPos(0.03 / 0.066 / 0.1)`, and `OnBodyPos` multiplies by `TotalSegments`, which **excludes the snout** (a 15-segment torso, `NeedleWorm.cs:70,983`). All three pairs therefore live in the first 1-1.4 torso segments, right behind the head. We missed the `+snout_n` conversion when mapping onto our own `seg` array, so they ended up at the very tip of the snout — a tuft of whiskers on the face.
- **Leg shape fixed as well**: the original is a 4-vertex flipper — root on the body side, tip held by `ConnectToPoint(…, 11/16·legsFac)` and pulled outward/down by gravity (`vel.y -= 0.9`) plus `LegConDir * 0.55`, i.e. a **short stub hanging out and down** (11-16·`legsFac` long, ~4.4·`legsFac` wide at the midpoint) with a `detailsColor` tip. Ours was a 2.6-wide sliver, which is why it read as whiskers.
- **The needle started one segment ahead; it now starts at the mouth**: the original `FangMesh` puts its first ring of vertices on `vector5` (the mouth root). Our loop advanced first and only then recorded a point, shifting the whole needle forward by `fangLength / 3.5` (≈14 px) so it looked detached from the head. The root goes in first now, then the five segments follow (5 segments, 6 nodes).
- **Needle layer**: per `InitiateSprites`, `FangMesh = 5 < BodyMesh = 6` — the needle is drawn **under the body**, the way a needle coming out of the mouth should be. We had it after the body, floating over the face.
- **Needle half-width**: the original `num14 = Lerp(0.6 + 0.6·fangBlack, 0.5, num13)` *is* the half-width (1.2 at the root, 0.5 at the tip); we multiplied by an extra 0.5 and halved the thickness.
- **Needle wobble now includes `zRot.x`**: that term ends in `* vector2.x` in `DrawSprites`; without it the needle never sways with facing (at `fangOut = 1`, `Sin(num10·π) = 0`, so the original is straight there too).
- **Wing width taken from the original `CentipedeWing` texture**: the wing is a `CustomFSprite("CentipedeWing")` — an 8x52 white leaf texture mapped onto a quad with half-width `2*wingsSize` at both root and tip (`NeedleWormGraphics.cs:565`). CustomFSprite's uv order is 0=top-left 1=top-right 2=bottom-right 3=bottom-left while the wing's vertices 0/1 are at the tip and 2/3 at the root, so **the texture's top edge is the wing tip**. Its rows are 2,4,6,6,8x20,6x8,4x9,2x11 pixels wide, which as root-to-tip half-width ratios is **0.25 / 0.5 / 0.75 / 1.0 / 0.75 / 0.25** (widest in the outer half, like a cicada wing). Ours was a fixed 2.4-to-1.2 taper, wrong at both ends.
- Verification: `work/scratch/e2e_r46.py` (24 checks; a `ribbon` probe measures every polyline's endpoints, half-widths and draw order) and `outputs/noodlefly_parts_r46.png` (wiki kiss gif on the left, ours on the right: adult closed / adult fang-out / infant).

**Noodlefly torso radii + Saint cracking popcorn + pole throw + Saint meat stagger (round 47)**:

- **Noodlefly torso radii recomputed from `GraphSegmentRad`** (`NeedleWormGraphics.cs:709-720`): the snout is no longer a constant 1.0 but `1 + pow(InverseLerp(0, 0.5, fangOut), 0.6) * 1.5` (the whole snout thickens when the fangs come out; 1.0 closed); the tail no longer tapers linearly to 0.9 but follows the `LerpMap(i - snout - ...)` curve with `(1.4 - 1.35*thinTail) * Lerp(1.8, 0.2, fatness)` (0.707 at the tip with `thinTail = 1`, thinner than before); everything is then scaled by `num3` - an adult torso stretched from 50 to 80px scales 1 -> 0.85 (infants stay at 1.0). Render radii only; the physics radii are untouched.
- **The Saint will pick up a spear to crack a cob**: `SeedCob.HitByWeapon` only accepts a `Spear`, so opening a cob needs one - but the Saint's `_spear_willing()` is False (it never hunts with spears). "Willing because it is food" now goes through its own `_cob_spear_willing()` (vegetarian / special diets included), so it stays a pacifist and still opens the cob.
- **The throwing spot no longer parks in a dead band**: the cob's two chunks are diagonal, so `_cob_would_hit`'s dry run alternates between hit and no-hit bands at the same height. The old "stop once within 60px of the ideal spot" rule could park the cat inside a no-hit band, where it stood still until its budget ran out and then gave up - the "the Saint cannot crack the popcorn" report. Now: (1) it first checks whether the throw **hits from where it stands** and throws immediately if so; (2) otherwise it walks all the way to the stand point (4px arrival tolerance) and throws from there.
- **A light toss needs `firstFrameTraceFromPos` too**: the Saint throws spears through `Player.TossObject` (not `Weapon.Thrown`), which never recorded `firstFrameTraceFromPos`, so the real first frame's swept segment was shorter than the dry run predicted - the dry run said hit, the real spear went straight through the cob. The toss now sets `_f1` as well (the first frame sweeps from the pre-throw position), so prediction and reality agree exactly.
- **Throw direction aims at the cob itself**: the old code used the stand point for left/right, and when the cat stood right under the cob that point fell on the cat's own side, so the spear flew the wrong way. It now aims at the midpoint between the two chunks.
- **Climb a pole to the prey's height before throwing**: when the target is more than 40px above and the cat is on the floor with a vertical pole available, it picks the cheapest pole whose top clears the target, climbs until `|its height - prey height| <= THROW_JUMP_DY` and then throws horizontally - once. With no pole it keeps the old jump-and-throw behaviour.
- **The Saint is staggered by meat**: matching `Player.SaintStagger` (`Stun(time / 5)` with the meat `staggerTime` values of 220-800), a vegetarian / special diet (the Saint) eating something with `is_meat` gets `Stun(44)`, goes through the Stunned state and drops what it is holding; fruit does not stagger it, and an omnivore (the Survivor) is never staggered by meat.
- Verification: `work/scratch/e2e_r47.py` (23 checks: all 20 torso/snout/tail radii against an independent recomputation, both sides of a low cob opened, same-height pole throw, meat stagger).

**Noodlefly aggression / squidcada / lizard AI / slugcat aggression / corpses and the eraser (round 48)**:

- **Adult noodleflies actually hunt the slugcat now**: the static relationship is `BigNeedleWorm -> Slugcat = Eats 0.25`, but `AI.cs UncomfortableToAfraidRelationshipModifier` rewrites `Attacks` into `Afraid` inside `Lerp(150, 450, nervous)`. Only the "holds an infant -> Attacks 1.0" branch (`BigNeedleWormAI.cs:333-413`) used to be implemented, so adults almost never attacked. The afraid range is now interpolated from the per-creature `nervous` personality: beyond it the cat is prey and gets chased, inside it the worm turns and flees; corpses are neither hunted nor feared.
- **Noodlefly accuracy** (`BigNeedleWormAI.cs:325-349`): the attack-from point is no longer re-rolled only when off by more than 60px - every tick drops a candidate point within 300px of the current point or the target and keeps it if `AttackPosScore` is lower; the lead multiplies the target's velocity estimate by `LerpMap(dist to attack point, 80, 400, 0, 30, 0.35)` (the estimate itself decays 1% per tick, :154); the body-axis term now goes from the torso midpoint to the head (:520 - the old source made the charge condition almost never true); the "hugging the attack point" threshold went 60 -> 40 (:533).
- **Squidcada rewritten end to end** (`Cicada.cs` / `CicadaAI.cs` / `CicadaGraphics.cs`): stamina regenerates at 1/70 per tick (it used to be nearly unable to fly); the charge is 21 frames of wind-up, then a straight 21..38 dash (`CHARGE_THRUST = 4`/tick), then a recovery that zeroes the counter; the four tentacle nodes have half-widths `(1.6, 1.2, 0.9, 0.8)` and the root follows `lookDir` per `CicadaGraphics.cs:553-555` (`+lookDir*6` combined with `2*|p.x|*(1-|lookDir|)`, so the net shift is 4px); wings are collapsed from `|p.x|` alpha into fully drawn or not drawn, with no half-transparent fringing; **being eaten** now ticks `eaten` down and only vanishes at zero - the original repo's gradual "food shrinks as it is eaten" look, ported to the squidcada.
- **Lizard AI reordered to `LizardAI.DetermineBehavior`**: Flee > carry a corpse > Injured > Anger/Fight > casual bite > Hunt > InvestigateSound > Pack > wander.
  - Breed relationship tables copied line by line from `StaticWorld.cs:3691-3726` (green->blue `Eats 0.25`, blue->green `Afraid 0.25`, red->red `Attacks 1.0`, yellow->yellow `Pack 0.2`, ...) and the base table from `StaticWorld.cs:3668-3689` (-> scavenger `Eats 0.8`, -> squidcada `Eats 0.05`, -> adult noodlefly `Eats 0.25`).
  - Vision cones use `LizardBreeds.cs`'s `perfectVisionAngle / periferalVisionAngle = Lerp(1, -1, t)`, keeping 40% of the sight range outside the cone.
  - The `AgressionTracker` (`angerSpeedUp/Down = 0.001`, `Utility = InverseLerp(0.35, 1, anger)`) flips to Fighting above 0.35 and the lizards really bite chunks out of each other (`_lizard_bite` now accepts scavengers too); a wounded lizard flees to a corner (`LizardInjuryTracker`); `LurkTracker` keeps whites and salamanders lurking 4x longer; terrain impacts within 320px are investigated (throwing something at the ground pulls lizards away); yellow lizards travel in packs.
- **Slugcat aggression**: `FIGHT_UNARMED_R = 150` / `FIGHT_UNARMED_BRAVE = 0.70` (the radius and the bravery threshold for charging in bare-handed); hostile **scavengers** (no trade history, low `like`) join the throw-target list, while scavengers you traded a pearl with do not. The Saint still refuses to use spears for hunting.
- **Corpses**: dragging a non-slugcat corpse (scavengers included) off the window removes it on the spot; living creatures are never mis-culled.
- **Erase mode**: a new eraser button in the toolbar - click anything to delete just that one object. Thirteen pools (fruit, stones, slime mould, batflies, lizards, squidcadas, noodleflies, pearls, spears, scavengers, seed cobs, seeds, poles) are erasable and slugcats are never touched by it; Esc / right click leaves the mode.
- Verification: `work/scratch/e2e_r48.py` (29 checks: noodlefly near/far relationship and firing, squidcada charge phases / thrust / stamina / tentacle offset / being eaten, the lizard relationship table, vision cone, injury, noise and same-species bites, throw targets and friendly scavengers, corpse-out-of-screen culling, and erase mode including the real mouse event).

**Blocking and covering / carried items / edge wedging / phantom windows / small-creature hits / neighbour-pole hops (round 49)**:

- **Check the line before throwing**: `_launch_weapon` runs `_throw_line_blocked` over the self -> target segment (14px thick, up to 320px) and drops the throw if any companion body segment is on it - the original avoids hitting packmates when throwing (`ScavengerAI` throw checks plus `Weapon.Thrown` collisions). Otherwise a spear ends up in a friend's back. Popcorn and fruit throws are unaffected.
- **Hide behind whoever is carrying a spear**: new `CoverAlly` state. With a threat around and nothing in hand, a cat picks an **armed** companion (`_armed_peer`, ranked by distance and personality) and trails `COVER_BACK_OFF=26px` behind them, never crowding closer than `COVER_MIN_GAP=70px`. The moment it picks up a spear or a rock it leaves cover to fight; if the threat closes inside `FEAR_TOO_CLOSE_R` it simply runs. No armed companion, or `T_COVER_RETRY` ticks without success, and it falls back to the old fear logic.
- **Blocked with a threat around: always jump first**: the "scold before jumping" branch in `_scan_blocking` now only applies when nothing scary is on screen; with a threat present every personality jumps over the blocking companion first (`_threat_present()`), instead of scolding at a packmate while standing in front of a lizard.
- **Left-hand carry while pole climbing no longer clips**: a climbing hand is gripping the pole, so the item has to follow the hand. Added `SlugcatBody.hand_pos` (written back every frame by `graphics._update_hands`) and `_carry_anchor(side)`: when `bodyMode == "ClimbingOnBeam"` the carry anchor is the hand position and `arm_aim` is **not** written (in the original `SlugcatHand` hands the arm over to the pole while climbing and never reaches `HuntRelativePosition`). Per `Player.cs:5984-5990` (items follow the hand) and `SlugcatHand.cs:41-74 / 190-256`.
- **No more wedging against the left/right screen edges**: wall sliding was written as `vy = climb - g` and then had gravity subtracted again each frame, leaving a net 0.14px/tick (about 20 seconds to slide down a wall, which reads as "stuck on the edge"); it is now `vy = WALL_LEDGE_SLIDE + g`, i.e. the proper slide speed in one frame. Wall climbing also gained `WALL_APPROACH_TIMEOUT`: if the ledge is out of reach and the climb is not progressing, a distance-scaled grace period ends with the cat letting go and landing instead of replaying the climb forever.
- **Phantom windows**: enumerating other windows as platforms only excluded our own via the `own` set, but our QToolTip / tray tooltip / internal hidden Qt windows have no usable winId, so they were treated as an invisible floor. `_visit` now skips **every** window of this process via `GetWindowThreadProcessId` and also skips click-through windows with `WS_EX_TRANSPARENT`.
- **Spears no longer pass through noodleflies**: hits used to be tested only at the tip's **current** point, while a noodlefly travels ~40px/tick, so a spear almost always passed straight through. New `_small_hit`: bodies with a segment chain (noodleflies) are swept segment by segment, and round small creatures (batflies / squidcadas) use a circle test against the previous -> current tick segment, so one spear connects.
- **Pole-top hops to a neighbour pole now use a small arc** (old bug fixed along the way): "jump across and grab the other pole" used the full-strength `pole_jump` (~6px/tick horizontal, a single arc spanning 300+px), so a same-height pole 40px away was **flown over** and the cat landed far away on the ground - the `POLE_HOP_VX/VY` tuning values were never used. `SlugcatBody.pole_hop` now uses the small impulse (4.0 / 4.2) and the planning arc comes from the matching `jump_arc.get_pole_hop_arc`, so a 40px hop lands on the first try (`work/scratch/e2e_pole.py` section 5 went from "wanders into it" to an actual hop).
- Verification: `work/scratch/e2e_r49.py` (19 checks: no throw through a companion, cover positioning and leaving cover once armed, jump-first with a threat, left-hand carry hand position, wall-slide speed, wall approach timeout, own-process and transparent windows excluded, swept small-creature hits, pole-top hop hits).

**Social actions** (the sixth desire, "social", sends a cat over to a companion once it fills up; the vocabulary lives in `slugcatpet/behavior/social.py`):

| Action | Gesture | Meaning |
| --- | --- | --- |
| Point | reach out and hold a hand at the target | pointing / wanting / look here |
| Point-point | extend and retract the hand 1-5 times quickly | scolding / emphasis |
| Pet | draw a back-and-forth horizontal line on the target 2-5 times | liking / soothing |
| Pat | draw a back-and-forth vertical line on the target 2-5 times | liking / soothing |
| Revive | press down hard on the target 4-8 times, body pushing down too | reviving; the target comes back when the presses end |
| Crouch | lie flat | making way / sorry / afraid |
| Crouched point-point | point and scold while crouched | hatred / about to attack / hunt this / help me hit this |
| Crouched point | point while crouched | afraid of this / be careful of this |
| Crouch-walk | sneak away while crouched | afraid of a strong foe, sneaking |

Personality decides which ones come up: a low `crawl_like` (won't lie down) rules out the crouch family, a low `point_like` (good-natured) means less scolding, a high `sociability` favours petting and patting, and a cat you have a grudge against gets weighted crouched scolding.

The same vocabulary also drives **everyday** gestures (when the social urge has not filled up). Every place that reaches out now goes through one begin / tick / end interface instead of its own ad-hoc code:

| Situation | Action picked |
| --- | --- |
| Idling with a companion nearby, or the cursor hovering nearby long enough | a personality-weighted pick (point / point-point / pet / pat / crouch family), ends by itself |
| Blocked on the ground by another cat (can't jump over) | point-point; a hot-tempered crouchy cat uses crouched point-point instead |
| Blocked by a companion on a pole | nudge a few times mid-pole, then maybe point-point in the tail |
| Fruit stolen | walk over and point-point at the thief (`protest` is a legacy alias of `scold`) |
| Chasing the cursor / waking up | point at the cursor; a bad-tempered cat point-points it instead |
| Fighting a lizard bare-handed | get close and point-point while nudging |
| Being point-pointed at | a bad-tempered cat points back, others may turn and crouch |
| After making way for a shover | small chance to do a gesture back at them |
| Struggling while held by the mouse | reach out and paw at the cursor |
| Reviving a companion | 4-8 presses (`PressGesture`); the target comes back when done |
- With a spear or rock in hand (or lying within reach) a slugcat will pick a fight with a lizard: grab the weapon, keep its distance and throw a lead shot. It can also finish a meal while hanging on a pole.
- Dragging a **popcorn plant** only pulls the cob around (the plant stays rooted and springs back), and the cob is elastic and collides with the ground and window tops.
- **Shake the cat violently** left and right while it holds something and it drops it (rocks first, then fruit, then spears) - the dropped item flies off with the swing's velocity.
- **While the mouse is holding the cat**: it reaches out for poles and loose items by itself - let go and it keeps its grip, climbing a vertical pole or hanging off a horizontal one (including spears lodged into a beam pole); food in its hand is not let go even if you drag the cat away.
- **Being pointed at**: the cursor only has to *stay near* the cat for a while to draw a point or a scolding - it does **not** have to be held perfectly still; move it away and the timer restarts.
- When **every cat is dead** they reincarnate together: after a short wake (a companion can still nuzzle one back during it) their bodies rise as white motes and they are all reborn at the top centre of the screen.
- **Stamina economy**: standing still counts as catching your breath (it trickles back, and pacing around does not count as resting), but **every other action costs stamina** - climbing poles and walls most, fetching fruit and dodging next, anything else a small flat amount. Every stamina bar spent costs one pip of satiety, and **refilling a bar costs one too**, so stamina recovery is paid for with food. With no satiety and no stamina the cat puts itself to sleep (it wakes with a full bar but **loses one karma**); sleeping with food in its belly raises karma as usual.
- **Throwing a spear at a popcorn plant**: hit detection is now a per-frame swept segment against the cob's chunks (matching `Weapon.cs`, radius +5 for player throws), so a fast spear no longer tunnels through it; the spear that opens the cob **sticks into it** and sways along with it, and can be picked back out (spears stuck in creatures still cannot).
- **Liveliness**: shorter idle dwell, lower idle weight, faster interest recovery for poles/walls/cursor/small gestures and a lower play stamina gate - the cat is generally busier.
- **The hunter's spare spear on its back** is drawn behind the cat instead of on top of it.
- **The status panel background** is fixed (a plain QWidget needs `WA_StyledBackground` to paint its QSS background; it used to be see-through).
- **Jump height verified**: one logical unit is one original-game pixel (body = 17), and the measured standing jump peak is 43.7, matching an independent replay of the `Player.cs` constants (44.0) - 1.18x the drawn cat height, the same look as the game, so no pixel-ratio rescaling is needed.
- **Missing the popcorn plant fixed (round 28)**: first, the same-frame wall stick - when a spear hit the window's side wall on the very frame it flew past the cob, it was snapped back to its stuck pose and that flight segment was lost to hit detection; the swept segment now uses **the position it actually flew to before the collision** (`_seg_end`, matching `Weapon.Update`, which checks hits before `StuckInWall`). Second, ballistic preview - before throwing, the cat replays the exact `Spear.step` trajectory and only throws when the preview says it connects. Third, **climbing the stalk** - when the cob hangs above the throw line and is out of jumping reach, the cat climbs the popcorn plant and spears it level with the cob (that stalk pole is virtual: never drawn, never blocks, and it is **not allowed to hand off to other poles at crossings**). Measured: 40/40 cob seeds and 17/17 placements open, with the spear stuck in the cob every time.
- **Faster stamina (round 28)**: drain is now about 1.5x the previous values (vigorous 1/330, light 1/1000, pacing 1/1600, fallback 1/2000) while standing still recovers more slowly (1/2200), so the difference between acting and resting is far more visible. The "no food and no stamina" sleep gate also dropped from 0.35 to 0.15 - the cat only sleeps off a karma level when it genuinely has **no satiety and almost no stamina**, instead of lying down all the time.
- **Status panel background (fixed again in round 28)**: the previous round only fixed the panel itself; the scroll viewport holding the rows still painted the palette's default light grey, showing up as a grey band. Viewport and row host are transparent now, so the whole panel is one dark colour.
- **Reproducible tests**: in debug mode the first window seeds the global `random`, making the whole behaviour chain reproducible (`work/scratch/run_all19.ps1` now runs 40 scripts and reports `fails=0` repeatedly).

## Origin

This project is forked from [lingxiaojun/slugcatpet](https://github.com/lingxiaojun/slugcatpet) (upstream: https://github.com/lingxiaojun/slugcatpet). On top of it, the face-expression bug was fixed and placeable lizards, squidcadas, scavengers, pearls and spears were added.

## Assets and copyright

- This repository contains no Rain World assets. All game images are extracted on your machine from your own copy.
- This is a fan project. Rain World and all related names and artwork belong to their respective owners.
- The code is released under the MIT license (see [LICENSE](LICENSE)). It covers this repository's code only and grants no rights to any game assets.
