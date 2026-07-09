import customtkinter as ctk

class ProgressRow(ctk.CTkFrame):
    def __init__(self, master, task, **kwargs):
        super().__init__(master, **kwargs)
        self.task = task
        
        self.grid_columnconfigure(1, weight=1)

        # Title Label
        self.title_label = ctk.CTkLabel(self, text=task.url, anchor="w")
        self.title_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="ew")

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, columnspan=2, padx=10, pady=(5, 5), sticky="ew")

        # Status Label (Speed, ETA, Size)
        self.status_label = ctk.CTkLabel(self, text="Starting...", font=("Arial", 11), text_color="gray")
        self.status_label.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="w")

        # Cancel Button
        self.cancel_button = ctk.CTkButton(self, text="Cancel", width=60, fg_color="#C62828", hover_color="#B71C1C", command=self.cancel_download)
        self.cancel_button.grid(row=2, column=1, padx=10, pady=(0, 10), sticky="e")

    def update_progress(self, d):
        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '0%').strip()
            # Clean string because yt-dlp returns ANSI escape codes sometimes
            import re
            percent_str = re.sub(r'\x1b\[[0-9;]*m', '', percent_str)
            try:
                percent = float(percent_str.replace('%', ''))
                self.progress_bar.set(percent / 100)
            except ValueError:
                pass

            speed = d.get('_speed_str', 'N/A')
            speed = re.sub(r'\x1b\[[0-9;]*m', '', speed)
            
            eta = d.get('_eta_str', 'N/A')
            eta = re.sub(r'\x1b\[[0-9;]*m', '', eta)

            self.status_label.configure(text=f"Downloading... {percent_str} at {speed} ETA: {eta}")
        
        elif d['status'] == 'finished':
            self.progress_bar.set(1)
            self.status_label.configure(text="Finished downloading, merging/processing...")
            self.cancel_button.configure(state="disabled")
            
        elif d['status'] == 'error':
            self.status_label.configure(text="Error occurred.", text_color="#C62828")

    def cancel_download(self):
        self.task.cancel()
        self.status_label.configure(text="Cancelled.", text_color="#C62828")
        self.cancel_button.configure(state="disabled")

    def mark_completed(self):
        self.progress_bar.set(1)
        self.status_label.configure(text="Completed.", text_color="#2E7D32")
        self.cancel_button.configure(state="disabled")

    def mark_error(self, err_msg):
        self.status_label.configure(text=f"Failed: {err_msg}", text_color="#C62828")
        self.cancel_button.configure(state="disabled")
