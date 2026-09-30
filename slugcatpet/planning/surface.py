                r = land_sweep(stats, [(b.lo, b.y, b.hi)], launches,
                               want=(b.anchor, b.y), land_off=off)
                if r is None:
                    continue
                if same_level_block:
                    rk, rh, rmd, rlx, _rly, _rticks, _rlaunch = r
                    arc = get_arc(stats, rh, rmd)
                    if _arc_hits_solids(arc, rlx, a.y - arc.takeoff_h):
                        continue
                kind, hold, md, land_x, _ly, ticks, launch_x = r
                if not landing_safe(land_x, b.lo, b.hi):
                    continue                   # 落点贴着平台边：这只猫不愿意赌
                if abs(land_x - b.anchor) > max(LAND_PAD, ANCHOR_STEP):
                    continue                   # 落到别的锚点去了：那条边在管