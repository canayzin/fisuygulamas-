from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, ttk

from complete_batch import firm_identity
from receipt_styles import (
    ROLES, FirmReceiptStyleStore, StyleUndoManager, default_role_styles,
    resolve_role_styles, validate_overrides,
)


ROLE_LABELS = {
    "firm_name": "Firma Adı", "sector": "Sektör", "address": "Adres", "phone": "Telefon/Web",
    "tax_office": "Vergi Dairesi", "date": "Tarih", "time": "Saat", "receipt_no": "Fiş No",
    "product": "Ürün Satırı", "vat": "KDV Satırı", "total": "Toplam Satırı",
    "payment": "Ödeme Türü", "trade_registry": "Ticaret Sicil No", "eku_z": "EKU / Z No",
    "footer_logo": "NF Logo Alanı",
}

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
        self.bold_var = tk.BooleanVar()
        self.width_var = tk.IntVar(value=1)
        self.height_var = tk.IntVar(value=1)
        self.align_var = tk.StringVar(value="left")
        self.visible_var = tk.BooleanVar(value=True)
        self.wrap_var = tk.BooleanVar(value=True)
        self.spacing_var = tk.IntVar(value=0)
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

        right = ttk.LabelFrame(self, text="Role Bazlı Stil", padding=8)
        right.grid(row=1, column=2, sticky="nsew", padx=(5, 0))
        ttk.Label(right, text="Alan").pack(anchor="w")
        role_combo = ttk.Combobox(right, textvariable=self.role_var,
                                  values=list(ROLES), state="readonly")
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
        ttk.Separator(right).pack(fill="x", pady=10)
        ttk.Label(right, text="Preset").pack(anchor="w")
        ttk.Combobox(right, textvariable=self.preset_var, values=list(PRESETS), state="readonly").pack(fill="x")
        ttk.Button(right, text="Preset Uygula", command=self.apply_preset).pack(fill="x", pady=4)

    def _wire(self):
        self.search_var.trace_add("write", lambda *_: self.refresh_firms())
        self.filter_var.trace_add("write", lambda *_: self.refresh_firms())
        self.role_var.trace_add("write", lambda *_: self._load_role_vars())
        for var in (self.bold_var, self.width_var, self.height_var, self.align_var,
                    self.visible_var, self.wrap_var, self.spacing_var):
            var.trace_add("write", self._style_changed)
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
        style = resolve_role_styles(self.template_provider(), self.edit_state)[self.role_var.get()]
        self.bold_var.set(style.bold)
        self.width_var.set(style.width_scale)
        self.height_var.set(style.height_scale)
        self.align_var.set(style.align)
        self.visible_var.set(style.visible)
        self.wrap_var.set(True if style.wrap is None else style.wrap)
        self.spacing_var.set(style.line_spacing)
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
        }
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
        receipt = self.preview_builder(self.current_firm, self.edit_state)
        self.preview.configure(state="normal")
        self.preview.delete("1.0", tk.END)
        for index, block in enumerate(receipt.blocks):
            tag = f"block-{index}"
            size = 10 * max(block.style.width_scale, block.style.height_scale)
            weight = "bold" if block.style.bold else "normal"
            self.preview.tag_configure(tag, font=("Courier New", size, weight),
                                       justify=block.style.align,
                                       spacing3=block.style.line_spacing * 3)
            display = "▰ NF LOGO" + block.text.split("]", 1)[-1] if "[NF LOGO]" in block.text else block.text
            self.preview.insert(tk.END, display + "\n", tag)
        self.preview.configure(state="disabled")

    def _update_dirty(self):
        self.dirty_var.set("● Kaydedilmemiş değişiklikler" if self.is_dirty else "Kaydedildi")

    def save(self):
        if self.current_firm is None:
            return
        validate_overrides(self.edit_state)
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
        firms = [firm for firm in self.firms_provider() if firm_identity(firm) != firm_identity(self.current_firm)]
        for firm in firms:
            listing.insert(tk.END, firm.name)

        def apply():
            targets = [firms[index] for index in listing.curselection()]
            if targets and messagebox.askyesno("Stil Kopyala", f"Stil {len(targets)} firmaya uygulansın mı?", parent=window):
                for target in targets:
                    self.store.set(target, self.edit_state)
                self.store.save()
                window.destroy()
                self.refresh_firms()

        ttk.Button(window, text="Seçilen Firmalara Uygula", command=apply).pack(fill="x", padx=8, pady=8)

    def test_print(self):
        if self.current_firm is not None:
            self.test_print_callback(self.current_firm, self.edit_state)

    def select_firm_by_id(self, firm_id: str):
        self.search_var.set(firm_id)
        self.refresh_firms()
        if self.filtered_firms:
            self.firm_list.selection_set(0)
            self._select_firm()
