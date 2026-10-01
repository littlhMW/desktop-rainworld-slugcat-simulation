"""Optional Push To Meow integration.

The desktop pet does not ship Workshop audio.  When the local Push To Meow
workshop item is present we reuse its WAV files and keep the feature silent
when it is absent.  This mirrors the user's requested dependency while making
the packaged app safe to run without the mod installed.
"""
from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect

WORKSHOP_ID = "3257541402"
_VARIANT_PREFIX = {
    "gourmand": "Fat",
    "saint": "Whispery",
    "artificer": "Coarse",
    "spearmaster": "Spear",
    "rivulet": "RivuletA",
    "watcher": "Watcher",
    "slugpup": "Pup",
    # Push To Meow uses the original Sofanthiel stem for Inv (怪猫); falling
    # back to Normal made it sound indistinguishable from Survivor.
    "inv": "Sofanthiel",
}


def _roots() -> list[Path]:
    out = []
    env = Path(str(__import__("os").environ.get("SLUGCATPET_PUSH_TO_MEOW", "")))
    if str(env) not in ("", "."):
        out.append(env)
    for drive in ("C", "D", "E", "F"):
        out.extend((
            Path(f"{drive}:/Steam/steamapps/workshop/content/312520/{WORKSHOP_ID}"),
            Path(f"{drive}:/SteamLibrary/steamapps/workshop/content/312520/{WORKSHOP_ID}"),
            Path(f"{drive}:/Program Files (x86)/Steam/steamapps/workshop/content/312520/{WORKSHOP_ID}"),
        ))
    return out


def find_push_to_meow() -> Path | None:
    for root in _roots():
        p = root / "soundeffects"
        if (p / "MeowNormal1.wav").is_file():
            return p
    return None


class MeowManager:
    """Low-frequency, context-aware meows driven from the world tick."""

    def __init__(self, params: dict):
        self.params = params
        self.enabled = bool(params.get("meows_enabled", False))
        self.volume = max(0, min(100, int(params.get("meows_volume", 70))))
        self.root = find_push_to_meow()
        self._rng = random.Random(0x4D454F57)
        self._cooldowns: dict[str, int] = {}
        self._playing: list[QSoundEffect] = []
        self._event_cd: dict[str, int] = {}

    @property
    def available(self) -> bool:
        return self.root is not None

    def set_enabled(self, value: bool) -> None:
        self.enabled = bool(value)
        self.params["meows_enabled"] = self.enabled
        if not self.enabled:
            for effect in self._playing:
                effect.stop()
            self._playing.clear()

    def set_volume(self, value: int) -> None:
        self.volume = max(0, min(100, int(value)))
        self.params["meows_volume"] = self.volume
        for effect in self._playing:
            effect.setVolume(self.volume / 100.0)

    def _prefix(self, pet) -> str:
        return _VARIANT_PREFIX.get(getattr(pet, "variant", ""), "Normal")

    def _context(self, pet) -> tuple[float, bool]:
        beh = getattr(pet, "behavior", None)
        state = str(getattr(beh, "state", ""))
        body = getattr(pet, "body", None)
        hungry = float(getattr(body, "food", 1.0)) <= 0.25
        danger = any(k in state.lower() for k in ("flee", "fight", "threat", "panic", "hurt"))
        speed = abs(float(getattr(body, "vx", 0.0))) + abs(float(getattr(body, "vy", 0.0)))
        # Probability per 40 Hz tick.  Distress is audible sooner; idle cats
        # remain occasional enough that a group does not become a chorus.
        chance = 1.0 / (180.0 if danger else 900.0 if hungry else 2400.0)
        if speed > 8.0:
            chance *= 0.55
        return chance, danger or hungry

    def _play(self, pet, long_call: bool) -> bool:
        if self.root is None:
            return False
        prefix = self._prefix(pet)
        stem = f"Meow{prefix}{'' if long_call else 'Short'}"
        # A plain glob for MeowNormal* also matches MeowNormalShort*.  That
        # silently made even requested long calls sound clipped and shrill.
        files = sorted(p for p in self.root.glob(stem + "*.wav")
                       if p.stem == stem or p.stem[len(stem):].isdigit())
        if not files:
            stem = "MeowNormal" + ("" if long_call else "Short")
            files = sorted(p for p in self.root.glob(stem + "*.wav")
                           if p.stem == stem or p.stem[len(stem):].isdigit())
        if not files:
            return False
        path = self._rng.choice(files)
        # 独立实例避免 play() 重启同一个长叫，导致声音被截断。
        effect = QSoundEffect()
        effect.setSource(QUrl.fromLocalFile(str(path)))
        effect.setLoopCount(1)
        effect.setVolume(self.volume / 100.0)
        effect.play()
        self._playing.append(effect)
        gfx = getattr(pet, "gfx", None)
        if gfx is not None:
            gfx.meow_t = 18 if long_call else 9
        return True

    def event(self, pet, kind: str) -> None:
        if not self.enabled or not self.available or pet is None:
            return
        key = "%s:%s" % (getattr(pet, "id", id(pet)), kind)
        if self._event_cd.get(key, 0) > 0:
            return
        self._event_cd[key] = 22 if kind == "grab" else 16
        self._play(pet, long_call=(kind == "grab" or self._rng.random() < 0.45))

    def notify_grab(self, pet) -> None:
        self.event(pet, "grab")

    def notify_shake(self, pet) -> None:
        self.event(pet, "shake")

    def tick(self, pets) -> None:
        if not self.enabled or not self.available:
            return
        self._playing = [e for e in self._playing if e.isPlaying()]
        for key in list(self._event_cd):
            self._event_cd[key] -= 1
            if self._event_cd[key] <= 0:
                del self._event_cd[key]
        if len(self._playing) >= 3:
            return
        for pet in pets:
            key = str(getattr(pet, "id", id(pet)))
            cd = self._cooldowns.get(key, 0)
            if cd > 0:
                self._cooldowns[key] = cd - 1
                continue
            if getattr(pet, "behavior", None) is None or getattr(pet.behavior, "dead", False):
                continue
            chance, urgent = self._context(pet)
            if self._rng.random() >= chance:
                continue
            self._play(pet, long_call=urgent or self._rng.random() < 0.35)
            self._cooldowns[key] = self._rng.randint(180, 420)
