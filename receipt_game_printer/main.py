from __future__ import annotations

import random
import threading
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from bulk_firm_editor import ask_bulk_firms
from firm_dialog import ask_firm
from firm_manager import Firm, FirmManager
from printer_service import PrinterService
from receipt_formatter import ReceiptData, build_receipt_text

BASE_DIR = Path(__file__).resolve().parent
FIRMS_JSON = BASE_DIR / "firms.json"
OUTPUT_DIR = BASE_DIR / "receipts_output"
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
        self.printer_service = PrinterService()
        self.stop_batch = False
        self.print_count = 0
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
        self.manual_printer_var = tk.StringVar()

        self.batch_count_var = tk.StringVar(value="10")
        self.mode_var = tk.StringVar(value="Sırayla")
        self.no_repeat_var = tk.BooleanVar(value=False)
        self.amount_mode_var = tk.StringVar(value="Sabit")
        self.min_amount_var = tk.StringVar(value="500")
        self.max_amount_var = tk.StringVar(value="5000")
        self.time_mode_var = tk.StringVar(value="Şu andan başlat")
        self.start_dt_var = tk.StringVar(value=datetime.now().strftime("%d-%m-%Y %H:%M:%S"))
        self.delta_var = tk.StringVar(value="5 saniye")
        self.counter_var = tk.StringVar(value="0")

    def _build_menu(self):
        menu = tk.Menu(self.root)
        self.root.config(menu=menu)

        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="Firmaları Kaydet", command=self.save_firms)
        file_menu.add_command(label="Firmaları Yeniden Yükle", command=self.load_firms)
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
        self.settings_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.single_tab, text="Tek Fiş")
        self.notebook.add(self.batch_tab, text="Seri Baskı")
        self.notebook.add(self.firms_tab, text="Firma Yönetimi")
        self.notebook.add(self.settings_tab, text="Ayarlar")

        self._build_single_tab()
        self._build_batch_tab()
        self._build_firms_tab(self.firms_tab)
        self._build_settings_tab()

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
        content = ttk.LabelFrame(self.batch_tab, text="Seri Baskı Ayarları", padding=10)
        content.pack(fill="both", expand=True)

        self._add_entry(content, "Fiş sayısı", self.batch_count_var)
        ttk.Label(content, text="Firma seçim modu").pack(anchor="w")
        ttk.Combobox(content, textvariable=self.mode_var, values=["Sırayla", "Rastgele", "Tek firma"], state="readonly").pack(fill="x")
        ttk.Checkbutton(content, text="Aynı firma üst üste gelmesin", variable=self.no_repeat_var).pack(anchor="w", pady=4)
        ttk.Label(content, text="Tutar modu").pack(anchor="w")
        ttk.Combobox(content, textvariable=self.amount_mode_var, values=["Sabit", "Rastgele", "Firma bazlı"], state="readonly").pack(fill="x")
        self._add_entry(content, "Minimum tutar", self.min_amount_var)
        self._add_entry(content, "Maksimum tutar", self.max_amount_var)
        ttk.Label(content, text="Tarih-saat modu").pack(anchor="w")
        ttk.Combobox(content, textvariable=self.time_mode_var, values=["Şu andan başlat", "Belirli tarihten başlat"], state="readonly").pack(fill="x")
        self._add_entry(content, "Başlangıç (GG-AA-YYYY SS:DD:SS)", self.start_dt_var)
        ttk.Label(content, text="Fişler arası zaman farkı").pack(anchor="w")
        ttk.Combobox(content, textvariable=self.delta_var, values=["1 saniye", "5 saniye", "10 saniye", "Rastgele"], state="readonly").pack(fill="x")
        ttk.Button(content, text="Seri Baskı Başlat", command=self.start_batch).pack(fill="x", pady=(10, 2))
        ttk.Button(content, text="Baskıyı Durdur", command=self.stop_batch_print).pack(fill="x", pady=2)
        ttk.Label(content, text="Basılan fiş sayısı:").pack(anchor="w", pady=(8, 0))
        ttk.Label(content, textvariable=self.counter_var, font=("Segoe UI", 14, "bold")).pack(anchor="w")

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

    def _build_settings_tab(self):
        panel = ttk.LabelFrame(self.settings_tab, text="Yazıcı ve Genel Ayarlar", padding=10)
        panel.pack(fill="both", expand=True)
        self._build_printer_controls(panel)
        self._add_separator(panel)
        ttk.Label(panel, text=TURKISH_CHAR_WARNING, foreground="#9a5b00", wraplength=850).pack(anchor="w", pady=8)

    def _build_printer_controls(self, parent):
        ttk.Label(parent, text="Windows yazıcı listesi").pack(anchor="w")
        printer_combo = ttk.Combobox(parent, state="readonly")
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
        self._add_entry(parent, "Fiş No Başlangıç", self.receipt_no_var)
        ttk.Label(parent, text="Ödeme Tipi").pack(anchor="w")
        ttk.Combobox(parent, textvariable=self.pay_var, values=["NAKIT", "KART", "OYUN PARASI"], state="readonly").pack(fill="x")

    def _add_entry(self, parent, label, var):
        ttk.Label(parent, text=label).pack(anchor="w", pady=(6, 0))
        ttk.Entry(parent, textvariable=var).pack(fill="x")

    def _add_separator(self, parent):
        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=10)

    def _wire_preview_updates(self):
        for var in [self.product_var, self.amount_var, self.vat_var, self.pay_var, self.receipt_no_var]:
            var.trace_add("write", lambda *_args: self.update_preview())

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
        for combo in self.printer_combos:
            selected = combo.get().strip()
            if selected:
                return selected
        return ""

    def _refresh_firm_list(self, selected_index: int | None = None):
        names = [firm.name for firm in self.firms]
        self.firm_combo["values"] = names
        self.firm_list.delete(0, tk.END)
        for name in names:
            self.firm_list.insert(tk.END, name)

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
            text = build_receipt_text(self._build_receipt_data(receipt_no, datetime.now()))
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
            data = self._build_receipt_data(receipt_no, datetime.now())
            text = build_receipt_text(data)
            self.printer_service.print_raw(printer, text)
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

    def start_batch(self):
        try:
            self._validate_printer()
            count = int(self.batch_count_var.get())
            if count <= 0:
                raise ValueError("Fiş sayısı 0'dan büyük olmalı")
            if not self.firms:
                raise ValueError("Firma listesi boş")
            self.stop_batch = False
            threading.Thread(target=self._run_batch, args=(count,), daemon=True).start()
        except ValueError as exc:
            messagebox.showerror("Hata", str(exc))
        except Exception as exc:
            messagebox.showerror("Hata", f"Seri baskı başlatılamadı: {exc}")

    def _run_batch(self, count: int):
        try:
            printer = self._validate_printer()
            start_no = int(self.receipt_no_var.get())
            firms = self._pick_firm_sequence(count)
            dt = (
                datetime.now()
                if self.time_mode_var.get() == "Şu andan başlat"
                else datetime.strptime(self.start_dt_var.get(), "%d-%m-%Y %H:%M:%S")
            )

            self.print_count = 0
            for i in range(count):
                if self.stop_batch:
                    break
                firm = firms[i]
                amount = self._pick_amount(firm)
                data = self._build_receipt_data(start_no + i, dt, firm=firm, amount=amount)
                text = build_receipt_text(data)
                self.printer_service.print_raw(printer, text)
                self.printer_service.save_txt(OUTPUT_DIR, f"receipt_{start_no + i:06d}.txt", text)
                self.print_count += 1
                self.root.after(0, lambda c=self.print_count: self.counter_var.set(str(c)))
                self.root.after(0, lambda t=text: self._set_preview_text(t))
                dt = self._next_dt(dt)

            self.root.after(0, lambda: messagebox.showinfo("Bitti", f"Seri baskı tamamlandı. Basılan: {self.print_count}"))
        except Exception as exc:
            self.root.after(0, lambda: messagebox.showerror("Hata", f"Baskı gönderilemedi: {exc}"))

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

    def show_help(self):
        messagebox.showinfo(
            "Kullanım Bilgisi",
            "1. Ayarlar veya Tek Fiş sekmesinden yazıcı seçin.\n"
            "2. Tek Fiş sekmesinde firma, ürün, tutar, KDV ve ödeme tipini girin.\n"
            "3. Firma Yönetimi sekmesinden firma ekleyebilir, düzenleyebilir, silebilir veya toplu içe aktarabilirsiniz.\n"
            "4. Seri Baskı sekmesinde fiş sayısı, firma modu, tutar modu ve zaman farkını ayarlayın.\n\n"
            + TURKISH_CHAR_WARNING,
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    app.update_preview()
    root.mainloop()
