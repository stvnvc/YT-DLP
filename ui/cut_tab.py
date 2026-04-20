import os

import customtkinter as ctk
from tkinter import filedialog

from utils import timestamp_to_seconds, validate_timestamp
from worker import CutJob


class CutRow(ctk.CTkFrame):
    """Single start / end / filename row with a remove button."""

    def __init__(self, parent, on_remove):
        super().__init__(parent, fg_color="transparent")

        ctk.CTkLabel(self, text="Start:").pack(side="left", padx=(0, 2))
        self.start_entry = ctk.CTkEntry(self, width=90, placeholder_text="HH:MM:SS")
        self.start_entry.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(self, text="End:").pack(side="left", padx=(0, 2))
        self.end_entry = ctk.CTkEntry(self, width=90, placeholder_text="HH:MM:SS")
        self.end_entry.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(self, text="Output name:").pack(side="left", padx=(0, 2))
        self.name_entry = ctk.CTkEntry(self, width=200, placeholder_text="clip_name")
        self.name_entry.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            self, text="Remove", width=70, fg_color="gray", hover_color="#555555",
            command=lambda: on_remove(self),
        ).pack(side="left")

    def get_values(self) -> tuple[str, str, str]:
        return (
            self.start_entry.get().strip(),
            self.end_entry.get().strip(),
            self.name_entry.get().strip(),
        )


class CutTab(ctk.CTkFrame):
    def __init__(self, parent, config, job_queue):
        super().__init__(parent)
        self.config = config
        self.job_queue = job_queue
        self._job_ids: set[int] = set()
        self.cut_rows: list[CutRow] = []

        # -- Source file picker -----------------------------------------------
        src_frame = ctk.CTkFrame(self, fg_color="transparent")
        src_frame.pack(fill="x", padx=10, pady=(10, 5))
        ctk.CTkLabel(src_frame, text="Source video:").pack(side="left")
        self.source_var = ctk.StringVar()
        ctk.CTkEntry(src_frame, textvariable=self.source_var, width=450).pack(side="left", padx=5)
        ctk.CTkButton(src_frame, text="Browse", width=70, command=self._browse_source).pack(side="left")

        # -- Output folder picker ---------------------------------------------
        out_frame = ctk.CTkFrame(self, fg_color="transparent")
        out_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(out_frame, text="Output folder:").pack(side="left")
        self.folder_var = ctk.StringVar(value=config.cut_folder)
        ctk.CTkEntry(out_frame, textvariable=self.folder_var, width=400).pack(side="left", padx=5)
        ctk.CTkButton(out_frame, text="Browse", width=70, command=self._browse_folder).pack(side="left")

        # -- Dynamic cut rows (scrollable) ------------------------------------
        self.rows_frame = ctk.CTkScrollableFrame(self, height=150)
        self.rows_frame.pack(fill="x", padx=10, pady=5)
        self._add_row()  # start with one row

        # -- Action buttons ---------------------------------------------------
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(btn_row, text="Add Cut", width=100, command=self._add_row).pack(side="left", padx=(0, 10))

        self.delete_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(btn_row, text="Delete source video after cutting", variable=self.delete_var).pack(
            side="left", padx=(0, 10),
        )

        ctk.CTkButton(btn_row, text="Process All Cuts", command=self._process).pack(side="left")

        # -- Progress bar -----------------------------------------------------
        self.progress = ctk.CTkProgressBar(self)
        self.progress.pack(fill="x", padx=10, pady=5)
        self.progress.set(0)

        # -- Log area ---------------------------------------------------------
        self.log = ctk.CTkTextbox(self, state="disabled")
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # -- row management -------------------------------------------------------

    def _add_row(self):
        row = CutRow(self.rows_frame, self._remove_row)
        row.pack(fill="x", pady=2)
        self.cut_rows.append(row)

    def _remove_row(self, row: CutRow):
        if len(self.cut_rows) <= 1:
            return
        self.cut_rows.remove(row)
        row.destroy()

    # -- file pickers ---------------------------------------------------------

    def _browse_source(self):
        path = filedialog.askopenfilename(
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.webm *.mov *.flv"), ("All files", "*.*")],
        )
        if path:
            self.source_var.set(path)

    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or None)
        if folder:
            self.folder_var.set(folder)
            self.config.cut_folder = folder
            self.config.save()

    # -- process cuts ---------------------------------------------------------

    def _process(self):
        source = self.source_var.get().strip()
        if not source or not os.path.isfile(source):
            self._log("Select a valid source video file.")
            return

        folder = self.folder_var.get().strip()
        if not folder:
            self._log("Select an output folder.")
            return

        self.config.cut_folder = folder
        self.config.save()

        # Validate all rows before queuing anything
        cuts: list[tuple[str, str, str]] = []
        for i, row in enumerate(self.cut_rows, 1):
            start, end, name = row.get_values()
            if not validate_timestamp(start):
                self._log(f"Row {i}: Invalid start timestamp '{start}'. Use HH:MM:SS.")
                return
            if not validate_timestamp(end):
                self._log(f"Row {i}: Invalid end timestamp '{end}'. Use HH:MM:SS.")
                return
            if timestamp_to_seconds(end) <= timestamp_to_seconds(start):
                self._log(f"Row {i}: End must be after Start.")
                return
            if not name:
                self._log(f"Row {i}: Output filename is required.")
                return
            if "." not in os.path.basename(name):
                name += ".mp4"
            cuts.append((start, end, name))

        if not cuts:
            self._log("No cuts defined.")
            return

        delete_source = self.delete_var.get()

        for i, (start, end, name) in enumerate(cuts):
            is_last = i == len(cuts) - 1
            job = CutJob(
                input_file=source,
                start=start,
                end=end,
                output_path=os.path.join(folder, name),
                delete_source=delete_source and is_last,
            )
            self._job_ids.add(job.job_id)
            self.job_queue.put(job)

        self._log(f"Queued {len(cuts)} cut(s).")
        self.progress.set(0)

    # -- result handling ------------------------------------------------------

    def handle_result(self, msg: dict):
        if msg.get("tab") != "cut" or msg["job_id"] not in self._job_ids:
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
        elif t == "delete_source":
            try:
                os.remove(msg["path"])
                self._log(f"Deleted source: {os.path.basename(msg['path'])}")
            except OSError as e:
                self._log(f"Failed to delete source: {e}")

    def on_cancel(self):
        self._job_ids.clear()
        self._log("Cancelled all cuts.")
        self.progress.set(0)

    # -- helpers --------------------------------------------------------------

    def _log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
