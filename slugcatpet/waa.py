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


def _valid_cache(dest: Path, source: Path) -> bool:
    gain_tag = dest.with_suffix(dest.suffix + ".gain3")
    if (not dest.is_file() or not gain_tag.is_file()
            or dest.stat().st_mtime_ns < source.stat().st_mtime_ns):
        return False
    try:
        with wave.open(str(dest), "rb") as wav:
            return wav.getnframes() / wav.getframerate() >= 60
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
