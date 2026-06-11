from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from firm_manager import Firm


FIELD_LABELS = {
    "name": "Firma adı",
    "sector": "Sektör",
    "address_line1": "Adres Satır 1",
    "address_line2": "Adres Satır 2",
    "phone1": "Telefon Numarası",
    "phone2": "Telefon Numarası 2 (opsiyonel)",
    "website": "Web Sitesi (opsiyonel)",
    "tax_office": "Vergi Dairesi (opsiyonel)",
    "game_code": "Oyun kodu / fiş kodu",
    "default_product": "Ürün/Hizmet",
    "default_vat": "Varsayılan KDV",
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
            "address_line1": tk.StringVar(value=getattr(initial, "address_line1", getattr(initial, "address", ""))),
            "address_line2": tk.StringVar(value=getattr(initial, "address_line2", "")),
            "phone1": tk.StringVar(value=getattr(initial, "phone1", "")),
            "phone2": tk.StringVar(value=getattr(initial, "phone2", "")),
            "website": tk.StringVar(value=getattr(initial, "website", "")),
            "tax_office": tk.StringVar(value=getattr(initial, "tax_office", "")),
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
        ttk.Label(container, text=warning, wraplength=500, foreground="#9a5b00").grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10)
        )

        for row, (key, label) in enumerate(FIELD_LABELS.items(), start=1):
            ttk.Label(container, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
            ttk.Entry(container, textvariable=self.vars[key], width=50).grid(row=row, column=1, sticky="ew", pady=3)

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
            address_line1=self.vars["address_line1"].get().strip(),
            address_line2=self.vars["address_line2"].get().strip(),
            phone1=self.vars["phone1"].get().strip(),
            phone2=self.vars["phone2"].get().strip(),
            website=self.vars["website"].get().strip(),
            tax_office=self.vars["tax_office"].get().strip(),
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
