# 本仓库的移植约定

- 移植原版生物 / 物件（部件、位置、大小、骨骼、图层、翻转、精灵、AI、交互）**一律按
  `docs/DECOMPILE_PROCESS.md` 的流程走**：先反编译 Rain World 本体（`work/scratch/decomp_full`），
  再查 wiki，最后才动代码；每处照抄在注释里标 `文件名.cs:行号`。
- 移植完必跑：`tools/parts_audit.py --check`、`tools/sprite_variants.py`、
  `work/scratch/run_all19.ps1`（须 `fails=0`）；渲染 / 贴图类改动先出图目视核对再提交。
