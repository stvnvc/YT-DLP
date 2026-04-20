import re


def validate_timestamp(ts: str) -> bool:
    """Check HH:MM:SS format with valid minute/second ranges."""
    m = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})", ts)
    if not m:
        return False
    _, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return mi < 60 and s < 60


def timestamp_to_seconds(ts: str) -> int:
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def seconds_to_timestamp(total: int) -> str:
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_ytdlp_progress(line: str) -> float | None:
    """Extract download percentage from a yt-dlp output line."""
    m = re.search(r"\[download\]\s+([\d.]+)%", line)
    return float(m.group(1)) if m else None


def parse_ffmpeg_progress(line: str, total_seconds: float) -> float | None:
    """Extract encoding percentage from an ffmpeg progress line."""
    m = re.search(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d+)", line)
    if m and total_seconds > 0:
        h, mi, s, frac = m.groups()
        current = int(h) * 3600 + int(mi) * 60 + int(s) + int(frac) / (10 ** len(frac))
        return min(100.0, (current / total_seconds) * 100)
    return None
