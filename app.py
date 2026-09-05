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
            reading_date TEXT,
            created_at TEXT NOT NULL
        )
    """)
    # Check if reading_date column exists for backwards compatibility
    cursor = conn.execute("PRAGMA table_info(calculations)")
    cols = [row[1] for row in cursor.fetchall()]
    if "reading_date" not in cols:
        conn.execute("ALTER TABLE calculations ADD COLUMN reading_date TEXT")
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# Calculation
# ---------------------------------------------------------------------------

def safe_float(val, default=None):
    """Safely convert any value to float, handling Turkish/English number strings."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        parsed = parse_number_flex(val)
        return parsed if parsed is not None else default
    return default


def calculate(data):
    if not isinstance(data, dict):
        return {"errors": ["Geçersiz veri formatı."]}

    total_bill = safe_float(data.get("totalBill"))
    main_meter = safe_float(data.get("mainMeter"))
    lokanta_start = safe_float(data.get("lokantaStart"), 0.0)
    lokanta_end = safe_float(data.get("lokantaEnd"), 0.0)
    koltukcu_start = safe_float(data.get("koltukcuStart"), 0.0)
    koltukcu_end = safe_float(data.get("koltukcuEnd"), 0.0)
    reading_date = str(data.get("readingDate") or "").strip()

    errors = []
    warnings = []

    if total_bill is None or total_bill <= 0:
        errors.append("Fatura tutarı sıfırdan büyük geçerli bir sayı olmalıdır.")
    if main_meter is None or main_meter <= 0:
        errors.append("Ana sayaç tüketimi sıfırdan büyük geçerli bir sayı olmalıdır.")

    if errors:
        return {"errors": errors}

    lokanta_consumption = round(lokanta_end - lokanta_start, 2)
    koltukcu_consumption = round(koltukcu_end - koltukcu_start, 2)
    sub_total = round(lokanta_consumption + koltukcu_consumption, 2)
    emlak_consumption = round(main_meter - sub_total, 2)

    if lokanta_consumption < 0:
        warnings.append("Lokanta alt sayacında başlangıç değeri bitiş değerinden büyük. Lütfen okumaları kontrol ediniz.")
    if koltukcu_consumption < 0:
        warnings.append("Koltukçu alt sayacında başlangıç değeri bitiş değerinden büyük. Lütfen okumaları kontrol ediniz.")
    if sub_total > main_meter:
        warnings.append(
            f"Alt sayaç toplamı ({sub_total:.1f} kWh) ana sayaç tüketimini "
            f"({main_meter:.1f} kWh) aşmaktadır. Emlak Ofisi tüketimi negatif görünüyor. "
            f"Okumaları kontrol ediniz."
        )

    unit_price = round(total_bill / main_meter, 6)

    # Calculate amounts
    lokanta_amount = round((lokanta_consumption / main_meter) * total_bill, 2)
    koltukcu_amount = round((koltukcu_consumption / main_meter) * total_bill, 2)

    # Kuruş dengesi: Emlak Ofisi arta kalan birim olduğundan,
    # 3 işletmenin toplamının ana faturaya kuruşu kuruşuna tam eşit olması sağlanır.
    emlak_amount = round(total_bill - lokanta_amount - koltukcu_amount, 2)

    # Calculate percentages
    lokanta_pct = round((lokanta_consumption / main_meter) * 100, 1)
    koltukcu_pct = round((koltukcu_consumption / main_meter) * 100, 1)
    emlak_pct = round((emlak_consumption / main_meter) * 100, 1)

    return {
        "totalBill": total_bill,
        "mainMeter": main_meter,
        "readingDate": reading_date,
        "unitPrice": unit_price,
        "shops": [
            {
                "id": "lokanta",
                "name": "Lokanta",
                "icon": "\U0001F37D️",
                "consumption": lokanta_consumption,
                "percentage": lokanta_pct,
                "amount": lokanta_amount,
                "color": "#f59e0b",
            },
            {
                "id": "koltukcu",
                "name": "Koltukçu",
                "icon": "\U0001F4BA",
                "consumption": koltukcu_consumption,
                "percentage": koltukcu_pct,
                "amount": koltukcu_amount,
                "color": "#3b82f6",
            },
            {
                "id": "emlak",
                "name": "Emlak Ofisi",
                "icon": "\U0001F3EA",
                "consumption": emlak_consumption,
                "percentage": emlak_pct,
                "amount": emlak_amount,
                "color": "#10b981",
            },
        ],
        "warnings": warnings,
    }

# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def parse_number_flex(s):
    """Parse a number string supporting both Turkish (1.500,75 or 150,5) and English (1,500.75 or 150.5) formats.

    Correctly distinguishes between decimal and thousands separators without stripping
    valid decimal digits.
    """
    if s is None:
        return None
    s = str(s).strip()
    # Remove currency symbols and extraneous characters, keep only digits, comma, dot
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return None

    comma_count = s.count(",")
    dot_count = s.count(".")

    # Case 1: Both comma and dot present
    if comma_count > 0 and dot_count > 0:
        last_comma = s.rfind(",")
        last_dot = s.rfind(".")
        if last_comma > last_dot:
            # Turkish: 1.500,75 or 1.500.000,50
            clean = s.replace(".", "").replace(",", ".")
        else:
            # English: 1,500.75 or 1,500,000.50
            clean = s.replace(",", "")
        try:
            return float(clean)
        except ValueError:
            return None

    # Case 2: Only comma present
    if comma_count > 0:
        if comma_count > 1:
            # Multiple commas, e.g. 1,500,000 -> thousands
            clean = s.replace(",", "")
        else:
            # Single comma in Turkish is always decimal mark: 150,5 -> 150.5, 1500,75 -> 1500.75
            clean = s.replace(",", ".")
        try:
            return float(clean)
        except ValueError:
            return None

    # Case 3: Only dot present
    if dot_count > 0:
        if dot_count > 1:
            # Multiple dots: 1.500.000 -> thousands
            clean = s.replace(".", "")
        else:
            # Single dot: e.g. 150.5, 2450.80, 1.500
            digits_after = len(s) - s.find(".") - 1
            if digits_after in (1, 2) or s.startswith("0."):
                clean = s
            elif digits_after == 3 and len(s[:s.find(".")]) <= 3:
                # e.g. 1.500 or 2.450 in Turkish invoice context -> 1500, 2450
                clean = s.replace(".", "")
            else:
                clean = s
        try:
            return float(clean)
        except ValueError:
            return None

    # Case 4: Plain integer
    try:
        return float(s)
    except ValueError:
        return None


def parse_kwh(s):
    """Parse electricity consumption (kWh).
    
    In electricity meters and bills, readings are recorded down to thousandths of a kWh
    (e.g. 870.000, 8.350, 878.350). Therefore, a single dot is always a decimal point.
    """
    if s is None:
        return None
    s = str(s).strip()
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return None
    comma_count = s.count(",")
    dot_count = s.count(".")
    if comma_count > 0 and dot_count > 0:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif comma_count > 0:
        if comma_count > 1:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif dot_count > 1:
        s = s.replace(".", "")
    # Single dot: in kWh context, 870.000 is 870.0 kWh, 8.350 is 8.35 kWh
    try:
        return float(s)
    except ValueError:
        return None


def parse_money(s):
    """Parse monetary amounts (TL), handling Turkish and English decimal conventions."""
    if s is None:
        return None
    s = str(s).strip()
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return None
    comma_count = s.count(",")
    dot_count = s.count(".")
    if comma_count > 0 and dot_count > 0:
        if s.rfind(",") > s.rfind("."):
            clean = s.replace(".", "").replace(",", ".")
        else:
            clean = s.replace(",", "")
    elif comma_count > 0:
        if comma_count > 1:
            clean = s.replace(",", "")
        else:
            clean = s.replace(",", ".")
    elif dot_count > 0:
        if dot_count > 1:
            clean = s.replace(".", "")
        else:
            clean = s
    else:
        clean = s
    try:
        return float(clean)
    except ValueError:
        return None


