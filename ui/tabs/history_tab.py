import customtkinter as ctk
from core.history import history_db

class HistoryTab(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header Frame
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        self.header_label = ctk.CTkLabel(header_frame, text="Download History", font=ctk.CTkFont(size=20, weight="bold"))
        self.header_label.grid(row=0, column=0, sticky="w")

        self.refresh_btn = ctk.CTkButton(header_frame, text="Refresh", width=80, command=self.load_history)
        self.refresh_btn.grid(row=0, column=1, sticky="e", padx=(0, 10))

        self.clear_btn = ctk.CTkButton(header_frame, text="Clear All", width=80, fg_color="#C62828", hover_color="#B71C1C", command=self.clear_history)
        self.clear_btn.grid(row=0, column=2, sticky="e")

        # Table-like display
        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")

        self.load_history()

    def load_history(self):
        # Clear existing
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        history = history_db.get_all()
        if not history:
            lbl = ctk.CTkLabel(self.scroll_frame, text="No download history found.", text_color="gray")
            lbl.pack(pady=20)
            return

        for entry in history:
            row = ctk.CTkFrame(self.scroll_frame)
            row.pack(fill="x", padx=5, pady=2)
            row.grid_columnconfigure(0, weight=1)
            
            info = f"[{entry['date']}] {entry['platform']} - {entry['status']}\n{entry['url']}"
            lbl = ctk.CTkLabel(row, text=info, anchor="w", justify="left")
            lbl.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
            
            del_btn = ctk.CTkButton(row, text="X", width=30, fg_color="#C62828", hover_color="#B71C1C", 
                                    command=lambda e_id=entry['id']: self.delete_entry(e_id))
            del_btn.grid(row=0, column=1, padx=5, pady=5)

    def delete_entry(self, entry_id):
        history_db.delete_entry(entry_id)
        self.load_history()

    def clear_history(self):
        history_db.clear_history()
        self.load_history()
