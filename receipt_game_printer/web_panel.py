from __future__ import annotations

import random
import socket
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from firm_manager import FirmManager
from printer_service import PrinterService
from receipt_formatter import ReceiptData, build_receipt_text
from template_manager import TemplateManager

BASE_DIR = Path(__file__).resolve().parent
FIRMS_JSON = BASE_DIR / "firms.json"
TEMPLATE_JSON = BASE_DIR / "receipt_template.json"
OUTPUT_DIR = BASE_DIR / "receipts_output"

app = Flask(__name__)
firm_manager = FirmManager(FIRMS_JSON)
template_manager = TemplateManager(TEMPLATE_JSON)
printer_service = PrinterService()

print_jobs: dict[str, dict] = {}
job_lock = threading.Lock()


def load_firms():
    return firm_manager.load()


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def pick_firms(count: int, mode: str, firms: list, no_repeat: bool, single_name: str | None):
    if mode == "single":
        selected = next((f for f in firms if f.name == single_name), None)
        if selected is None:
            raise ValueError("Tek firma seçimi geçersiz.")
        return [selected for _ in range(count)]
    if mode == "ordered":
        return [firms[i % len(firms)] for i in range(count)]
    out = []
    prev = None
    for _ in range(count):
        candidates = firms
        if no_repeat and prev is not None and len(firms) > 1:
            candidates = [f for f in firms if f.name != prev.name]
        cur = random.choice(candidates)
        out.append(cur)
        prev = cur
    return out


def pick_amount(mode: str, fixed: float, min_v: float, max_v: float, firm_default: float):
    if mode == "fixed":
        return fixed
    if mode == "firm":
        return firm_default
    if min_v > max_v:
        raise ValueError("Minimum tutar maksimumdan büyük olamaz.")
    return round(random.uniform(min_v, max_v), 2)


def next_dt(current: datetime, delta_mode: str):
    if delta_mode == "1":
        return current + timedelta(seconds=1)
    if delta_mode == "5":
        return current + timedelta(seconds=5)
    if delta_mode == "10":
        return current + timedelta(seconds=10)
    return current + timedelta(seconds=random.randint(1, 10))


def run_print_job(job_id: str, printer_name: str, receipt_texts: list[str]):
    with job_lock:
        print_jobs[job_id] = {"printed": 0, "total": len(receipt_texts), "stopped": False, "done": False, "error": None}

    for text in receipt_texts:
        with job_lock:
            if print_jobs[job_id]["stopped"]:
                break
        try:
            printer_service.print_raw(printer_name, text)
        except Exception:
            with job_lock:
                print_jobs[job_id]["error"] = "Baskı gönderilemedi. Yazıcı bulunamadı veya bağlantı kesildi."
            break
        with job_lock:
            print_jobs[job_id]["printed"] += 1

    with job_lock:
        print_jobs[job_id]["done"] = True


@app.get("/")
def index():
    firms = load_firms()
    local_ip = get_local_ip()
    return render_template("index.html", firms=firms, local_ip=local_ip)


@app.post("/api/generate")
def api_generate():
    try:
        firms = load_firms()
        if not firms:
            return jsonify({"error": "Firma listesi boş."}), 400

        payload = request.json or {}
        count = int(payload.get("count", 1))
        if count <= 0:
            return jsonify({"error": "Fiş sayısı 0'dan büyük olmalı."}), 400

        mode = payload.get("firm_mode", "ordered")
        no_repeat = bool(payload.get("no_repeat", False))
        single_name = payload.get("single_firm")

        amount_mode = payload.get("amount_mode", "fixed")
        fixed = float(payload.get("fixed_amount", 100))
        min_amount = float(payload.get("min_amount", 500))
        max_amount = float(payload.get("max_amount", 5000))

        start_mode = payload.get("start_mode", "now")
        if start_mode == "custom":
            dt = datetime.strptime(payload.get("start_datetime"), "%d-%m-%Y %H:%M:%S")
        else:
            dt = datetime.now()
        delta_mode = payload.get("delta_mode", "5")

        receipt_no = int(payload.get("start_receipt_no", 1))
        vat_rate = float(payload.get("vat_rate", 20))
        payment = payload.get("payment", "NAKIT")

        sequence = pick_firms(count, mode, firms, no_repeat, single_name)
        receipts = []
        for i in range(count):
            firm = sequence[i]
            amount = pick_amount(amount_mode, fixed, min_amount, max_amount, firm.default_amount)
            data = ReceiptData(
                firm_name=firm.name,
                sector=firm.sector,
                address=firm.address,
                address_line1=firm.address_line1,
                address_line2=firm.address_line2,
                phone1=firm.phone1,
                phone2=firm.phone2,
                website=firm.website,
                tax_office=firm.tax_office,
                game_code=firm.game_code,
                receipt_no=receipt_no + i,
                dt=dt,
                product_name=firm.default_product,
                vat_rate=vat_rate,
                amount=amount,
                payment_type=payment,
            )
            text = build_receipt_text(data, template_manager.load())
            filename = f"receipt_{receipt_no + i:06d}.txt"
            printer_service.save_txt(OUTPUT_DIR, filename, text)
            receipts.append({"filename": filename, "text": text})
            dt = next_dt(dt, delta_mode)

        return jsonify({"count": len(receipts), "receipts": receipts})
    except Exception:
        return jsonify({"error": "Fiş üretilemedi. Girdileri kontrol edin."}), 400


@app.post("/api/print")
def api_print():
    payload = request.json or {}
    printer_name = payload.get("printer_name", "").strip()
    texts = payload.get("texts")
    text = payload.get("text", "")

    if not printer_name:
        return jsonify({"error": "Yazıcı bulunamadı."}), 400

    receipt_texts = []
    if isinstance(texts, list) and texts:
        receipt_texts = [str(t) for t in texts if str(t).strip()]
    elif text.strip():
        receipt_texts = [text]

    if not receipt_texts:
        return jsonify({"error": "Baskı gönderilemedi. Yazdırılacak fiş bulunamadı."}), 400

    job_id = str(uuid.uuid4())
    threading.Thread(target=run_print_job, args=(job_id, printer_name, receipt_texts), daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})


@app.post("/api/print/stop")
def api_print_stop():
    payload = request.json or {}
    job_id = payload.get("job_id", "")
    with job_lock:
        if job_id not in print_jobs:
            return jsonify({"error": "Baskı işi bulunamadı."}), 404
        print_jobs[job_id]["stopped"] = True
    return jsonify({"ok": True})


@app.get("/api/print/status/<job_id>")
def api_print_status(job_id: str):
    with job_lock:
        if job_id not in print_jobs:
            return jsonify({"error": "Baskı işi bulunamadı."}), 404
        return jsonify(print_jobs[job_id])


@app.get("/api/printers")
def api_printers():
    return jsonify({"printers": printer_service.list_printers()})


@app.post("/api/print/test")
def api_print_test():
    payload = request.json or {}
    printer_name = payload.get("printer_name", "").strip()
    if not printer_name:
        return jsonify({"error": "Yazıcı bulunamadı."}), 400
    test_text = "TEST FISI\nYAZICI BAGLANTI TESTI\n"
    try:
        printer_service.print_raw(printer_name, test_text)
        return jsonify({"ok": True})
    except Exception:
        return jsonify({"error": "Baskı gönderilemedi. Yazıcı bulunamadı veya bağlantı kesildi."}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