def normalize_date(d_str):
    """Normalize date strings (DD-MM-YYYY, DD.MM.YYYY, DD/MM/YYYY) to YYYY-MM-DD."""
    if not d_str:
        return None
    d_str = d_str.strip().replace("/", "-").replace(".", "-")
    parts = d_str.split("-")
    if len(parts) == 3:
        if len(parts[0]) == 4:  # YYYY-MM-DD
            return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
        elif len(parts[2]) == 4:  # DD-MM-YYYY
            return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
    return None


def extract_from_text(text):
    """Extract total bill (TL), consumption (kWh), and reading date from bill text.
    
    Specifically tuned for Turkish electricity bills (CK Boğaziçi, BEDAŞ, Enerjisa, etc.):
    - Focuses on the core section between Fatura Tutarı and Fatura Detayı / Okuma Bilgisi.
    - Sums multi-tier (kademeli) Enerji Bedeli consumption rows (e.g. 870.000 + 8.350 = 878.350 kWh).
    - Authoritative Tek Zamanlı Fark in Okuma Bilgisi.
    - Strictly filters out annual totals ('Dönem Toplam'), previous bills ('Önceki fatura'),
      and tax bases.
    """
    if not text:
        return None

    # Normalize encoding / OCR artifacts
    text_clean = text.replace("|", "I")
    lines = [line.strip() for line in text_clean.splitlines() if line.strip()]

    result = {}

    # -----------------------------------------------------------------------
    # 1. Okuma Tarihi (Reading Date)
    # -----------------------------------------------------------------------
    # E.g.: "Okuma Günü 29-07-2026 27-08-2026" (2nd date is Son Okuma)
    m_okuma = re.search(
        r"Okuma\s*G[üu]n[üu][^\d]*(\d{2}[-./]\d{2}[-./]\d{4})\s+(\d{2}[-./]\d{2}[-./]\d{4})",
        text_clean,
        re.IGNORECASE,
    )
    if m_okuma:
        result["readingDate"] = normalize_date(m_okuma.group(2))
    else:
        m_son_okuma = re.search(
            r"(?:Son\s*Okuma(?:\s*Tarihi)?|Fatura\s*Tarihi)[^\d]*(\d{2}[-./]\d{2}[-./]\d{4})",
            text_clean,
            re.IGNORECASE,
        )
        if m_son_okuma:
            result["readingDate"] = normalize_date(m_son_okuma.group(1))

    # -----------------------------------------------------------------------
    # 2. Tüketim (kWh) Odak: Okuma Bilgisi & Fatura Detayı
    # -----------------------------------------------------------------------
    kwh_found = None
    kwh_context = None

    # Step 2.1: Tek Zamanlı Fark in Okuma Bilgisi
    # E.g.: "Tek Zamanlı 4201.919 5080.269 878.350"
    m_tek = re.search(
        r"Tek\s*Zamanl[ıi]\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)",
        text_clean,
        re.IGNORECASE,
    )
    if m_tek:
        fark = parse_kwh(m_tek.group(3))
        if fark and 5 < fark < 50000:
            kwh_found = fark
            kwh_context = f"Okuma Bilgisi Tek Zamanlı Fark ({fark} kWh)"

    # Step 2.2: Kademeli / Çoklu "Enerji Bedeli" Satırlarının Toplamı
    # E.g.: "Enerji Bedeli-Düşük Kade 870.000 5.352457 4656.64"
    #       "Enerji Bedeli-Yüksek Kade 8.350 5.934455 49.55"
    # (Exclude "T. Enerji Bedeli" or "Toplam Enerji Bedeli" which are monetary amounts)
    enerji_lines_kwh = []
    for line in lines:
        line_lower = line.lower()
        if "enerji bedeli" in line_lower and not re.match(r"^(?:t\.|toplam)\s*enerji\s*bedeli", line_lower):
            rest = line[line_lower.find("enerji bedeli") + len("enerji bedeli"):]
            m_num = re.search(r"([\d.,]+)", rest)
            if m_num:
                v = parse_kwh(m_num.group(1))
                if v and 0.5 <= v < 50000:
                    enerji_lines_kwh.append(v)

    if enerji_lines_kwh:
        total_enerji_kwh = round(sum(enerji_lines_kwh), 3)
        if kwh_found is None:
            kwh_found = total_enerji_kwh
            kwh_context = f"Fatura Detayı Enerji Bedeli Toplamı ({total_enerji_kwh} kWh)"
        elif abs(kwh_found - total_enerji_kwh) < 0.1:
            kwh_found = total_enerji_kwh
            kwh_context = f"Fatura Detayı ve Okuma Bilgisi Doğrulandı ({total_enerji_kwh} kWh)"

    # Step 2.3: Üç Zamanlı (Gündüz + Puant + Gece Farkları)
    if kwh_found is None:
        rates = []
        for kw in ["Gündüz", "Puant", "Gece"]:
            m_rate = re.search(
                rf"{kw}[^\n\r\d]*[\d.,]+\s+[\d.,]+\s+([\d.,]+)",
                text_clean,
                re.IGNORECASE,
            )
            if m_rate:
                v = parse_kwh(m_rate.group(1))
                if v:
                    rates.append(v)
        if len(rates) == 3:
            kwh_found = round(sum(rates), 3)
            kwh_context = f"Okuma Bilgisi 3-Zamanlı Toplam ({kwh_found} kWh)"

    # Step 2.4: Fallback genel arama (Dönem Toplam, Önceki Fatura ve Ortalama Tüketim hariç)
    if kwh_found is None:
        for m in re.finditer(r"([\d.,]+)\s*k[wW][hH]", text_clean):
            ctx_start = max(0, m.start() - 70)
            ctx = text_clean[ctx_start:m.end()].lower()
            if any(bad in ctx for bad in [
                "önceki", "nceki", "dönem toplam", "donem toplam",
                "yıllık", "yillik", "geçen", "ortalama", "günlük", "gunluk"
            ]):
                continue
            v = parse_kwh(m.group(1))
            if v and 5 < v < 50000:
                kwh_found = v
                kwh_context = ctx.strip()
                break

    if kwh_found is not None:
        result["mainMeter"] = kwh_found
        result["mainMeterContext"] = kwh_context

    # -----------------------------------------------------------------------
    # 3. Fatura Tutarı (TL) Odak: Doğrudan Fatura Tutarı
    # -----------------------------------------------------------------------
    tl_found = None
    tl_context = None

    # Step 3.1: Üst özet kutusundaki "Fatura Tutarı ... 5800.00 TL"
    # Matches "Fatura Tutarı" followed within ~150 chars by an amount with TL/TI/T/1L
    m_box_tl = re.search(
        r"Fatura\s*Tutar[ıi].{0,150}?([\d.,]+)\s*(?:TL|TI|T|1L)\b",
        text_clean,
        re.DOTALL | re.IGNORECASE,
    )
    if m_box_tl:
        val = parse_money(m_box_tl.group(1))
        if val and 10 < val < 200000:
            tl_found = val
            tl_context = f"Fatura Tutarı Kutusu ({val} TL)"

    # Step 3.2: Doğrudan "Fatura Tutarı: X" (yuvarlama veya ekleme/çıkarma yapmadan)
    if tl_found is None:
        for m in re.finditer(r"Fatura\s*Tutar[ıi]\s*[:]?\s*([\d.,]+)", text_clean, re.IGNORECASE):
            raw_num = m.group(1)
            val = parse_money(raw_num)
            if val and 10 < val < 200000:
                tl_found = val
                tl_context = f"Fatura Tutarı ({val} TL)"
                break

    # Step 3.3: Doğrudan "Ödenecek Tutar / Toplam Tutar / Fatura Bedeli: X"
    if tl_found is None:
        for kw in ["ödenecek tutar", "odenecek tutar", "fatura bedeli", "toplam tutar"]:
            m = re.search(rf"{kw}\s*[:]?\s*([\d.,]+)", text_clean, re.IGNORECASE)
            if m:
                val = parse_money(m.group(1))
                if val and 10 < val < 200000:
                    tl_found = val
                    tl_context = f"{kw.title()} ({val} TL)"
                    break

    # Step 3.4: Genel TL regex (KDV matrahı, BTV, fon, çarpan, demand ve sayaç verileri filtrelenir)
    if tl_found is None:
        candidates = []
        for m in re.finditer(r"([\d.,]+)\s*(?:TL|TI)\b", text_clean, re.IGNORECASE):
            ctx_start = max(0, m.start() - 60)
            ctx_end = min(len(text_clean), m.end() + 20)
            ctx = text_clean[ctx_start:ctx_end].lower()
            if any(bad in ctx for bad in [
                "kdv", "matrah", "fon", "enerji bedeli", "btv", "kesme",
                "çarpan", "carpan", "demand", "güç", "guc", "seri", "sayaç", "sayac",
                "tesisat", "sözleşme", "dönem toplam"
            ]):
                continue
            val = parse_money(m.group(1))
            if val and 10 < val < 200000:
                candidates.append((val, ctx.strip()))
        if candidates:
            best = max(candidates, key=lambda x: x[0])
            tl_found = best[0]
            tl_context = best[1]

    if tl_found is not None:
        result["totalBill"] = tl_found
        result["totalBillContext"] = tl_context

    if "mainMeter" in result or "totalBill" in result:
        return result
    return None


