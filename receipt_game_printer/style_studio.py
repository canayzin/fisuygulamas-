from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, ttk

from complete_batch import firm_identity
from receipt_styles import (
    ROLES, FirmReceiptStyleStore, StyleUndoManager, default_role_styles,
    resolve_role_styles, validate_overrides,
    validate_layout,
)
from printer_service import NF_LOGO_BITMAP


ROLE_LABELS = {
    "firm_name": "Firma Adı", "sector": "Sektör", "address": "Adres", "phone": "Telefon/Web",
    "tax_office": "Vergi Dairesi", "date": "Tarih", "time": "Saat", "receipt_no": "Fiş No",
    "product": "Ürün Satırı", "vat": "KDV Satırı", "total": "Toplam Satırı",
    "payment": "Ödeme Türü", "trade_registry": "Ticaret Sicil No", "eku_z": "EKU / Z No",
    "footer_logo": "NF Logo Alanı",
}
ROLE_LABELS.update({role: role.replace("_", " ").title() for role in ROLES if role not in ROLE_LABELS})

PRESETS = {
    "Standart": {},
    "Kalın Başlık": {"firm_name": {"bold": True}},
    "Büyük KDV": {"vat": {"bold": True, "width_scale": 2}},
    "Büyük Toplam": {"total": {"bold": True, "height_scale": 2}},
    "Kompakt": {"firm_name": {"height_scale": 1}, "address": {"line_spacing": 0}},
}


