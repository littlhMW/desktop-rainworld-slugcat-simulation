# 桌面雨世界-蛞蝓猫模拟

![桌面雨世界-蛞蝓猫模拟](slugcatpet/resources/icons/app_icon.png)  ![gobgjiang](docs/showcase/gobgjiang.png)  ![shengtu](docs/showcase/shengtu.png)  ![xiliu](docs/showcase/xiliu.png) 
 ![hongmao](docs/showcase/hongmao.png)  ![huangmao](docs/showcase/huangmao.png)  ![taotie](docs/showcase/taotie.png)  ![maodashi](docs/showcase/maodashi.png) 

面向蛞蝓猫桌宠的 Rain World 生态模拟器。项目重点是蛞蝓猫的日常行为、AI、寻路、物理与互动，同时提供一个可运行的雨世界生态沙盒。

## 项目内容

- **蛞蝓猫桌宠**：不同角色的 AI、社交、寻路、步态、物理和物件互动。
- **雨世界生态**：蜥蜴、禅乌贼、面条蝇、猫崽、植物和食物等生物与物件。
- **环境与场景**：雨循环、庇护所、杆、墙和可保存的场景状态。

## 运行要求

- Windows 10 / 11
- Python 3.10+
- Rain World
- Downpour / More Slugcats DLC

源码运行需要本机安装 Rain World。首次启动时选择 Rain World 安装目录，程序从本机读取所需素材。

## 安装与运行

```powershell
pip install -e .
desktop-rainworld-slugcat-simulation
```

也可以构建 Windows 可执行文件 `RainWorldSlugcatSimulation.exe`：

```powershell
.\build_exe.ps1
```

构建结果以脚本实际输出为准。

## 基本操作

- 工具栏选择对象后，在窗口中点击放置。
- `Esc` / 右键取消当前操作。
- 拖动物件进行移动、携带或投掷。
- 使用橡皮工具删除对象，使用清空功能清除场景对象。
- 庇护所通过拖拽区域创建，尺寸由拖拽范围决定。
- 自带雨循环计时器，可在环境面板中手动开启或关闭。

## 角色

当前包含：

- 僧侣（Monk）
- 求生者（Survivor）
- 溪流（Rivulet）
- 守望者（Watcher）
- 饕餮（Gourmand）
- 猎手（Hunter）
- 工匠（Artificer）
- 矛大师（Spearmaster）
- 圣徒（Saint）
- 蛞蝓猫幼崽（Slugpup）
- 怪猫（Inv）

## 来源、致谢与独立维护

本项目现为独立维护的衍生作品。早期版本参考并基于
[lingxiaojun/slugcatpet](https://github.com/lingxiaojun/slugcatpet)，感谢其公开代码与创意；
后续生物生态、AI、寻路、物理、渲染、环境和工具链由本项目大规模重写与新增；仓库仍保留部分早期代码及其许可声明。

当前维护者：littlhMW。历史作者与上游归属保留在 Git 历史、[NOTICE](NOTICE) 和许可证中。

Rain World 及其游戏素材归原权利人所有。程序运行时读取用户本机安装的游戏资源；仓库中少量界面图标与音效的来源和许可边界见 [NOTICE](NOTICE)。

## 许可

源码采用 MIT License，详见 [LICENSE](LICENSE)。

---

# Desktop Rain World — Slugcat Simulation

A Rain World desktop ecology simulator focused on slugcat pets, with creature behavior, pathfinding, physics, interactions, environmental systems, and persistent scenes.

The repository also includes a [visual showcase](docs/showcase/) of the current project icon and character artwork.

## Features

- **Slugcat pets**: Character-specific AI, social behavior, pathfinding, gait, physics, and item interactions.
- **Rain World ecology**: Lizards, Squidcada, Noodleflies, Slugpups, plants, food, and other creatures and objects.
- **Environment and scenes**: Rain cycles, shelters, poles, walls, and persistent scene state.

## Requirements

- Windows 10 / 11
- Python 3.10+
- Rain World
- Downpour / More Slugcats DLC

Running from source requires a local Rain World installation. On first launch, select the Rain World installation directory so the program can read the required local assets.

## Installation

```powershell
pip install -e .
desktop-rainworld-slugcat-simulation
```

To build the Windows executable `RainWorldSlugcatSimulation.exe`:

```powershell
.\build_exe.ps1
```

The exact output location depends on the build script.

## Basic Controls

- Select an object from the toolbar and click in the window to place it.
- Press `Esc` or right-click to cancel the current action.
- Drag objects to move, carry, or throw them.
- Use the eraser to remove objects or the clear function to clear scene objects.
- Create shelters by dragging an area; the shelter size follows the dragged area.
- A built-in rain-cycle timer can be manually started or stopped from the environment panel.

## Characters

Currently included:

- Monk
- Survivor
- Rivulet
- Watcher
- Gourmand
- Hunter
- Artificer
- Spearmaster
- Saint
- Slugpup
- Inv

## Origin, acknowledgement, and independent maintenance

This project is independently maintained. Early versions referenced and built on
[lingxiaojun/slugcatpet](https://github.com/lingxiaojun/slugcatpet); thanks to that project for its public code and ideas.
The ecology, AI, pathfinding, physics, rendering, environment systems, and tooling have since been substantially rewritten and expanded here; some early code and its license notice remain in the repository.

Current maintainer: littlhMW. Historical authorship and upstream attribution remain documented in Git history, [NOTICE](NOTICE), and the license.

Rain World and its game assets belong to their respective rights holders. The program reads game resources from the user's local installation; see [NOTICE](NOTICE) for the provenance and licensing boundaries of the repository's small set of interface icons and audio files.

## License

The source code is licensed under the MIT License. See [LICENSE](LICENSE).
