    # 猫崽的绘制尺寸：保持独立的整体视觉缩放，不改物理碰撞体和骨骼位置。
    # 这里使用 0.65，是当前素材尺寸下与 Rain World 猫崽比例最接近的视觉值。
    # 缩放以脚下支点为中心应用（见 graphics_draw.py），因此落地位置不会随缩放漂移。
    # 注意：表情绘制不在这里处理，猫崽表情使用独立的 face 参数，不要在此处联动缩放。
    visual={"pup_wide": True, "draw_scale": 0.65},
    fsm_mount=None,
    wip=False,
)