class FirmReceiptStudioFrame(ttk.Frame):
    def __init__(self, parent, firms_provider, template_provider, store: FirmReceiptStyleStore,
                 preview_builder, test_print_callback):
        super().__init__(parent, padding=8)
        self.firms_provider = firms_provider
        self.template_provider = template_provider
        self.store = store
        self.preview_builder = preview_builder
        self.test_print_callback = test_print_callback
        self.filtered_firms = []
        self.current_firm = None
        self.saved_state: dict = {}
        self.edit_state: dict = {}
        self.undo_manager = StyleUndoManager({})
        self._updating = False

        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar(value="Tümü")
        self.role_var = tk.StringVar(value="firm_name")
        self.role_display_var = tk.StringVar(value=ROLE_LABELS["firm_name"])
        self.bold_var = tk.BooleanVar()
        self.width_var = tk.IntVar(value=1)
        self.height_var = tk.IntVar(value=1)
        self.align_var = tk.StringVar(value="left")
        self.visible_var = tk.BooleanVar(value=True)
        self.wrap_var = tk.BooleanVar(value=True)
        self.spacing_var = tk.IntVar(value=0)
        self.x_var = tk.IntVar(value=0)
        self.y_var = tk.IntVar(value=0)
        self.before_var = tk.IntVar(value=0)
        self.after_var = tk.IntVar(value=0)
        self.order_var = tk.IntVar(value=0)
        self.column_var = tk.IntVar(value=0)
        self.same_line_var = tk.BooleanVar()
        self.locked_var = tk.BooleanVar()
        self.prefix_var = tk.StringVar()
        self.suffix_var = tk.StringVar()
        self.text_override_var = tk.StringVar()
        self.logo_x_var = tk.IntVar(value=0)
        self.logo_y_var = tk.IntVar(value=0)
        self.code_gap_var = tk.IntVar(value=2)
        self.code_x_var = tk.IntVar(value=0)
        self.code_y_var = tk.IntVar(value=0)
        self.code_bold_var = tk.BooleanVar()
        self.code_align_var = tk.StringVar(value="left")
        self.code_width_var = tk.IntVar(value=1)
        self.code_height_var = tk.IntVar(value=1)
        self.zoom_var = tk.IntVar(value=100)
        self.grid_var = tk.BooleanVar()
        self.sample_amount_var = tk.StringVar(value="5000")
        self.sample_vat_var = tk.StringVar(value="20")
        self.sample_receipt_var = tk.StringVar(value="123")
        self.sample_payment_var = tk.StringVar(value="NAKIT")
        self.sample_date_var = tk.StringVar(value="16.08.2026")
        self.preset_var = tk.StringVar(value="Standart")
        self.dirty_var = tk.StringVar(value="")
        self._build()
        self.refresh_firms()
        self._wire()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)
        self.columnconfigure(2, weight=1)
        self.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        for text, command in [
            ("Kaydet", self.save), ("Geri Al", self.undo), ("İleri Al", self.redo),
            ("Kaydedilmiş Hale Dön", self.restore_saved),
            ("Orijinal Varsayılana Dön", self.reset_default),
            ("Stili Kopyala/Uygula", self.copy_to_firms),
            ("Bu Firmayı Test Bas", self.test_print),
            ("Logo Hizalama Testi Bas", self.logo_test_print),
        ]:
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=(0, 4))
        ttk.Label(toolbar, textvariable=self.dirty_var, foreground="#a35b00").pack(side="right")

        left = ttk.LabelFrame(self, text="Firmalar", padding=6)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        left.rowconfigure(2, weight=1)
        left.columnconfigure(0, weight=1)
        ttk.Entry(left, textvariable=self.search_var).grid(row=0, column=0, sticky="ew")
        ttk.Combobox(left, textvariable=self.filter_var,
                     values=["Tümü", "Sadece özel tasarımlı", "Varsayılan kullananlar"],
                     state="readonly").grid(row=1, column=0, sticky="ew", pady=4)
        self.firm_list = tk.Listbox(left, exportselection=False)
        self.firm_list.grid(row=2, column=0, sticky="nsew")
        self.firm_list.bind("<<ListboxSelect>>", self._select_firm)

        middle = ttk.LabelFrame(self, text="Canlı Fiş Önizlemesi", padding=6)
        middle.grid(row=1, column=1, sticky="nsew", padx=5)
        middle.rowconfigure(0, weight=1)
        middle.columnconfigure(0, weight=1)
        self.preview = tk.Text(middle, width=38, background="#fffdf2", state="disabled", font=("Courier New", 10))
        self.preview.grid(row=0, column=0, sticky="nsew")
        preview_tools = ttk.Frame(middle)
        preview_tools.grid(row=1, column=0, sticky="ew")
        ttk.Label(preview_tools, text="Zoom").pack(side="left")
        ttk.Combobox(preview_tools, textvariable=self.zoom_var, values=[50, 75, 100, 125, 150, 200], width=5,
                     state="readonly").pack(side="left")
        ttk.Checkbutton(preview_tools, text="Grid / Safe Area", variable=self.grid_var).pack(side="left", padx=6)
        for label, variable, width in [("Tutar", self.sample_amount_var, 7), ("KDV", self.sample_vat_var, 4),
                                       ("Fiş No", self.sample_receipt_var, 5), ("Ödeme", self.sample_payment_var, 7)]:
            ttk.Label(preview_tools, text=label).pack(side="left")
            ttk.Entry(preview_tools, textvariable=variable, width=width).pack(side="left")
        ttk.Label(preview_tools, text="Tarih").pack(side="left")
        ttk.Entry(preview_tools, textvariable=self.sample_date_var, width=10).pack(side="left")

        right_shell = ttk.LabelFrame(self, text="Alan / Layout Özellikleri", padding=4)
        right_shell.grid(row=1, column=2, sticky="nsew", padx=(5, 0))
        right_canvas = tk.Canvas(right_shell, highlightthickness=0, width=285)
        right_scroll = ttk.Scrollbar(right_shell, orient="vertical", command=right_canvas.yview)
        right_canvas.configure(yscrollcommand=right_scroll.set)
        right_canvas.pack(side="left", fill="both", expand=True)
        right_scroll.pack(side="right", fill="y")
        right = ttk.Frame(right_canvas, padding=4)
        right_window = right_canvas.create_window((0, 0), window=right, anchor="nw")
        right.bind("<Configure>", lambda _event: right_canvas.configure(scrollregion=right_canvas.bbox("all")))
        right_canvas.bind("<Configure>", lambda event: right_canvas.itemconfigure(right_window, width=event.width))
        ttk.Label(right, text="Alan").pack(anchor="w")
        role_combo = ttk.Combobox(right, textvariable=self.role_display_var,
                                  values=[ROLE_LABELS[role] for role in ROLES], state="readonly")
        role_combo.pack(fill="x")
        ttk.Checkbutton(right, text="Kalın", variable=self.bold_var).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(right, text="Görünür", variable=self.visible_var).pack(anchor="w")
        ttk.Label(right, text="Genişlik ölçeği").pack(anchor="w", pady=(8, 0))
        ttk.Combobox(right, textvariable=self.width_var, values=[1, 2], state="readonly").pack(fill="x")
        ttk.Label(right, text="Yükseklik ölçeği").pack(anchor="w", pady=(8, 0))
        ttk.Combobox(right, textvariable=self.height_var, values=[1, 2], state="readonly").pack(fill="x")
        ttk.Label(right, text="Hizalama").pack(anchor="w", pady=(8, 0))
        ttk.Combobox(right, textvariable=self.align_var, values=["left", "center", "right"],
                     state="readonly").pack(fill="x")
        ttk.Checkbutton(right, text="Adres satırlarını kır", variable=self.wrap_var).pack(anchor="w", pady=(8, 0))
        ttk.Label(right, text="Satır aralığı").pack(anchor="w")
        ttk.Combobox(right, textvariable=self.spacing_var, values=[0, 1, 2, 3], state="readonly").pack(fill="x")
        position = ttk.LabelFrame(right, text="Layout / Konum", padding=4)
        position.pack(fill="x", pady=6)
        for label, variable, values in [
            ("X offset", self.x_var, list(range(-10, 11))), ("Y offset", self.y_var, list(range(-5, 6))),
            ("Ön boşluk", self.before_var, list(range(6))), ("Son boşluk", self.after_var, list(range(6))),
            ("Sıra", self.order_var, list(range(0, 101))),
            ("Kolon genişliği", self.column_var, list(range(0, 49))),
        ]:
            row = ttk.Frame(position); row.pack(fill="x")
            ttk.Label(row, text=label, width=11).pack(side="left")
            ttk.Spinbox(row, textvariable=variable, values=values, width=6).pack(side="left")
        ttk.Checkbutton(position, text="Sonraki alan aynı satırda", variable=self.same_line_var).pack(anchor="w")
        ttk.Checkbutton(position, text="Alanı kilitle", variable=self.locked_var).pack(anchor="w")
        ttk.Label(position, text="Prefix / Suffix").pack(anchor="w")
        ttk.Entry(position, textvariable=self.prefix_var).pack(fill="x")
        ttk.Entry(position, textvariable=self.suffix_var).pack(fill="x")
        ttk.Label(position, text="Metin / separator override").pack(anchor="w")
        ttk.Entry(position, textvariable=self.text_override_var).pack(fill="x")
        movement = ttk.Frame(position); movement.pack(fill="x")
        ttk.Button(movement, text="↑ Yukarı", command=lambda: self.move_field(-1)).pack(side="left")
        ttk.Button(movement, text="↓ Aşağı", command=lambda: self.move_field(1)).pack(side="left")
        ttk.Button(position, text="Bu Alanı Varsayılana Döndür", command=self.reset_field).pack(fill="x")
        ttk.Button(position, text="Bu Bölümü Varsayılana Döndür", command=self.reset_section).pack(fill="x")
        ttk.Button(position, text="+ Metin Alanı Ekle / Kopyala", command=self.add_custom_text).pack(fill="x")

        logo = ttk.LabelFrame(right, text="NF Logo / Kod İnce Ayarı", padding=4)
        logo.pack(fill="x")
        for label, variable, values in [
            ("Logo X dot", self.logo_x_var, list(range(-20, 21))), ("Logo Y dot", self.logo_y_var, list(range(-8, 9))),
            ("Kod aralığı", self.code_gap_var, list(range(11))), ("Kod X dot", self.code_x_var, list(range(-20, 21))),
            ("Kod Y dot", self.code_y_var, list(range(-8, 9))),
        ]:
            row = ttk.Frame(logo); row.pack(fill="x")
            ttk.Label(row, text=label, width=12).pack(side="left")
            ttk.Spinbox(row, textvariable=variable, values=values, width=6).pack(side="left")
        ttk.Checkbutton(logo, text="Logo kodu kalın", variable=self.code_bold_var).pack(anchor="w")
        ttk.Combobox(logo, textvariable=self.code_align_var, values=["left", "center", "right"],
                     state="readonly").pack(fill="x")
        code_size = ttk.Frame(logo); code_size.pack(fill="x")
        ttk.Label(code_size, text="Kod W/H").pack(side="left")
        ttk.Combobox(code_size, textvariable=self.code_width_var, values=[1, 2], width=3, state="readonly").pack(side="left")
        ttk.Combobox(code_size, textvariable=self.code_height_var, values=[1, 2], width=3, state="readonly").pack(side="left")
        ttk.Separator(right).pack(fill="x", pady=10)
        ttk.Label(right, text="Preset").pack(anchor="w")
        ttk.Combobox(right, textvariable=self.preset_var, values=list(PRESETS), state="readonly").pack(fill="x")
        ttk.Button(right, text="Preset Uygula", command=self.apply_preset).pack(fill="x", pady=4)

    def _wire(self):
        self.search_var.trace_add("write", lambda *_: self.refresh_firms())
        self.filter_var.trace_add("write", lambda *_: self.refresh_firms())
        self.role_var.trace_add("write", lambda *_: self._load_role_vars())
        self.role_display_var.trace_add("write", self._display_role_changed)
        for var in (self.bold_var, self.width_var, self.height_var, self.align_var,
                    self.visible_var, self.wrap_var, self.spacing_var, self.x_var, self.y_var,
                    self.before_var, self.after_var, self.order_var, self.column_var, self.same_line_var, self.locked_var,
                    self.prefix_var, self.suffix_var, self.text_override_var, self.logo_x_var, self.logo_y_var, self.code_gap_var,
                    self.code_x_var, self.code_y_var, self.code_bold_var, self.code_align_var,
                    self.code_width_var, self.code_height_var):
            var.trace_add("write", self._style_changed)
        for var in (self.zoom_var, self.grid_var, self.sample_amount_var, self.sample_vat_var,
                    self.sample_receipt_var, self.sample_payment_var, self.sample_date_var):
            var.trace_add("write", lambda *_: self._update_preview())
        self.bind_all("<Control-s>", lambda _event: self.save())
        self.bind_all("<Control-z>", lambda _event: self.undo())
        self.bind_all("<Control-y>", lambda _event: self.redo())

    def refresh_firms(self):
        query = self.search_var.get().strip().casefold()
        mode = self.filter_var.get()
        self.filtered_firms = []
        self.firm_list.delete(0, tk.END)
        selected_index = None
        for firm in self.firms_provider():
            firm_id = firm_identity(firm)
            special = bool(self.store.get(firm_id))
            haystack = f"{firm.name} {getattr(firm, 'game_code', '')} {firm_id}".casefold()
            if query and query not in haystack:
                continue
            if mode == "Sadece özel tasarımlı" and not special:
                continue
            if mode == "Varsayılan kullananlar" and special:
                continue
            self.filtered_firms.append(firm)
            self.firm_list.insert(tk.END, f"{firm.name}{'   ● Özel' if special else ''}")
            if self.current_firm is not None and firm_id == firm_identity(self.current_firm):
                selected_index = len(self.filtered_firms) - 1
        if selected_index is not None:
            self.firm_list.selection_set(selected_index)
        if self.filtered_firms and self.current_firm is None:
            self.firm_list.selection_set(0)
            self._select_firm()

    def _display_role_changed(self, *_args):
        selected = next((role for role, label in ROLE_LABELS.items() if label == self.role_display_var.get()), None)
        if selected and selected != self.role_var.get():
            self.role_var.set(selected)

    def _select_firm(self, _event=None):
        if not self.firm_list.curselection():
            return
        target = self.filtered_firms[self.firm_list.curselection()[0]]
        if self.current_firm is not None and self.is_dirty:
            answer = messagebox.askyesnocancel(
                "Kaydedilmemiş Değişiklik", "Kaydedilmemiş değişiklikler var. Kaydedilsin mi?"
            )
            if answer is None:
                return
            if answer:
                self.save()
        self.current_firm = target
        self.saved_state = self.store.get(target)
        self.edit_state = copy.deepcopy(self.saved_state)
        self.undo_manager = StyleUndoManager(self.edit_state)
        self._load_role_vars()
        self._update_preview()
        self._update_dirty()

    @property
    def is_dirty(self):
        return self.edit_state != self.saved_state

    def _load_role_vars(self):
        if self.current_firm is None:
            return
        self._updating = True
        self.role_display_var.set(ROLE_LABELS[self.role_var.get()])
        style = resolve_role_styles(self.template_provider(), self.edit_state)[self.role_var.get()]
        self.bold_var.set(style.bold)
        self.width_var.set(style.width_scale)
        self.height_var.set(style.height_scale)
        self.align_var.set(style.align)
        self.visible_var.set(style.visible)
        self.wrap_var.set(True if style.wrap is None else style.wrap)
        self.spacing_var.set(style.line_spacing)
        self.x_var.set(style.x_offset); self.y_var.set(style.y_offset)
        self.before_var.set(style.space_before); self.after_var.set(style.space_after)
        self.order_var.set(style.order); self.same_line_var.set(style.same_line); self.locked_var.set(style.locked)
        self.column_var.set(style.column_width)
        self.prefix_var.set(style.prefix); self.suffix_var.set(style.suffix)
        self.text_override_var.set(style.text_override)
        self.logo_x_var.set(style.logo_x_offset); self.logo_y_var.set(style.logo_y_offset)
        self.code_gap_var.set(style.code_gap); self.code_x_var.set(style.code_x_offset)
        self.code_y_var.set(style.code_y_offset); self.code_bold_var.set(style.code_bold)
        self.code_align_var.set(style.code_align)
        self.code_width_var.set(style.code_width_scale); self.code_height_var.set(style.code_height_scale)
        self._updating = False

    def _style_changed(self, *_args):
        if self._updating or self.current_firm is None:
            return
        role = self.role_var.get()
        defaults = default_role_styles(self.template_provider())[role]
        values = {
            "bold": self.bold_var.get(), "width_scale": self.width_var.get(),
            "height_scale": self.height_var.get(), "align": self.align_var.get(),
            "visible": self.visible_var.get(), "line_spacing": self.spacing_var.get(),
            "x_offset": self.x_var.get(), "y_offset": self.y_var.get(),
            "space_before": self.before_var.get(), "space_after": self.after_var.get(),
            "order": self.order_var.get(), "same_line": self.same_line_var.get(), "locked": self.locked_var.get(),
            "column_width": self.column_var.get(),
            "prefix": self.prefix_var.get(), "suffix": self.suffix_var.get(),
            "text_override": self.text_override_var.get(),
        }
        if role in {"footer_logo", "logo_code"}:
            values.update({
                "logo_x_offset": self.logo_x_var.get(), "logo_y_offset": self.logo_y_var.get(),
                "code_gap": self.code_gap_var.get(), "code_x_offset": self.code_x_var.get(),
                "code_y_offset": self.code_y_var.get(), "code_bold": self.code_bold_var.get(),
                "code_align": self.code_align_var.get(),
                "code_width_scale": self.code_width_var.get(), "code_height_scale": self.code_height_var.get(),
            })
        if role == "address":
            values["wrap"] = self.wrap_var.get()
        default_values = {key: getattr(defaults, key) for key in values}
        changed = {key: value for key, value in values.items() if value != default_values[key]}
        state = copy.deepcopy(self.edit_state)
        if changed:
            state[role] = changed
        else:
            state.pop(role, None)
        validate_overrides(state)
        self.edit_state = state
        self.undo_manager.push(state)
        self._update_preview()
        self._update_dirty()

    def _update_preview(self):
        if self.current_firm is None:
            return
        sample = {
            "amount": self.sample_amount_var.get(), "vat_rate": self.sample_vat_var.get(),
            "receipt_no": self.sample_receipt_var.get(), "payment_type": self.sample_payment_var.get(),
            "date": self.sample_date_var.get(),
        }
        try:
            receipt = self.preview_builder(self.current_firm, self.edit_state, sample)
        except (ValueError, TypeError):
            return
        self.preview.configure(state="normal")
        self.preview.delete("1.0", tk.END)
        self._preview_images = []
        for index, block in enumerate(receipt.blocks):
            tag = f"block-{index}"
            size = max(5, int(10 * max(block.style.width_scale, block.style.height_scale) * self.zoom_var.get() / 100))
            weight = "bold" if block.style.bold else "normal"
            self.preview.tag_configure(tag, font=("Courier New", size, weight),
                                       justify=block.style.align,
                                       spacing3=block.style.line_spacing * 3)
            self.preview.tag_bind(tag, "<Button-1>", lambda _event, role=block.role: self.role_var.set(role)
                                  if role in ROLES else None)
            if "[NF LOGO]" in block.text:
                scale = max(1, self.zoom_var.get() // 50)
                image = self._logo_image(scale, max(0, min(10, 7 + block.style.logo_y_offset)))
                self.preview.image_create(tk.END, image=image, padx=max(0, block.style.logo_x_offset))
                self._preview_images.append(image)
                code = block.text.split("]", 1)[-1].strip()
                code_tag = tag + "-code"
                code_size = max(5, int(10 * max(block.style.code_width_scale, block.style.code_height_scale)
                                       * self.zoom_var.get() / 100))
                self.preview.tag_configure(code_tag, font=("Courier New", code_size,
                                           "bold" if block.style.code_bold else "normal"),
                                           justify=block.style.code_align)
                self.preview.insert(tk.END, " " * block.style.code_gap + code + "\n", code_tag)
            else:
                self.preview.insert(tk.END, block.text + "\n", tag)
        if self.grid_var.get():
            self.preview.tag_configure("grid", background="#f3f3e8")
            self.preview.tag_add("grid", "1.0", tk.END)
        self.preview.configure(state="disabled")

    def _logo_image(self, scale, y_offset):
        width, height = len(NF_LOGO_BITMAP[0]), 24
        image = tk.PhotoImage(width=width * scale, height=height * scale)
        image.put("white", to=(0, 0, width * scale, height * scale))
        for y, row in enumerate(NF_LOGO_BITMAP):
            target_y = y + y_offset
            if 0 <= target_y < height:
                for x, pixel in enumerate(row):
                    if pixel == "#":
                        image.put("black", to=(x * scale, target_y * scale, (x + 1) * scale, (target_y + 1) * scale))
        return image

    def _update_dirty(self):
        self.dirty_var.set("● Kaydedilmemiş değişiklikler" if self.is_dirty else "Kaydedildi")

    def save(self):
        if self.current_firm is None:
            return
        validate_layout(self.edit_state, self.template_provider().width, ["*12.345.678,90"])
        self.store.set(self.current_firm, self.edit_state)
        self.store.save()
        self.saved_state = copy.deepcopy(self.edit_state)
        self._update_dirty()
        self.refresh_firms()

    def undo(self):
        self.edit_state = self.undo_manager.undo()
        self._load_role_vars()
        self._update_preview()
        self._update_dirty()

    def redo(self):
        self.edit_state = self.undo_manager.redo()
        self._load_role_vars()
        self._update_preview()
        self._update_dirty()

    def restore_saved(self):
        if self.is_dirty and not messagebox.askyesno(
            "Kaydedilmiş Hale Dön", "Kaydedilmemiş değişiklikler silinecek. Devam edilsin mi?"
        ):
            return
        self.edit_state = copy.deepcopy(self.saved_state)
        self.undo_manager.push(self.edit_state)
        self._load_role_vars()
        self._update_preview()
        self._update_dirty()

    def reset_default(self):
        if not messagebox.askyesno("Orijinal Varsayılan", "Bütün firma override'ları temizlensin mi?"):
            return
        self.edit_state = {}
        self.undo_manager.push({})
        self._load_role_vars()
        self._update_preview()
        self._update_dirty()

    def reset_field(self):
        role = self.role_var.get()
        state = copy.deepcopy(self.edit_state)
        state.pop(role, None)
        self._apply_edit_state(state)

    def reset_section(self):
        role = self.role_var.get()
        sections = {
            "header": {"firm_name", "sector", "address", "address_line1", "address_line2", "phone", "phone1", "phone2", "website", "tax_office", "trade_registry"},
            "financial": {"product", "product_name", "vat_rate", "product_amount", "vat", "vat_label", "vat_amount", "total", "total_label", "total_amount", "payment", "payment_type", "payment_amount", "separator1", "separator2"},
            "footer": {"eku_z", "eku_label", "eku_value", "z_label", "z_value", "footer_logo", "logo_code", "footer"},
        }
        selected = next((values for values in sections.values() if role in values), {role})
        state = {key: value for key, value in self.edit_state.items() if key not in selected}
        self._apply_edit_state(state)

    def move_field(self, direction):
        role = self.role_var.get()
        state = copy.deepcopy(self.edit_state)
        current = resolve_role_styles(self.template_provider(), state)[role].order
        state.setdefault(role, {})["order"] = max(1, current or ROLES.index(role) + 1) + direction
        self._apply_edit_state(state)

    def add_custom_text(self):
        state = copy.deepcopy(self.edit_state)
        current = state.get("custom_text", {})
        text = current.get("text_override", "TESEKKUR EDERIZ")
        state["custom_text"] = {**current, "text_override": text, "align": "center", "order": current.get("order", 90)}
        self.role_var.set("custom_text")
        self._apply_edit_state(state)

    def _apply_edit_state(self, state):
        validate_overrides(state)
        self.edit_state = state
        self.undo_manager.push(state)
        self._load_role_vars(); self._update_preview(); self._update_dirty()

    def apply_preset(self):
        self.edit_state = copy.deepcopy(PRESETS[self.preset_var.get()])
        self.undo_manager.push(self.edit_state)
        self._load_role_vars()
        self._update_preview()
        self._update_dirty()

    def copy_to_firms(self):
        if self.current_firm is None:
            return
        window = tk.Toplevel(self)
        window.title("Stili Seçilen Firmalara Uygula")
        listing = tk.Listbox(window, selectmode="multiple", exportselection=False)
        listing.pack(fill="both", expand=True, padx=8, pady=8)
        scope_var = tk.StringVar(value="Tüm tasarım")
        ttk.Combobox(window, textvariable=scope_var, state="readonly", values=[
            "Tüm tasarım", "Sadece header", "Sadece finansal bölüm", "Sadece footer/logo", "Sadece seçili alan"
        ]).pack(fill="x", padx=8)
        firms = [firm for firm in self.firms_provider() if firm_identity(firm) != firm_identity(self.current_firm)]
        for firm in firms:
            listing.insert(tk.END, firm.name)

        def apply():
            targets = [firms[index] for index in listing.curselection()]
            if targets and messagebox.askyesno("Stil Kopyala", f"Stil {len(targets)} firmaya uygulansın mı?", parent=window):
                groups = {
                    "Sadece header": {"firm_name", "sector", "address", "address_line1", "address_line2", "phone", "phone1", "phone2", "website", "tax_office", "trade_registry"},
                    "Sadece finansal bölüm": {"product", "product_name", "vat_rate", "product_amount", "vat", "vat_label", "vat_amount", "total", "total_label", "total_amount", "payment", "payment_type", "payment_amount", "separator1", "separator2"},
                    "Sadece footer/logo": {"eku_z", "eku_label", "eku_value", "z_label", "z_value", "footer_logo", "logo_code", "footer"},
                    "Sadece seçili alan": {self.role_var.get()},
                }
                selected_roles = groups.get(scope_var.get())
                profile = self.edit_state if selected_roles is None else {
                    key: value for key, value in self.edit_state.items() if key in selected_roles
                }
                for target in targets:
                    target_profile = self.store.get(target)
                    if selected_roles is None:
                        target_profile = profile
                    else:
                        for role in selected_roles:
                            target_profile.pop(role, None)
                        target_profile.update(profile)
                    self.store.set(target, target_profile)
                self.store.save()
                window.destroy()
                self.refresh_firms()

        ttk.Button(window, text="Seçilen Firmalara Uygula", command=apply).pack(fill="x", padx=8, pady=8)

    def test_print(self):
        if self.current_firm is not None:
            self.test_print_callback(self.current_firm, self.edit_state)

    def logo_test_print(self):
        if self.current_firm is not None:
            self.test_print_callback(self.current_firm, self.edit_state, logo_only=True)

    def select_firm_by_id(self, firm_id: str):
        self.search_var.set(firm_id)
        self.refresh_firms()
        if self.filtered_firms:
            self.firm_list.selection_set(0)
            self._select_firm()
