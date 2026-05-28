import io
import os
import re
import sqlite3
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="")

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "bills.db")
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "uploads")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calculations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total_bill REAL NOT NULL,
            main_meter REAL NOT NULL,
            lokanta_start REAL NOT NULL,
            lokanta_end REAL NOT NULL,
            koltukcu_start REAL NOT NULL,
            koltukcu_end REAL NOT NULL,
            lokanta_consumption REAL NOT NULL,
            koltukcu_consumption REAL NOT NULL,
            emlak_consumption REAL NOT NULL,
            lokanta_amount REAL NOT NULL,
            koltukcu_amount REAL NOT NULL,
            emlak_amount REAL NOT NULL,
            unit_price REAL NOT NULL,
            warnings TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# Calculation
# ---------------------------------------------------------------------------

def calculate(data):
    total_bill = data["totalBill"]
    main_meter = data["mainMeter"]
    lokanta_start = data["lokantaStart"]
    lokanta_end = data["lokantaEnd"]
    koltukcu_start = data["koltukcuStart"]
    koltukcu_end = data["koltukcuEnd"]

    errors = []
    warnings = []

    if total_bill <= 0:
        errors.append("Fatura tutarı sıfırdan büyük olmalıdır.")
    if main_meter <= 0:
        errors.append("Ana sayaç tüketimi sıfırdan büyük olmalıdır.")

    lokanta_consumption = lokanta_end - lokanta_start
    koltukcu_consumption = koltukcu_end - koltukcu_start
    sub_total = lokanta_consumption + koltukcu_consumption
    emlak_consumption = main_meter - sub_total

    if lokanta_consumption < 0:
        warnings.append("Lokanta alt sayacında başlangıç değeri bitiş değerinden büyük. Lütfen kontrol ediniz.")
    if koltukcu_consumption < 0:
        warnings.append("Koltukçu alt sayacında başlangıç değeri bitiş değerinden büyük. Lütfen kontrol ediniz.")
    if sub_total > main_meter:
        warnings.append(
            f"Alt sayaç toplamı ({sub_total:.1f} kWh) ana sayaç tüketimini "
            f"({main_meter:.1f} kWh) aşmaktadır. Emlak Ofisi tüketimi negatif görünüyor. "
            f"Okumaları kontrol ediniz."
        )

    if errors:
        return {"errors": errors}

    unit_price = total_bill / main_meter

    lokanta_amount = (lokanta_consumption / main_meter) * total_bill
    koltukcu_amount = (koltukcu_consumption / main_meter) * total_bill
    emlak_amount = (emlak_consumption / main_meter) * total_bill

    return {
        "totalBill": total_bill,
        "mainMeter": main_meter,
        "unitPrice": unit_price,
        "shops": [
            {
                "id": "lokanta",
                "name": "Lokanta",
                "icon": "\U0001F37D️",
                "consumption": round(lokanta_consumption, 2),
                "percentage": round((lokanta_consumption / main_meter) * 100, 1),
                "amount": round(lokanta_amount, 2),
                "color": "#f59e0b",
            },
            {
                "id": "koltukcu",
                "name": "Koltukçu",
                "icon": "\U0001F4BA",
                "consumption": round(koltukcu_consumption, 2),
                "percentage": round((koltukcu_consumption / main_meter) * 100, 1),
                "amount": round(koltukcu_amount, 2),
                "color": "#3b82f6",
            },
            {
                "id": "emlak",
                "name": "Emlak Ofisi",
                "icon": "\U0001F3EA",
                "consumption": round(emlak_consumption, 2),
                "percentage": round((emlak_consumption / main_meter) * 100, 1),
                "amount": round(emlak_amount, 2),
                "color": "#10b981",
            },
        ],
        "warnings": warnings,
    }

# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def parse_number_flex(s):
    """Parse a number string that may use either English or Turkish format.

    English: 4,325.00  (comma=thousands, dot=decimal)
    Turkish: 1.500,75  (dot=thousands, comma=decimal)

    Heuristic: the LAST separator (comma or dot) in the string is the
    decimal mark if there are exactly 2 digits after it; otherwise it
    is a thousands separator and the number has no fractional part.
    """
    s = s.strip()
    if not s:
        return None

    comma_idx = s.rfind(",")
    dot_idx = s.rfind(".")

    if comma_idx == -1 and dot_idx == -1:
        # No separators at all — plain integer
        try:
            return float(s)
        except ValueError:
            return None

    # Determine which separator is the decimal mark
    last_sep_idx = max(comma_idx, dot_idx)
    last_sep_char = s[last_sep_idx]
    digits_after = len(s) - last_sep_idx - 1

    if digits_after == 2:
        # The last separator is the decimal mark
        decimal_char = last_sep_char
        thousands_char = "." if decimal_char == "," else ","
        clean = s.replace(thousands_char, "").replace(decimal_char, ".")
    elif digits_after == 3 and comma_idx >= 0 and dot_idx >= 0:
        # Both present, last separator has 3 digits after
        # Treat the other one as decimal if it has 2 digits after
        first_sep_idx = min(comma_idx, dot_idx)
        first_digits_after = last_sep_idx - first_sep_idx - 1
        if first_digits_after == 2:
            decimal_char = s[first_sep_idx]
            thousands_char = s[last_sep_idx]
            clean = s.replace(thousands_char, "").replace(decimal_char, ".")
        else:
            clean = s.replace(",", "").replace(".", "")
    else:
        # Only one separator, or can't determine — treat all as thousands
        clean = s.replace(",", "").replace(".", "")

    try:
        return float(clean)
    except ValueError:
        return None


