        self._pole_tick += 1
        self._plat_tick -= 1
        if self._plat_tick <= 0:
            self._plat_tick = PLATFORM_REFRESH_TICKS
            self._refresh_platforms()
        # 抖动衰减，须在 impact 前
        self._shake[0] *= SHAKE_DECAY
        self._shake[1] *= SHAKE_DECAY
        if abs(self._shake[0]) + abs(self._shake[1]) < SHAKE_EPS:
            self._shake[0] = self._shake[1] = 0.0
        cur = self.cursor_logical()
        self._cursor_world = cur          # 矛的「钉在光标上」判定用（见 items._tick_spears）
        self._mouse_pole_tick(cur)

        storm_was_active = bool(self.storm.active)
        self._storm_tick()            # 须在 pet.step 前：雨强/门/积水目标当 tick 生效

        self._zerog_update()
        cycle_prog = self._cold_update_world()
        self._water_update()          # 须在 pet.step 前

        for pet in self.pets:
            pet.step(cur, cycle_prog)

        self._rain_push_tick()        # 雨压：暴露在雨里的东西被轻轻往下压

        self._all_dead_tick()
        self._natural_spawn_tick()

        self._tick_fruits()
        self._tick_stones()
        self._tick_slimemolds()
        self._tick_batflies()
        self._tick_lizards()
        self._tick_squidcadas()
        self._tick_needleworms()
        self._tick_pearls()
        self._tick_spears()
        self._tick_scavengers()
        self._tick_seedcobs()
        self._tick_karmaflowers()
        self._water_splash_detect()   # 须在物体积分后