def find_blue_marker_region(img):
    """Detect hand-drawn blue marker annotations on an invoice image.
    
    When a user circles or underlines target areas with a blue/azure marker,
    this function isolates the vertical bounding box spanning from the first
    marker cluster (e.g. Fatura Tutarı) to the last (e.g. Fatura Detayı).
    Returns (left, top, right, bottom) crop box or None if no markers found.
    """
    w, h = img.size
    row_counts = [0] * h

    for y in range(h):
        for x in range(0, w, 2):
            r, g, b = img.getpixel((x, y))
            # Android/iOS blue pen marker stroke:
            # Saturated blue, significantly higher than red and green
            # (distinct from invoice cyan header banners where G ~ B)
            if b > 160 and (b - r) > 75 and (b - g) > 25:
                row_counts[y] += 2

    # Group into vertical clusters
    clusters = []
    current = []
    for y in range(h):
        if row_counts[y] >= 6:
            current.append((y, row_counts[y]))
        else:
            if current:
                if len(current) >= 10:
                    total_px = sum(c for _, c in current)
                    if total_px >= 120:
                        clusters.append(current)
                current = []
    if current and len(current) >= 10:
        total_px = sum(c for _, c in current)
        if total_px >= 120:
            clusters.append(current)

    if not clusters:
        return None

    top_y = min(c[0][0] for c in clusters)
    bottom_y = max(c[-1][0] for c in clusters)

    # Top: 20px padding
    # Bottom: 55px padding to fully include Fatura Tutarı (5800.51) and Güncel Yuvarlama
    # while stopping before Çarpan/Demand/Dönem Toplam
    top = max(0, top_y - 20)
    bottom = min(h, bottom_y + 55)
    return (0, top, w, bottom)