def extract_from_text(text):
    """Extract total bill (TL) and consumption (kWh) from OCR text."""
    if not text:
        return None

    # Normalize encoding artifacts
    text = text.replace("|", "I")
    text_lower = text.lower()

    kwh_candidates = []
    tl_candidates = []

    # ---- kWh detection ----
    for m in re.finditer(r"([\d.,]+)\s*k[wW][hH]", text):
        val = parse_number_flex(m.group(1))
        # Filter implausible values: must be between 5 and 50000 kWh
        if val is not None and 5 < val < 50000:
            start = max(0, m.start() - 60)
            ctx = text[start:m.end()].lower()
            # Exclude "önceki" references
            is_prev = any(kw in ctx for kw in ["önceki", "nceki", "nceki fatura"])
            kwh_candidates.append({
                "value": val,
                "context": ctx.strip(),
                "is_total": any(kw in ctx for kw in
                    ["toplam", "tüketim", "tuketim", "endeks", "sayaç", "sayac"]),
                "is_prev": is_prev,
            })

    # ---- kWh: "Enerji Bedeli" nearby (BEDAŞ format) ----
    # The first number after "Enerji Bedeli" is consumption (kWh),
    # the second is the unit rate — only take the first.
    for kw in ["enerji bedeli"]:
        idx = text_lower.find(kw)
        if idx >= 0:
            snippet = text[idx:idx + 100]
            numbers = list(re.finditer(r"([\d.,]+)", snippet))
            if numbers:
                val = parse_number_flex(numbers[0].group(1))
                if val is not None and 5 < val < 50000:
                    kwh_candidates.append({
                        "value": val,
                        "context": kw.title(),
                        "is_total": True,
                        "is_prev": False,
                    })

    # ---- TL detection: number + "TL" ----
    for m in re.finditer(r"([\d.,]+)\s*[Tt][Ll]", text):
        val = parse_number_flex(m.group(1))
        if val is not None and val > 0:
            start = max(0, m.start() - 60)
            ctx = text[start:m.end()].lower()
            tl_candidates.append({
                "value": val,
                "context": ctx.strip(),
                "is_total": any(kw in ctx for kw in
                    ["toplam", "ödenecek", "odenecek", "fatura", "tutar",
                     "borç", "borc", "tahakkuk", "öde", "ode"]),
            })

    # ---- TL detection: "Fatura Tutarı" / "Toplam" keyword nearby ----
    for kw in ["fatura tutar", "toplam tutar", "fatura bedeli", "ödenecek tutar",
               "toplam borç", "fatura toplam"]:
        idx = text_lower.find(kw)
        if idx >= 0:
            # Scan the 200 chars after keyword for a number
            snippet = text[idx:idx + 200]
            for m in re.finditer(r"([\d.,]+)", snippet):
                val = parse_number_flex(m.group(1))
                if val is not None and val > 10:  # must be > 10 TL to be a bill
                    tl_candidates.append({
                        "value": val,
                        "context": kw.title(),
                        "is_total": True,
                    })
                    break  # one per keyword

    # ---- kWh: "Toplam" / "Tüketim" keyword nearby (on its own line) ----
    for kw in ["toplam(kwh)", "toplam tüketim", "dönem\ntoplam"]:
        idx = text_lower.find(kw)
        if idx >= 0:
            snippet = text[idx:idx + 300]
            # Find numbers, take the largest plausible one
            best = None
            for m in re.finditer(r"([\d.,]+)", snippet):
                val = parse_number_flex(m.group(1))
                if val is not None and 5 < val < 50000:
                    if best is None or val > best["value"]:
                        best = {"value": val, "context": kw.title(), "is_total": True, "is_prev": False}
            if best:
                kwh_candidates.append(best)

    # ---- kWh: also scan for bare "kW" (without h) ----
    for m in re.finditer(r"([\d.,]+)\s*k[wW]\b", text):
        val = parse_number_flex(m.group(1))
        if val is not None and 5 < val < 50000:
            start = max(0, m.start() - 60)
            ctx = text[start:m.end()].lower().strip()
            is_prev = any(kw in ctx for kw in ["önceki", "nceki"])
            kwh_candidates.append({
                "value": val,
                "context": ctx,
                "is_total": False,
                "is_prev": is_prev,
            })

    result = {}

    # ---- Pick best kWh ----
    if kwh_candidates:
        # Exclude previous-bill references first
        current = [c for c in kwh_candidates if not c.get("is_prev")]
        pool = current if current else kwh_candidates

        # Prefer "enerji bedeli" source (always current period consumption)
        from_energy = [c for c in pool if "enerji bedeli" in c.get("context", "").lower()]
        if from_energy:
            best_kwh = max(from_energy, key=lambda c: c["value"])
        else:
            totals = [c for c in pool if c["is_total"]]
            source = totals if totals else pool
            best_kwh = max(source, key=lambda c: c["value"])

        result["mainMeter"] = best_kwh["value"]
        result["mainMeterContext"] = best_kwh["context"][:100]

    # ---- Pick best TL ----
    if tl_candidates:
        totals = [c for c in tl_candidates if c["is_total"]]
        source = totals if totals else tl_candidates
        best_tl = max(source, key=lambda c: c["value"])
        result["totalBill"] = best_tl["value"]
        result["totalBillContext"] = best_tl["context"][:100]

    if "mainMeter" in result or "totalBill" in result:
        return result
    return None


def ocr_image(image_bytes):
    """Run Tesseract OCR on an image, return extracted text."""
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        return None

    img = Image.open(io.BytesIO(image_bytes))
    # Convert to RGB if needed (e.g. PNG with alpha)
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    try:
        text = pytesseract.image_to_string(img, lang="tur")
        return text
    except Exception:
        return None


