# -*- coding: utf-8 -*-
r"""RainWorldExtractor v2 —— 把正版 Rain World 与反编译源码变成一份可查询的逆向资料库。

```python
from slugcatpet.rwdump import extract
extract.extract(install=r"D:\Steam\...\Rain World", decomp=r"...\decomp_full")
```

命令行：

    python -m slugcatpet.rwdump.extract [--install DIR] [--decomp DIR] [--out DIR]
                                        [--graphics-only] [--no-images] [--show]

产出的目录结构与各层含义见 `docs/DECOMPILE_PROCESS.md`。
"""
from __future__ import annotations

__version__ = "2.0"

from . import assets, code, report, rig      # noqa: F401

__all__ = ["assets", "code", "rig", "report", "__version__"]