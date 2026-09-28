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

展开侧边工具栏可以把东西放到屏幕上：藤蔓、水果、石子、灯笼、黏菌、蝠蝇、蜥蜴、蝉乌贼、拾荒者、珍珠、矛。

所有物件都没有数量上限，想放多少放多少。

- 点工具栏里的图标，鼠标变十字后，在屏幕上点一下即可放下该物件；按 Esc 或右键取消放置。
- **蜥蜴**品种按放置顺序轮换（粉 / 绿 / 蓝 / 黄 / 白 / 红 / 黑 / 蝾螈 / 青），个体颜色、尾色与背刺随机；绿 / 粉 / 白三个品种按原版外观还原。
- 放下的蜥蜴会自己爬行。蛞蝓猫靠近时会扑上去咬一口，被咬到的猫会眩晕一小会儿。
- **蝉乌贼**悬停飞行，被靠近就扑翅逃跑；力竭落地后可以被蛞蝓猫叼起来。
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
| 杆上被同伴挡住 | 先停在中间扒拉几下，后半段有概率改成指指点点 |
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
- **测试可复现**：debug 模式下首次开窗会 `random.seed(...)`，整套行为链变得可复现（`work/scratch/run_all19.ps1` 现在 25 个脚本、连跑多次 `fails=0`）。

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
- **Reproducible tests**: in debug mode the first window seeds the global `random`, making the whole behaviour chain reproducible (`work/scratch/run_all19.ps1` now runs 25 scripts and reports `fails=0` repeatedly).

## Origin

This project is forked from [lingxiaojun/slugcatpet](https://github.com/lingxiaojun/slugcatpet) (upstream: https://github.com/lingxiaojun/slugcatpet). On top of it, the face-expression bug was fixed and placeable lizards, squidcadas, scavengers, pearls and spears were added.

## Assets and copyright

- This repository contains no Rain World assets. All game images are extracted on your machine from your own copy.
- This is a fan project. Rain World and all related names and artwork belong to their respective owners.
- The code is released under the MIT license (see [LICENSE](LICENSE)). It covers this repository's code only and grants no rights to any game assets.
