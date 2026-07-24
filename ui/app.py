import customtkinter as ctk
from core.config import config
from ui.tabs.dashboard import DashboardTab
from ui.tabs.queue import QueueTab
from ui.tabs.history_tab import HistoryTab
from ui.tabs.settings_tab import SettingsTab
from ui.tabs.shorts_tab import ShortsTab


class App(ctk.CTk):
    def __init__(self):
        # ── Theme (must be set before CTk window is created) ───────────────
        ctk.set_appearance_mode(config.get("general", "theme") or "dark")
        ctk.set_default_color_theme("blue")

        super().__init__()

        # Hide while building to avoid half-drawn flash, then reveal at the end
        self.withdraw()

        # ── Window basics ──────────────────────────────────────────────────
        self.title("Media Downloader")
        self.minsize(820, 520)

        # ── Grid layout: sidebar | content ─────────────────────────────────
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ── Sidebar ────────────────────────────────────────────────────────
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)
        self.sidebar_frame.grid_rowconfigure(7, weight=1)

        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="🎬 Media\nDownloader",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20))

        nav_items = [
            ("  Dashboard", "dashboard"),
            ("  Queue",     "queue"),
            ("  History",   "history"),
            ("  Settings",  "settings"),
            ("  Shorts",    "shorts"),
        ]
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        for i, (label, tab_name) in enumerate(nav_items, start=1):
            btn = ctk.CTkButton(
                self.sidebar_frame,
                text=label,
                anchor="w",
                command=lambda t=tab_name: self.show_tab(t),
            )
            btn.grid(row=i, column=0, padx=15, pady=6, sticky="ew")
            self._nav_buttons[tab_name] = btn

        self.ver_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="Powered by yt-dlp",
            font=("Arial", 10),
            text_color="gray",
        )
        self.ver_label.grid(row=8, column=0, padx=10, pady=(0, 15))

        # ── Content area ───────────────────────────────────────────────────
        self.main_container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew")
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        # Build tabs (queue/history must exist before dashboard references them)
        self.queue_tab     = QueueTab(self.main_container)
        self.history_tab   = HistoryTab(self.main_container)
        self.settings_tab  = SettingsTab(self.main_container)
        self.dashboard_tab = DashboardTab(self.main_container, self)
        self.shorts_tab    = ShortsTab(self.main_container, self)

        self.tabs: dict[str, ctk.CTkFrame] = {
            "dashboard": self.dashboard_tab,
            "queue":     self.queue_tab,
            "history":   self.history_tab,
            "settings":  self.settings_tab,
            "shorts":    self.shorts_tab,
        }

        for tab in self.tabs.values():
            tab.grid(row=0, column=0, sticky="nsew")

        startup = config.get("general", "startup_behavior") or "dashboard"
        self.show_tab(startup if startup in self.tabs else "dashboard")

        # ── Show the window centred AFTER everything is built ──────────────
        self.after(0, self._show_centered)

    def _show_centered(self):
        """Centre and reveal the window once the event loop is running."""
        self.update_idletasks()                 # force layout calculation

        w, h = 1000, 640
        sw = self.winfo_screenwidth()  or 1536
        sh = self.winfo_screenheight() or 864

        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.deiconify()                        # reveal now that position is set
        self.state("normal")
        self.lift()
        self.attributes("-topmost", True)
        self.after(600, lambda: self.attributes("-topmost", False))
        self.focus_force()

    # ── Navigation ─────────────────────────────────────────────────────────
    def show_tab(self, name: str):
        for tab_name, tab in self.tabs.items():
            if tab_name == name:
                tab.grid()
                self._nav_buttons[tab_name].configure(fg_color=("gray75", "gray30"))
            else:
                tab.grid_remove()
                self._nav_buttons[tab_name].configure(fg_color=("gray70", "gray20"))