def ocr_image(image_bytes):
    """Run Tesseract OCR on an image, return extracted text.
    
    If hand-drawn blue markers are present, crops between them to focus OCR
    precisely on the user-highlighted region (Fatura Tutarı + Detaylar).
    """
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        return None

    img = Image.open(io.BytesIO(image_bytes))
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    # Focus between blue markers if detected
    marker_box = find_blue_marker_region(img)
    if marker_box:
        img = img.crop(marker_box)

    # Upscale narrow/low-DPI mobile screenshots so Tesseract reads small fonts cleanly
    if img.width < 1000:
        scale = max(2, int(1200 / img.width))
        img = img.resize((img.width * scale, img.height * scale), Image.Resampling.LANCZOS)

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


@app.route("/api/calculate", methods=["POST"])
def calculate_preview():
    data = request.get_json()
    if not data:
        return jsonify({"errors": ["Geçersiz istek. JSON gövdesi bekleniyor."]}), 400

    result = calculate(data)
    if "errors" in result:
        return jsonify(result), 400

    return jsonify(result), 200


@app.route("/api/last-readings", methods=["GET"])
def last_readings():
    """Return the most recent end readings to auto-fill start fields."""
    conn = get_db()
    row = conn.execute(
        """
        SELECT lokanta_end, koltukcu_end, 
               COALESCE(NULLIF(reading_date, ''), SUBSTR(created_at, 1, 10)) AS date 
        FROM calculations 
        ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    conn.close()
    if row:
        return jsonify({
            "lokantaEnd": row["lokanta_end"],
            "koltukcuEnd": row["koltukcu_end"],
            "date": row["date"],
        })
    return jsonify({})


@app.route("/api/calculations", methods=["GET"])
def list_calculations():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT *, 
               COALESCE(NULLIF(reading_date, ''), SUBSTR(created_at, 1, 10)) AS effective_date 
        FROM calculations 
        ORDER BY id DESC
        """
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/calculations/<int:calc_id>", methods=["GET"])
def get_calculation(calc_id):
    conn = get_db()
    row = conn.execute(
        """
        SELECT *, 
               COALESCE(NULLIF(reading_date, ''), SUBSTR(created_at, 1, 10)) AS effective_date 
        FROM calculations 
        WHERE id = ?
        """,
        (calc_id,)
    ).fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({"error": "Kayıt bulunamadı."}), 404


@app.route("/api/calculations", methods=["POST"])
def create_calculation():
    data = request.get_json()
    if not data:
        return jsonify({"errors": ["Geçersiz istek."]}), 400

    result = calculate(data)
    if "errors" in result:
        return jsonify(result), 400

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    reading_date = str(data.get("readingDate") or now[:10]).strip()
    shops = {s["id"]: s for s in result["shops"]}

    conn = get_db()
    cursor = conn.execute(
        """
        INSERT INTO calculations
            (total_bill, main_meter,
             lokanta_start, lokanta_end, koltukcu_start, koltukcu_end,
             lokanta_consumption, koltukcu_consumption, emlak_consumption,
             lokanta_amount, koltukcu_amount, emlak_amount,
             unit_price, warnings, reading_date, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result["totalBill"], result["mainMeter"],
            safe_float(data.get("lokantaStart"), 0.0), safe_float(data.get("lokantaEnd"), 0.0),
            safe_float(data.get("koltukcuStart"), 0.0), safe_float(data.get("koltukcuEnd"), 0.0),
            shops["lokanta"]["consumption"],
            shops["koltukcu"]["consumption"],
            shops["emlak"]["consumption"],
            shops["lokanta"]["amount"],
            shops["koltukcu"]["amount"],
            shops["emlak"]["amount"],
            result["unitPrice"],
            "|".join(result["warnings"]),
            reading_date,
            now,
        ),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()

    result["id"] = row_id
    result["readingDate"] = reading_date
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
    debug_mode = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug_mode)

