import json
import os
import queue
import threading
import wave
from datetime import datetime
from pathlib import Path

import numpy as np
import requests
import sounddevice as sd
import tkinter as tk
from tkinter import messagebox
from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://api.gapgpt.app/v1"
TRANSCRIPT_PATH = "/audio/transcriptions"
CHAT_PATH = "/chat/completions"

DEFAULT_TRANSCRIPTION_MODEL = "gapgpt/whisper-1"
DEFAULT_ARTICULATION_MODEL = "openai/gpt-4o-mini"

ENV_FILE = ".env"
RECORDINGS_DIR = Path("recordings")
TRANSCRIPTS_DIR = Path("transcripts")

COLORS = {
    "bg": "#1e1e2e",
    "fg": "#cdd6f4",
    "primary": "#89b4fa",
    "primary_hover": "#74c7ec",
    "secondary": "#a6e3a1",
    "secondary_hover": "#94e2d5",
    "danger": "#f38ba8",
    "danger_hover": "#eba0ac",
    "surface": "#313244",
    "surface_light": "#45475a",
    "border": "#585b70",
    "muted": "#6c7086",
}

FONTS = {
    "title": ("Segoe UI", 14, "bold"),
    "label": ("Segoe UI", 10, "bold"),
    "normal": ("Segoe UI", 10),
    "small": ("Segoe UI", 9),
    "text": ("Tahoma", 11),
}


class ModernButton(tk.Canvas):
    def __init__(self, parent, text, command, color="primary", font=None, **kwargs):
        super().__init__(
            parent,
            width=150,
            height=38,
            bg=parent.cget("bg") if parent.cget("bg") else COLORS["surface"],
            highlightthickness=0,
            bd=0,
            **kwargs
        )
        self.command = command
        self.color = color
        self.enabled = True

        self._base_color = COLORS.get(color, COLORS["primary"])
        self._hover_color = COLORS.get(f"{color}_hover", COLORS["primary_hover"])

        self.rect = self.create_rectangle(2, 2, 148, 36, fill=self._base_color, outline="")
        self.text_item = self.create_text(
            75,
            19,
            text=text,
            fill="#1e1e2e",
            font=font or FONTS["normal"]
        )

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.config(cursor="hand2")

    def _on_enter(self, event):
        if self.enabled:
            self.itemconfig(self.rect, fill=self._hover_color)

    def _on_leave(self, event):
        if self.enabled:
            self.itemconfig(self.rect, fill=self._base_color)

    def _on_click(self, event):
        if self.enabled and self.command:
            self.command()

    def set_state(self, state):
        self.enabled = state != "disabled"
        if self.enabled:
            self.itemconfig(self.rect, fill=self._base_color)
            self.itemconfig(self.text_item, fill="#1e1e2e")
            self.config(cursor="hand2")
        else:
            self.itemconfig(self.rect, fill=COLORS["muted"])
            self.itemconfig(self.text_item, fill="#c0c0c0")
            self.config(cursor="arrow")


class ModernEntry(tk.Entry):
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            bg=COLORS["surface_light"],
            fg=COLORS["fg"],
            insertbackground=COLORS["fg"],
            selectbackground=COLORS["primary"],
            selectforeground="#1e1e2e",
            highlightthickness=1,
            highlightcolor=COLORS["border"],
            highlightbackground=COLORS["border"],
            bd=0,
            relief="flat",
            **kwargs
        )


