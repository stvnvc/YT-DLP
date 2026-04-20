import customtkinter as ctk
from tkinter import filedialog

from worker import DownloadJob


class DownloadTab(ctk.CTkFrame):
    def __init__(self, parent, config, job_queue):
        super().__init__(parent)
        self.config = config
        self.job_queue = job_queue
        self._job_ids: set[int] = set()

        # -- URL input --------------------------------------------------------
        ctk.CTkLabel(self, text="URLs (one per line):").pack(anchor="w", padx=10, pady=(10, 0))
        self.url_box = ctk.CTkTextbox(self, height=100)
        self.url_box.pack(fill="x", padx=10, pady=5)

        # -- Options row ------------------------------------------------------
        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(opts, text="Quality:").pack(side="left")
        self.quality_var = ctk.StringVar(value="Best")
        ctk.CTkOptionMenu(
            opts, variable=self.quality_var,
            values=["Best", "1080p", "720p", "480p", "Audio only (MP3)"],
        ).pack(side="left", padx=(5, 20))

        ctk.CTkLabel(opts, text="Output name:").pack(side="left")
        self.name_var = ctk.StringVar()
        ctk.CTkEntry(opts, textvariable=self.name_var, width=180,
                      placeholder_text="leave empty = video title").pack(side="left", padx=(5, 20))

        ctk.CTkLabel(opts, text="Output folder:").pack(side="left")
        self.folder_var = ctk.StringVar(value=config.download_folder)
        ctk.CTkEntry(opts, textvariable=self.folder_var, width=300).pack(side="left", padx=5)
        ctk.CTkButton(opts, text="Browse", width=70, command=self._browse_folder).pack(side="left")

        # -- Buttons ----------------------------------------------------------
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(btn_row, text="Start Download", command=self._start).pack(side="left")

        # -- Progress bar -----------------------------------------------------
        self.progress = ctk.CTkProgressBar(self)
        self.progress.pack(fill="x", padx=10, pady=5)
        self.progress.set(0)

        # -- Log area ---------------------------------------------------------
        self.log = ctk.CTkTextbox(self, state="disabled")
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # -- callbacks ------------------------------------------------------------

    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or None)
        if folder:
            self.folder_var.set(folder)
            self.config.download_folder = folder
            self.config.save()

    def _start(self):
        urls = [u.strip() for u in self.url_box.get("1.0", "end").strip().splitlines() if u.strip()]
        if not urls:
            self._log("No URLs entered.")
            return

        folder = self.folder_var.get().strip()
        if not folder:
            self._log("No output folder selected.")
            return

        self.config.download_folder = folder
        self.config.save()

        quality = self.quality_var.get()
        name = self.name_var.get().strip()
        for i, url in enumerate(urls):
            # For batch with a custom name, append _1, _2, …
            if name and len(urls) > 1:
                job_name = f"{name}_{i + 1}"
            else:
                job_name = name
            job = DownloadJob(url=url, quality=quality, output_folder=folder, output_name=job_name)
            self._job_ids.add(job.job_id)
            self.job_queue.put(job)

        self._log(f"Queued {len(urls)} download(s).")
        self.progress.set(0)

    # -- result handling ------------------------------------------------------

    def handle_result(self, msg: dict):
        if msg.get("tab") != "download" or msg["job_id"] not in self._job_ids:
            return
        t = msg["type"]
        if t == "progress":
            self.progress.set(msg["percent"] / 100)
        elif t == "log":
            self._log(msg["line"])
        elif t == "complete":
            self.progress.set(1.0)
            self._log(msg["message"])
            self._job_ids.discard(msg["job_id"])
        elif t == "error":
            self._log(f"ERROR: {msg['message']}")
            self._job_ids.discard(msg["job_id"])

    def on_cancel(self):
        self._job_ids.clear()
        self._log("Cancelled all downloads.")
        self.progress.set(0)

    # -- helpers --------------------------------------------------------------

    def _log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
