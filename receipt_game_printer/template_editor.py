from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from template_manager import ReceiptTemplate, default_template, validate_template


class TemplateEditorFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, on_change):
        super().__init__(parent, padding=10)
        self.on_change = on_change
        self._updating = False

        self.eku_format_var = tk.StringVar()
        self.eku_no_var = tk.StringVar()
        self.z_no_var = tk.StringVar()
        self.separator_char_var = tk.StringVar()
        self.width_var = tk.StringVar()
        self.center_firm_var = tk.BooleanVar()
        self.product_format_var = tk.StringVar()
        self.show_vat_var = tk.BooleanVar()
        self.show_time_var = tk.BooleanVar()
        self.show_receipt_no_var = tk.BooleanVar()
        self.show_footer_var = tk.BooleanVar()
        self.show_phone_var = tk.BooleanVar()
        self.show_phone2_var = tk.BooleanVar()
        self.show_website_var = tk.BooleanVar()
        self.show_tax_office_var = tk.BooleanVar()
        self.phone_position_var = tk.StringVar()
        self.header_compact_var = tk.BooleanVar()
        self.wrap_address_var = tk.BooleanVar()
        self.receipt_no_zero_pad_var = tk.BooleanVar()
        self.show_trade_registry_no_var = tk.BooleanVar()
        self.show_footer_logo_var = tk.BooleanVar()
        self.footer_logo_text_var = tk.StringVar()
        self.use_firm_eku_z_var = tk.BooleanVar()
        self.use_bitmap_nf_logo_var = tk.BooleanVar()

        self._build()
        self.set_template(default_template())
        self._wire_changes()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="Üst bilgi satırları (her satır ayrı basılır)").grid(row=0, column=0, sticky="w")
        ttk.Label(self, text="Alt bilgi satırları (boş bırakılabilir)").grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.header_text = tk.Text(self, height=8, width=45)
        self.header_text.grid(row=1, column=0, sticky="nsew", pady=(4, 10))
        self.footer_text = tk.Text(self, height=8, width=45)
        self.footer_text.grid(row=1, column=1, sticky="nsew", padx=(10, 0), pady=(4, 10))

        form = ttk.LabelFrame(self, text="Şablon Ayarları", padding=10)
        form.grid(row=2, column=0, columnspan=2, sticky="ew")
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        self._entry(form, "EKU No formatı", self.eku_format_var, 0, 0)
        self._entry(form, "Varsayılan EKU No", self.eku_no_var, 0, 2)
        self._entry(form, "Z No değeri", self.z_no_var, 1, 0)
        self._entry(form, "Ayraç çizgisi karakteri", self.separator_char_var, 1, 2)
        self._entry(form, "Fiş genişliği karakter sayısı", self.width_var, 2, 0)
        self._entry(form, "Ürün satırı formatı", self.product_format_var, 3, 0, columnspan=3)
        self._entry(form, "Alt logo metni (bitmap kapalıysa)", self.footer_logo_text_var, 4, 0, columnspan=3)

        checks = ttk.Frame(form)
        checks.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Checkbutton(checks, text="Firma adı ortalansın mı?", variable=self.center_firm_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks, text="KDV satırı göster", variable=self.show_vat_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks, text="Saat göster", variable=self.show_time_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks, text="Fiş no göster", variable=self.show_receipt_no_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks, text="Alt bilgi göster", variable=self.show_footer_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks, text="Telefon göster", variable=self.show_phone_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks, text="İkinci telefon göster", variable=self.show_phone2_var).pack(side="left", padx=(0, 12))

        checks2 = ttk.Frame(form)
        checks2.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Checkbutton(checks2, text="Web sitesi göster", variable=self.show_website_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks2, text="Vergi dairesi göster", variable=self.show_tax_office_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks2, text="Adresleri satır kır", variable=self.wrap_address_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks2, text="Kompakt üst blok", variable=self.header_compact_var).pack(side="left", padx=(0, 12))

        checks3 = ttk.Frame(form)
        checks3.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Checkbutton(checks3, text="Fiş no sıfır dolgulu", variable=self.receipt_no_zero_pad_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks3, text="T. Sicil No göster", variable=self.show_trade_registry_no_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks3, text="Alt logo göster", variable=self.show_footer_logo_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks3, text="Bitmap NF logo kullan", variable=self.use_bitmap_nf_logo_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks3, text="Firma bazlı EKU/Z kullan", variable=self.use_firm_eku_z_var).pack(side="left", padx=(0, 12))

        position_box = ttk.LabelFrame(form, text="Telefon satırının yeri", padding=6)
        position_box.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Radiobutton(position_box, text="Adres üstünde", value="address_above", variable=self.phone_position_var).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(position_box, text="Adres altında", value="address_below", variable=self.phone_position_var).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(position_box, text="Tarih bölümünün üstünde", value="date_above", variable=self.phone_position_var).pack(side="left")

        ttk.Label(
            self,
            text="Not: Alt bilgi tamamen isteğe bağlıdır. Boş bırakılırsa fişin altında ekstra açıklama basılmaz.",
            foreground="#555",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _entry(self, parent, label, var, row, col, columnspan=1):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=col + 1, columnspan=columnspan, sticky="ew", pady=4)

    def _wire_changes(self):
        for var in [
            self.eku_format_var,
            self.eku_no_var,
            self.z_no_var,
            self.separator_char_var,
            self.width_var,
            self.center_firm_var,
            self.product_format_var,
            self.show_vat_var,
            self.show_time_var,
            self.show_receipt_no_var,
            self.show_footer_var,
            self.show_phone_var,
            self.show_phone2_var,
            self.show_website_var,
            self.show_tax_office_var,
            self.phone_position_var,
            self.header_compact_var,
            self.wrap_address_var,
            self.receipt_no_zero_pad_var,
            self.show_trade_registry_no_var,
            self.show_footer_logo_var,
            self.footer_logo_text_var,
            self.use_firm_eku_z_var,
            self.use_bitmap_nf_logo_var,
        ]:
            var.trace_add("write", self._changed)
        self.header_text.bind("<KeyRelease>", self._changed)
        self.footer_text.bind("<KeyRelease>", self._changed)

    def _changed(self, *_args):
        if not self._updating:
            self.on_change()

    def set_template(self, template: ReceiptTemplate):
        self._updating = True
        self.header_text.delete("1.0", tk.END)
        self.header_text.insert("1.0", "\n".join(template.header_lines))
        self.footer_text.delete("1.0", tk.END)
        self.footer_text.insert("1.0", "\n".join(template.footer_lines))
        self.eku_format_var.set(template.eku_format)
        self.eku_no_var.set(template.eku_no)
        self.z_no_var.set(template.z_no)
        self.separator_char_var.set(template.separator_char)
        self.width_var.set(str(template.width))
        self.center_firm_var.set(template.center_firm_name)
        self.product_format_var.set(template.product_line_format)
        self.show_vat_var.set(template.show_vat)
        self.show_time_var.set(template.show_time)
        self.show_receipt_no_var.set(template.show_receipt_no)
        self.show_footer_var.set(template.show_footer)
        self.show_phone_var.set(template.show_phone)
        self.show_phone2_var.set(template.show_phone2)
        self.show_website_var.set(template.show_website)
        self.show_tax_office_var.set(template.show_tax_office)
        self.phone_position_var.set(template.phone_position)
        self.header_compact_var.set(template.header_compact)
        self.wrap_address_var.set(template.wrap_address)
        self.receipt_no_zero_pad_var.set(template.receipt_no_zero_pad)
        self.show_trade_registry_no_var.set(template.show_trade_registry_no)
        self.show_footer_logo_var.set(template.show_footer_logo)
        self.footer_logo_text_var.set(template.footer_logo_text)
        self.use_firm_eku_z_var.set(template.use_firm_eku_z)
        self.use_bitmap_nf_logo_var.set(template.use_bitmap_nf_logo)
        self._updating = False

    def get_template(self) -> ReceiptTemplate:
        try:
            width = int(self.width_var.get())
        except ValueError as exc:
            raise ValueError("Fiş genişliği geçersiz") from exc
        template = ReceiptTemplate(
            header_lines=self._text_lines(self.header_text),
            footer_lines=self._text_lines(self.footer_text),
            eku_format=self.eku_format_var.get().strip() or "EKU NO: {eku_no}",
            eku_no=self.eku_no_var.get().strip() or "001",
            z_no=self.z_no_var.get().strip() or "707",
            separator_char=(self.separator_char_var.get().strip() or "-")[0],
            width=width,
            center_firm_name=self.center_firm_var.get(),
            product_line_format=self.product_format_var.get().strip() or "{product}",
            show_vat=self.show_vat_var.get(),
            show_time=self.show_time_var.get(),
            show_receipt_no=self.show_receipt_no_var.get(),
            show_footer=self.show_footer_var.get(),
            show_phone=self.show_phone_var.get(),
            show_phone2=self.show_phone2_var.get(),
            show_website=self.show_website_var.get(),
            show_tax_office=self.show_tax_office_var.get(),
            phone_position=self.phone_position_var.get() or "address_below",
            header_compact=self.header_compact_var.get(),
            wrap_address=self.wrap_address_var.get(),
            receipt_no_zero_pad=self.receipt_no_zero_pad_var.get(),
            show_trade_registry_no=self.show_trade_registry_no_var.get(),
            show_footer_logo=self.show_footer_logo_var.get(),
            footer_logo_text=self.footer_logo_text_var.get().strip() or "NF",
            use_firm_eku_z=self.use_firm_eku_z_var.get(),
            use_bitmap_nf_logo=self.use_bitmap_nf_logo_var.get(),
        )
        validate_template(template)
        return template

    def _text_lines(self, widget: tk.Text) -> list[str]:
        return [line.rstrip() for line in widget.get("1.0", tk.END).splitlines() if line.strip()]
