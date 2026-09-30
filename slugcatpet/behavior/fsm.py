        self._haul_cd = 0             # 清场（拖走无用尸体）的冷却
        self._clear_target = None     # 正在拖的那具无用尸体
        self._haul_left = 0           # 本趟剩余 tick
        self._itemplay_target = None
        self._itemplay_left = 0
        self._itemplay_phase = 0
        self._itemplay_side = "r"
        self._itemplay_mode = "inspect"
        self._lick_cd = 0                # 圣徒舔生物玩耍的冷却
        self._play_face = 1              # 玩耍时的朝向倾向（进玩法时随机一次）
        # 觅食欲望：
        # - 冬眠食物线以下：由 hunger_need + _food_urge 驱动，保证真的饿了会找
        # - 已达到冬眠线：每次吃东西后按“距离 food_max 还差几格”安排下一次觅食等待
        self._food_urge = 1.0
        self._food_prev = self.body.food
        self._food_prev_q = self.body.food * 4 + self.body.food_quarter
        self._food_seek_wait = 0       # 冬眠线以上的主动觅食等待（tick）