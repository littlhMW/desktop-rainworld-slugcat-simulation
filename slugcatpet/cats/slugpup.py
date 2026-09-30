    # 猫崽整体尺寸：视觉、物理碰撞体和骨骼统一缩放。
    # 0.65 是当前素材下采用的猫崽整体尺寸倍率；它不是单纯的绘制层缩放。
    # SlugcatBody 会用 body_scale 同步调整 chunk 半径、胸胯间距、站姿步距等，
    # 因此猫崽真正会“变小”，而不是成人碰撞体套一个小精灵。
    # 表情参数保持独立；这里不要修改 face / eye / expression 的任何逻辑。
    visual={"pup_wide": True},
    fsm_mount=None,
    wip=False,
)