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
    gain9 = dest.with_name(dest.stem + "_gain9" + dest.suffix)

    def valid(path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            with wave.open(str(path), "rb") as wav:
                return wav.getnframes() / wav.getframerate() >= 60
        except (OSError, EOFError, ZeroDivisionError, wave.Error):
            return False

    # New caches are marked as gain=9.  Older builds left a gain=3 cache;
    # amplify that user-local file once and keep the result separate so the
    # same file is never multiplied again on the next launch.
    if valid(dest) and dest.with_suffix(dest.suffix + ".gain9").exists():
        return dest
    if valid(gain9) and gain9.with_suffix(gain9.suffix + ".gain9").exists():
        return gain9
    if not valid(dest):
        return None
    try:
        with wave.open(str(dest), "rb") as wav:
            params = wav.getparams()
            pcm = audioop.mul(wav.readframes(wav.getnframes()), params.sampwidth, 3.0)
        gain9.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(gain9), "wb") as out:
            out.setparams(params)
            out.writeframes(pcm)
        gain9.with_suffix(gain9.suffix + ".gain9").write_text(
            "legacy SU_7 cache boosted from gain=3 to gain=9\n", encoding="ascii")
        return gain9
    except (OSError, EOFError, ZeroDivisionError, wave.Error):
        return dest
    return dest


def _valid_cache(dest: Path, source: Path) -> bool:
    gain_tag = dest.with_suffix(dest.suffix + ".gain9")
    # A cache without the gain=9 marker belongs to an older build.  Let the
    # extractor replace it when the game resource is available; when it is
    # not, cached_cue() above creates a separate boosted copy instead.
    if (not dest.is_file() or dest.stat().st_mtime_ns < source.stat().st_mtime_ns):
        return False
    if not gain_tag.exists():
        return False
    try:
        with wave.open(str(dest), "rb") as wav:
            valid = wav.getnframes() / wav.getframerate() >= 60
        return valid
    except (OSError, EOFError, ZeroDivisionError, wave.Error):
        return False


def prepare_cue(source: Path, dest: Path | None = None) -> Path:
    """Extract SU_7 into a user-only, 9x-gained cache; never ship game audio."""
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
            pcm = audioop.mul(wav.readframes(wav.getnframes()), params.sampwidth, 9.0)
    except (EOFError, ZeroDivisionError, wave.Error) as exc:
        raise ValueError("Rain World SU_7 audio clip cannot be decoded") from exc

    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=dest.name + ".", suffix=".tmp", dir=dest.parent)
    os.close(fd)
    temp = Path(name)
    tag = dest.with_suffix(dest.suffix + ".gain9")
    tag_temp = tag.with_suffix(tag.suffix + ".tmp")
    try:
        with wave.open(str(temp), "wb") as out:
            out.setparams(params)
            out.writeframes(pcm)
        os.replace(temp, dest)
        tag_temp.write_text("SU_7 gain=9.0 clipped\n", encoding="ascii")
        os.replace(tag_temp, tag)
    finally:
        if temp.exists():
            temp.unlink()
        if tag_temp.exists():
            tag_temp.unlink()
    return dest
