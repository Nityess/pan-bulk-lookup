"""
IRD Nepal PAN Bulk Lookup - Desktop App
"""

import json
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd
from playwright.sync_api import sync_playwright

API_URL_PATTERN = "getPanSearch"

# --- Theme palette ---
BG = "#f4f6fb"          # window background
CARD = "#ffffff"        # panel/card background
TEXT = "#1f2933"        # primary text
MUTED = "#6b7280"       # secondary text
ACCENT = "#1a73e8"      # brand blue
GREEN = "#1e8e3e"       # start / found
GREEN_HOVER = "#176c30"
RED = "#d93025"         # stop / error
RED_HOVER = "#b3261e"
BORDER = "#e3e7ef"

ROW_FOUND = "#e6f4ea"
ROW_ERROR = "#fce8e6"
ROW_NOTFOUND = "#fef7e0"
ROW_STRIPE = "#f7f9fc"

COLUMNS = [
    ("pan", "PAN", 90),
    ("name_eng", "Name (English)", 200),
    ("name_nep", "Name (Nepali)", 180),
    ("address", "Address", 150),
    ("ward", "Ward", 50),
    ("phone", "Phone", 110),
    ("office", "Office", 160),
    ("reg_date", "Reg. Date", 90),
    ("acct_status", "Acct Status", 80),
    ("tax_clearance", "Tax Clearance", 90),
    ("status", "Status", 80),
]


def get_browser_path():
    if getattr(sys, "_MEIPASS", None):
        p = os.path.join(sys._MEIPASS, "ms-playwright", "chromium-1208", "chrome-win64", "chrome.exe")
        if os.path.exists(p):
            return p
    # Also check next to the exe (onedir mode)
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    p = os.path.join(exe_dir, "ms-playwright", "chromium-1208", "chrome-win64", "chrome.exe")
    if os.path.exists(p):
        return p
    return None


def parse_result(data):
    row = {}
    details = data.get("panDetails", [])
    if details:
        d = details[0]
        row["PAN"] = d.get("pan", "")
        row["Name (English)"] = d.get("trade_Name_Eng", "")
        row["Name (Nepali)"] = d.get("trade_Name_Nep", "")
        row["Address"] = d.get("vdc_Town", "")
        row["Street"] = d.get("street_Name", "")
        row["Ward"] = d.get("ward_No", "")
        row["Phone"] = d.get("telephone", "")
        row["Mobile"] = d.get("mobile", "")
        row["Office"] = d.get("office_Name", "")
        row["Registration Date"] = d.get("eff_Reg_Date", "")
        row["Account Type"] = d.get("acctType", "")
        row["Account Status"] = d.get("account_Status", "")
        row["Is Personal"] = d.get("is_Personal", "")

    biz = data.get("businessDetail", [])
    if biz:
        row["Business Names"] = " | ".join(b.get("trade_Name_Eng", "") for b in biz)

    reg = data.get("panRegistrationDetail", [])
    if reg:
        row["Filing Period"] = reg[0].get("filing_Period", "")

    tc = data.get("panTaxClearance", [])
    if tc:
        t = tc[0]
        row["Tax Clearance FY"] = t.get("fiscal_Year", "")
        row["Tax Clearance Date"] = t.get("return_Verified_Date", "")
        row["Tax Clearance Status"] = "Cleared" if t.get("exists_Yn") == "Y" else "Not Cleared"

    return row


class HoverButton(tk.Button):
    """A flat button that lightens/darkens on hover for a modern feel."""

    def __init__(self, master, hover_bg=None, **kw):
        super().__init__(master, **kw)
        self._base_bg = kw.get("bg", self.cget("bg"))
        self._hover_bg = hover_bg or self._base_bg
        self.configure(relief="flat", bd=0, cursor="hand2",
                       activebackground=self._hover_bg,
                       highlightthickness=0)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _):
        if str(self["state"]) != "disabled":
            self.configure(bg=self._hover_bg)

    def _on_leave(self, _):
        self.configure(bg=self._base_bg)


