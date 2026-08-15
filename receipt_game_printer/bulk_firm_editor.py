from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from firm_manager import Firm

BULK_HELP = "Firma | Sektör | Adres 1 | Adres 2 | Tel 1 | Tel 2 | Web | Vergi Dairesi | T.Sicil | EKU | Z | Alt Logo Kodu | Oyun Kodu | Ürün | KDV | Tutar"
LEGACY_HELP = "Firma | Sektör | Adres | Oyun Kodu | Ürün | KDV | Tutar"


class BulkFirmEditor(tk.Toplevel):
    def __init__(self, parent: tk.Misc, firms: list[Firm]):
        super().__init__(parent)
        self.title("Toplu Firma Düzenle")
        self.geometry("1000x600")
        self.result: tuple[str, list[Firm]] | None = None
        self.mode_var = tk.StringVar(value="replace")

        container = ttk.Frame(self, padding=12)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="Her satıra bir firma yazın:").pack(anchor="w")
        ttk.Label(container, text=BULK_HELP, foreground="#444", wraplength=950).pack(anchor="w", pady=(0, 8))

        self.text = tk.Text(container, font=("Courier New", 10), height=18)
        self.text.pack(fill="both", expand=True)
        self.text.insert("1.0", self._firms_to_text(firms))

        mode_frame = ttk.LabelFrame(container, text="İçe aktarma şekli", padding=8)
        mode_frame.pack(fill="x", pady=8)
        ttk.Radiobutton(mode_frame, text="Mevcut firmaları değiştir", value="replace", variable=self.mode_var).pack(anchor="w")
        ttk.Radiobutton(mode_frame, text="Mevcut firmaların üzerine ekle", value="append", variable=self.mode_var).pack(anchor="w")

        buttons = ttk.Frame(container)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="İçe Aktar", command=self._import).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(buttons, text="İptal", command=self.destroy).pack(side="left", fill="x", expand=True, padx=(4, 0))

        self.transient(parent)
        self.grab_set()

    def _firms_to_text(self, firms: list[Firm]) -> str:
        rows = []
        for firm in firms:
            rows.append(
                " | ".join(
                    [
                        firm.name,
                        firm.sector,
                        firm.address_line1,
                        firm.address_line2,
                        firm.phone1,
                        firm.phone2,
                        firm.website,
                        firm.tax_office,
                        firm.trade_registry_no,
                        firm.eku_no,
                        firm.z_no,
                        firm.footer_logo_code,
                        firm.game_code,
                        firm.default_product,
                        str(firm.default_vat).rstrip("0").rstrip("."),
                        str(firm.default_amount).rstrip("0").rstrip("."),
                    ]
                )
            )
        return "\n".join(rows)

    def _import(self):
        try:
            firms = parse_bulk_firms(self.text.get("1.0", tk.END))
        except ValueError as exc:
            messagebox.showerror("Hata", str(exc))
            return
        if not firms:
            messagebox.showerror("Hata", "Firma listesi boş")
            return
        self.result = (self.mode_var.get(), firms)
        self.destroy()


def parse_bulk_firms(text: str) -> list[Firm]:
    firms: list[Firm] = []
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) == 7:
            name, sector, address, game_code, product, vat_text, amount_text = parts
            address_line1, address_line2 = address, ""
            phone1 = phone2 = website = tax_office = trade_registry_no = eku_no = z_no = footer_logo_code = ""
        elif len(parts) == 12:
            (
                name, sector, address_line1, address_line2, phone1, phone2, website, tax_office,
                game_code, product, vat_text, amount_text,
            ) = parts
            trade_registry_no = eku_no = z_no = footer_logo_code = ""
        elif len(parts) == 16:
            (
                name, sector, address_line1, address_line2, phone1, phone2, website, tax_office,
                trade_registry_no, eku_no, z_no, footer_logo_code, game_code, product, vat_text, amount_text,
            ) = parts
        else:
            raise ValueError(f"{line_no}. satır hatalı. Format: {BULK_HELP} veya eski format: {LEGACY_HELP}")
        if not name:
            raise ValueError(f"{line_no}. satır: Firma adı boş olamaz")
        try:
            vat = float(vat_text.replace(",", "."))
        except ValueError as exc:
            raise ValueError(f"{line_no}. satır: KDV sayısal olmalı") from exc
        try:
            amount = float(amount_text.replace(",", "."))
        except ValueError as exc:
            raise ValueError(f"{line_no}. satır: Tutar sayısal olmalı") from exc
        firms.append(
            Firm(name, sector, address_line1, address_line2, phone1, phone2, website, tax_office, trade_registry_no, eku_no, z_no, footer_logo_code, game_code, product, vat, amount)
        )
    return firms


def ask_bulk_firms(parent: tk.Misc, firms: list[Firm]) -> tuple[str, list[Firm]] | None:
    dialog = BulkFirmEditor(parent, firms)
    parent.wait_window(dialog)
    return dialog.result
