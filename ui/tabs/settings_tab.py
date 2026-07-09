import customtkinter as ctk
from core.config import config
from core.utils import get_default_download_folder
import tkinter.filedialog as filedialog

MAX_CONCURRENT = 10  # Hard ceiling the user can choose up to

class SettingsTab(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.scroll_frame.grid_columnconfigure(1, weight=1)

        row = 0

        # ── Header ────────────────────────────────────────────────────────
        ctk.CTkLabel(
            self.scroll_frame, text="⚙  Settings",
            font=ctk.CTkFont(size=20, weight="bold")
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 20))
        row += 1

        # ══ General ═══════════════════════════════════════════════════════
        self._section("General", row)
        row += 1

        # Download folder
        ctk.CTkLabel(self.scroll_frame, text="Download Folder:").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        folder_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        folder_frame.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        folder_frame.grid_columnconfigure(0, weight=1)

        self.folder_var = ctk.StringVar(
            value=config.get("general", "download_folder") or get_default_download_folder()
        )
        ctk.CTkEntry(folder_frame, textvariable=self.folder_var, state="readonly").grid(
            row=0, column=0, sticky="ew"
        )
        ctk.CTkButton(folder_frame, text="Browse", width=70, command=self.browse_folder).grid(
            row=0, column=1, padx=(8, 0)
        )
        row += 1

        # Theme
        ctk.CTkLabel(self.scroll_frame, text="Theme:").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        self.theme_var = ctk.StringVar(value=config.get("general", "theme") or "dark")
        ctk.CTkOptionMenu(
            self.scroll_frame,
            values=["dark", "light", "system"],
            variable=self.theme_var,
            command=self.change_theme,
        ).grid(row=row, column=1, sticky="w", padx=10, pady=5)
        row += 1

        # ══ Network ═══════════════════════════════════════════════════════
        self._section("Network", row)
        row += 1

        # Concurrent downloads slider (1 – MAX_CONCURRENT)
        ctk.CTkLabel(self.scroll_frame, text="Concurrent Downloads:").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )

        slider_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        slider_frame.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
        slider_frame.grid_columnconfigure(0, weight=1)

        current_val = int(config.get("network", "concurrent_downloads") or 3)
        current_val = max(1, min(current_val, MAX_CONCURRENT))

        self.concurrent_var = ctk.IntVar(value=current_val)
        self.concurrent_label = ctk.CTkLabel(
            slider_frame,
            text=str(current_val),
            font=ctk.CTkFont(size=14, weight="bold"),
            width=30,
        )
        self.concurrent_label.grid(row=0, column=1, padx=(10, 0))

        self.concurrent_slider = ctk.CTkSlider(
            slider_frame,
            from_=1,
            to=MAX_CONCURRENT,
            number_of_steps=MAX_CONCURRENT - 1,
            variable=self.concurrent_var,
            command=self._on_slider_change,
        )
        self.concurrent_slider.grid(row=0, column=0, sticky="ew")

        # Hint label under slider
        ctk.CTkLabel(
            slider_frame,
            text=f"Default: 3  •  Max: {MAX_CONCURRENT}",
            font=("Arial", 10),
            text_color="gray",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        row += 1

        # Retry count
        ctk.CTkLabel(self.scroll_frame, text="Retry Count:").grid(
            row=row, column=0, sticky="w", padx=10, pady=5
        )
        self.retry_var = ctk.StringVar(value=str(config.get("network", "retry_count") or "5"))
        ctk.CTkEntry(self.scroll_frame, textvariable=self.retry_var, width=80).grid(
            row=row, column=1, sticky="w", padx=10, pady=5
        )
        row += 1

        # ══ Save Button ════════════════════════════════════════════════════
        self.save_btn = ctk.CTkButton(
            self.scroll_frame, text="💾  Save Settings", height=40, command=self.save_settings
        )
        self.save_btn.grid(row=row, column=0, columnspan=2, pady=30)

        self.save_label = ctk.CTkLabel(self.scroll_frame, text="", font=("Arial", 12))
        self.save_label.grid(row=row + 1, column=0, columnspan=2)

    # ─── Helpers ──────────────────────────────────────────────────────────
    def _section(self, title: str, row: int):
        ctk.CTkLabel(
            self.scroll_frame, text=title,
            font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=(20, 5))

    def _on_slider_change(self, value):
        v = int(value)
        self.concurrent_label.configure(text=str(v))

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get())
        if folder:
            self.folder_var.set(folder)

    def change_theme(self, choice: str):
        ctk.set_appearance_mode(choice)

    def save_settings(self):
        config.set("general", "download_folder", self.folder_var.get())
        config.set("general", "theme", self.theme_var.get())
        config.set("network", "concurrent_downloads", int(self.concurrent_var.get()))
        try:
            config.set("network", "retry_count", int(self.retry_var.get()))
        except ValueError:
            pass
        config.save_config()
        self.save_label.configure(text="✅  Settings saved.", text_color="#4CAF50")
        self.after(3000, lambda: self.save_label.configure(text=""))