class PanLookupApp:
    def __init__(self, root):
        self.root = root
        self.root.title("IRD Nepal — PAN Bulk Lookup")
        self.root.geometry("1120x680")
        self.root.minsize(940, 520)
        self.root.configure(bg=BG)

        self.pans = []
        self.results = []
        self.result_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.worker_threads = []

        self._setup_style()
        self._build_header()
        self._build_file_section()
        self._build_controls()
        self._build_progress()
        self._build_table()
        self._build_statusbar()

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # --- Styling ---

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)

        # Treeview
        style.configure(
            "Treeview",
            background=CARD,
            fieldbackground=CARD,
            foreground=TEXT,
            rowheight=26,
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            background="#eef1f7",
            foreground=MUTED,
            relief="flat",
            font=("Segoe UI Semibold", 9),
            padding=(6, 6),
        )
        style.map("Treeview.Heading", background=[("active", "#e2e7f1")])
        style.map("Treeview",
                  background=[("selected", "#cfe2ff")],
                  foreground=[("selected", TEXT)])

        # Progress bar
        style.configure(
            "Brand.Horizontal.TProgressbar",
            troughcolor=BORDER,
            background=ACCENT,
            thickness=8,
            borderwidth=0,
        )

        # Scrollbars
        style.configure("Vertical.TScrollbar", background="#d7dce6",
                        troughcolor=BG, borderwidth=0, arrowsize=12)
        style.configure("Horizontal.TScrollbar", background="#d7dce6",
                        troughcolor=BG, borderwidth=0, arrowsize=12)

    def _build_header(self):
        header = tk.Frame(self.root, bg=ACCENT, height=58)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(header, text="PAN Bulk Lookup", bg=ACCENT, fg="white",
                 font=("Segoe UI Semibold", 16)).pack(side=tk.LEFT, padx=20)
        tk.Label(header, text="Inland Revenue Department · Nepal", bg=ACCENT,
                 fg="#dbe7ff", font=("Segoe UI", 10)).pack(side=tk.LEFT, pady=(6, 0))

        tk.Label(header, text="ca.nityes", bg=ACCENT, fg="white",
                 font=("Segoe UI Semibold", 12)).pack(side=tk.RIGHT, padx=20)

    def _card(self, pad_y=(10, 0)):
        """Create a white rounded-look card container packed into the window."""
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill=tk.X, padx=16, pady=pad_y)
        card = tk.Frame(outer, bg=CARD, highlightbackground=BORDER,
                        highlightthickness=1, bd=0)
        card.pack(fill=tk.X)
        return card

    def _build_file_section(self):
        card = self._card(pad_y=(14, 0))
        frame = tk.Frame(card, bg=CARD, padx=14, pady=12)
        frame.pack(fill=tk.X)

        tk.Label(frame, text="Input file", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 10))

        self.file_var = tk.StringVar()
        entry = tk.Entry(frame, textvariable=self.file_var, state="readonly",
                         font=("Segoe UI", 10), relief="flat",
                         readonlybackground="#f0f3f9", fg=TEXT,
                         highlightbackground=BORDER, highlightthickness=1)
        entry.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True, ipady=5)

        self.browse_btn = HoverButton(frame, text="Browse…", command=self.select_file,
                                      font=("Segoe UI Semibold", 10), bg="#eef1f7",
                                      hover_bg="#e2e7f1", fg=TEXT, padx=16, pady=6)
        self.browse_btn.pack(side=tk.LEFT)

        self.count_label = tk.Label(frame, text="", bg=CARD, fg=ACCENT,
                                    font=("Segoe UI Semibold", 10))
        self.count_label.pack(side=tk.LEFT, padx=(14, 0))

    def _build_controls(self):
        card = self._card(pad_y=(10, 0))
        frame = tk.Frame(card, bg=CARD, padx=14, pady=12)
        frame.pack(fill=tk.X)

        self.start_btn = HoverButton(frame, text="▶  Start Lookup", command=self.start_lookup,
                                     font=("Segoe UI Semibold", 10), bg=GREEN,
                                     hover_bg=GREEN_HOVER, fg="white", padx=18, pady=7,
                                     state=tk.DISABLED, disabledforeground="#cfd6df")
        self.start_btn.pack(side=tk.LEFT)

        self.stop_btn = HoverButton(frame, text="■  Stop", command=self.stop_lookup,
                                    font=("Segoe UI Semibold", 10), bg=RED,
                                    hover_bg=RED_HOVER, fg="white", padx=18, pady=7,
                                    state=tk.DISABLED, disabledforeground="#e7c9c6")
        self.stop_btn.pack(side=tk.LEFT, padx=(10, 0))

        self.export_btn = HoverButton(frame, text="⭳  Export Results", command=self.export_results,
                                      font=("Segoe UI Semibold", 10), bg="#eef1f7",
                                      hover_bg="#e2e7f1", fg=TEXT, padx=18, pady=7,
                                      state=tk.DISABLED, disabledforeground="#aab2bd")
        self.export_btn.pack(side=tk.LEFT, padx=(10, 0))

        # Delay control on the right
        self.delay_var = tk.StringVar(value="0")
        tk.Spinbox(frame, from_=0, to=10, textvariable=self.delay_var, width=4,
                   font=("Segoe UI", 10), relief="flat", justify="center",
                   highlightbackground=BORDER, highlightthickness=1,
                   buttonbackground="#eef1f7").pack(side=tk.RIGHT)
        tk.Label(frame, text="Delay (sec)", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side=tk.RIGHT, padx=(0, 6))

        # Parallel-tabs control
        self.workers_var = tk.StringVar(value="3")
        tk.Spinbox(frame, from_=1, to=6, textvariable=self.workers_var, width=4,
                   font=("Segoe UI", 10), relief="flat", justify="center",
                   highlightbackground=BORDER, highlightthickness=1,
                   buttonbackground="#eef1f7").pack(side=tk.RIGHT, padx=(0, 18))
        tk.Label(frame, text="Parallel tabs", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side=tk.RIGHT, padx=(0, 6))

    def _build_progress(self):
        card = self._card(pad_y=(10, 0))
        frame = tk.Frame(card, bg=CARD, padx=14, pady=12)
        frame.pack(fill=tk.X)

        self.progress = ttk.Progressbar(frame, mode="determinate",
                                        style="Brand.Horizontal.TProgressbar")
        self.progress.pack(fill=tk.X, side=tk.TOP)

        self.status_var = tk.StringVar(value="Ready — select a file to begin")
        tk.Label(frame, textvariable=self.status_var, bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9), anchor=tk.W).pack(fill=tk.X, pady=(8, 0))

    def _build_table(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=16, pady=(10, 0))
        frame = tk.Frame(outer, bg=CARD, highlightbackground=BORDER,
                         highlightthickness=1, bd=0)
        frame.pack(fill=tk.BOTH, expand=True)

        col_ids = [c[0] for c in COLUMNS]
        self.tree = ttk.Treeview(frame, columns=col_ids, show="headings", selectmode="browse")

        for col_id, heading, width in COLUMNS:
            self.tree.heading(col_id, text=heading)
            anchor = tk.CENTER if col_id in ("ward", "status", "acct_status") else tk.W
            self.tree.column(col_id, width=width, minwidth=50, anchor=anchor)

        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        self.tree.tag_configure("found", background=ROW_FOUND)
        self.tree.tag_configure("error", background=ROW_ERROR)
        self.tree.tag_configure("notfound", background=ROW_NOTFOUND)
        self.tree.tag_configure("stripe", background=ROW_STRIPE)

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=BG, height=30)
        bar.pack(fill=tk.X, padx=16, pady=(6, 10))
        self.summary_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.summary_var, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9), anchor=tk.W).pack(side=tk.LEFT)
        tk.Label(bar, text="ca.nityes", bg=BG, fg=ACCENT,
                 font=("Segoe UI Semibold", 9), anchor=tk.E).pack(side=tk.RIGHT)

    # --- File ---

    def select_file(self):
        filepath = filedialog.askopenfilename(
            title="Select file with PAN numbers",
            filetypes=[("Excel/CSV", "*.xlsx *.xls *.csv"), ("All files", "*.*")]
        )
        if not filepath:
            return

        self.file_var.set(filepath)
        path = Path(filepath)

        try:
            if path.suffix.lower() in (".xlsx", ".xls"):
                df = pd.read_excel(path, header=None, dtype=str)
            else:
                df = pd.read_csv(path, header=None, dtype=str)

            pans = df.iloc[:, 0].dropna().str.strip().tolist()
            self.pans = [p for p in pans if re.fullmatch(r"\d{9}", p)]

            if not self.pans:
                self.count_label.config(text="No valid PANs!", fg=RED)
                self.start_btn.config(state=tk.DISABLED)
                messagebox.showwarning("No PANs", "No valid 9-digit PAN numbers found in the first column.")
                return

            self.count_label.config(text=f"{len(self.pans)} PANs found", fg=ACCENT)
            self.start_btn.config(state=tk.NORMAL)
            self.status_var.set(f"Loaded {len(self.pans)} PAN numbers — click Start Lookup")

        except Exception as e:
            messagebox.showerror("Error", f"Could not read file:\n{e}")

    # --- Lookup ---

    def start_lookup(self):
        if not self.pans:
            return

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.results = []

        self.progress["value"] = 0
        self.progress["maximum"] = len(self.pans)
        self.stop_event.clear()
        self.summary_var.set("")
        self._error_shown = False

        self.browse_btn.config(state=tk.DISABLED)
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.export_btn.config(state=tk.DISABLED)

        try:
            num_workers = max(1, min(6, int(self.workers_var.get())))
        except ValueError:
            num_workers = 1
        num_workers = min(num_workers, len(self.pans))

        try:
            delay = max(0, int(self.delay_var.get()))
        except ValueError:
            delay = 0

        # Shared work queue — each worker pulls the next PAN as it finishes.
        self.task_queue = queue.Queue()
        for pan in self.pans:
            self.task_queue.put(pan)

        self.total_to_process = len(self.pans)
        self.workers_done = 0
        self.workers_lock = threading.Lock()

        self.worker_threads = []
        for wid in range(num_workers):
            t = threading.Thread(target=self._worker,
                                 args=(wid, num_workers, delay), daemon=True)
            t.start()
            self.worker_threads.append(t)
        self.worker_thread = self.worker_threads[0]  # for liveness checks
        self._poll_queue()

    def stop_lookup(self):
        self.stop_event.set()
        self.stop_btn.config(state=tk.DISABLED)
        self.status_var.set("Stopping…")

    def _worker(self, wid, num_workers, delay):
        """One worker owns its own browser + page and pulls PANs from the shared
        queue until it's empty or the user stops. Runs concurrently with peers."""
        try:
            with sync_playwright() as pw:
                browser_path = get_browser_path()
                launch_args = {"headless": True}
                if browser_path:
                    launch_args["executable_path"] = browser_path

                browser = pw.chromium.launch(**launch_args)
                page = browser.new_page()

                if wid == 0:
                    self.result_queue.put(("progress", 0, self.total_to_process,
                                           f"Loading IRD website ({num_workers} tabs)…"))
                page.goto("https://ird.gov.np/pan-search", wait_until="networkidle", timeout=60000)

                while not self.stop_event.is_set():
                    try:
                        pan = self.task_queue.get_nowait()
                    except queue.Empty:
                        break

                    self.result_queue.put(("progress", 0, self.total_to_process,
                                           f"Looking up PAN {pan}…"))

                    try:
                        pan_input = page.locator("#pan")
                        pan_input.fill("")
                        pan_input.fill(pan)

                        with page.expect_response(
                            lambda r: API_URL_PATTERN in r.url, timeout=30000
                        ) as resp_info:
                            page.locator("#submit").click()

                        response = resp_info.value
                        body = response.body().decode("utf-8", errors="replace")
                        api_data = json.loads(body)

                        if api_data.get("data"):
                            row = parse_result(api_data["data"])
                            row["Status"] = "Found"
                        else:
                            row = {"PAN": pan, "Status": "Not Found"}

                    except Exception:
                        row = {"PAN": pan, "Status": "Error"}
                        # Lightweight recovery: only reload if the input field is gone.
                        try:
                            if page.locator("#pan").count() == 0:
                                page.goto("https://ird.gov.np/pan-search",
                                          wait_until="networkidle", timeout=60000)
                        except Exception:
                            try:
                                page.goto("https://ird.gov.np/pan-search",
                                          wait_until="networkidle", timeout=60000)
                            except Exception:
                                pass

                    self.result_queue.put(("result", row))

                    if delay > 0 and not self.stop_event.is_set():
                        time.sleep(delay)

                browser.close()

        except Exception as e:
            self.result_queue.put(("error", str(e)))

        # Signal "done" only when the LAST worker finishes.
        with self.workers_lock:
            self.workers_done += 1
            if self.workers_done >= len(self.worker_threads):
                self.result_queue.put(("done", ""))

    def _poll_queue(self):
        try:
            while True:
                msg = self.result_queue.get_nowait()
                kind = msg[0]

                if kind == "result":
                    row = msg[1]
                    self.results.append(row)
                    self._add_row(row)
                    self.progress["value"] = len(self.results)
                    self._update_summary()

                elif kind == "progress":
                    _, current, total, text = msg
                    self.status_var.set(f"[{len(self.results)}/{total}] {text}")

                elif kind == "error":
                    # A worker crashed (e.g. browser launch failed). Surface it
                    # once, but let remaining workers and the queue carry on.
                    if not getattr(self, "_error_shown", False):
                        self._error_shown = True
                        messagebox.showerror("Error", f"A lookup worker failed:\n{msg[1]}")

                elif kind == "done":
                    found = sum(1 for r in self.results if r.get("Status") == "Found")
                    self.status_var.set(
                        f"Done — {found} found, {len(self.results) - found} failed out of {len(self.results)}"
                    )
                    self._update_summary()
                    self._finish()
                    return

        except queue.Empty:
            pass

        any_alive = any(t.is_alive() for t in getattr(self, "worker_threads", []))
        if any_alive:
            self.root.after(80, self._poll_queue)

    def _add_row(self, row):
        status = row.get("Status", "")
        if status == "Found":
            tag = "found"
        elif "Error" in status:
            tag = "error"
        else:
            tag = "notfound"

        values = (
            row.get("PAN", ""),
            row.get("Name (English)", ""),
            row.get("Name (Nepali)", ""),
            row.get("Address", ""),
            row.get("Ward", ""),
            row.get("Phone", ""),
            row.get("Office", ""),
            row.get("Registration Date", ""),
            row.get("Account Status", ""),
            row.get("Tax Clearance Status", ""),
            status,
        )
        self.tree.insert("", tk.END, values=values, tags=(tag,))
        self.tree.yview_moveto(1.0)

    def _update_summary(self):
        total = len(self.results)
        found = sum(1 for r in self.results if r.get("Status") == "Found")
        notfound = sum(1 for r in self.results if r.get("Status") == "Not Found")
        errors = total - found - notfound
        self.summary_var.set(
            f"Processed {total}   ·   ✓ {found} found   ·   {notfound} not found   ·   ✗ {errors} errors"
        )

    def _finish(self):
        self.browse_btn.config(state=tk.NORMAL)
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        if self.results:
            self.export_btn.config(state=tk.NORMAL)

    # --- Export ---

    def export_results(self):
        if not self.results:
            messagebox.showwarning("No Data", "No results to export.")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
            initialfile="pan_results"
        )
        if not filepath:
            return

        df = pd.DataFrame(self.results)
        columns = [
            "PAN", "Name (English)", "Name (Nepali)", "Address", "Street", "Ward",
            "Phone", "Mobile", "Office", "Registration Date", "Account Type",
            "Account Status", "Is Personal", "Business Names", "Filing Period",
            "Tax Clearance FY", "Tax Clearance Date", "Tax Clearance Status", "Status"
        ]
        df = df[[c for c in columns if c in df.columns]]

        if filepath.endswith(".csv"):
            df.to_csv(filepath, index=False, encoding="utf-8-sig")
        else:
            df.to_excel(filepath, index=False, engine="openpyxl")

        messagebox.showinfo("Exported", f"Results saved to:\n{filepath}")

    # --- Close ---

    def _on_closing(self):
        any_alive = any(t.is_alive() for t in getattr(self, "worker_threads", []))
        if any_alive:
            if messagebox.askokcancel("Quit", "Lookup is still running. Stop and quit?"):
                self.stop_event.set()
                self.root.destroy()
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    PanLookupApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
