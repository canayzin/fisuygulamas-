from __future__ import annotations

import random
import threading
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from bulk_firm_editor import ask_bulk_firms
from advanced_batch import (
    FailureStore,
    PendingBatchStore,
    SessionStore,
    build_balanced_print_jobs,
    build_filtered_jobs,
    build_matrix_status,
    check_integrity,
    filter_pending_jobs,
    get_last_receipt_number_for_firm,
    remove_jobs,
)
from complete_batch import FirmReceiptJob, PrintHistory, build_missing_firm_receipt_jobs, firm_identity
from date_randomizer import RandomDateTimeOptions, build_random_datetimes
from firm_dialog import ask_firm
from firm_manager import Firm, FirmManager
from printer_service import PrinterService
from receipt_formatter import ReceiptData, build_receipt_text
from template_editor import TemplateEditorFrame
from template_manager import TemplateManager

BASE_DIR = Path(__file__).resolve().parent
FIRMS_JSON = BASE_DIR / "firms.json"
TEMPLATE_JSON = BASE_DIR / "receipt_template.json"
OUTPUT_DIR = BASE_DIR / "receipts_output"
PRINT_HISTORY_JSON = BASE_DIR / "print_history.json"
PRINT_FAILURES_JSON = BASE_DIR / "print_failures.json"
PRINT_SESSIONS_JSON = BASE_DIR / "print_sessions.json"
PENDING_BATCH_JSON = BASE_DIR / "pending_batch.json"
TURKISH_CHAR_WARNING = (
    "Gerçekçi ve temiz baskı için Türkçe karakter kullanmayın: "
    "Ç yerine C, Ğ yerine G, İ yerine I, Ş yerine S, Ü yerine U, Ö yerine O."
)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Oyun Fiş Yazdırıcı (58mm ESC/POS)")
        self.root.geometry("1180x780")
        self.root.minsize(980, 680)

        self.firm_manager = FirmManager(FIRMS_JSON)
        self.firms = self.firm_manager.load()
        self.template_manager = TemplateManager(TEMPLATE_JSON)
        self.receipt_template = self.template_manager.load()
        self.printer_service = PrinterService()
        self.print_history = PrintHistory(PRINT_HISTORY_JSON)
        self.failure_store = FailureStore(PRINT_FAILURES_JSON)
        self.session_store = SessionStore(PRINT_SESSIONS_JSON)
        self.pending_store = PendingBatchStore(PENDING_BATCH_JSON)
        self.stop_batch = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.print_count = 0
        self.batch_lock = threading.Lock()
        self.updating_selection = False

        self._init_vars()
        self._build_menu()
        self.printer_combos: list[ttk.Combobox] = []
        self._build_ui()
        self._wire_preview_updates()
        self._refresh_firm_list()
        self._refresh_printers()

    def _init_vars(self):
        self.product_var = tk.StringVar()
        self.amount_var = tk.StringVar(value="100.00")
        self.vat_var = tk.StringVar(value="20")
        self.pay_var = tk.StringVar(value="NAKIT")
        self.receipt_no_var = tk.StringVar(value="1")
        self.batch_receipt_no_var = tk.StringVar(value="1")
        self.manual_printer_var = tk.StringVar()
        self.selected_printer_var = tk.StringVar()

        self.batch_count_var = tk.StringVar(value="10")
        self.complete_batch_end_no_var = tk.StringVar(value="10")
        self.complete_batch_randomize_var = tk.BooleanVar(value=True)
        self.advanced_start_no_var = tk.StringVar(value="1")
        self.advanced_end_no_var = tk.StringVar(value="10")
        self.advanced_count_var = tk.StringVar(value="100")
        self.last_receipt_var = tk.StringVar(value="Son basılan fiş: yok")
        self.mode_var = tk.StringVar(value="Sırayla")
        self.no_repeat_var = tk.BooleanVar(value=False)
        self.amount_mode_var = tk.StringVar(value="Sabit")
        self.min_amount_var = tk.StringVar(value="500")
        self.max_amount_var = tk.StringVar(value="5000")
        self.time_mode_var = tk.StringVar(value="Şu andan başlat")
        self.start_dt_var = tk.StringVar(value=datetime.now().strftime("%d-%m-%Y %H:%M:%S"))
        self.delta_var = tk.StringVar(value="5 saniye")
        self.counter_var = tk.StringVar(value="0")

        now = datetime.now()
        self.random_dt_enabled_var = tk.BooleanVar(value=False)
        self.random_month_var = tk.StringVar(value=str(now.month))
        self.random_year_var = tk.StringVar(value=str(now.year))
        self.random_days_var = tk.BooleanVar(value=True)
        self.random_times_var = tk.BooleanVar(value=True)
        self.avoid_night_var = tk.BooleanVar(value=True)
        self.random_start_time_var = tk.StringVar(value="08:00")
        self.random_end_time_var = tk.StringVar(value="22:59")
        self.allow_same_day_var = tk.BooleanVar(value=False)
        self.random_preview_var = tk.StringVar(value="Rastgele tarih-saat kapalı")

    def _build_menu(self):
        menu = tk.Menu(self.root)
        self.root.config(menu=menu)

        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="Firmaları Kaydet", command=self.save_firms)
        file_menu.add_command(label="Firmaları Yeniden Yükle", command=self.load_firms)
        file_menu.add_separator()
        file_menu.add_command(label="Şablonu Kaydet", command=self.save_template)
        file_menu.add_command(label="Şablonu Yükle", command=self.load_template)
        file_menu.add_command(label="Varsayılan Şablona Dön", command=self.reset_template)
        file_menu.add_separator()
        file_menu.add_command(label="Çıkış", command=self.root.destroy)
        menu.add_cascade(label="Dosya", menu=file_menu)

        firm_menu = tk.Menu(menu, tearoff=0)
        firm_menu.add_command(label="Firma Ekle", command=self.add_firm)
        firm_menu.add_command(label="Seçili Firmayı Düzenle", command=self.edit_firm)
        firm_menu.add_command(label="Seçili Firmayı Sil", command=self.delete_firm)
        firm_menu.add_separator()
        firm_menu.add_command(label="Toplu Firma Düzenle", command=self.bulk_edit_firms)
        menu.add_cascade(label="Firma Yönetimi", menu=firm_menu)

        help_menu = tk.Menu(menu, tearoff=0)
        help_menu.add_command(label="Kullanım Bilgisi", command=self.show_help)
        menu.add_cascade(label="Yardım", menu=help_menu)

    def _build_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.single_tab = ttk.Frame(self.notebook, padding=10)
        self.batch_tab = ttk.Frame(self.notebook, padding=10)
        self.firms_tab = ttk.Frame(self.notebook, padding=10)
        self.template_tab = ttk.Frame(self.notebook, padding=10)
        self.settings_tab = ttk.Frame(self.notebook, padding=10)
        self.advanced_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.single_tab, text="Tek Fiş")
        self.notebook.add(self.batch_tab, text="Seri Baskı")
        self.notebook.add(self.firms_tab, text="Firma Yönetimi")
        self.notebook.add(self.template_tab, text="Fiş Şablonu")
        self.notebook.add(self.settings_tab, text="Ayarlar")
        self.notebook.add(self.advanced_tab, text="Gelişmiş Seri Basım")

        self._build_single_tab()
        self._build_batch_tab()
        self._build_firms_tab(self.firms_tab)
        self._build_template_tab()
        self._build_settings_tab()
        self._build_advanced_tab()
        self.root.after(250, self._offer_resume_pending)

    def _build_single_tab(self):
        self.single_tab.columnconfigure(0, weight=1)
        self.single_tab.columnconfigure(1, weight=1)
        self.single_tab.rowconfigure(0, weight=1)

        settings = ttk.LabelFrame(self.single_tab, text="Yazdırma Ayarları", padding=10)
        settings.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        preview_box = ttk.LabelFrame(self.single_tab, text="Fiş Önizleme (salt okunur)", padding=10)
        preview_box.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        preview_box.rowconfigure(0, weight=1)
        preview_box.columnconfigure(0, weight=1)

        self._build_printer_controls(settings)
        self._add_separator(settings)
        self._build_receipt_controls(settings)
        ttk.Button(settings, text="Tek Fiş Bas", command=self.print_single).pack(fill="x", pady=(10, 0))

        self.preview = tk.Text(preview_box, font=("Courier New", 10), width=42, state="disabled")
        self.preview.grid(row=0, column=0, sticky="nsew")
        preview_scroll = ttk.Scrollbar(preview_box, orient="vertical", command=self.preview.yview)
        preview_scroll.grid(row=0, column=1, sticky="ns")
        self.preview.configure(yscrollcommand=preview_scroll.set)

    def _build_batch_tab(self):
        canvas = tk.Canvas(self.batch_tab, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.batch_tab, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        content = ttk.LabelFrame(scroll_frame, text="Seri Baskı Ayarları", padding=10)
        content.pack(fill="both", expand=True, padx=4, pady=4)

        self._add_entry(content, "Fiş sayısı", self.batch_count_var)
        self._add_entry(content, "Seri Fiş No Başlangıç", self.batch_receipt_no_var)
        ttk.Label(content, text="Firma seçim modu").pack(anchor="w")
        ttk.Combobox(content, textvariable=self.mode_var, values=["Sırayla", "Rastgele", "Tek firma"], state="readonly").pack(fill="x")
        ttk.Checkbutton(content, text="Aynı firma üst üste gelmesin", variable=self.no_repeat_var).pack(anchor="w", pady=4)
        ttk.Label(content, text="Tutar modu").pack(anchor="w")
        ttk.Combobox(content, textvariable=self.amount_mode_var, values=["Sabit", "Rastgele", "Firma bazlı"], state="readonly").pack(fill="x")
        self._add_entry(content, "Minimum tutar", self.min_amount_var)
        self._add_entry(content, "Maksimum tutar", self.max_amount_var)
        ttk.Label(content, text="Tarih-saat modu").pack(anchor="w")
        ttk.Combobox(
            content,
            textvariable=self.time_mode_var,
            values=["Şu andan başlat", "Belirli tarihten başlat", "Rastgele tarih-saat üret"],
            state="readonly",
        ).pack(fill="x")
        self._add_entry(content, "Başlangıç (GG-AA-YYYY SS:DD:SS)", self.start_dt_var)
        ttk.Label(content, text="Fişler arası zaman farkı").pack(anchor="w")
        ttk.Combobox(content, textvariable=self.delta_var, values=["1 saniye", "5 saniye", "10 saniye", "Rastgele"], state="readonly").pack(fill="x")
        self._build_random_datetime_controls(content)
        self.batch_start_button = ttk.Button(content, text="Seri Baskı Başlat", command=self.start_batch)
        self.batch_start_button.pack(fill="x", pady=(10, 2))
        complete_box = ttk.LabelFrame(content, text="Firma Bazlı Eksiksiz Seri Basım", padding=8)
        complete_box.pack(fill="x", pady=(10, 2))
        self._add_entry(complete_box, "Bitiş Fiş No", self.complete_batch_end_no_var)
        ttk.Checkbutton(
            complete_box,
            text="Baskı sırasını rastgele karıştır",
            variable=self.complete_batch_randomize_var,
        ).pack(anchor="w", pady=4)
        ttk.Label(
            complete_box,
            text="Her firma seçilen her fiş numarasını yalnızca bir kez kullanır; mevcut olanlar atlanır.",
            foreground="#555",
            wraplength=850,
        ).pack(anchor="w", pady=(2, 6))
        self.complete_batch_button = ttk.Button(
            complete_box,
            text="Firma Bazlı Eksiksiz Basım",
            command=self.start_complete_batch,
        )
        self.complete_batch_button.pack(fill="x")
        ttk.Button(content, text="Baskıyı Durdur", command=self.stop_batch_print).pack(fill="x", pady=2)
        pause_row = ttk.Frame(content)
        pause_row.pack(fill="x", pady=2)
        ttk.Button(pause_row, text="Duraklat", command=self.pause_batch).pack(side="left", fill="x", expand=True)
        ttk.Button(pause_row, text="Devam Et", command=self.resume_batch).pack(side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Label(content, text="Basılan fiş sayısı:").pack(anchor="w", pady=(8, 0))
        ttk.Label(content, textvariable=self.counter_var, font=("Segoe UI", 14, "bold")).pack(anchor="w")

    def _build_random_datetime_controls(self, parent):
        random_box = ttk.LabelFrame(parent, text="Tarih Rastgeleleştirme", padding=10)
        random_box.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(
            random_box,
            text="Rastgele tarih-saat kullan",
            variable=self.random_dt_enabled_var,
            command=self._on_random_datetime_toggle,
        ).grid(row=0, column=0, columnspan=4, sticky="w")

        self.random_dt_widgets: list[tk.Widget] = []
        self._grid_random_entry(random_box, "Ay seçimi (1-12)", self.random_month_var, 1, 0)
        self._grid_random_entry(random_box, "Yıl seçimi", self.random_year_var, 1, 2)

        for text, var, row, col in [
            ("Günleri rastgele üret", self.random_days_var, 2, 0),
            ("Saatleri rastgele üret", self.random_times_var, 2, 1),
            ("Gece saatlerini kullanma", self.avoid_night_var, 2, 2),
            ("Aynı gün tekrar kullanılabilsin", self.allow_same_day_var, 2, 3),
        ]:
            command = self._on_avoid_night_toggle if var is self.avoid_night_var else self._on_datetime_setting_changed
            widget = ttk.Checkbutton(random_box, text=text, variable=var, command=command)
            widget.grid(row=row, column=col, sticky="w", padx=(0, 8), pady=4)
            self.random_dt_widgets.append(widget)

        self._grid_random_entry(random_box, "Başlangıç saat", self.random_start_time_var, 3, 0)
        self._grid_random_entry(random_box, "Bitiş saat", self.random_end_time_var, 3, 2)
        ttk.Label(random_box, textvariable=self.random_preview_var, foreground="#555", wraplength=900).grid(
            row=4, column=0, columnspan=4, sticky="ew", pady=(8, 0)
        )
        self._set_random_datetime_state()

    def _grid_random_entry(self, parent, label, var, row, col):
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(row=row, column=col, sticky="w", padx=(0, 8), pady=4)
        entry = ttk.Entry(parent, textvariable=var, width=12)
        entry.grid(row=row, column=col + 1, sticky="w", pady=4)
        self.random_dt_widgets.extend([label_widget, entry])

    def _build_firms_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        ttk.Label(parent, text=TURKISH_CHAR_WARNING, foreground="#9a5b00", wraplength=980).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        panel = ttk.LabelFrame(parent, text="Firma Yönetimi", padding=10)
        panel.grid(row=1, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)

        list_frame = ttk.Frame(panel)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self.firm_list = tk.Listbox(list_frame, height=14)
        self.firm_list.grid(row=0, column=0, sticky="nsew")
        self.firm_list.bind("<<ListboxSelect>>", self._sync_combo_from_list)
        firm_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.firm_list.yview)
        firm_scroll.grid(row=0, column=1, sticky="ns")
        self.firm_list.configure(yscrollcommand=firm_scroll.set)

        buttons = ttk.Frame(panel)
        buttons.grid(row=0, column=1, sticky="ns")
        ttk.Button(buttons, text="Firma Ekle", command=self.add_firm).pack(fill="x", pady=2)
        ttk.Button(buttons, text="Firma Düzenle", command=self.edit_firm).pack(fill="x", pady=2)
        ttk.Button(buttons, text="Firma Sil", command=self.delete_firm).pack(fill="x", pady=2)
        ttk.Button(buttons, text="Toplu Firma Düzenle", command=self.bulk_edit_firms).pack(fill="x", pady=(10, 2))
        ttk.Button(buttons, text="Firmaları Kaydet", command=self.save_firms).pack(fill="x", pady=(10, 2))
        ttk.Button(buttons, text="Firmaları Yükle", command=self.load_firms).pack(fill="x", pady=2)

    def _build_template_tab(self):
        self.template_editor = TemplateEditorFrame(self.template_tab, self.on_template_changed)
        self.template_editor.pack(fill="both", expand=True)
        self.template_editor.set_template(self.receipt_template)

    def _build_settings_tab(self):
        panel = ttk.LabelFrame(self.settings_tab, text="Yazıcı ve Genel Ayarlar", padding=10)
        panel.pack(fill="both", expand=True)
        self._build_printer_controls(panel)
        self._add_separator(panel)
        ttk.Label(panel, text=TURKISH_CHAR_WARNING, foreground="#9a5b00", wraplength=850).pack(anchor="w", pady=8)

    def _build_advanced_tab(self):
        self.advanced_tab.columnconfigure(0, weight=1)
        self.advanced_tab.columnconfigure(1, weight=1)
        self.advanced_tab.rowconfigure(1, weight=1)
        range_box = ttk.LabelFrame(self.advanced_tab, text="Firma ve Fiş Aralığı", padding=10)
        range_box.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._add_entry(range_box, "Başlangıç Fiş No", self.advanced_start_no_var)
        self._add_entry(range_box, "Bitiş Fiş No", self.advanced_end_no_var)
        self._add_entry(range_box, "Planlayıcı Fiş Adedi", self.advanced_count_var)
        ttk.Button(range_box, text="Son Numaradan Devam Et", command=self.use_last_receipt_number).pack(fill="x", pady=4)
        ttk.Label(range_box, textvariable=self.last_receipt_var).pack(anchor="w")

        firms_box = ttk.LabelFrame(self.advanced_tab, text="Firmalar (çoklu seçim)", padding=8)
        firms_box.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(8, 0))
        firms_box.rowconfigure(0, weight=1)
        firms_box.columnconfigure(0, weight=1)
        self.advanced_firm_list = tk.Listbox(firms_box, selectmode="extended", exportselection=False)
        self.advanced_firm_list.grid(row=0, column=0, sticky="nsew")
        self.advanced_firm_list.bind("<<ListboxSelect>>", lambda _event: self._update_last_receipt_label())
        scroll = ttk.Scrollbar(firms_box, orient="vertical", command=self.advanced_firm_list.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.advanced_firm_list.configure(yscrollcommand=scroll.set)

        actions = ttk.LabelFrame(self.advanced_tab, text="Araçlar", padding=10)
        actions.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(8, 0))
        for label, command in [
            ("Akıllı Eksik Fiş Bulucu", self.show_missing_finder),
            ("Yalnızca Eksikleri Bas", self.print_only_missing),
            ("Baskı Matrisi", self.show_print_matrix),
            ("Akıllı Seri Basım Planlayıcı", self.show_balanced_plan),
            ("Güvenli Filtreli Baskı", lambda: self.show_filtered_plan(False)),
            ("Manuel Yeniden Baskı", lambda: self.show_filtered_plan(True)),
            ("Hatalı Baskılar", self.show_failures),
            ("Baskı Geçmişi / Oturumlar", self.show_sessions),
        ]:
            ttk.Button(actions, text=label, command=command).pack(fill="x", pady=3)

    def _build_printer_controls(self, parent):
        ttk.Label(parent, text="Windows yazıcı listesi").pack(anchor="w")
        printer_combo = ttk.Combobox(parent, textvariable=self.selected_printer_var, state="readonly")
        printer_combo.pack(fill="x")
        self.printer_combos.append(printer_combo)
        ttk.Button(parent, text="Yazıcıları Yenile", command=self._refresh_printers).pack(fill="x", pady=4)
        ttk.Label(parent, text="Manuel yazıcı adı (opsiyonel - boş bırakılırsa listeden seçilen kullanılır)").pack(anchor="w")
        ttk.Entry(parent, textvariable=self.manual_printer_var).pack(fill="x")

    def _build_receipt_controls(self, parent):
        ttk.Label(parent, text="Firma seçimi").pack(anchor="w")
        self.firm_combo = ttk.Combobox(parent, state="readonly")
        self.firm_combo.pack(fill="x", pady=(0, 6))
        self.firm_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_firm_defaults())

        self._add_entry(parent, "Ürün/Hizmet", self.product_var)
        self._add_entry(parent, "Tutar", self.amount_var)
        self._add_entry(parent, "KDV", self.vat_var)
        self._add_entry(parent, "Tek Fiş No Başlangıç", self.receipt_no_var)
        ttk.Label(parent, text="Ödeme Tipi").pack(anchor="w")
        ttk.Combobox(parent, textvariable=self.pay_var, values=["NAKIT", "KART", "OYUN PARASI"], state="readonly").pack(fill="x")

    def _add_entry(self, parent, label, var):
        ttk.Label(parent, text=label).pack(anchor="w", pady=(6, 0))
        ttk.Entry(parent, textvariable=var).pack(fill="x")

    def _add_separator(self, parent):
        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=10)

    def _wire_preview_updates(self):
        preview_vars = [
            self.product_var,
            self.amount_var,
            self.vat_var,
            self.pay_var,
            self.receipt_no_var,
            self.time_mode_var,
            self.random_dt_enabled_var,
            self.random_month_var,
            self.random_year_var,
            self.random_days_var,
            self.random_times_var,
            self.avoid_night_var,
            self.random_start_time_var,
            self.random_end_time_var,
            self.allow_same_day_var,
        ]
        for var in preview_vars:
            var.trace_add("write", lambda *_args: self._on_datetime_setting_changed())

    def _refresh_printers(self):
        printers = self.printer_service.list_printers()
        if not printers:
            for combo in self.printer_combos:
                combo["values"] = []
                combo.set("")
            return
        pos_index = next((i for i, name in enumerate(printers) if "POS-1903" in name.upper()), 0)
        for combo in self.printer_combos:
            combo["values"] = printers
            combo.current(pos_index)

    def _selected_printer(self):
        manual = self.manual_printer_var.get().strip()
        if manual:
            return manual
        return self.selected_printer_var.get().strip()

    def _refresh_firm_list(self, selected_index: int | None = None):
        names = [firm.name for firm in self.firms]
        self.firm_combo["values"] = names
        self.firm_list.delete(0, tk.END)
        for name in names:
            self.firm_list.insert(tk.END, name)
        if hasattr(self, "advanced_firm_list"):
            self.advanced_firm_list.delete(0, tk.END)
            for name in names:
                self.advanced_firm_list.insert(tk.END, name)
            if names:
                self.advanced_firm_list.selection_set(0, tk.END)
                self._update_last_receipt_label()

        if not names:
            self.update_preview()
            return
        index = selected_index if selected_index is not None else self.firm_combo.current()
        if index < 0 or index >= len(names):
            index = 0
        self.firm_combo.current(index)
        self.updating_selection = True
        self.firm_list.selection_clear(0, tk.END)
        self.firm_list.selection_set(index)
        self.firm_list.see(index)
        self.updating_selection = False
        self._apply_firm_defaults()

    def _sync_combo_from_list(self, _event=None):
        if self.updating_selection:
            return
        selection = self.firm_list.curselection()
        if not selection:
            return
        self.firm_combo.current(selection[0])
        self._apply_firm_defaults()

    def _selected_firm_index(self) -> int:
        selection = self.firm_list.curselection()
        if selection:
            return selection[0]
        index = self.firm_combo.current()
        if index < 0:
            raise ValueError("Firma listesi boş")
        return index

    def _apply_firm_defaults(self):
        index = self.firm_combo.current()
        if index < 0 or index >= len(self.firms):
            return
        firm = self.firms[index]
        self.product_var.set(firm.default_product)
        self.vat_var.set(str(firm.default_vat))
        self.amount_var.set(str(firm.default_amount))
        if hasattr(self, "firm_list"):
            self.updating_selection = True
            self.firm_list.selection_clear(0, tk.END)
            self.firm_list.selection_set(index)
            self.firm_list.see(index)
            self.updating_selection = False
        self.update_preview()

    def _current_firm(self) -> Firm:
        index = self.firm_combo.current()
        if index < 0 or index >= len(self.firms):
            raise ValueError("Firma listesi boş")
        return self.firms[index]

    def _set_preview_text(self, text: str):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", tk.END)
        self.preview.insert(tk.END, text)
        self.preview.configure(state="disabled")

    def update_preview(self):
        if not hasattr(self, "preview"):
            return
        try:
            receipt_no = int(self.receipt_no_var.get() or "1")
            text = build_receipt_text(self._build_receipt_data(receipt_no, self._single_receipt_datetime()), self.receipt_template)
        except Exception:
            text = "Önizleme oluşturulamadı. Firma, tutar ve KDV alanlarını kontrol edin."
        self._set_preview_text(text)

    def _parse_float(self, value: str, error_message: str) -> float:
        try:
            return float(value.replace(",", "."))
        except ValueError as exc:
            raise ValueError(error_message) from exc

    def _build_receipt_data(self, receipt_no: int, dt: datetime, firm: Firm | None = None, amount: float | None = None):
        firm = firm or self._current_firm()
        receipt_amount = amount if amount is not None else self._parse_float(self.amount_var.get(), "Tutar sayısal olmalı")
        return ReceiptData(
            firm_name=firm.name,
            sector=firm.sector,
            address=firm.address,
            address_line1=firm.address_line1,
            address_line2=firm.address_line2,
            phone1=firm.phone1,
            phone2=firm.phone2,
            website=firm.website,
            tax_office=firm.tax_office,
            trade_registry_no=firm.trade_registry_no,
            eku_no=firm.eku_no,
            z_no=firm.z_no,
            footer_logo_code=firm.footer_logo_code,
            game_code=firm.game_code,
            receipt_no=receipt_no,
            dt=dt,
            product_name=self.product_var.get().strip() or firm.default_product,
            vat_rate=self._parse_float(self.vat_var.get(), "KDV sayısal olmalı"),
            amount=receipt_amount,
            payment_type=self.pay_var.get(),
        )

    def _validate_printer(self) -> str:
        printer = self._selected_printer()
        if not printer:
            raise ValueError("Yazıcı bulunamadı")
        if not self.printer_service.printer_exists(printer):
            raise ValueError("Yazıcı bulunamadı")
        return printer

    def print_single(self):
        try:
            printer = self._validate_printer()
            receipt_no = int(self.receipt_no_var.get())
            data = self._build_receipt_data(receipt_no, self._single_receipt_datetime())
            text = build_receipt_text(data, self.receipt_template)
            self.printer_service.print_raw(printer, text)
            self.print_history.record_printed((firm_identity(self._current_firm()), receipt_no))
            self.printer_service.save_txt(OUTPUT_DIR, f"receipt_{receipt_no:06d}.txt", text)
            self.update_preview()
            messagebox.showinfo("Başarılı", "Tek fiş basıldı.")
        except ValueError as exc:
            messagebox.showerror("Hata", str(exc))
        except Exception as exc:
            messagebox.showerror("Hata", f"Baskı gönderilemedi: {exc}")

    def _pick_firm_sequence(self, count: int):
        if not self.firms:
            raise ValueError("Firma listesi boş")
        mode = self.mode_var.get()
        if mode == "Tek firma":
            return [self._current_firm() for _ in range(count)]
        if mode == "Sırayla":
            return [self.firms[i % len(self.firms)] for i in range(count)]

        result = []
        prev = None
        for _ in range(count):
            candidates = self.firms
            if self.no_repeat_var.get() and prev is not None and len(self.firms) > 1:
                candidates = [firm for firm in self.firms if firm.name != prev.name]
            firm = random.choice(candidates)
            result.append(firm)
            prev = firm
        return result

    def _pick_amount(self, firm: Firm):
        mode = self.amount_mode_var.get()
        if mode == "Sabit":
            return self._parse_float(self.amount_var.get(), "Tutar sayısal olmalı")
        if mode == "Firma bazlı":
            return firm.default_amount
        minimum = self._parse_float(self.min_amount_var.get(), "Tutar sayısal olmalı")
        maximum = self._parse_float(self.max_amount_var.get(), "Tutar sayısal olmalı")
        if minimum > maximum:
            raise ValueError("Minimum tutar maksimumdan büyük olamaz")
        return round(random.uniform(minimum, maximum), 2)

    def _next_dt(self, current: datetime):
        delta = self.delta_var.get()
        if delta == "1 saniye":
            return current + timedelta(seconds=1)
        if delta == "5 saniye":
            return current + timedelta(seconds=5)
        if delta == "10 saniye":
            return current + timedelta(seconds=10)
        return current + timedelta(seconds=random.randint(1, 10))

    def _on_datetime_setting_changed(self):
        self._set_random_datetime_state()
        self._update_random_datetime_preview()
        self.update_preview()

    def _on_random_datetime_toggle(self):
        self._on_datetime_setting_changed()

    def _on_avoid_night_toggle(self):
        if self.avoid_night_var.get():
            self.random_start_time_var.set("08:00")
            self.random_end_time_var.set("22:59")
        else:
            self.random_start_time_var.set("00:00")
            self.random_end_time_var.set("23:59")
        self._on_datetime_setting_changed()

    def _random_datetime_active(self) -> bool:
        return self.random_dt_enabled_var.get() or self.time_mode_var.get() == "Rastgele tarih-saat üret"

    def _set_random_datetime_state(self):
        if not hasattr(self, "random_dt_widgets"):
            return
        active = self._random_datetime_active()
        state = "normal" if active else "disabled"
        for widget in self.random_dt_widgets:
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass

    def _random_datetime_options(self) -> RandomDateTimeOptions:
        try:
            month = int(self.random_month_var.get())
            year = int(self.random_year_var.get())
        except ValueError as exc:
            raise ValueError("Ay ve yıl sayısal olmalı") from exc
        return RandomDateTimeOptions(
            enabled=self._random_datetime_active(),
            year=year,
            month=month,
            random_days=self.random_days_var.get(),
            random_times=self.random_times_var.get(),
            avoid_night_hours=self.avoid_night_var.get(),
            start_time=self.random_start_time_var.get(),
            end_time=self.random_end_time_var.get(),
            allow_same_day=self.allow_same_day_var.get(),
        )

    def _single_receipt_datetime(self) -> datetime:
        if self._random_datetime_active():
            return build_random_datetimes(1, self._random_datetime_options())[0]
        return datetime.now()

    def _batch_random_datetimes(self, count: int) -> list[datetime] | None:
        if not self._random_datetime_active():
            return None
        return build_random_datetimes(count, self._random_datetime_options())

    def _initial_batch_datetime(self) -> datetime:
        if self.time_mode_var.get() == "Şu andan başlat":
            return datetime.now()
        return datetime.strptime(self.start_dt_var.get(), "%d-%m-%Y %H:%M:%S")

    def _update_random_datetime_preview(self):
        if not hasattr(self, "random_preview_var"):
            return
        if not self._random_datetime_active():
            self.random_preview_var.set("Rastgele tarih-saat kapalı")
            return
        try:
            samples = build_random_datetimes(5, self._random_datetime_options())
        except ValueError as exc:
            self.random_preview_var.set(str(exc))
            return
        formatted = ", ".join(sample.strftime("%d.%m.%Y %H:%M") for sample in samples)
        self.random_preview_var.set(f"Örnek tarihler: {formatted}")

    def _advanced_selected_firms(self) -> list[Firm]:
        indexes = self.advanced_firm_list.curselection()
        if not indexes:
            raise ValueError("En az bir firma seçin")
        return [self.firms[index] for index in indexes]

    def _advanced_range(self) -> tuple[int, int]:
        start_no = int(self.advanced_start_no_var.get())
        end_no = int(self.advanced_end_no_var.get())
        if start_no > end_no:
            raise ValueError("Başlangıç fiş no, bitiş fiş no değerinden büyük olamaz")
        return start_no, end_no

    def _update_last_receipt_label(self):
        try:
            firm = self._advanced_selected_firms()[0]
            last = get_last_receipt_number_for_firm(firm_identity(firm), self.print_history.load_pairs())
            self.last_receipt_var.set(f"Son basılan fiş: {last if last is not None else 'yok'}")
        except (ValueError, OSError) as exc:
            self.last_receipt_var.set(str(exc))

    def use_last_receipt_number(self):
        try:
            firm = self._advanced_selected_firms()[0]
            last = get_last_receipt_number_for_firm(firm_identity(firm), self.print_history.load_pairs())
            self.advanced_start_no_var.set(str(1 if last is None else last + 1))
            self._update_last_receipt_label()
        except ValueError as exc:
            messagebox.showerror("Hata", str(exc))

    def show_missing_finder(self):
        try:
            firms = self._advanced_selected_firms()
            start_no, end_no = self._advanced_range()
            jobs = build_missing_firm_receipt_jobs(
                firms, start_no, end_no, self.print_history.load_pairs(), randomize=False
            )
            if not jobs:
                messagebox.showinfo("Akıllı Eksik Fiş Bulucu", "Seçilen aralıkta eksik fiş bulunmuyor.")
                return
            self._show_job_preview(
                jobs, "Akıllı Eksik Fiş Bulucu", allow_reprint=False,
                integrity_scope=(firms, start_no, end_no),
            )
        except (ValueError, OSError) as exc:
            messagebox.showerror("Hata", str(exc))

    def print_only_missing(self):
        self.show_missing_finder()

    def show_balanced_plan(self):
        try:
            jobs = build_balanced_print_jobs(
                self._advanced_selected_firms(), int(self.advanced_start_no_var.get()),
                int(self.advanced_count_var.get()), self.print_history.load_pairs()
            )
            self._show_job_preview(jobs, "Akıllı Seri Basım Planlayıcı", allow_reprint=False)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Hata", str(exc))

    def show_filtered_plan(self, manual_reprint: bool):
        try:
            firms = self._advanced_selected_firms()
            start_no, end_no = self._advanced_range()
            jobs = build_filtered_jobs(firms, start_no, end_no, self.print_history.load_pairs(), manual_reprint)
            if not jobs:
                messagebox.showinfo("Filtreli Baskı", "Seçilen filtrede basılacak fiş yok.")
                return
            if manual_reprint and not messagebox.askyesno(
                "Tehlikeli Manuel Yeniden Baskı",
                "Bu mod daha önce basılmış firma/fiş kombinasyonlarını tekrar yazdırabilir. Devam edilsin mi?",
            ):
                return
            self._show_job_preview(jobs, "Manuel Yeniden Baskı" if manual_reprint else "Güvenli Filtreli Baskı",
                                   allow_reprint=manual_reprint)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Hata", str(exc))

    def _show_job_preview(self, jobs, mode: str, allow_reprint: bool, skipped: int = 0, integrity_scope=None):
        window = tk.Toplevel(self.root)
        window.title("Seri Basım Önizleme")
        window.geometry("650x500")
        tree = ttk.Treeview(window, columns=("order", "firm", "receipt", "status"), show="headings", selectmode="extended")
        for column, title, width in [("order", "Sıra", 60), ("firm", "Firma", 280),
                                     ("receipt", "Fiş No", 100), ("status", "Durum", 120)]:
            tree.heading(column, text=title)
            tree.column(column, width=width)
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        working = list(jobs)

        def refresh():
            tree.delete(*tree.get_children())
            for index, job in enumerate(working, 1):
                tree.insert("", "end", iid=str(index - 1), values=(index, getattr(job.firm, "name", job.firm_id),
                                                                   job.receipt_no, "Bekliyor"))

        def remove_selected():
            nonlocal working
            indexes = sorted((int(item) for item in tree.selection()))
            working = remove_jobs(working, indexes)
            refresh()

        def reshuffle():
            random.shuffle(working)
            refresh()

        def move_selected(offset: int):
            if len(tree.selection()) != 1:
                return
            index = int(tree.selection()[0])
            target = index + offset
            if 0 <= target < len(working):
                working[index], working[target] = working[target], working[index]
                refresh()
                tree.selection_set(str(target))

        def start():
            if not working:
                messagebox.showinfo("Önizleme", "Yazdırılacak iş kalmadı.", parent=window)
                return
            final_jobs = list(working)
            if not allow_reprint:
                used = self.print_history.load_pairs()
                final_jobs = [job for job in final_jobs if job.pair_key not in used]
            window.destroy()
            self._launch_advanced_jobs(final_jobs, mode, allow_reprint, skipped, integrity_scope)

        controls = ttk.Frame(window)
        controls.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(controls, text="Seçilenleri Çıkar", command=remove_selected).pack(side="left")
        ttk.Button(controls, text="Yukarı", command=lambda: move_selected(-1)).pack(side="left", padx=(4, 0))
        ttk.Button(controls, text="Aşağı", command=lambda: move_selected(1)).pack(side="left", padx=(4, 0))
        ttk.Button(controls, text="Yeniden Karıştır", command=reshuffle).pack(side="left", padx=4)
        ttk.Button(controls, text="Yazdırmayı Başlat", command=start).pack(side="right")
        refresh()

    def show_print_matrix(self):
        try:
            firms = self._advanced_selected_firms()
            start_no, end_no = self._advanced_range()
            history = self.print_history.load_pairs()
            matrix = build_matrix_status(firms, start_no, end_no, history, self.failure_store.active_pairs())
        except (ValueError, OSError) as exc:
            messagebox.showerror("Hata", str(exc))
            return
        window = tk.Toplevel(self.root)
        window.title("Baskı Matrisi")
        window.geometry("900x550")
        filter_var = tk.StringVar(value="Tümü")
        top = ttk.Frame(window)
        top.pack(fill="x", padx=8, pady=8)
        ttk.Combobox(top, textvariable=filter_var, values=["Tümü", "Sadece Eksikler", "Sadece Hatalar"],
                     state="readonly").pack(side="left")
        columns = [str(number) for number in range(start_no, end_no + 1)]
        tree = ttk.Treeview(window, columns=["firm", *columns], show="headings", selectmode="extended")
        tree.heading("firm", text="Firma")
        tree.column("firm", width=180, stretch=False)
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=45, stretch=False, anchor="center")
        yscroll = ttk.Scrollbar(window, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(window, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.pack(fill="both", expand=True, padx=(8, 22))
        yscroll.place(relx=1.0, rely=0.08, relheight=0.82, anchor="ne")
        xscroll.pack(fill="x", padx=8)

        def refresh_matrix(*_args):
            tree.delete(*tree.get_children())
            wanted = filter_var.get()
            for index, firm in enumerate(firms):
                firm_id = firm_identity(firm)
                statuses = [matrix[(firm_id, number)] for number in range(start_no, end_no + 1)]
                if wanted == "Sadece Eksikler" and "missing" not in statuses:
                    continue
                if wanted == "Sadece Hatalar" and "failed" not in statuses:
                    continue
                symbols = {"printed": "✓", "missing": "○", "failed": "⚠"}
                tree.insert("", "end", iid=str(index), values=[firm.name, *[symbols[item] for item in statuses]])

        def print_selected_missing():
            selected = [firms[int(item)] for item in tree.selection()]
            if not selected:
                messagebox.showinfo("Baskı Matrisi", "En az bir firma satırı seçin.", parent=window)
                return
            jobs = build_missing_firm_receipt_jobs(selected, start_no, end_no, self.print_history.load_pairs(), False)
            window.destroy()
            self._show_job_preview(jobs, "Matristen Seçilen Eksikler", False)

        filter_var.trace_add("write", refresh_matrix)
        ttk.Button(top, text="Seçilen Eksikleri Bas", command=print_selected_missing).pack(side="right")
        refresh_matrix()

    def show_failures(self):
        failures = self.failure_store.active()
        if not failures:
            messagebox.showinfo("Hatalı Baskılar", "Aktif hatalı baskı yok.")
            return
        firm_map = {firm_identity(firm): firm for firm in self.firms}
        jobs = [FirmReceiptJob(firm_map[item["firm_id"]], item["firm_id"], int(item["receipt_no"]))
                for item in failures if item["firm_id"] in firm_map]
        self._show_job_preview(jobs, "Hatalı Baskıları Tekrar Bas", False)

    def show_sessions(self):
        window = tk.Toplevel(self.root)
        window.title("Baskı Geçmişi / Oturumlar")
        window.geometry("850x450")
        columns = ("started", "mode", "range", "planned", "success", "failed", "status")
        tree = ttk.Treeview(window, columns=columns, show="headings")
        for column, title in zip(columns, ("Başlangıç", "Mod", "Aralık", "Plan", "Başarılı", "Hata", "Durum")):
            tree.heading(column, text=title)
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        sessions = list(reversed(self.session_store.list()))
        for index, session in enumerate(sessions):
            tree.insert("", "end", iid=str(index), values=(session["started_at"][:19], session["mode"],
                f'{session["start_receipt_no"]}-{session["end_receipt_no"]}', session["planned_count"],
                session["successful_count"], session["failed_count"], session["status"]))

        def show_detail(_event=None):
            if not tree.selection():
                return
            session = sessions[int(tree.selection()[0])]
            detail = "\n".join(f"{key}: {value}" for key, value in session.items())
            messagebox.showinfo("Oturum Detayı", detail, parent=window)

        tree.bind("<Double-1>", show_detail)

    def pause_batch(self):
        self.pause_event.clear()

    def resume_batch(self):
        self.pause_event.set()

    def _offer_resume_pending(self):
        try:
            pending = self.pending_store.load()
        except ValueError as exc:
            messagebox.showerror("Kayıt Hatası", str(exc))
            return
        if not pending.get("pending"):
            return
        if not messagebox.askyesno("Tamamlanmamış Baskı", "Tamamlanmamış baskı oturumu bulundu. Devam edilsin mi?"):
            return
        firm_map = {firm_identity(firm): firm for firm in self.firms}
        allow_reprint = bool(pending.get("allow_reprint", False))
        used = set() if allow_reprint else self.print_history.load_pairs()
        saved_jobs = [FirmReceiptJob(firm_map[firm_id], firm_id, int(no)) for firm_id, no in pending["pending"]
                      if firm_id in firm_map]
        jobs = saved_jobs if allow_reprint else filter_pending_jobs(saved_jobs, used)
        if jobs:
            self._show_job_preview(jobs, pending.get("mode", "Kurtarılan Oturum"), allow_reprint)
        else:
            self.pending_store.clear()

    def _launch_advanced_jobs(self, jobs, mode: str, allow_reprint: bool, skipped: int = 0, integrity_scope=None):
        if not jobs:
            messagebox.showinfo("Seri Baskı", "Yazdırılacak iş bulunmuyor.")
            return
        if not self.batch_lock.acquire(blocking=False):
            messagebox.showerror("Hata", "Başka bir seri baskı halen devam ediyor")
            return
        try:
            printer = self._validate_printer()
            pair_keys = [job.pair_key for job in jobs]
            if len(pair_keys) != len(set(pair_keys)):
                raise ValueError("Plan duplicate firma/fiş kombinasyonu içeriyor")
            if not allow_reprint:
                used = self.print_history.load_pairs()
                jobs = [job for job in jobs if job.pair_key not in used]
            if not jobs:
                raise ValueError("Bütün işler daha önce basılmış")
            start_no = min(job.receipt_no for job in jobs)
            end_no = max(job.receipt_no for job in jobs)
            session = self.session_store.create(
                mode, jobs, start_no, end_no, randomize=False, skipped=skipped,
                reprint_count=len(jobs) if allow_reprint else 0,
            )
            self.active_session = session
            self.pending_store.save(session["session_id"], mode, jobs, allow_reprint)
            self.stop_batch = False
            self.pause_event.set()
            self._set_batch_buttons_state("disabled")
            threading.Thread(
                target=self._run_advanced_jobs,
                args=(printer, list(jobs), session, allow_reprint, integrity_scope),
                daemon=True,
            ).start()
        except Exception as exc:
            self.batch_lock.release()
            messagebox.showerror("Hata", str(exc))

    def _run_advanced_jobs(self, printer: str, jobs, session: dict, allow_reprint: bool, integrity_scope=None):
        pending = list(jobs)
        try:
            random_datetimes = self._batch_random_datetimes(len(jobs))
            dt = self._initial_batch_datetime() if random_datetimes is None else random_datetimes[0]
            self.print_count = 0
            for index, job in enumerate(jobs):
                while not self.pause_event.wait(0.2):
                    session["status"] = "PAUSED"
                    self.session_store.update(session)
                    if self.stop_batch:
                        break
                if self.stop_batch:
                    break
                session["status"] = "RUNNING"
                if not allow_reprint and job.pair_key in self.print_history.load_pairs():
                    session["skipped_count"] += 1
                    pending.pop(0)
                    self.pending_store.save(session["session_id"], session["mode"], pending, allow_reprint)
                    continue
                try:
                    amount = self._pick_amount(job.firm)
                    if random_datetimes is not None:
                        dt = random_datetimes[index]
                    data = self._build_receipt_data(job.receipt_no, dt, firm=job.firm, amount=amount)
                    text = build_receipt_text(data, self.receipt_template)
                    self.printer_service.print_raw(printer, text)
                    self.print_history.record_printed(job.pair_key)
                    self.failure_store.resolve(job.pair_key)
                    session["successful_count"] += 1
                    if len(session["successful_pairs"]) < 1000:
                        session["successful_pairs"].append([job.firm_id, job.receipt_no])
                    else:
                        session["pair_details_truncated"] = True
                    safe_id = "".join(char if char.isalnum() else "_" for char in job.firm_id)
                    self.printer_service.save_txt(
                        OUTPUT_DIR, f"receipt_{safe_id}_{job.receipt_no:06d}.txt", text
                    )
                    self.print_count += 1
                    self.root.after(0, lambda c=self.print_count: self.counter_var.set(str(c)))
                    self.root.after(0, lambda t=text: self._set_preview_text(t))
                    if random_datetimes is None:
                        dt = self._next_dt(dt)
                except Exception as exc:
                    session["failed_count"] += 1
                    session["failed_pairs"].append([job.firm_id, job.receipt_no])
                    self.failure_store.record(job.pair_key, str(exc), session["session_id"])
                pending.pop(0)
                self.pending_store.save(session["session_id"], session["mode"], pending, allow_reprint)
                self.session_store.update(session)

            session["status"] = "STOPPED" if self.stop_batch else "COMPLETED"
            session["finished_at"] = datetime.now().astimezone().isoformat()
            self.session_store.update(session)
            if not self.stop_batch:
                self.pending_store.clear()
            unique_firms = []
            seen = set()
            for job in jobs:
                if job.firm_id not in seen:
                    seen.add(job.firm_id)
                    unique_firms.append(job.firm)
            integrity_firms, integrity_start, integrity_end = integrity_scope or (
                unique_firms, session["start_receipt_no"], session["end_receipt_no"]
            )
            integrity = check_integrity(
                integrity_firms, integrity_start, integrity_end,
                self.print_history.load_pairs(),
            )
            message = (
                f"Beklenen: {integrity.expected}\nBaşarılı: {integrity.successful}\n"
                f"Eksik: {integrity.missing}\nOturum hatası: {session['failed_count']}"
            )
            if integrity.missing:
                self.root.after(0, lambda m=message, missing=integrity.missing_jobs:
                    self._show_integrity_result(m, missing))
            else:
                self.root.after(0, lambda m=message: messagebox.showinfo(
                    "Bütünlük Kontrolü", m + "\n\nSeri başarıyla tamamlandı. Eksik fiş yok."
                ))
        finally:
            self.batch_lock.release()
            self.root.after(0, lambda: self._set_batch_buttons_state("normal"))

    def _show_integrity_result(self, message: str, missing_jobs):
        if messagebox.askyesno("Bütünlük Kontrolü", message + "\n\nEksik fişler basılsın mı?"):
            self._show_job_preview(missing_jobs, "Bütünlük Eksiklerini Tamamla", False)

    def start_batch(self):
        acquired = False
        try:
            if not self.batch_lock.acquire(blocking=False):
                raise ValueError("Başka bir seri baskı halen devam ediyor")
            acquired = True
            self._validate_printer()
            count = int(self.batch_count_var.get())
            if count <= 0:
                raise ValueError("Fiş sayısı 0'dan büyük olmalı")
            if not self.firms:
                raise ValueError("Firma listesi boş")
            self.stop_batch = False
            self.pause_event.set()
            self._set_batch_buttons_state("disabled")
            threading.Thread(target=self._run_batch, args=(count,), daemon=True).start()
        except ValueError as exc:
            if acquired:
                self.batch_lock.release()
            messagebox.showerror("Hata", str(exc))
        except Exception as exc:
            if acquired:
                self.batch_lock.release()
            messagebox.showerror("Hata", f"Seri baskı başlatılamadı: {exc}")

    def _run_batch(self, count: int):
        try:
            printer = self._validate_printer()
            start_no = int(self.batch_receipt_no_var.get())
            firms = self._pick_firm_sequence(count)
            jobs = [FirmReceiptJob(firm, firm_identity(firm), start_no + index) for index, firm in enumerate(firms)]
            session = self.session_store.create("Normal Seri Baskı", jobs, start_no, start_no + count - 1, False)
            pending = list(jobs)
            self.pending_store.save(session["session_id"], session["mode"], pending)
            random_datetimes = self._batch_random_datetimes(count)
            dt = self._initial_batch_datetime() if random_datetimes is None else random_datetimes[0]

            self.print_count = 0
            for i in range(count):
                while not self.pause_event.wait(0.2):
                    if self.stop_batch:
                        break
                if self.stop_batch:
                    break
                job = jobs[i]
                try:
                    amount = self._pick_amount(job.firm)
                    if random_datetimes is not None:
                        dt = random_datetimes[i]
                    data = self._build_receipt_data(job.receipt_no, dt, firm=job.firm, amount=amount)
                    text = build_receipt_text(data, self.receipt_template)
                    self.printer_service.print_raw(printer, text)
                    self.print_history.record_printed(job.pair_key)
                    self.failure_store.resolve(job.pair_key)
                    self.printer_service.save_txt(OUTPUT_DIR, f"receipt_{job.receipt_no:06d}.txt", text)
                    session["successful_count"] += 1
                    if len(session["successful_pairs"]) < 1000:
                        session["successful_pairs"].append([job.firm_id, job.receipt_no])
                    else:
                        session["pair_details_truncated"] = True
                    self.print_count += 1
                    self.root.after(0, lambda c=self.print_count: self.counter_var.set(str(c)))
                    self.root.after(0, lambda t=text: self._set_preview_text(t))
                    if random_datetimes is None:
                        dt = self._next_dt(dt)
                except Exception as exc:
                    session["failed_count"] += 1
                    session["failed_pairs"].append([job.firm_id, job.receipt_no])
                    self.failure_store.record(job.pair_key, str(exc), session["session_id"])
                pending.pop(0)
                self.pending_store.save(session["session_id"], session["mode"], pending)
                self.session_store.update(session)

            session["status"] = "STOPPED" if self.stop_batch else "COMPLETED"
            session["finished_at"] = datetime.now().astimezone().isoformat()
            self.session_store.update(session)
            if not self.stop_batch:
                self.pending_store.clear()
            self.root.after(0, lambda: messagebox.showinfo("Bitti", f"Seri baskı tamamlandı. Basılan: {self.print_count}"))
        except Exception as exc:
            self.root.after(0, lambda: messagebox.showerror("Hata", f"Baskı gönderilemedi: {exc}"))
        finally:
            self.batch_lock.release()
            self.root.after(0, lambda: self._set_batch_buttons_state("normal"))

    def _set_batch_buttons_state(self, state: str):
        self.batch_start_button.configure(state=state)
        self.complete_batch_button.configure(state=state)

    def _complete_batch_firms(self) -> list[Firm]:
        if not self.firms:
            raise ValueError("Firma listesi boş")
        if self.mode_var.get() == "Tek firma":
            return [self._current_firm()]
        return list(self.firms)

    def start_complete_batch(self):
        acquired = False
        try:
            printer = self._validate_printer()
            firms = self._complete_batch_firms()
            start_no = int(self.batch_receipt_no_var.get())
            end_no = int(self.complete_batch_end_no_var.get())
            used_pairs = self.print_history.load_pairs()
            jobs = build_missing_firm_receipt_jobs(
                firms,
                start_no,
                end_no,
                used_pairs,
                randomize=self.complete_batch_randomize_var.get(),
            )
            number_count = end_no - start_no + 1
            unique_firm_count = len({firm_identity(firm) for firm in firms})
            theoretical_count = unique_firm_count * number_count
            existing_count = theoretical_count - len(jobs)
            if not jobs:
                messagebox.showinfo(
                    "Eksiksiz Basım",
                    "Bu aralıktaki tüm firma/fiş kombinasyonları zaten basılmış.",
                )
                return
            summary = (
                f"Seçili firma: {unique_firm_count}\n"
                f"Fiş No: {start_no}-{end_no}\n"
                f"Teorik kombinasyon: {theoretical_count}\n"
                f"Daha önce basılmış: {existing_count}\n"
                f"Basılacak yeni fiş: {len(jobs)}\n\n"
                "Baskı başlatılsın mı?"
            )
            if not messagebox.askyesno("Firma Bazlı Eksiksiz Basım", summary):
                return
            self._show_job_preview(
                jobs, "Firma Bazlı Eksiksiz Basım", False, existing_count,
                integrity_scope=(firms, start_no, end_no),
            )
        except ValueError as exc:
            if acquired:
                self.batch_lock.release()
            messagebox.showerror("Hata", str(exc))
        except Exception as exc:
            if acquired:
                self.batch_lock.release()
            messagebox.showerror("Hata", f"Eksiksiz seri baskı başlatılamadı: {exc}")

    def stop_batch_print(self):
        self.stop_batch = True

    def add_firm(self):
        firm = ask_firm(self.root)
        if firm:
            self.firms.append(firm)
            self._refresh_firm_list(len(self.firms) - 1)
            self.update_preview()

    def edit_firm(self):
        try:
            index = self._selected_firm_index()
        except ValueError as exc:
            messagebox.showerror("Hata", str(exc))
            return
        firm = ask_firm(self.root, self.firms[index])
        if firm:
            self.firms[index] = firm
            self._refresh_firm_list(index)
            self.update_preview()

    def delete_firm(self):
        try:
            index = self._selected_firm_index()
        except ValueError as exc:
            messagebox.showerror("Hata", str(exc))
            return
        if not messagebox.askyesno("Onay", f"{self.firms[index].name} silinsin mi?"):
            return
        del self.firms[index]
        self._refresh_firm_list(min(index, len(self.firms) - 1) if self.firms else None)
        self.update_preview()

    def bulk_edit_firms(self):
        result = ask_bulk_firms(self.root, self.firms)
        if not result:
            return
        mode, imported_firms = result
        if mode == "replace":
            self.firms = imported_firms
        else:
            self.firms.extend(imported_firms)
        self._refresh_firm_list(0)
        self.update_preview()
        messagebox.showinfo("Başarılı", f"{len(imported_firms)} firma içe aktarıldı.")

    def save_firms(self):
        self.firm_manager.firms = self.firms
        self.firm_manager.save()
        messagebox.showinfo("Kaydedildi", "Firmalar firms.json dosyasına kaydedildi.")

    def load_firms(self):
        self.firms = self.firm_manager.load()
        self._refresh_firm_list(0)
        self.update_preview()
        messagebox.showinfo("Yüklendi", "Firmalar yeniden yüklendi.")

    def on_template_changed(self):
        try:
            self.receipt_template = self.template_editor.get_template()
        except ValueError:
            return
        self.update_preview()

    def save_template(self):
        try:
            self.receipt_template = self.template_editor.get_template()
            self.template_manager.save(self.receipt_template)
            messagebox.showinfo("Kaydedildi", "Şablon receipt_template.json dosyasına kaydedildi.")
        except ValueError as exc:
            messagebox.showerror("Hata", str(exc))
        except Exception:
            messagebox.showerror("Hata", "Şablon kaydedilemedi")

    def load_template(self):
        try:
            self.receipt_template = self.template_manager.load()
            self.template_editor.set_template(self.receipt_template)
            self.update_preview()
            messagebox.showinfo("Yüklendi", "Şablon yüklendi.")
        except Exception:
            messagebox.showerror("Hata", "Şablon yüklenemedi")

    def reset_template(self):
        self.receipt_template = self.template_manager.reset()
        self.template_editor.set_template(self.receipt_template)
        self.update_preview()
        messagebox.showinfo("Şablon", "Varsayılan temiz şablona dönüldü. Alt bilgi boş bırakılabilir.")

    def show_help(self):
        messagebox.showinfo(
            "Kullanım Bilgisi",
            "1. Ayarlar veya Tek Fiş sekmesinden yazıcı seçin.\n"
            "2. Tek Fiş sekmesinde firma, ürün, tutar, KDV ve ödeme tipini girin.\n"
            "3. Firma Yönetimi sekmesinden firma ekleyebilir, düzenleyebilir, silebilir veya toplu içe aktarabilirsiniz.\n"
            "4. Seri Baskı sekmesinde fiş sayısı, firma modu, tutar modu ve zaman farkını ayarlayın.\n"
            "5. Firma Bazlı Eksiksiz Basım, seçilen aralıktaki eksik firma/fiş çiftlerini tamamlar.\n"
            "6. Fiş Şablonu sekmesinden üst/alt bilgi, genişlik, ayraç ve görünür alanları düzenleyin.\n\n"
            + TURKISH_CHAR_WARNING,
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    app.update_preview()
    root.mainloop()
