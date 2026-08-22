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

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/"


class Launcher(tk.Tk):
    """A deliberately thin GUI: all parsing remains owned by the CLI."""

    def __init__(self) -> None:
        super().__init__()
        self.title("PodleParsesSkewl - Lecture review")
        self.geometry("700x470")
        self.minsize(620, 420)
        self.configure(bg="#fff8ed")
        self._recording = tk.StringVar()
        self._output = tk.StringVar()
        self._transcript = tk.StringVar()
        self._status = tk.StringVar(value="Choose an MP4 recording to begin.")
        self._build()
        self.after(100, self._check_ffmpeg)

    def _build(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#fff8ed")
        style.configure("TLabel", background="#fff8ed", foreground="#203040", font=("Segoe UI", 10))
        style.configure("Title.TLabel", foreground="#d45532", font=("Segoe UI", 22, "bold"))
        style.configure("Hint.TLabel", foreground="#617080", font=("Segoe UI", 9))
        style.configure("TButton", padding=(12, 7), font=("Segoe UI", 10))
        style.configure("Accent.TButton", background="#d45532", foreground="white", font=("Segoe UI", 10, "bold"))

        outer = ttk.Frame(self, padding=28)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="PodleParsesSkewl", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Turn one lecture recording into a reviewable Lecture Document.", style="Hint.TLabel").pack(anchor="w", pady=(2, 24))
        self._path_row(outer, "Recording (MP4)", self._recording, self._choose_recording)
        self._path_row(outer, "Output folder (optional)", self._output, self._choose_output)
        self._path_row(outer, "Caption sidecar (optional)", self._transcript, self._choose_transcript)
        ttk.Label(outer, text="A .srt, .vtt, or .json beside the MP4 is detected automatically.", style="Hint.TLabel").pack(anchor="w", pady=(4, 18))
        ttk.Button(outer, text="Create Lecture Review", style="Accent.TButton", command=self._start).pack(anchor="w")
        ttk.Label(outer, textvariable=self._status, wraplength=630).pack(anchor="w", pady=(22, 8))
        self._log = tk.Text(outer, height=8, state="disabled", bg="#fffdf9", fg="#203040", relief="flat", font=("Consolas", 9))
        self._log.pack(fill="both", expand=True)

    def _path_row(self, parent: ttk.Frame, label: str, variable: tk.StringVar, command: object) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=25).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, text="Browse...", command=command).pack(side="right")

    def _choose_recording(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("MP4 recordings", "*.mp4"), ("All files", "*.*")])
        if path:
            self._recording.set(path)

    def _choose_output(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self._output.set(path)

    def _choose_transcript(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Caption files", "*.srt *.vtt *.json"), ("All files", "*.*")])
        if path:
            self._transcript.set(path)

    def _check_ffmpeg(self) -> None:
        if not inspect_environment().can_parse_video:
            self._status.set("ffmpeg and ffprobe are required. Install them, then reopen or retry.")
            if messagebox.askyesno("ffmpeg is required", "PodleParsesSkewl needs ffmpeg and ffprobe to read MP4 files. Open the Windows download instructions?"):
                webbrowser.open(FFMPEG_URL)

    def _start(self) -> None:
        recording = self._recording.get().strip()
        if not recording:
            messagebox.showinfo("Choose a recording", "Select an MP4 recording first.")
            return
        output = self._output.get().strip()
        transcript = self._transcript.get().strip()
        self._set_log("")
        self._status.set("Working locally... this window may take a while for transcription.")
        threading.Thread(target=self._run, args=(recording, output, transcript), daemon=True).start()

    def _run(self, recording: str, output: str, transcript: str) -> None:
        args = ["parse", recording]
        if output:
            args += ["--output", output]
        if transcript:
            args += ["--transcript", transcript]
        buffer = io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(buffer):
            code = cli_main(args)
        text = buffer.getvalue()
        self.after(0, self._finished, code, text)

    def _finished(self, code: int, text: str) -> None:
        self._set_log(text)
        self._status.set("Finished successfully." if code == 0 else "Could not create the review. See details below.")
        if code == 0:
            messagebox.showinfo("Review ready", "The Lecture Document and HTML review were created.")

    def _set_log(self, text: str) -> None:
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.insert("end", text)
        self._log.configure(state="disabled")


def main() -> None:
    Launcher().mainloop()


if __name__ == "__main__":
    main()
