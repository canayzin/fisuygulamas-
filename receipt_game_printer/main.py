from __future__ import annotations

import random
import threading
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from firm_manager import FirmManager, Firm
from printer_service import PrinterService
from receipt_formatter import ReceiptData, build_receipt_text

BASE_DIR = Path(__file__).resolve().parent
FIRMS_JSON = BASE_DIR / "firms.json"
OUTPUT_DIR = BASE_DIR / "receipts_output"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Oyun Fiş Yazdırıcı (58mm ESC/POS)")
        self.root.geometry("1100x760")

        self.firm_manager = FirmManager(FIRMS_JSON)
        self.firms = self.firm_manager.load()
        self.printer_service = PrinterService()
        self.stop_batch = False
        self.print_count = 0

        self._build_ui()
        self._refresh_firm_list()
        self._refresh_printers()

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="both", expand=True)

        left = ttk.Frame(top)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(top)
        right.pack(side="right", fill="both", expand=True)

        self.printer_combo = ttk.Combobox(left, state="readonly")
        self.printer_combo.pack(fill="x")
        ttk.Button(left, text="Yazıcıları Yenile", command=self._refresh_printers).pack(fill="x", pady=4)
        self.printer_entry = ttk.Entry(left)
        self.printer_entry.pack(fill="x")
        self.printer_entry.insert(0, "Manuel yazıcı adı (opsiyonel)")

        self.firm_combo = ttk.Combobox(left, state="readonly")
        self.firm_combo.pack(fill="x", pady=4)
        self.firm_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_firm_defaults())

        self.product_var = tk.StringVar()
        self.amount_var = tk.StringVar(value="100.00")
        self.vat_var = tk.StringVar(value="20")
        self.pay_var = tk.StringVar(value="NAKIT")
        self.receipt_no_var = tk.StringVar(value="1")

        self._add_entry(left, "Ürün/Hizmet", self.product_var)
        self._add_entry(left, "Tutar", self.amount_var)
        self._add_entry(left, "KDV", self.vat_var)
        self._add_entry(left, "Fiş No Başlangıç", self.receipt_no_var)
        ttk.Label(left, text="Ödeme Tipi").pack(anchor="w")
        ttk.Combobox(left, textvariable=self.pay_var, values=["NAKIT", "KART", "OYUN PARASI"], state="readonly").pack(fill="x")

        ttk.Button(left, text="Tek Fiş Bas", command=self.print_single).pack(fill="x", pady=4)

        self.preview = tk.Text(right, font=("Courier New", 10), width=45)
        self.preview.pack(fill="both", expand=True)

        batch = ttk.LabelFrame(left, text="Seri Baskı", padding=8)
        batch.pack(fill="x", pady=8)
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

        self._add_entry(batch, "Fiş sayısı", self.batch_count_var)
        ttk.Label(batch, text="Firma seçim modu").pack(anchor="w")
        ttk.Combobox(batch, textvariable=self.mode_var, values=["Sırayla", "Rastgele", "Tek firma"], state="readonly").pack(fill="x")
        ttk.Checkbutton(batch, text="Aynı firma üst üste gelmesin", variable=self.no_repeat_var).pack(anchor="w")
        ttk.Label(batch, text="Tutar modu").pack(anchor="w")
        ttk.Combobox(batch, textvariable=self.amount_mode_var, values=["Sabit", "Rastgele", "Firma bazlı"], state="readonly").pack(fill="x")
        self._add_entry(batch, "Min tutar", self.min_amount_var)
        self._add_entry(batch, "Max tutar", self.max_amount_var)
        ttk.Label(batch, text="Tarih-saat modu").pack(anchor="w")
        ttk.Combobox(batch, textvariable=self.time_mode_var, values=["Şu andan başlat", "Belirli tarihten başlat"], state="readonly").pack(fill="x")
        self._add_entry(batch, "Başlangıç (GG-AA-YYYY SS:DD:SS)", self.start_dt_var)
        ttk.Label(batch, text="Fişler arası zaman farkı").pack(anchor="w")
        ttk.Combobox(batch, textvariable=self.delta_var, values=["1 saniye", "5 saniye", "10 saniye", "Rastgele"], state="readonly").pack(fill="x")
        ttk.Button(batch, text="Seri Baskı Başlat", command=self.start_batch).pack(fill="x", pady=2)
        ttk.Button(batch, text="Baskıyı Durdur", command=self.stop_batch_print).pack(fill="x", pady=2)
        ttk.Label(batch, text="Basılan fiş sayısı:").pack(anchor="w")
        ttk.Label(batch, textvariable=self.counter_var).pack(anchor="w")

        fm = ttk.LabelFrame(left, text="Firma Yönetimi", padding=8)
        fm.pack(fill="both", expand=True)
        self.firm_list = tk.Listbox(fm, height=8)
        self.firm_list.pack(fill="both", expand=True)
        ttk.Button(fm, text="Firma Ekle", command=self.add_firm).pack(fill="x")
        ttk.Button(fm, text="Firma Düzenle", command=self.edit_firm).pack(fill="x")
        ttk.Button(fm, text="Firma Sil", command=self.delete_firm).pack(fill="x")
        ttk.Button(fm, text="Firmaları Kaydet", command=self.save_firms).pack(fill="x")
        ttk.Button(fm, text="Firmaları Yükle", command=self.load_firms).pack(fill="x")

    def _add_entry(self, parent, label, var):
        ttk.Label(parent, text=label).pack(anchor="w")
        ttk.Entry(parent, textvariable=var).pack(fill="x")

    def _refresh_printers(self):
        printers = self.printer_service.list_printers()
        self.printer_combo["values"] = printers
        if printers:
            self.printer_combo.current(0)

    def _selected_printer(self):
        manual = self.printer_entry.get().strip()
        if manual and manual != "Manuel yazıcı adı (opsiyonel)":
            return manual
        return self.printer_combo.get().strip()

    def _refresh_firm_list(self):
        names = [f.name for f in self.firms]
        self.firm_combo["values"] = names
        self.firm_list.delete(0, tk.END)
        for n in names:
            self.firm_list.insert(tk.END, n)
        if names:
            self.firm_combo.current(0)
            self._apply_firm_defaults()

    def _apply_firm_defaults(self):
        idx = self.firm_combo.current()
        if idx < 0:
            return
        firm = self.firms[idx]
        self.product_var.set(firm.default_product)
        self.vat_var.set(str(firm.default_vat))
        self.amount_var.set(str(firm.default_amount))
        self.update_preview()

    def _current_firm(self) -> Firm:
        idx = self.firm_combo.current()
        if idx < 0:
            raise ValueError("Firma seçin")
        return self.firms[idx]

    def update_preview(self):
        try:
            text = build_receipt_text(self._build_receipt_data(1, datetime.now()))
            self.preview.delete("1.0", tk.END)
            self.preview.insert(tk.END, text)
        except Exception:
            pass

    def _build_receipt_data(self, receipt_no: int, dt: datetime, firm: Firm | None = None, amount: float | None = None):
        firm = firm or self._current_firm()
        a = amount if amount is not None else float(self.amount_var.get())
        return ReceiptData(
            firm_name=firm.name,
            sector=firm.sector,
            address=firm.address,
            game_code=firm.game_code,
            receipt_no=receipt_no,
            dt=dt,
            product_name=self.product_var.get() or firm.default_product,
            vat_rate=float(self.vat_var.get()),
            amount=a,
            payment_type=self.pay_var.get(),
        )

    def _validate_printer(self) -> str:
        printer = self._selected_printer()
        if not printer:
            raise ValueError("Yazıcı seçin veya yazıcı adı girin.")
        if not self.printer_service.printer_exists(printer):
            raise ValueError("Yazıcı bulunamadı veya bağlı değil.")
        return printer

    def print_single(self):
        try:
            printer = self._validate_printer()
            no = int(self.receipt_no_var.get())
            data = self._build_receipt_data(no, datetime.now())
            text = build_receipt_text(data)
            self.printer_service.print_raw(printer, text)
            self.printer_service.save_txt(OUTPUT_DIR, f"receipt_{no:06d}.txt", text)
            self.update_preview()
            messagebox.showinfo("Başarılı", "Tek fiş basıldı.")
        except Exception as exc:
            messagebox.showerror("Hata", str(exc))

    def _pick_firm_sequence(self, count: int):
        if not self.firms:
            raise ValueError("Firma listesi boş.")
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
                candidates = [f for f in self.firms if f.name != prev.name]
            firm = random.choice(candidates)
            result.append(firm)
            prev = firm
        return result

    def _pick_amount(self, firm: Firm):
        mode = self.amount_mode_var.get()
        if mode == "Sabit":
            return float(self.amount_var.get())
        if mode == "Firma bazlı":
            return firm.default_amount
        mn = float(self.min_amount_var.get())
        mx = float(self.max_amount_var.get())
        if mn > mx:
            raise ValueError("Minimum tutar maksimumdan büyük olamaz.")
        return round(random.uniform(mn, mx), 2)

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
                raise ValueError("Fiş sayısı 0'dan büyük olmalı.")
            self.stop_batch = False
            threading.Thread(target=self._run_batch, args=(count,), daemon=True).start()
        except Exception as exc:
            messagebox.showerror("Hata", str(exc))

    def _run_batch(self, count: int):
        try:
            printer = self._validate_printer()
            start_no = int(self.receipt_no_var.get())
            firms = self._pick_firm_sequence(count)
            dt = datetime.now() if self.time_mode_var.get() == "Şu andan başlat" else datetime.strptime(self.start_dt_var.get(), "%d-%m-%Y %H:%M:%S")

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
                self.root.after(0, lambda t=text: (self.preview.delete("1.0", tk.END), self.preview.insert(tk.END, t)))
                dt = self._next_dt(dt)

            self.root.after(0, lambda: messagebox.showinfo("Bitti", f"Seri baskı tamamlandı. Basılan: {self.print_count}"))
        except Exception as exc:
            self.root.after(0, lambda: messagebox.showerror("Hata", str(exc)))

    def stop_batch_print(self):
        self.stop_batch = True

    def add_firm(self):
        firm = self._firm_dialog()
        if firm:
            self.firms.append(firm)
            self._refresh_firm_list()

    def edit_firm(self):
        sel = self.firm_list.curselection()
        if not sel:
            return
        idx = sel[0]
        firm = self._firm_dialog(self.firms[idx])
        if firm:
            self.firms[idx] = firm
            self._refresh_firm_list()

    def delete_firm(self):
        sel = self.firm_list.curselection()
        if not sel:
            return
        del self.firms[sel[0]]
        self._refresh_firm_list()

    def save_firms(self):
        self.firm_manager.firms = self.firms
        self.firm_manager.save()
        messagebox.showinfo("Kaydedildi", "Firmalar kaydedildi.")

    def load_firms(self):
        self.firms = self.firm_manager.load()
        self._refresh_firm_list()
        messagebox.showinfo("Yüklendi", "Firmalar yüklendi.")

    def _firm_dialog(self, initial: Firm | None = None):
        dialog = tk.Toplevel(self.root)
        dialog.title("Firma")
        vars_ = {
            "name": tk.StringVar(value=getattr(initial, "name", "")),
            "sector": tk.StringVar(value=getattr(initial, "sector", "")),
            "address": tk.StringVar(value=getattr(initial, "address", "")),
            "game_code": tk.StringVar(value=getattr(initial, "game_code", "")),
            "default_product": tk.StringVar(value=getattr(initial, "default_product", "")),
            "default_vat": tk.StringVar(value=str(getattr(initial, "default_vat", 20))),
            "default_amount": tk.StringVar(value=str(getattr(initial, "default_amount", 100))),
        }
        for key, var in vars_.items():
            ttk.Label(dialog, text=key).pack(anchor="w")
            ttk.Entry(dialog, textvariable=var).pack(fill="x")
        result = {"firm": None}

        def ok():
            try:
                result["firm"] = Firm(
                    name=vars_["name"].get().strip(),
                    sector=vars_["sector"].get().strip(),
                    address=vars_["address"].get().strip(),
                    game_code=vars_["game_code"].get().strip(),
                    default_product=vars_["default_product"].get().strip(),
                    default_vat=float(vars_["default_vat"].get()),
                    default_amount=float(vars_["default_amount"].get()),
                )
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Hata", "KDV ve tutar sayısal olmalı")

        ttk.Button(dialog, text="Tamam", command=ok).pack(fill="x")
        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)
        return result["firm"]


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    app.update_preview()
    root.mainloop()
