import queue
from tkinter import messagebox

import customtkinter as ctk

from config import Config
from worker import Worker
from ui.download_tab import DownloadTab
from ui.cut_tab import CutTab


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("YT-DLP GUI")
        self.geometry("900x650")
        self.minsize(750, 500)

        self.cfg = Config.load()

        # Shared queues and single worker thread
        self.job_queue: queue.Queue = queue.Queue()
        self.result_queue: queue.Queue = queue.Queue()
        self.worker = Worker(self.job_queue, self.result_queue)
        self.worker.start()

        # Tab container
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        self.tabview.add("Download")
        self.tabview.add("Cut")

        self.download_tab = DownloadTab(self.tabview.tab("Download"), self.cfg, self.job_queue)
        self.cut_tab = CutTab(self.tabview.tab("Cut"), self.cfg, self.job_queue)
        self.download_tab.pack(fill="both", expand=True)
        self.cut_tab.pack(fill="both", expand=True)

        # Cancel button
        self.cancel_btn = ctk.CTkButton(
            self, text="Cancel All Jobs",
            fg_color="#d9534f", hover_color="#c9302c",
            command=self._cancel,
        )
        self.cancel_btn.pack(pady=8)

        # Start polling the result queue
        self._poll()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _poll(self):
        """Drain the result queue and dispatch messages to tabs."""
        while True:
            try:
                msg = self.result_queue.get_nowait()
            except queue.Empty:
                break
            self.download_tab.handle_result(msg)
            self.cut_tab.handle_result(msg)
        self.after(200, self._poll)

    def _cancel(self):
        self.worker.cancel_all()
        self.download_tab.on_cancel()
        self.cut_tab.on_cancel()

    def _on_close(self):
        if self.worker._current_process and self.worker._current_process.poll() is None:
            if not messagebox.askokcancel("Quit", "A job is still running. Quit anyway?"):
                return
        self.worker.cancel_all()
        self.destroy()
