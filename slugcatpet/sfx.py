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

    def _path(self, name):
        return self.root / (name + ".wav")

    def play(self, name, gain=1.0) -> None:
        if not self.enabled:
            return
        path = self._path(name)
        if not path.is_file():
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
        if not path.is_file():
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
