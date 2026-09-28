Windows 桌面宠物：让 Rain World 的蛞蝓猫住在你的屏幕上。exe 见 release 压缩包。

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

展开侧边工具栏可以把东西放到屏幕上：藤蔓、水果、石子、灯笼、黏菌、蝠蝇，以及蜥蜴。

- 点工具栏里的**蜥蜴**图标，鼠标变十字后，在屏幕上点一下即可放下一只蜥蜴（场上最多同时 2 只）。
- 蜥蜴品种按放置顺序轮换（粉 / 绿 / 蓝 / 黄 / 白 / 红 / 黑 / 蝾螈 / 青），个体颜色与尾色随机。
- 放下的蜥蜴会自己爬行。蛞蝓猫靠近时会扑上去咬一口，被咬到的猫会眩晕一小会儿。
- 用鼠标按住蜥蜴可以拖着它走，松手就放开；丢进水里、半空中都可以。
- 按 Esc 或右键取消放置。工具栏最右的禁止图标一键清空场上所有物件（含蜥蜴）。

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

Open the side toolbar to drop things onto your screen: poles, fruit, rocks, a lantern, a slimemold, batflies, and lizards.

- Click the **lizard** icon, then click anywhere on screen to place one (up to 2 at a time).
- Breeds cycle in placement order (pink / green / blue / yellow / white / red / black / salamander / cyan); each individual's body and tail tint are randomized.
- A placed lizard crawls around on its own. When a slugcat comes close it lunges and bites, stunning the cat for a moment.
- Hold the mouse on a lizard to drag it around; release to let go. It works in water and in zero-g too.
- Esc or right-click cancels placement. The crossed-out icon at the end of the toolbar clears everything on the field, lizards included.

## Assets and copyright

- This repository contains no Rain World assets. All game images are extracted on your machine from your own copy.
- This is a fan project. Rain World and all related names and artwork belong to their respective owners.
- The code is released under the MIT license (see [LICENSE](LICENSE)). It covers this repository's code only and grants no rights to any game assets.
