# SlugcatPet Extended

Rain World 桌面宠物扩展版。基于 `lingxiaojun/slugcatpet`，重点扩展生物、物件、行为、环境与场景系统。

## 扩展内容

- **更多生物**：蜥蜴、禅乌贼、面条蝇、猫崽等。
- **更多物件**：珍珠、矛、石头、食物、业力花、杆等，并支持更完整的抓取、携带、投掷与交互。
- **更多行为**：扩展生物行为、社交、追逐、逃避、攀爬、飞行与物件交互。
- **环境系统**：增加雨循环计时器、雨眠、庇护所及相关生物状态处理。
- **场景存档**：支持世界状态及物件状态保存与恢复。
- **解锁上限**：移除原有物品数量上限并优化性能。

## 运行要求

- Windows 10 / 11
- Python 3.10+
- Rain World
- Downpour / More Slugcats DLC

源码运行需要本机安装 Rain World。首次启动时选择 Rain World 安装目录，程序从本机读取所需素材。

## 安装与运行

```powershell
pip install -e .
python run_slugcatpet.py
```

也可以直接构建 Windows 可执行文件：

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

## 项目来源

本项目基于 [lingxiaojun/slugcatpet](https://github.com/lingxiaojun/slugcatpet) 进行扩展，目前作为独立衍生项目维护。

Rain World 及其游戏素材归原权利人所有。本项目不分发 Rain World 游戏素材，程序仅读取用户本机安装的游戏资源。

## 许可

源码采用 MIT License，详见 [LICENSE](LICENSE)。
