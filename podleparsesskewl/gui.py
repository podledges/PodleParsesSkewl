"""Small Windows-friendly graphical launcher for the local CLI."""

from __future__ import annotations

import io
import threading
import tkinter as tk
import webbrowser
from contextlib import redirect_stderr, redirect_stdout
from tkinter import filedialog, messagebox, ttk

from podleparsesskewl.cli import main as cli_main
from podleparsesskewl.deps import inspect_environment
from podleparsesskewl.workflow import (
    build_notes_argv,
    build_parse_argv,
    suggested_archive_path,
    suggested_output_path,
)

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/"


class Launcher(tk.Tk):
    """A deliberately thin GUI: all parsing remains owned by the CLI."""

    def __init__(self) -> None:
        super().__init__()
        self.title("PodleSkewl - Lecture review")
        self.geometry("740x620")
        self.minsize(660, 560)
        self.configure(bg="#fff8ed")
        self._recording = tk.StringVar()
        self._output = tk.StringVar()
        self._transcript = tk.StringVar()
        self._archive = tk.StringVar(value=suggested_archive_path())
        self._archive_inputs = tk.BooleanVar(value=True)
        self._status = tk.StringVar(value="Choose an MP4 recording to begin.")
        self._busy = False
        self._build()
        self.after(100, self._check_ffmpeg)

    def _build(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#fff8ed")
        style.configure("TLabel", background="#fff8ed", foreground="#203040", font=("Segoe UI", 10))
        style.configure("Title.TLabel", foreground="#d45532", font=("Segoe UI", 22, "bold"))
        style.configure("Hint.TLabel", foreground="#617080", font=("Segoe UI", 9))
        style.configure("TCheckbutton", background="#fff8ed", foreground="#203040", font=("Segoe UI", 10))
        style.configure("TButton", padding=(12, 7), font=("Segoe UI", 10))
        style.configure("Accent.TButton", background="#d45532", foreground="white", font=("Segoe UI", 10, "bold"))
        style.configure("TProgressbar", background="#d45532", troughcolor="#f3e6d8")

        outer = ttk.Frame(self, padding=28)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="PodleSkewl", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Turn one lecture recording into a reviewable Lecture Document, or into teaching notes.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(2, 18))
        self._path_row(outer, "Recording (MP4)", self._recording, self._choose_recording)
        self._path_row(outer, "Output folder (optional)", self._output, self._choose_output)
        self._path_row(outer, "Caption sidecar (optional)", self._transcript, self._choose_transcript)
        self._path_row(outer, "Archive folder (notes)", self._archive, self._choose_archive)
        ttk.Label(
            outer,
            text="Leave output empty to use the configured default, or a folder next to the recording. "
            "Parse + Notes can move the input into a unique archive folder after success.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(4, 8))
        ttk.Checkbutton(
            outer,
            text="After Parse + Notes, move the input into the archive (never overwrite)",
            variable=self._archive_inputs,
        ).pack(anchor="w", pady=(0, 14))
        actions = ttk.Frame(outer)
        actions.pack(anchor="w", fill="x")
        self._parse_button = ttk.Button(actions, text="Parse", command=lambda: self._start("parse"))
        self._parse_button.pack(side="left")
        self._notes_button = ttk.Button(
            actions,
            text="Parse + Notes",
            style="Accent.TButton",
            command=lambda: self._start("notes"),
        )
        self._notes_button.pack(side="left", padx=(10, 0))
        self._progress = ttk.Progressbar(outer, mode="indeterminate")
        self._progress.pack(fill="x", pady=(18, 6))
        ttk.Label(outer, textvariable=self._status, wraplength=670).pack(anchor="w", pady=(4, 8))
        self._log = tk.Text(outer, height=10, state="disabled", bg="#fffdf9", fg="#203040", relief="flat", font=("Consolas", 9))
        self._log.pack(fill="both", expand=True)

    def _path_row(self, parent: ttk.Frame, label: str, variable: tk.StringVar, command: object) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=26).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, text="Browse...", command=command).pack(side="right")

    def _choose_recording(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("MP4 recordings", "*.mp4"), ("All files", "*.*")])
        if path:
            self._recording.set(path)
            if not self._output.get().strip():
                self._output.set(suggested_output_path(path))
            if not self._archive.get().strip():
                self._archive.set(suggested_archive_path(path))

    def _choose_output(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self._output.set(path)

    def _choose_transcript(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Caption files", "*.srt *.vtt *.json"), ("All files", "*.*")])
        if path:
            self._transcript.set(path)

    def _choose_archive(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self._archive.set(path)

    def _check_ffmpeg(self) -> None:
        if not inspect_environment().can_parse_video:
            self._status.set("ffmpeg and ffprobe are required. Install them, then reopen or retry.")
            if messagebox.askyesno(
                "ffmpeg is required",
                "PodleParsesSkewl needs ffmpeg and ffprobe to read MP4 files. Open the Windows download instructions?",
            ):
                webbrowser.open(FFMPEG_URL)

    def _start(self, mode: str) -> None:
        if self._busy:
            return
        recording = self._recording.get().strip()
        if not recording:
            messagebox.showinfo("Choose a recording", "Select an MP4 recording first.")
            return
        output = self._output.get().strip()
        transcript = self._transcript.get().strip()
        archive_dir = self._archive.get().strip()
        archive = bool(self._archive_inputs.get())
        if mode == "parse":
            argv = build_parse_argv(recording, output, transcript)
            working = "Parsing locally... this window may take a while for transcription."
        else:
            argv = build_notes_argv(recording, output, transcript, archive_dir, archive)
            working = "Parsing and writing notes locally... input files move only after success."
        self._set_log("")
        self._status.set(working)
        self._set_busy(True)
        threading.Thread(target=self._run, args=(mode, argv), daemon=True).start()

    def _run(self, mode: str, argv: list[str]) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(buffer):
            code = cli_main(argv)
        self.after(0, self._finished, mode, code, buffer.getvalue())

    def _finished(self, mode: str, code: int, text: str) -> None:
        self._set_busy(False)
        self._set_log(text)
        if code == 0 and mode == "parse":
            self._status.set("Parse finished. Lecture Document and HTML review are ready.")
            messagebox.showinfo("Review ready", "The Lecture Document and HTML review were created.")
            return
        if code == 0:
            archived = (
                "Archive skipped."
                if "Archive   skipped" in text
                else "Input was moved into a unique archive folder."
            )
            self._status.set(f"Parse + Notes finished. {archived}")
            messagebox.showinfo(
                "Notes ready",
                "lecture.present.html was written next to the Lecture Document.\n\n" + archived,
            )
            return
        self._status.set("Could not finish. See the log. Notes stay in the output folder if they were written.")
        messagebox.showerror(
            "Could not finish",
            "The run failed. If archive had not started, the input is still in place. See the log.",
        )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self._parse_button.configure(state=state)
        self._notes_button.configure(state=state)
        if busy:
            self._progress.start(12)
        else:
            self._progress.stop()

    def _set_log(self, text: str) -> None:
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.insert("end", text)
        self._log.configure(state="disabled")


def main() -> None:
    Launcher().mainloop()


if __name__ == "__main__":
    main()
