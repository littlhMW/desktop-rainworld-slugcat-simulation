"""按 Rain World SoundID 语义驱动的环境与动作音效。"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect


class SoundManager:
    def __init__(self, params: dict):
        self.params = params
        self.enabled = bool(params.get("sfx_enabled", True))
        self.volume = max(0, min(100, int(params.get("sfx_volume", 55))))
        self.root = Path(__file__).with_name("resources") / "audio"
        # Rain World keeps the original action samples in the user's local
        # install.  Resolve that directory at runtime so the executable does
        # not redistribute game audio while still restoring the complete
        # Slugcat action set when the game is installed.
        self._game_root = None
        self._cat_state = {}
        self._cat_cd = {}
        self._playing = []
        self._loops = {}

    def set_enabled(self, value: bool) -> None:
        self.enabled = bool(value)
        self.params["sfx_enabled"] = self.enabled
        if not self.enabled:
            self.stop_all()

    def set_volume(self, value: int) -> None:
        self.volume = max(0, min(100, int(value)))
        self.params["sfx_volume"] = self.volume
        for effect in (*self._playing, *self._loops.values()):
            effect.setVolume(self.volume / 100.0)

    def _game_audio_root(self):
        if self._game_root is None:
            try:
                from .gameassets import detect_install
                install = detect_install()
                self._game_root = (install / "RainWorld_Data" / "StreamingAssets"
                                   / "loadedsoundeffects") if install else False
            except Exception:
                self._game_root = False
        return self._game_root if self._game_root and self._game_root.is_dir() else None

    def _path(self, name):
        stem = str(name)
        if stem.lower().endswith(".wav"):
            stem = stem[:-4]
        local = self.root / (stem + ".wav")
        if local.is_file():
            return local
        external = self._game_audio_root()
        if external is not None:
            p = external / (stem + ".wav")
            if p.is_file():
                return p
        return None

    def _play_candidates(self, names, gain=1.0):
        """Play one random sample from a SoundID-equivalent candidate list."""
        import random
        paths = [self._path(n) for n in names]
        paths = [p for p in paths if p is not None]
        if not paths:
            return False
        path = random.choice(paths)
        effect = QSoundEffect()
        effect.setSource(QUrl.fromLocalFile(str(path)))
        effect.setLoopCount(1)
        effect.setVolume(max(0.0, min(1.0, self.volume / 100.0 * gain)))
        effect.play()
        self._playing.append(effect)
        return True

    def play(self, name, gain=1.0) -> None:
        if not self.enabled:
            return
        path = self._path(name)
        if path is None:
            return
        effect = QSoundEffect()
        effect.setSource(QUrl.fromLocalFile(str(path)))
        effect.setLoopCount(1)
        effect.setVolume(max(0.0, min(1.0, self.volume / 100.0 * gain)))
        effect.play()
        self._playing.append(effect)

    def loop(self, name, level) -> None:
        level = max(0.0, min(1.0, float(level)))
        if not self.enabled or level <= 0.001:
            old = self._loops.pop(name, None)
            if old is not None:
                old.stop()
            return
        path = self._path(name)
        if path is None:
            return
        effect = self._loops.get(name)
        if effect is None:
            effect = QSoundEffect()
            effect.setSource(QUrl.fromLocalFile(str(path)))
            # PySide6 6.8 exposes Infinite as an enum while the binding accepts int.
            effect.setLoopCount(int(getattr(QSoundEffect.Infinite, "value", -2)))
            self._loops[name] = effect
            effect.play()
        effect.setVolume(self.volume / 100.0 * level)

    def tick(self, rain_level=0.0) -> None:
        self.loop("rain_loop", rain_level)
        self._playing = [e for e in self._playing if e.isPlaying()]

    def stop_all(self) -> None:
        for effect in (*self._playing, *self._loops.values()):
            effect.stop()
        self._playing.clear()
        self._loops.clear()

    def observe_pets(self, pets) -> None:
        """Emit the original Slugcat movement/impact cues for every variant.

        The state edge detector is shared by all cats, so it stays cheap even
        with a crowded scene and avoids tying audio coverage to a particular
        species FSM.
        """
        if not self.enabled:
            return
        alive = set()
        for pet in pets or ():
            body = getattr(pet, "body", None)
            if body is None:
                continue
            key = id(pet)
            alive.add(key)
            c0, c1 = getattr(body, "chunk0", None), getattr(body, "chunk1", None)
            if c0 is None or c1 is None:
                continue
            prev = self._cat_state.get(key)
            state = (float(getattr(c1, "x", 0.0)), float(getattr(c1, "y", 0.0)),
                     float(getattr(c1, "vy", 0.0)), int(getattr(body, "stun", 0)),
                     bool(getattr(body, "dead", False)),
                     float(getattr(body, "stride_phase", 0.0)),
                     bool(getattr(body, "standing", True)),
                     bool(getattr(c1, "on_floor", False)),
                     str(getattr(body, "bodyMode", "")))
            self._cat_state[key] = state
            if prev is None or state[4]:
                continue
            cd = self._cat_cd.get(key, 0)
            if cd > 0:
                self._cat_cd[key] = cd - 1
            # Damage/stun edge: UI_Slugcat_Stunned_Init from the local game.
            if state[3] > prev[3] and prev[4] is False:
                if self._play_candidates(("UI_Wood4", "stun"), 0.55):
                    self._cat_cd[key] = max(self._cat_cd.get(key, 0), 10)
                continue
            # A downward airborne chunk becoming grounded is the standard
            # floor impact cue; it also covers high drops and shelter landings.
            if (not prev[7] and state[7] and prev[2] > 7.5
                    and self._cat_cd.get(key, 0) <= 0):
                if self._play_candidates(("thud3", "stun"), 0.45):
                    self._cat_cd[key] = 8
                continue
            if (prev[7] and not state[7] and state[2] < -5.0
                    and self._cat_cd.get(key, 0) <= 0):
                if self._play_candidates(("jump2A", "jump2B", "jump2C", "jump2D"), 0.22):
                    self._cat_cd[key] = 5
                continue
            if (prev[8] != "ClimbingOnBeam" and state[8] == "ClimbingOnBeam"
                    and self._cat_cd.get(key, 0) <= 0):
                if self._play_candidates(("grabBeam", "walk3A"), 0.20):
                    self._cat_cd[key] = 5
                continue
            if self._cat_cd.get(key, 0) > 0:
                continue
            moving = state[7] and abs(float(getattr(c1, "vx", 0.0))) > 0.8
            phase_wrapped = state[5] < prev[5] - 0.5
            if moving and phase_wrapped:
                names = ("gravel1A", "gravel1B", "gravel1C", "gravel1H") if not state[6] else ("walk3A", "walk3B")
                if self._play_candidates(names, 0.18):
                    self._cat_cd[key] = 4
        for key in tuple(self._cat_state):
            if key not in alive:
                self._cat_state.pop(key, None)
                self._cat_cd.pop(key, None)
