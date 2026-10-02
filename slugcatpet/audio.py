"""Optional Push To Meow integration.

The desktop pet does not ship Workshop audio.  When the local Push To Meow
workshop item is present we reuse its WAV files and keep the feature silent
when it is absent.  This mirrors the user's requested dependency while making
the packaged app safe to run without the mod installed.
"""
from __future__ import annotations

import random
import threading
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect, QAudioOutput, QMediaPlayer

from ._paths import log_error
from .waa import cached_cue, game_resource, prepare_cue

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
        # From the user's game install only; the generated cue stays in user_dir.
        # The easter egg is enabled by default; users can opt out in Settings.
        self.waa_enabled = bool(params.get("waa_enabled", True))
        self.params.pop("waa_audio_path", None)
        # Reuse a complete user-local extraction immediately.  This avoids a
        # second Unity parse on startup and keeps the feature working while
        # Steam/Rain World is closed.
        self.waa_path: Path | None = cached_cue()
        self._waa_source: Path | None = None
        self._waa_checked = False
        self._waa_preparing = False
        self._waa_error = ""
        self._waa_player = None
        self._waa_output = None
        self._waa_cooldown = 0
        self._waa_threat_latched = False
        self._waa_mode = False
        self._waa_elapsed = 0.0
        if self.waa_enabled:
            self.prepare_waa()

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
            self._stop_waa()

    def set_volume(self, value: int) -> None:
        self.volume = max(0, min(100, int(value)))
        self.params["meows_volume"] = self.volume
        for effect in self._playing:
            effect.setVolume(self.volume / 100.0)
        if self._waa_output is not None:
            self._waa_output.setVolume(min(1.0, self.volume / 100.0 * 9.0))

    @property
    def waa_eligible(self) -> bool:
        return bool(self.enabled and self.waa_enabled and self.waa_path
                    and self.waa_path.is_file())

    @property
    def waa_supported(self) -> bool:
        if not self._waa_checked:
            self._waa_source = game_resource()
            self._waa_checked = True
        return self._waa_source is not None

    @property
    def waa_status(self) -> str:
        if not self.waa_supported:
            return "missing"
        if self._waa_preparing:
            return "preparing"
        if self._waa_error:
            return "failed"
        return "ready" if self.waa_path and self.waa_path.is_file() else "idle"

    @property
    def waa_detail(self) -> str:
        return "\n".join(str(part) for part in
                         (self._waa_source, self.waa_path, self._waa_error) if part)

    def prepare_waa(self) -> None:
        if not self.waa_supported or self._waa_preparing or self.waa_path:
            return
        self._waa_preparing = True
        self._waa_error = ""

        def work() -> None:
            try:
                self.waa_path = prepare_cue(self._waa_source)
            except Exception as exc:
                self._waa_error = str(exc)
                log_error("waa cue extraction failed: %r" % (exc,))
            finally:
                self._waa_preparing = False

        threading.Thread(target=work, name="WaaCueExtract", daemon=True).start()

    def set_waa_enabled(self, value: bool) -> None:
        self.waa_enabled = bool(value)
        self.params["waa_enabled"] = self.waa_enabled
        if self.waa_enabled:
            self.prepare_waa()
        else:
            self._stop_waa()

    def _waa_only_survivor(self, pets) -> bool:
        return len(pets or ()) == 1 and getattr(pets[0], "variant", "") == "survivor"

    @staticmethod
    def _pet_in_threat(pet) -> bool:
        beh = getattr(pet, "behavior", None)
        if beh is None:
            return False
        state = str(getattr(beh, "state", "")).lower()
        if any(k in state for k in ("flee", "fight", "threat", "panic", "hurt")):
            return True
        body = getattr(pet, "body", None)
        chunk = getattr(body, "chunk1", None)
        field = getattr(getattr(beh, "win", None), "threat_field", None)
        if chunk is not None and field is not None:
            try:
                if float(field.danger_at(chunk.x, chunk.y)) >= 0.22:
                    return True
            except Exception:
                pass
        try:
            return float(beh._threat_level()) >= 0.22
        except Exception:
            return False

    def _stop_waa(self) -> None:
        if self._waa_player is not None:
            self._waa_player.stop()
            self._waa_player.setSource(QUrl())
        self._waa_threat_latched = False
        self._waa_mode = False
        self._waa_elapsed = 0.0

    def _play_waa(self) -> bool:
        if (not self.waa_eligible or self._waa_player is not None
                and self._waa_player.playbackState() != QMediaPlayer.PlaybackState.StoppedState):
            return False
        if self._waa_player is None:
            self._waa_output = QAudioOutput()
            # SU_7 is mastered considerably quieter than the short meow clips.
            # Apply the requested 3x gain while keeping Qt's output ceiling.
            self._waa_output.setVolume(min(1.0, self.volume / 100.0 * 9.0))
            self._waa_player = QMediaPlayer()
            self._waa_player.setAudioOutput(self._waa_output)
        source = QUrl.fromLocalFile(str(self.waa_path))
        if self._waa_player.source() != source:
            self._waa_player.setSource(source)
        self._waa_player.setPosition(0)
        self._waa_player.play()
        self._waa_elapsed = 0.0
        return True

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
        beh = getattr(pet, "behavior", None)
        dead_fn = getattr(beh, "is_dead", None)
        if (beh is None or (dead_fn() if callable(dead_fn) else getattr(beh, "dead", False))
                or getattr(getattr(pet, "body", None), "dead", False)):
            return
        # Waa~ 完全替代唯一求生者的普通猫叫。
        if self._waa_mode and getattr(pet, "variant", "") == "survivor":
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
        self._waa_mode = bool(self.enabled and self.waa_enabled
                              and self._waa_only_survivor(pets)
                              and (self._waa_preparing or self.waa_eligible))
        # Expose the active Survivor state to the lizard perception pass.
        # Items runs after audio each frame, so this flag is consumed in the
        # same frame by lizard perception and only lasts while SU_7 plays.
        for pet in pets:
            setattr(pet, "_waa_active", False)
            gfx = getattr(pet, "gfx", None)
            if gfx is not None:
                gfx.waa_active = False
        if not self._waa_mode and self._waa_player is not None and self._waa_player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            self._stop_waa()
        elif not self._waa_mode:
            self._waa_threat_latched = False
        self._playing = [e for e in self._playing if e.isPlaying()]
        for key in list(self._event_cd):
            self._event_cd[key] -= 1
            if self._event_cd[key] <= 0:
                del self._event_cd[key]
        if self._waa_cooldown > 0:
            self._waa_cooldown -= 1
        if self._waa_mode:
            pet = pets[0]
            dead_fn = getattr(getattr(pet, "behavior", None), "is_dead", None)
            if (callable(dead_fn) and dead_fn()) or getattr(getattr(pet, "body", None), "dead", False):
                if self._waa_player is not None:
                    self._waa_player.stop()
                self._waa_threat_latched = False
                return
            threatened = self._pet_in_threat(pet)
            if not threatened:
                self._waa_threat_latched = False
            if threatened and not self._waa_threat_latched and self._waa_cooldown <= 0:
                if self._waa_player is None or self._waa_player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
                    if self._play_waa():
                        self._waa_threat_latched = True
                        self._waa_cooldown = 800
                        gfx = getattr(pet, "gfx", None)
                        if gfx is not None:
                            gfx.meow_t = 6
            # Keep the vocal pose and call arcs alive while SU_7 is playing.
            if (self._waa_player is not None
                    and self._waa_player.playbackState() != QMediaPlayer.PlaybackState.StoppedState):
                self._waa_elapsed += 1.0 / 40.0
                try:
                    pos_s = max(0.0, float(self._waa_player.position()) / 1000.0)
                except (AttributeError, TypeError, ValueError):
                    pos_s = 0.0
                waa_time = max(self._waa_elapsed, pos_s)
                gfx = getattr(pet, "gfx", None)
                if gfx is not None and not getattr(gfx, "dead", False):
                    gfx.meow_t = max(getattr(gfx, "meow_t", 0), 6)
                    gfx.waa_time = waa_time
                    gfx.waa_active = True
                setattr(pet, "_waa_active", True)
            return
        if not self.enabled or not self.available:
            return
        if len(self._playing) >= 3:
            return
        for pet in pets:
            key = str(getattr(pet, "id", id(pet)))
            cd = self._cooldowns.get(key, 0)
            if cd > 0:
                self._cooldowns[key] = cd - 1
                continue
            beh = getattr(pet, "behavior", None)
            dead_fn = getattr(beh, "is_dead", None)
            if (beh is None or (dead_fn() if callable(dead_fn) else getattr(beh, "dead", False))
                    or getattr(getattr(pet, "body", None), "dead", False)):
                continue
            chance, urgent = self._context(pet)
            if self._rng.random() >= chance:
                continue
            self._play(pet, long_call=urgent or self._rng.random() < 0.35)
            self._cooldowns[key] = self._rng.randint(180, 420)