def ocr_pdf(file_bytes):
    """Extract text from PDF. Falls back to OCR if no embedded text found."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    if len(doc) == 0:
        doc.close()
        return None

    # Try embedded text first (first 2 pages)
    text_parts = []
    for i in range(min(2, len(doc))):
        page = doc[i]
        t = page.get_text()
        if t:
            text_parts.append(t)

    full_text = "\n".join(text_parts).strip()

    # If we got decent text, use it
    if len(full_text) > 100:
        doc.close()
        return full_text

    # Scanned PDF — render first page as image and OCR
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        doc.close()
        return full_text if full_text else None

    page = doc[0]
    # Render at 200 DPI for decent OCR quality
    mat = fitz.Matrix(200 / 72, 200 / 72)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")

    try:
        img = Image.open(io.BytesIO(img_bytes))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        ocr_text = pytesseract.image_to_string(img, lang="tur")
        doc.close()
        return ocr_text if ocr_text else full_text
    except Exception:
        doc.close()
        return full_text if full_text else None


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/api/upload", methods=["POST"])
def upload_and_ocr():
    if "file" not in request.files:
        return jsonify({"error": "Dosya bulunamadı."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Dosya seçilmedi."}), 400

    file_bytes = file.read()
    if len(file_bytes) == 0:
        return jsonify({"error": "Dosya boş."}), 400

    filename = file.filename.lower()
    is_pdf = filename.endswith(".pdf")
    is_image = any(filename.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"))

    if not is_pdf and not is_image:
        return jsonify({"error": "Desteklenmeyen dosya formatı. PDF veya resim (JPG, PNG) yükleyin."}), 400

    # Save uploaded file for reference
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = os.path.splitext(file.filename)[1] or (".pdf" if is_pdf else ".jpg")
    save_path = os.path.join(UPLOAD_DIR, f"{ts}{ext}")
    with open(save_path, "wb") as f:
        f.write(file_bytes)

    # OCR
    if is_pdf:
        text = ocr_pdf(file_bytes)
    else:
        text = ocr_image(file_bytes)

    if text is None:
        return jsonify({"error": "OCR işlemi başarısız. Tesseract OCR kurulu değil veya dosya okunamadı."}), 500

    result = extract_from_text(text)

    if result is None:
        return jsonify({
            "error": "Fatura değerleri tespit edilemedi. Lütfen manuel giriniz.",
            "ocrText": text[:500],
        }), 422

    result["ocrText"] = text[:500]
    return jsonify(result)


@app.route("/api/last-readings", methods=["GET"])
def last_readings():
    """Return the most recent end readings to auto-fill start fields."""
    conn = get_db()
    row = conn.execute(
        "SELECT lokanta_end, koltukcu_end, created_at FROM calculations ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        return jsonify({
            "lokantaEnd": row["lokanta_end"],
            "koltukcuEnd": row["koltukcu_end"],
            "date": row["created_at"],
        })
    return jsonify({})


@app.route("/api/calculations", methods=["GET"])
def list_calculations():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM calculations ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/calculations", methods=["POST"])
def create_calculation():
    data = request.get_json()
    if not data:
        return jsonify({"errors": ["Geçersiz istek."]}), 400

    result = calculate(data)
    if "errors" in result:
        return jsonify(result), 400

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    shops = {s["id"]: s for s in result["shops"]}

    conn = get_db()
    conn.execute(
        """
        INSERT INTO calculations
            (total_bill, main_meter,
             lokanta_start, lokanta_end, koltukcu_start, koltukcu_end,
             lokanta_consumption, koltukcu_consumption, emlak_consumption,
             lokanta_amount, koltukcu_amount, emlak_amount,
             unit_price, warnings, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["totalBill"], data["mainMeter"],
            data["lokantaStart"], data["lokantaEnd"],
            data["koltukcuStart"], data["koltukcuEnd"],
            shops["lokanta"]["consumption"],
            shops["koltukcu"]["consumption"],
            shops["emlak"]["consumption"],
            shops["lokanta"]["amount"],
            shops["koltukcu"]["amount"],
            shops["emlak"]["amount"],
            result["unitPrice"],
            "|".join(result["warnings"]),
            now,
        ),
    )
    conn.commit()
    row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    result["id"] = row_id
    result["createdAt"] = now
    return jsonify(result), 201


@app.route("/api/calculations/<int:calc_id>", methods=["DELETE"])
def delete_calculation(calc_id):
    conn = get_db()
    conn.execute("DELETE FROM calculations WHERE id = ?", (calc_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
