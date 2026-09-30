        if elastic > 0:
            self.vx += dx * elastic
            self.vy += dy * elastic
        self.vx += host_vx * exaggerate
        self.vy += host_vy * exaggerate
        d = math.hypot(dx, dy)
        if d > connect_rad and d > 1e-6:
            ux, uy = dx / d, dy / d
            corr = connect_rad - d
            vecx, vecy = ux * corr, uy * corr
            self.x -= vecx
            self.y -= vecy
            self.vx -= vecx
            self.vy -= vecy
        self.vx = host_vx + (self.vx - host_vx) * adapt_retain
        self.vy = host_vy + (self.vy - host_vy) * adapt_retain


class HeadBone(GenericBone):
    """头部骨。"""


class Hand:
    """手：Retracted / HuntAbsolutePosition 两态机。"""
    __slots__ = ("x", "y", "lx", "ly", "vx", "vy", "j", "active",
                 "retract_counter", "mode", "reached")

    def __init__(self, sx, sy, j):
        self.x = self.lx = sx
        self.y = self.ly = sy
        self.vx = self.vy = 0.0
        self.j = j
        self.active = False
        self.retract_counter = 0
        self.mode = "Retracted"
        self.reached = True

    def update(self, sx, sy, target, speed=HUNT_SPEED, quickness=HAND_QUICKNESS):
        """sx,sy=肩点；target=绝对目标或 None（收回）。"""
        self.lx, self.ly = self.x, self.y

        if target is not None:
            retracting = False
            self.mode = "HuntAbsolutePosition"
            self.active = True
        else:
            retracting = True
            self.active = False

        hunt_target = target

        if retracting and self.mode != "Retracted":
            self.retract_counter += 1
            if self.retract_counter > 5:
                self.mode = "HuntAbsolutePosition"
                k = min(1.0, (self.retract_counter - 5) * 0.05)
                self.x += (sx - self.x) * k
                self.y += (sy - self.y) * k
                speed = 1.0 + self.retract_counter * 0.2
                quickness = 1.0
                hunt_target = (sx, sy)
                if math.hypot(self.x - sx, self.y - sy) < 2.0 and self.reached:
                    self.mode = "Retracted"
        else:
            self.retract_counter -= 10
            if self.retract_counter < 0:
                self.retract_counter = 0

        if self.mode == "Retracted":
            self.vx = 0.0
            self.vy = 0.0
            self.x = sx
            self.y = sy
            self.reached = True
        elif self.mode == "HuntAbsolutePosition":
            if hunt_target is not None:
                tx, ty = hunt_target
                dx, dy = tx - self.x, ty - self.y
                d = math.hypot(dx, dy)
                if d < speed:
                    self.vx, self.vy = dx, dy
                    self.reached = True
                else:
                    ux, uy = dx / d, dy / d
                    self.vx += (ux * speed - self.vx) * quickness
                    self.vy += (uy * speed - self.vy) * quickness
                    self.reached = False
                self.x += self.vx
                self.y += self.vy
        if self.mode != "Retracted":
            sdx, sdy = sx - self.x, sy - self.y