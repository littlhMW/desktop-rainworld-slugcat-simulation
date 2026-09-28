# 反编译部件表工具（parts_table.py）

## 它解决什么问题

移植原版生物/物件时最容易搞错的三件事：**图层顺序**、**部件尺寸**、**部件位置**。
这三样在原版里其实都是「机械可查」的，不需要凭截图猜：

| 想知道 | 原版里的出处 |
| --- | --- |
| 图层顺序 | `InitiateSprites` 里 `sLeaser.sprites[下标] = ...` 的**下标顺序** = `FContainer` 子节点顺序 = 绘制顺序（后画盖前画） |
| 部件尺寸 | atlas 元件原始像素（`assets/rainWorld` 里 `frame.w/h`）× `DrawSprites` 里赋的 `scale/scaleX/scaleY` |
| 部件位置 | `DrawSprites` 里赋的 `x/y`、`anchorX/anchorY`、`rotation`（y 轴向下，与桌宠一致，**符号不要改**） |

`parts_table.py` 就是把上面三列自动抓出来的工具。

## 用法

```powershell
# 反编译源码目录（默认 ..\..\scratch\decomp_full，可用环境变量覆盖）
$env:RW_DECOMP = "C:\path\to\decomp_full"
# 图集目录（默认 ~\.slugcatpet\assets）
$env:SLUGCATPET_ASSETS = "C:\Users\你\.slugcatpet\assets"

D:\spenv\Scripts\python.exe -X utf8 parts_table.py CicadaGraphics
D:\spenv\Scripts\python.exe -X utf8 parts_table.py CicadaGraphics SeedCob LizardGraphics
```

输出示例（CicadaGraphics）：

```
   idx  下标写法                   元件                         atlas WxH   变换
   (0)  BodySprite             "Cicada" + num3 + "body"   0:19x33 1:23x29 ... 8:19x29
            · sLeaser.sprites[BodySprite].scale = iVars.fatness;
     i  i                      ?                          -           <- 循环下标（第 i 个精灵）
   (1)  HighlightSprite        Circle20                   20x20
            · ...x = ...bodyChunks[1]... - 2f
            · ...y = ...bodyChunks[1]... + 3f
            · ...rotation = num + 12f
```

## 读取结果的约定

1. **idx 列**：`(0)` `(6)` 这种是常量下标；`i` / `num3` / `SpriteHeadEnd - 1` 是运行时算出来的
   下标（循环变量、`SpriteXxxStart + n` 之类），需要人眼代入；`Sprite*` 助手会被自动展开成常量。
2. **元件列**：`"Cicada" + num3 + "body"` 表示运行时按朝向挑 `Cicada0body`…`Cicada8body`，
   后面会自动列出每个候选帧的真实尺寸。
3. **Debug 精灵**：名字带 `Debug` 的（`DebugHead`、`DebugBodyChunks*`）在 Release 里不画，已过滤。
4. **Mesh 类精灵**（`TriangleMesh.MakeLongMesh(n, ...)`）没有 atlas 尺寸：它的形状由
   `MoveVertice(...)` 的顶点坐标决定，尺寸要读那段代码（例如禅乌贼触须的半宽是
   `1.6T / 1.0T / 0.8T`，来自 `CicadaGraphics.cs:570-600`）。

## 已知限制

* 循环体里用 `sprites[i]` / `sprites[SpriteLimbsStart + n]` 批量赋值的（`LizardGraphics`
  的身体圆/四肢、`PlayerGraphics` 的尾巴等），工具只能给出行，**需要人工代入循环变量**，
  再按 `SpriteXxxStart/End` 助手展开后的数值排序。
* 只解析 `*Graphics.cs` + 少数 `*.cs`（物件本体如 `SeedCob.cs`）。
* 不带语法分析：极端写法（本地方法、`switch` 里赋 element）可能漏。

## 已核对结论（2026-09-28）

* **SeedCob.cs**：`SeedSprite(seed, part) = 3 + seed + part * N` —— 种子是按**层**排的
  （0..N-1 主豆粒、N..2N-1 高光、2N..3N-1 红点），不是逐颗 `主/高光/点` 相邻；
  外壳 `ShellSprite = 3 + 3N + side` 在**所有种子之上**，叶片最上。爆米花的渲染顺序必须
  跟着这个来（`world/seedcob.py:draw_seedcob`：茎 → 豆荚 → 种子 → 外壳 → 叶片）。
* **CicadaGraphics.cs**：14 个精灵 =
  `0 身体 / 1 高光 / 2-5 触须 / 6 头 / 7 盾 / 8-9 眼 / 10-13 翅`；身体缩放 = `iVars.fatness`、
  高光 = `Lerp(5,3)/20 × Lerp(12,8)/20`（Circle20 是 20×20）、翅 = `×iVars.wingLength`。
  高光钉在 `chunk1 + (-2, +3)`、`rotation = num + 12`；翅的**位置偏移**用 `(k==0?1:-1)`，
  而 **rotation/scaleX** 用 `(k==0?-1:1)`（两处符号不同，容易写错）。
