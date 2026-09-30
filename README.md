# SlugcatPet Extended

Windows 桌面蛞蝓猫宠物，基于 Rain World 风格实现猫、猫崽、生物、物件、地形、AI 与交互。

## 运行要求

- Windows 10 / 11
- Python 3.10+
- 源码首次运行需要本机 Rain World（含 Downpour / More Slugcats DLC）

## 安装与运行

```powershell
pip install PySide6 UnityPy numpy Pillow
python run_slugcatpet.py
```

首次启动会要求选择 Rain World 安装目录，用于提取本机所需素材。

发布版 `SlugcatPet.exe` 可直接运行。

## 基本操作

- 工具栏选择对象后，在窗口中点击放置；Esc / 右键取消。
- 拖动物件可以移动、投掷或丢出窗口。
- 橡皮删除对象；清空按钮清除场景对象。
- 猫可被拖动、操控或打开设置。
- 庇护所通过拖拽矩形创建：点击前光标处只显示庇护所图标，按住后拖出的矩形即为实时预览。
- 暴雨可在环境面板手动开启或关闭。

## 主要功能

- 多种蛞蝓猫、猫崽及 Rain World 生物。
- 食物、矛、石头、珍珠、业力花、杆、庇护所等物件。
- AI：进食、战斗、逃避、社交、睡眠、救援、避雨与寻路。
- 物理碰撞、窗口边界、庇护所墙体与杆/矛等攀附结构。
- Rain World 风格的动画、表情与像素渲染。
- 圣徒：伸舌逗弄生物的概率为 1/8；复活按压时用自己的默认表情（其他猫仍借晕眩脸）。
- 世界状态与物件存档恢复。

## 角色

正式蛞蝓猫：僧侣、求生者、溪流、守望者、饕餮、怪猫、猎手、工匠、矛大师、圣徒。

猫崽为独立生成对象，不占正式蛞蝓猫名额。

## 开发

反编译与素材资料库位于 `docs/` 与本机 `~/.slugcatpet/rainworld_dump/`。

移植规则见 `AGENTS.md`，详细逆向流程见 `docs/DECOMPILE_PROCESS.md`。

## 来源与许可

本项目 fork 自 `lingxiaojun/slugcatpet`。

Rain World 及其素材归原权利人所有。本仓库不分发 Rain World 素材；源码许可见 `LICENSE`。