class TranscriptCard(tk.Frame):
    def __init__(self, parent, transcript_text, timestamp, on_delete=None):
        super().__init__(
            parent,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            bd=0
        )

        self.transcript_text = transcript_text

        header = tk.Frame(self, bg=COLORS["surface"])
        header.pack(fill="x", padx=10, pady=(8, 4))

        time_label = tk.Label(
            header,
            text=timestamp,
            bg=COLORS["surface"],
            fg=COLORS["primary"],
            font=FONTS["small"]
        )
        time_label.pack(side="left")

        btn_frame = tk.Frame(header, bg=COLORS["surface"])
        btn_frame.pack(side="right")

        copy_btn = tk.Button(
            btn_frame,
            text="Copy",
            bg=COLORS["surface_light"],
            fg=COLORS["fg"],
            font=FONTS["small"],
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self._copy_text
        )
        copy_btn.pack(side="left", padx=(0, 5))

        if on_delete:
            delete_btn = tk.Button(
                btn_frame,
                text="Delete",
                bg=COLORS["surface_light"],
                fg=COLORS["danger"],
                font=FONTS["small"],
                bd=0,
                relief="flat",
                cursor="hand2",
                command=on_delete
            )
            delete_btn.pack(side="left")

        text_frame = tk.Frame(self, bg=COLORS["surface_light"])
        text_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.text_widget = tk.Text(
            text_frame,
            bg=COLORS["surface_light"],
            fg=COLORS["fg"],
            font=FONTS["text"],
            bd=0,
            padx=8,
            pady=8,
            wrap="word",
            relief="flat",
            height=6
        )
        self.text_widget.pack(side="left", fill="both", expand=True)
        self.text_widget.insert("1.0", transcript_text)
        self.text_widget.config(state="disabled")

        scrollbar = tk.Scrollbar(text_frame, orient="vertical", command=self.text_widget.yview)
        scrollbar.pack(side="right", fill="y")
        self.text_widget.configure(yscrollcommand=scrollbar.set)

    def _copy_text(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.transcript_text)
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to copy text: {exc}")


class GapGPTTranscriberApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("GapGPT Voice Transcriber")
        self.root.geometry("1100x750")
        self.root.configure(bg=COLORS["bg"])

        load_dotenv(ENV_FILE)

        self.api_key_var = tk.StringVar(value=os.getenv("GAPGPT_API_KEY", ""))
        self.base_url_var = tk.StringVar(value=os.getenv("GAPGPT_BASE_URL", DEFAULT_BASE_URL))
        self.transcription_model_var = tk.StringVar(
            value=os.getenv("GAPGPT_TRANSCRIPTION_MODEL", DEFAULT_TRANSCRIPTION_MODEL)
        )
        self.articulation_model_var = tk.StringVar(
            value=os.getenv("GAPGPT_ARTICULATION_MODEL", DEFAULT_ARTICULATION_MODEL)
        )
        self.sample_rate_var = tk.StringVar(value=os.getenv("AUDIO_SAMPLE_RATE", "16000"))
        self.channels_var = tk.StringVar(value=os.getenv("AUDIO_CHANNELS", "1"))
        self.enable_articulation_var = tk.BooleanVar(
            value=os.getenv("ENABLE_ARTICULATION", "true").strip().lower() == "true"
        )

        self.status_var = tk.StringVar(value="Idle")
        self.error_var = tk.StringVar(value="")
        self.last_file_var = tk.StringVar(value="")

        self.is_recording = False
        self.is_cancelled = False
        self.audio_chunks = []
        self.audio_queue = queue.Queue()
        self.stream = None
        self.transcripts = []
        self.settings_collapsed = True
        self.show_api_key = False

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._load_existing_transcripts)

    def _build_ui(self) -> None:
        main = tk.Frame(self.root, bg=COLORS["bg"])
        main.pack(fill="both", expand=True, padx=20, pady=20)
        main.rowconfigure(5, weight=1)
        main.columnconfigure(0, weight=1)

        title = tk.Label(
            main,
            text="GapGPT Voice Transcriber",
            bg=COLORS["bg"],
            fg=COLORS["primary"],
            font=("Segoe UI", 18, "bold")
        )
        title.grid(row=0, column=0, sticky="w", pady=(0, 15))

        self.settings_frame = tk.Frame(
            main,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1
        )
        self.settings_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))

        self.settings_toggle = tk.Button(
            self.settings_frame,
            text="Settings",
            bg=COLORS["surface_light"],
            fg=COLORS["fg"],
            font=FONTS["small"],
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self._toggle_settings
        )
        self.settings_toggle.pack(fill="x", padx=10, pady=10)

        self._settings_inner_ref = tk.Frame(self.settings_frame, bg=COLORS["surface"])

        controls = tk.Frame(main, bg=COLORS["bg"])
        controls.grid(row=2, column=0, sticky="w", pady=(0, 15))

        self.start_button = ModernButton(
            controls,
            text="Start Recording",
            command=self.start_recording,
            color="secondary",
            font=FONTS["label"]
        )
        self.start_button.pack(side="left", padx=(0, 10))

        self.stop_button = ModernButton(
            controls,
            text="Stop Recording",
            command=self.stop_recording,
            color="danger",
            font=FONTS["label"]
        )
        self.stop_button.pack(side="left", padx=(0, 10))
        self.stop_button.set_state("disabled")

        self.cancel_button = ModernButton(
            controls,
            text="Cancel",
            command=self.cancel_operation,
            color="danger",
            font=FONTS["label"]
        )
        self.cancel_button.pack(side="left")
        self.cancel_button.set_state("disabled")

        status_frame = tk.Frame(main, bg=COLORS["surface"])
        status_frame.grid(row=3, column=0, sticky="ew", pady=(0, 15))

        self.status_indicator = tk.Label(
            status_frame,
            text="●",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 12)
        )
        self.status_indicator.pack(side="left", padx=(10, 8), pady=8)

        tk.Label(
            status_frame,
            textvariable=self.status_var,
            bg=COLORS["surface"],
            fg=COLORS["fg"],
            font=FONTS["small"]
        ).pack(side="left", fill="x", expand=True)

        tk.Label(
            status_frame,
            textvariable=self.error_var,
            bg=COLORS["surface"],
            fg=COLORS["danger"],
            font=FONTS["small"],
            wraplength=700,
            justify="right"
        ).pack(side="right", padx=10)

        header = tk.Frame(main, bg=COLORS["bg"])
        header.grid(row=4, column=0, sticky="ew", pady=(0, 5))

        tk.Label(
            header,
            text="Transcripts",
            bg=COLORS["bg"],
            fg=COLORS["primary"],
            font=("Segoe UI", 13, "bold")
        ).pack(side="left")

        self.transcript_count_label = tk.Label(
            header,
            text="(0)",
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=FONTS["small"]
        )
        self.transcript_count_label.pack(side="left", padx=(5, 0))

        clear_btn = tk.Button(
            header,
            text="Clear All",
            bg=COLORS["surface_light"],
            fg=COLORS["danger"],
            font=FONTS["small"],
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self.clear_all_transcripts
        )
        clear_btn.pack(side="right")

        transcripts_container = tk.Frame(main, bg=COLORS["bg"])
        transcripts_container.grid(row=5, column=0, sticky="nsew")

        self.transcripts_canvas = tk.Canvas(
            transcripts_container,
            bg=COLORS["bg"],
            highlightthickness=0
        )
        self.transcripts_canvas.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(
            transcripts_container,
            orient="vertical",
            command=self.transcripts_canvas.yview
        )
        scrollbar.pack(side="right", fill="y")
        self.transcripts_canvas.configure(yscrollcommand=scrollbar.set)

        self.transcripts_inner = tk.Frame(self.transcripts_canvas, bg=COLORS["bg"])
        self.canvas_window = self.transcripts_canvas.create_window(
            (0, 0),
            window=self.transcripts_inner,
            anchor="nw"
        )

        self.transcripts_canvas.bind("<Configure>", self._on_canvas_configure)
        self.transcripts_inner.bind(
            "<Configure>",
            lambda e: self.transcripts_canvas.configure(
                scrollregion=self.transcripts_canvas.bbox("all")
            )
        )
        self.transcripts_inner.bind(
            "<Enter>",
            lambda e: self.transcripts_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        )
        self.transcripts_inner.bind(
            "<Leave>",
            lambda e: self.transcripts_canvas.unbind_all("<MouseWheel>")
        )

    def _build_settings_content(self):
        try:
            self._settings_inner_ref.destroy()
        except Exception:
            pass

        self._settings_inner_ref = tk.Frame(self.settings_frame, bg=COLORS["surface"])
        self._settings_inner_ref.pack(fill="x", padx=10, pady=(0, 10))
        self._settings_inner_ref.columnconfigure(1, weight=1)

        row = 0

        tk.Label(
            self._settings_inner_ref,
            text="API Key",
            bg=COLORS["surface"],
            fg=COLORS["fg"],
            font=FONTS["label"]
        ).grid(row=row, column=0, sticky="w", pady=8)

        api_frame = tk.Frame(self._settings_inner_ref, bg=COLORS["surface"])
        api_frame.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=8)
        api_frame.columnconfigure(0, weight=1)

        self.api_key_entry = ModernEntry(
            api_frame,
            textvariable=self.api_key_var,
            show="*" if not self.show_api_key else "",
            width=50
        )
        self.api_key_entry.grid(row=0, column=0, sticky="ew")

        tk.Button(
            api_frame,
            text="Show" if not self.show_api_key else "Hide",
            bg=COLORS["surface_light"],
            fg=COLORS["fg"],
            font=FONTS["small"],
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self._toggle_api_key_visibility
        ).grid(row=0, column=1, padx=(5, 0))

        row += 1

        tk.Label(
            self._settings_inner_ref,
            text="Base URL",
            bg=COLORS["surface"],
            fg=COLORS["fg"],
            font=FONTS["label"]
        ).grid(row=row, column=0, sticky="w", pady=8)

        ModernEntry(
            self._settings_inner_ref,
            textvariable=self.base_url_var,
            width=50
        ).grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=8)

        row += 1

        tk.Label(
            self._settings_inner_ref,
            text="Transcription Model",
            bg=COLORS["surface"],
            fg=COLORS["fg"],
            font=FONTS["label"]
        ).grid(row=row, column=0, sticky="w", pady=8)

        ModernEntry(
            self._settings_inner_ref,
            textvariable=self.transcription_model_var,
            width=50
        ).grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=8)

        row += 1

        tk.Label(
            self._settings_inner_ref,
            text="Articulation Model",
            bg=COLORS["surface"],
            fg=COLORS["fg"],
            font=FONTS["label"]
        ).grid(row=row, column=0, sticky="w", pady=8)

        ModernEntry(
            self._settings_inner_ref,
            textvariable=self.articulation_model_var,
            width=50
        ).grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=8)

        row += 1

        articulation_checkbox = tk.Checkbutton(
            self._settings_inner_ref,
            text="Enable articulation after transcription",
            variable=self.enable_articulation_var,
            bg=COLORS["surface"],
            fg=COLORS["fg"],
            selectcolor=COLORS["surface_light"],
            activebackground=COLORS["surface"],
            activeforeground=COLORS["fg"],
            font=FONTS["small"]
        )
        articulation_checkbox.grid(row=row, column=1, sticky="w", padx=(10, 0), pady=8)

        row += 1

        audio_row = tk.Frame(self._settings_inner_ref, bg=COLORS["surface"])
        audio_row.grid(row=row, column=0, columnspan=2, sticky="w", pady=8)

        tk.Label(
            audio_row,
            text="Sample Rate",
            bg=COLORS["surface"],
            fg=COLORS["fg"],
            font=FONTS["label"]
        ).pack(side="left", padx=(0, 5))

        ModernEntry(
            audio_row,
            textvariable=self.sample_rate_var,
            width=10
        ).pack(side="left", padx=(0, 20))

        tk.Label(
            audio_row,
            text="Channels",
            bg=COLORS["surface"],
            fg=COLORS["fg"],
            font=FONTS["label"]
        ).pack(side="left", padx=(0, 5))

        ModernEntry(
            audio_row,
            textvariable=self.channels_var,
            width=10
        ).pack(side="left")

        row += 1

        tk.Button(
            self._settings_inner_ref,
            text="Save Settings",
            bg=COLORS["secondary"],
            fg="#1e1e2e",
            font=FONTS["label"],
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self.save_settings
        ).grid(row=row, column=1, sticky="e", pady=(10, 0))

    def _toggle_settings(self):
        self.settings_collapsed = not self.settings_collapsed
        if self.settings_collapsed:
            try:
                self._settings_inner_ref.pack_forget()
            except Exception:
                pass
        else:
            self._build_settings_content()

    def _toggle_api_key_visibility(self):
        self.show_api_key = not self.show_api_key
        self._build_settings_content()

    def _on_canvas_configure(self, event):
        self.transcripts_canvas.itemconfig(self.canvas_window, width=event.width)
        self.transcripts_canvas.configure(scrollregion=self.transcripts_canvas.bbox("all"))

    def _on_mousewheel(self, event):
        self.transcripts_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _load_existing_transcripts(self):
        TRANSCRIPTS_DIR.mkdir(exist_ok=True)
        transcript_files = sorted(TRANSCRIPTS_DIR.glob("transcript_*.txt"))

        self.transcripts = []
        for tf in transcript_files:
            try:
                content = tf.read_text(encoding="utf-8").strip()
                if not content:
                    continue

                name = tf.stem
                parts = name.split("_", 1)
                if len(parts) == 2:
                    raw_stamp = parts[1]
                    try:
                        dt = datetime.strptime(raw_stamp, "%Y%m%d_%H%M%S")
                        timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        timestamp = raw_stamp
                else:
                    timestamp = tf.stem

                self.transcripts.append({
                    "file": str(tf),
                    "content": content,
                    "timestamp": timestamp
                })
            except Exception as exc:
                print(f"Error loading {tf}: {exc}")

        self._update_transcripts_display()

    def _update_transcripts_display(self):
        for widget in self.transcripts_inner.winfo_children():
            widget.destroy()

        count = len(self.transcripts)
        self.transcript_count_label.config(text=f"({count})")

        if not self.transcripts:
            empty_label = tk.Label(
                self.transcripts_inner,
                text="No transcripts yet. Start recording to create one!",
                bg=COLORS["bg"],
                fg=COLORS["muted"],
                font=FONTS["normal"]
            )
            empty_label.pack(pady=50)
        else:
            for idx, transcript_data in enumerate(self.transcripts):
                card = TranscriptCard(
                    self.transcripts_inner,
                    transcript_data["content"],
                    transcript_data["timestamp"],
                    on_delete=lambda i=idx: self._delete_transcript(i)
                )
                card.pack(fill="x", pady=5, padx=2)

        self.transcripts_inner.update_idletasks()
        self.transcripts_canvas.configure(scrollregion=self.transcripts_canvas.bbox("all"))

    def _delete_transcript(self, index):
        if not (0 <= index < len(self.transcripts)):
            return

        if messagebox.askyesno("Delete", "Delete this transcript?"):
            try:
                file_path = self.transcripts[index].get("file")
                if file_path:
                    Path(file_path).unlink(missing_ok=True)
            except Exception as exc:
                messagebox.showerror("Error", f"Failed to delete file: {exc}")

            self.transcripts.pop(index)
            self._update_transcripts_display()
            self.set_status("Transcript deleted")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)
        text_lower = text.lower()
        if "recording" in text_lower or "complete" in text_lower:
            self.status_indicator.config(fg=COLORS["secondary"])
        elif "error" in text_lower or "failed" in text_lower:
            self.status_indicator.config(fg=COLORS["danger"])
        else:
            self.status_indicator.config(fg=COLORS["muted"])
        self.root.update_idletasks()

    def set_error(self, text: str) -> None:
        self.error_var.set(text)
        self.root.update_idletasks()

    def clear_error(self) -> None:
        self.set_error("")

    def set_last_file(self, path: str) -> None:
        self.last_file_var.set(path)
        self.root.update_idletasks()

    def audio_callback(self, indata, frames, time_info, status) -> None:
        if self.is_cancelled:
            return
        if status:
            self.audio_queue.put(("error", str(status)))
        self.audio_queue.put(("audio", indata.copy()))

    def start_recording(self) -> None:
        if self.is_recording:
            return

        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showerror("Missing API Key", "Set GAPGPT_API_KEY in .env or enter it in the app.")
            return

        try:
            sample_rate = int(self.sample_rate_var.get().strip())
            channels = int(self.channels_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Audio Settings", "Sample rate and channels must be integers.")
            return

        self.audio_chunks = []
        self.audio_queue = queue.Queue()
        self.is_cancelled = False
        self.clear_error()

        try:
            self.stream = sd.InputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype="int16",
                callback=self.audio_callback
            )
            self.stream.start()
        except Exception as exc:
            self.set_error(f"Failed to start recording: {exc}")
            self.set_status("Recording failed")
            return

        self.is_recording = True
        self.start_button.set_state("disabled")
        self.stop_button.set_state("normal")
        self.cancel_button.set_state("normal")
        self.set_status("Recording...")
        self.root.after(100, self.process_audio_queue)

    def process_audio_queue(self) -> None:
        if self.is_cancelled:
            return

        while not self.audio_queue.empty():
            item_type, payload = self.audio_queue.get()
            if item_type == "error":
                self.set_error(payload)
            elif item_type == "audio":
                self.audio_chunks.append(payload)

        if self.is_recording:
            self.root.after(100, self.process_audio_queue)

    def stop_recording(self) -> None:
        if not self.is_recording:
            return

        self.is_recording = False

        try:
            if self.stream is not None:
                self.stream.stop()
                self.stream.close()
                self.stream = None
        except Exception as exc:
            self.set_error(f"Failed to stop recording cleanly: {exc}")

        while not self.audio_queue.empty():
            item_type, payload = self.audio_queue.get()
            if item_type == "error":
                self.set_error(payload)
            elif item_type == "audio":
                self.audio_chunks.append(payload)

        self.start_button.set_state("normal")
        self.stop_button.set_state("disabled")
        self.cancel_button.set_state("disabled")

        if not self.audio_chunks:
            self.set_status("No audio captured")
            return

        self.set_status("Saving WAV and uploading...")
        threading.Thread(target=self.save_and_transcribe, daemon=True).start()

    def cancel_operation(self) -> None:
        if self.is_recording:
            self.is_cancelled = True
            self.set_status("Cancelling...")
            try:
                if self.stream is not None:
                    self.stream.stop()
                    self.stream.close()
                    self.stream = None
            except Exception:
                pass

            self.is_recording = False
            self.audio_chunks = []
            self.audio_queue = queue.Queue()
            self.start_button.set_state("normal")
            self.stop_button.set_state("disabled")
            self.cancel_button.set_state("disabled")
            self.set_status("Recording cancelled")
        elif self.status_var.get().lower() in {"transcribing...", "articulating..."}:
            self.is_cancelled = True
            self.set_status("Operation cancelled")

    def save_and_transcribe(self) -> None:
        try:
            sample_rate = int(self.sample_rate_var.get().strip())
            channels = int(self.channels_var.get().strip())
            audio_data = np.concatenate(self.audio_chunks, axis=0)

            RECORDINGS_DIR.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            wav_path = RECORDINGS_DIR / f"recording_{timestamp}.wav"

            with wave.open(str(wav_path), "wb") as wav_writer:
                wav_writer.setnchannels(channels)
                wav_writer.setsampwidth(2)
                wav_writer.setframerate(sample_rate)
                wav_writer.writeframes(audio_data.tobytes())

            self.root.after(0, self.set_last_file, str(wav_path))
            self.root.after(0, lambda: self.set_status("Transcribing..."))

            raw_transcript = self.send_transcription(str(wav_path), "audio/wav")

            if self.is_cancelled:
                self.root.after(0, lambda: self.set_status("Operation cancelled"))
                return

            final_transcript = raw_transcript
            if self.enable_articulation_var.get() and raw_transcript.strip():
                self.root.after(0, lambda: self.set_status("Articulating..."))
                final_transcript = self.articulate_text(raw_transcript)

            if (
                not self.is_cancelled
                and final_transcript.strip()
                and not final_transcript.startswith("[JSON response but no transcript text found]")
                and final_transcript != "[Empty response body from server]"
            ):
                TRANSCRIPTS_DIR.mkdir(exist_ok=True)
                transcript_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                transcript_file = TRANSCRIPTS_DIR / f"transcript_{transcript_timestamp}.txt"
                transcript_file.write_text(final_transcript, encoding="utf-8")

                display_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.transcripts.append({
                    "file": str(transcript_file),
                    "content": final_transcript,
                    "timestamp": display_timestamp
                })

                def update_ui():
                    self._update_transcripts_display()
                    self.transcripts_canvas.update_idletasks()
                    self.transcripts_canvas.yview_moveto(1.0)
                    self.set_status("Transcription complete")
                    self.clear_error()

                self.root.after(0, update_ui)
            else:
                self.root.after(0, lambda: self.set_status("Operation cancelled or empty"))

        except Exception as exc:
            if not self.is_cancelled:
                self.root.after(0, lambda e=exc: self.set_error(f"Operation failed: {exec}"))
                self.root.after(0, lambda: self.set_status("Error"))

    def send_transcription(self, file_path: str, mime_type: str) -> str:
        base_url = self.base_url_var.get().strip().rstrip("/")
        api_key = self.api_key_var.get().strip()
        model = self.transcription_model_var.get().strip()

        if not base_url:
            raise ValueError("Base URL is empty.")
        if not api_key:
            raise ValueError("API key is empty.")
        if not model:
            raise ValueError("Transcription model is empty.")

        url = f"{base_url}{TRANSCRIPT_PATH}"
        headers = {"Authorization": f"Bearer {api_key}"}

        with open(file_path, "rb") as file_obj:
            files = {"file": (Path(file_path).name, file_obj, mime_type)}
            data = {"model": model}
            response = requests.post(
                url,
                headers=headers,
                files=files,
                data=data,
                timeout=300
            )

        raw_text = response.text.strip()

        if not response.ok:
            raise RuntimeError(f"{response.status_code} {raw_text}")

        content_type = response.headers.get("content-type", "").lower()

        if "application/json" in content_type:
            payload = response.json()
            extracted = self.extract_transcript(payload)
            if extracted:
                return extracted
            pretty = json.dumps(payload, indent=2, ensure_ascii=False)
            return "[JSON response but no transcript text found]\n\n" + pretty

        if raw_text:
            return raw_text

        return "[Empty response body from server]"

    def articulate_text(self, raw_text: str) -> str:
        base_url = self.base_url_var.get().strip().rstrip("/")
        api_key = self.api_key_var.get().strip()
        model = self.articulation_model_var.get().strip()

        if not base_url:
            raise ValueError("Base URL is empty.")
        if not api_key:
            raise ValueError("API key is empty.")
        if not model:
            raise ValueError("Articulation model is empty.")

        url = f"{base_url}{CHAT_PATH}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        system_prompt = (
            "You are an expert transcription editor. "
            "Rewrite the transcript so it is grammatically correct, clear, natural, "
            "and well-punctuated while preserving the original meaning. "
            "Remove filler words only when they do not add meaning, such as: uh, um, you know, like."
            "don t mention your change & correction"
            "you can add suggestion about topic(not as editor as specialized person in that field) but it should come after @."
            "your sugesstion should t be too long"
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text},
            ],
            "temperature": 0.2,
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            raw_response = response.text.strip()

            if not response.ok:
                raise RuntimeError(f"{response.status_code} {raw_response}")

            content_type = response.headers.get("content-type", "").lower()

            if "application/json" in content_type:
                data = response.json()
                articulated = self.extract_chat_content(data)
                if articulated:
                    return articulated

            if raw_response:
                return raw_response

            return raw_text
        except Exception as exc:
            self.root.after(0, lambda: self.set_error(f"Articulation failed, using raw transcript: {exec}"))
            return raw_text

    def extract_transcript(self, payload) -> str:
        if isinstance(payload, str):
            return payload.strip()

        if isinstance(payload, dict):
            for key in ("text", "output_text", "transcript", "content"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

            for key in ("data", "result", "message"):
                nested = payload.get(key)
                if nested is not None:
                    result = self.extract_transcript(nested)
                    if result:
                        return result

            choices = payload.get("choices")
            if isinstance(choices, list):
                for choice in choices:
                    result = self.extract_transcript(choice)
                    if result:
                        return result

        if isinstance(payload, list):
            for item in payload:
                result = self.extract_transcript(item)
                if result:
                    return result

        return ""

    def extract_chat_content(self, payload) -> str:
        if isinstance(payload, dict):
            choices = payload.get("choices")
            if isinstance(choices, list):
                for choice in choices:
                    message = choice.get("message")
                    if isinstance(message, dict):
                        content = message.get("content")
                        if isinstance(content, str) and content.strip():
                            return content.strip()

                        if isinstance(content, list):
                            parts = []
                            for item in content:
                                if isinstance(item, dict):
                                    text_value = item.get("text")
                                    if isinstance(text_value, str) and text_value.strip():
                                        parts.append(text_value.strip())
                            if parts:
                                return "\n".join(parts)

            for key in ("output_text", "text", "content"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

            for value in payload.values():
                result = self.extract_chat_content(value)
                if result:
                    return result

        if isinstance(payload, list):
            for item in payload:
                result = self.extract_chat_content(item)
                if result:
                    return result

        if isinstance(payload, str):
            return payload.strip()

        return ""

    def save_settings(self) -> None:
        env_text = (
            f'GAPGPT_API_KEY="{self.api_key_var.get().strip()}"\n'
            f'GAPGPT_BASE_URL="{self.base_url_var.get().strip()}"\n'
            f'GAPGPT_TRANSCRIPTION_MODEL="{self.transcription_model_var.get().strip()}"\n'
            f'GAPGPT_ARTICULATION_MODEL="{self.articulation_model_var.get().strip()}"\n'
            f'ENABLE_ARTICULATION="{str(self.enable_articulation_var.get()).lower()}"\n'
            f'AUDIO_SAMPLE_RATE="{self.sample_rate_var.get().strip()}"\n'
            f'AUDIO_CHANNELS="{self.channels_var.get().strip()}"\n'
        )
        Path(ENV_FILE).write_text(env_text, encoding="utf-8")
        self.set_status(f"Saved settings to {ENV_FILE}")

    def clear_all_transcripts(self) -> None:
        if messagebox.askyesno("Clear All", "Delete all transcripts?"):
            for item in self.transcripts:
                try:
                    file_path = item.get("file")
                    if file_path:
                        Path(file_path).unlink(missing_ok=True)
                except Exception:
                    pass

            self.transcripts.clear()
            self._update_transcripts_display()
            self.set_status("All transcripts cleared")

    def on_close(self) -> None:
        if self.is_recording:
            try:
                self.stop_recording()
            except Exception:
                pass
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    GapGPTTranscriberApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
