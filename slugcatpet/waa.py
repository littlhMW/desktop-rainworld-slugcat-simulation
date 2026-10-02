"""Extract SU_7 from the player's Rain World installation for the waa cue."""
from __future__ import annotations

import io
import os
import tempfile
import wave
import audioop
from pathlib import Path

from ._paths import user_dir
from .gameassets import detect_install


def game_resource() -> Path | None:
    install = detect_install()
    if install is None:
        return None
    source = install / "RainWorld_Data" / "resources.assets"
    return source if source.is_file() else None


def cached_cue() -> Path | None:
    """Return a complete user-local cue without touching the game install.

    This is deliberately independent of ``game_resource`` so a packaged app
    can keep using a cue prepared by an earlier run when Steam is closed or
    the game is temporarily unavailable.
    """
    dest = user_dir() / "cache" / "waa_su_7.wav"
    if not dest.is_file():
        return None
    try:
        with wave.open(str(dest), "rb") as wav:
            if wav.getnframes() / wav.getframerate() < 60:
                return None
    except (OSError, EOFError, ZeroDivisionError, wave.Error):
        return None
    return dest


def _valid_cache(dest: Path, source: Path) -> bool:
    gain_tag = dest.with_suffix(dest.suffix + ".gain3")
    # Older builds wrote the WAV before the ``.gain3`` marker was added.  A
    # complete cached SU_7 is still perfectly usable (playback applies the
    # requested gain), and forcing UnityPy to parse resources.assets again
    # made packaged builds fail with ``UnityPy.resources``/FileNotFoundError.
    # Validate the audio itself first; the marker is only metadata now.
    if (not dest.is_file() or dest.stat().st_mtime_ns < source.stat().st_mtime_ns):
        return False
    try:
        with wave.open(str(dest), "rb") as wav:
            valid = wav.getnframes() / wav.getframerate() >= 60
        if valid and not gain_tag.exists():
            # Best effort migration.  Never make a playable cache depend on
            # this sidecar being writable (read-only user profiles are valid).
            try:
                gain_tag.write_text("legacy SU_7 cache; playback gain=3.0\n",
                                    encoding="ascii")
            except OSError:
                pass
        return valid
    except (OSError, EOFError, ZeroDivisionError, wave.Error):
        return False


def prepare_cue(source: Path, dest: Path | None = None) -> Path:
    """Extract SU_7 into a user-only, 3x-gained cache; never ship game audio."""
    source = Path(source)
    dest = Path(dest) if dest is not None else user_dir() / "cache" / "waa_su_7.wav"
    if _valid_cache(dest, source):
        return dest

    import UnityPy

    env = UnityPy.load(str(source))
    clips = (obj for obj in env.objects
             if obj.type.name == "AudioClip" and obj.peek_name() == "SU_7")
    clip = next(clips, None)
    if clip is None:
        raise ValueError("Rain World SU_7 audio clip was not found")
    samples = clip.read().samples
    data = samples.get("SU_7.wav") if samples else None
    if not data:
        raise ValueError("Rain World SU_7 audio clip is empty")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            if wav.getnframes() / wav.getframerate() < 60:
                raise ValueError("Rain World SU_7 audio clip is incomplete")
            params = wav.getparams()
            pcm = audioop.mul(wav.readframes(wav.getnframes()), params.sampwidth, 3.0)
    except (EOFError, ZeroDivisionError, wave.Error) as exc:
        raise ValueError("Rain World SU_7 audio clip cannot be decoded") from exc

    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=dest.name + ".", suffix=".tmp", dir=dest.parent)
    os.close(fd)
    temp = Path(name)
    tag = dest.with_suffix(dest.suffix + ".gain3")
    tag_temp = tag.with_suffix(tag.suffix + ".tmp")
    try:
        with wave.open(str(temp), "wb") as out:
            out.setparams(params)
            out.writeframes(pcm)
        os.replace(temp, dest)
        tag_temp.write_text("SU_7 gain=3.0 clipped\n", encoding="ascii")
        os.replace(tag_temp, tag)
    finally:
        if temp.exists():
            temp.unlink()
        if tag_temp.exists():
            tag_temp.unlink()
    return dest
