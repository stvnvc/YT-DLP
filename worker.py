import itertools
import os
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional

from utils import (
    parse_ffmpeg_progress,
    parse_ytdlp_progress,
    seconds_to_timestamp,
    timestamp_to_seconds,
)

QUALITY_MAP = {
    "Best": ("bestvideo+bestaudio/best", False),
    "1080p": ("bestvideo[height<=1080]+bestaudio/best[height<=1080]", False),
    "720p": ("bestvideo[height<=720]+bestaudio/best[height<=720]", False),
    "480p": ("bestvideo[height<=480]+bestaudio/best[height<=480]", False),
    "Audio only (MP3)": ("bestaudio", True),
}

_job_counter = itertools.count(1)


def next_job_id() -> int:
    return next(_job_counter)


@dataclass
class DownloadJob:
    url: str
    quality: str
    output_folder: str
    output_name: str = ""  # empty = use video title
    job_id: int = field(default_factory=next_job_id)
    tab: str = "download"


@dataclass
class CutJob:
    input_file: str
    start: str
    end: str
    output_path: str
    delete_source: bool = False
    job_id: int = field(default_factory=next_job_id)
    tab: str = "cut"


class Worker(threading.Thread):
    def __init__(self, job_queue: queue.Queue, result_queue: queue.Queue):
        super().__init__(daemon=True)
        self.job_queue = job_queue
        self.result_queue = result_queue
        self._current_process: Optional[subprocess.Popen] = None
        self._cancel_flag = threading.Event()

    def cancel_all(self):
        self._cancel_flag.set()
        while not self.job_queue.empty():
            try:
                self.job_queue.get_nowait()
                self.job_queue.task_done()
            except queue.Empty:
                break
        proc = self._current_process
        if proc and proc.poll() is None:
            proc.kill()

    def run(self):
        while True:
            job = self.job_queue.get()
            self._cancel_flag.clear()
            try:
                if isinstance(job, DownloadJob):
                    self._run_download(job)
                elif isinstance(job, CutJob):
                    self._run_cut(job)
            except Exception as e:
                self._emit(job.tab, job.job_id, "error", message=str(e))
            finally:
                self.job_queue.task_done()

    # -- helpers ----------------------------------------------------------

    def _emit(self, tab: str, job_id: int, msg_type: str, **kwargs):
        self.result_queue.put({"type": msg_type, "tab": tab, "job_id": job_id, **kwargs})

    # -- download ---------------------------------------------------------

    def _run_download(self, job: DownloadJob):
        fmt, audio_only = QUALITY_MAP.get(job.quality, QUALITY_MAP["Best"])

        if job.output_name:
            template = job.output_name + ".%(ext)s"
        else:
            template = "%(title)s.%(ext)s"

        cmd = [
            "yt-dlp", "-f", fmt, "--newline",
            "-o", os.path.join(job.output_folder, template),
        ]
        if audio_only:
            cmd += ["--extract-audio", "--audio-format", "mp3", "--audio-quality", "0"]
        else:
            cmd += ["--merge-output-format", "mp4"]
        cmd.append(job.url)

        self._emit(job.tab, job.job_id, "log", line=f"Downloading: {job.url}")

        self._current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        for line in self._current_process.stdout:
            if self._cancel_flag.is_set():
                self._current_process.kill()
                self._emit(job.tab, job.job_id, "error", message="Cancelled")
                return
            line = line.strip()
            if not line:
                continue
            pct = parse_ytdlp_progress(line)
            if pct is not None:
                self._emit(job.tab, job.job_id, "progress", percent=pct)
            else:
                self._emit(job.tab, job.job_id, "log", line=line)

        rc = self._current_process.wait()
        self._current_process = None
        if rc == 0:
            self._emit(job.tab, job.job_id, "complete", message=f"Done: {job.url}")
        else:
            self._emit(job.tab, job.job_id, "error", message=f"yt-dlp failed (exit {rc})")

    # -- cut --------------------------------------------------------------

    def _run_cut(self, job: CutJob):
        duration_sec = timestamp_to_seconds(job.end) - timestamp_to_seconds(job.start)
        duration_str = seconds_to_timestamp(duration_sec)

        cmd = [
            "ffmpeg", "-y",
            "-ss", job.start,
            "-i", job.input_file,
            "-to", duration_str,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            job.output_path,
        ]

        self._emit(
            job.tab, job.job_id, "log",
            line=f"Cutting: {os.path.basename(job.input_file)} [{job.start} -> {job.end}]",
        )

        self._current_process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        # ffmpeg writes progress to stderr using \r to overwrite lines.
        # Read byte-by-byte and split on \r or \n for real-time updates.
        buf = bytearray()
        while True:
            byte = self._current_process.stderr.read(1)
            if not byte:
                break
            if byte in (b"\r", b"\n"):
                if buf:
                    line = buf.decode("utf-8", errors="replace").strip()
                    buf.clear()
                    if self._cancel_flag.is_set():
                        self._current_process.kill()
                        self._emit(job.tab, job.job_id, "error", message="Cancelled")
                        return
                    pct = parse_ffmpeg_progress(line, duration_sec)
                    if pct is not None:
                        self._emit(job.tab, job.job_id, "progress", percent=pct)
            else:
                buf += byte

        rc = self._current_process.wait()
        self._current_process = None

        if rc == 0:
            self._emit(
                job.tab, job.job_id, "complete",
                message=f"Cut complete: {os.path.basename(job.output_path)}",
            )
            if job.delete_source:
                self._emit(job.tab, job.job_id, "delete_source", path=job.input_file)
        else:
            self._emit(job.tab, job.job_id, "error", message=f"ffmpeg failed (exit {rc})")
