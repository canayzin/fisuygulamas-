from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from firm_manager import Firm


FIELD_LABELS = {
    "name": "Firma adı",
    "sector": "Sektör / açıklama",
    "address": "Adres",
    "game_code": "Oyun kodu / fiş kodu",
    "default_product": "Varsayılan ürün/hizmet adı",
    "default_vat": "Varsayılan KDV oranı",
    "default_amount": "Varsayılan tutar",
}


class FirmDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, initial: Firm | None = None):
        super().__init__(parent)
        self.title("Firma Ekle" if initial is None else "Firma Düzenle")
        self.resizable(False, False)
        self.result: Firm | None = None

        self.vars = {
            "name": tk.StringVar(value=getattr(initial, "name", "")),
            "sector": tk.StringVar(value=getattr(initial, "sector", "")),
            "address": tk.StringVar(value=getattr(initial, "address", "")),
            "game_code": tk.StringVar(value=getattr(initial, "game_code", "")),
            "default_product": tk.StringVar(value=getattr(initial, "default_product", "")),
            "default_vat": tk.StringVar(value=str(getattr(initial, "default_vat", 20))),
            "default_amount": tk.StringVar(value=str(getattr(initial, "default_amount", 100))),
        }

        container = ttk.Frame(self, padding=12)
        container.pack(fill="both", expand=True)
        warning = (
            "Gerçekçi ve temiz baskı için Türkçe karakter kullanmayın: "
            "Ç yerine C, Ğ yerine G, İ yerine I, Ş yerine S, Ü yerine U, Ö yerine O."
        )
        ttk.Label(container, text=warning, wraplength=430, foreground="#9a5b00").grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10)
        )

        for row, (key, label) in enumerate(FIELD_LABELS.items(), start=1):
            ttk.Label(container, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Entry(container, textvariable=self.vars[key], width=42).grid(row=row, column=1, sticky="ew", pady=4)

        buttons = ttk.Frame(container)
        buttons.grid(row=len(FIELD_LABELS) + 1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(buttons, text="Kaydet", command=self._save).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(buttons, text="İptal", command=self.destroy).pack(side="left", fill="x", expand=True, padx=(4, 0))

        self.transient(parent)
        self.grab_set()
        self.vars["name"].set(self.vars["name"].get().strip())

    def _save(self):
        name = self.vars["name"].get().strip()
        if not name:
            messagebox.showerror("Hata", "Firma adı boş olamaz")
            return

        try:
            vat = float(self.vars["default_vat"].get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Hata", "KDV sayısal olmalı")
            return

        try:
            amount = float(self.vars["default_amount"].get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Hata", "Tutar sayısal olmalı")
            return

        self.result = Firm(
            name=name,
            sector=self.vars["sector"].get().strip(),
            address=self.vars["address"].get().strip(),
            game_code=self.vars["game_code"].get().strip(),
            default_product=self.vars["default_product"].get().strip(),
            default_vat=vat,
            default_amount=amount,
        )
        self.destroy()


def ask_firm(parent: tk.Misc, initial: Firm | None = None) -> Firm | None:
    dialog = FirmDialog(parent, initial)
    parent.wait_window(dialog)
    return dialog.result
