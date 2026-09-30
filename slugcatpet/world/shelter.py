    def solid_rects(self):
        """四面墙 + 门**完全关上**时的入口格（开门 / 关门途中都还能过）。"""
        out = list(self.wall_rects())
        if self.door_state == CLOSED:
            out.append(self.entrance)
        return out

    def cat_solid_rects(self):
        """蛞蝓猫用的实心墙体 —— 与生物 / 物品完全一致（没有暴雨放行开关）。

        猫从「走廊层」缺口走进屋（两侧都通），走廊层以上四面墙完全实心，
        门完全关上时入口那一格也变实心。
        """
        return self.solid_rects()

    # ── 导航层查询（planning/surface.py 与走带切分用；只读几何） ──
    def interior_floor_y(self):
        """屋里可站的那条地面（底墙顶边）—— 猫进了门就站在它上面。"""
        return self.ground_y - self.wall_px

    def interior_span(self):
        """屋里地面的 x 区间：两道侧墙之间（= 底墙铺开的那一段）。"""
        return (self.x + self.wall_px, self.x + self.w - self.wall_px)

    def roof_span(self):
        return (self.x, self.x + self.w)

    def cut_span(self, y, body_h=14.0, step_up=8.0):
        """在高度 y 这条走道上被墙挡住的 x 区间；没挡住就空表。

        口径与 planning 的走带切分一致：底边高过猫头（能从下面走过）的不算墙，
        顶边离脚面不到一步的也不算（那是底墙台阶，一步就踩上去）。于是「地面
        那条走带」是通的（走廊层），屋子中段那条走带会被两侧墙切断。
        """
        out = []
        for (x0, y0, x1, y1) in self.solid_rects():
            if x1 <= x0 or y1 <= y0:
                continue
            if y1 <= y - body_h or y0 >= y - step_up:
                continue
            out.append((x0, x1))