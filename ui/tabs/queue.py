import customtkinter as ctk
from ui.components.progress_row import ProgressRow

class QueueTab(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        self.header_label = ctk.CTkLabel(self, text="Download Queue", font=ctk.CTkFont(size=20, weight="bold"))
        self.header_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        # Scrollable Frame for downloads
        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")

        self.rows = []

    def add_download(self, task):
        row = ProgressRow(self.scroll_frame, task)
        row.pack(fill="x", padx=5, pady=5)
        self.rows.append(row)
        return row
