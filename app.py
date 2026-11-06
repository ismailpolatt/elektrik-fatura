import io
import math
import uuid
from decimal import Decimal, ROUND_HALF_UP
import os
import re
import sqlite3
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

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

def parse_input_number(value):
    """Strict form/API number parser; a single separator is decimal, including .xxx."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except (ValueError, OverflowError):
            return None
        return number if math.isfinite(number) else None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            pattern = r"[+-]?(?:[0-9]{1,3}(?:\.[0-9]{3})+),[0-9]+"
            clean = text.replace(".", "").replace(",", ".")
        else:
            pattern = r"[+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+)\.[0-9]+"
            clean = text.replace(",", "")
    elif text.count(",") > 1 or text.count(".") > 1:
        pattern = r"[+-]?[0-9]{1,3}(?:\.[0-9]{3}){2,}|[+-]?[0-9]{1,3}(?:,[0-9]{3}){2,}"
        clean = text.replace(",", "").replace(".", "")
    else:
        pattern = r"[+-]?[0-9]+(?:[.,][0-9]+)?"
        clean = text.replace(",", ".")
    if not re.fullmatch(pattern, text):
        return None
    try:
        number = float(clean)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def safe_float(val, default=None):
    parsed = parse_input_number(val)
    return parsed if parsed is not None else default


def valid_reading_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def calculate(data):
    if not isinstance(data, dict):
        return {"errors": ["Geçersiz veri formatı."]}

    total_bill = safe_float(data.get("totalBill"))
    main_meter = safe_float(data.get("mainMeter"))
    lokanta_start = safe_float(data.get("lokantaStart"))
    lokanta_end = safe_float(data.get("lokantaEnd"))
    koltukcu_start = safe_float(data.get("koltukcuStart"))
    koltukcu_end = safe_float(data.get("koltukcuEnd"))
    reading_date = data.get("readingDate") or datetime.now().strftime("%Y-%m-%d")

    errors = []
    warnings = []

    if total_bill is None or total_bill <= 0:
        errors.append("Fatura tutarı sıfırdan büyük geçerli bir sayı olmalıdır.")
    if main_meter is None or main_meter <= 0:
        errors.append("Ana sayaç tüketimi sıfırdan büyük geçerli bir sayı olmalıdır.")

    for label, value in [("Fatura tutarı", total_bill), ("Ana sayaç", main_meter),
                         ("Lokanta başlangıç", lokanta_start), ("Lokanta bitiş", lokanta_end),
                         ("Koltukçu başlangıç", koltukcu_start), ("Koltukçu bitiş", koltukcu_end)]:
        if value is None or value < 0 or value > 1_000_000_000_000:
            errors.append(f"{label} geçerli, negatif olmayan bir sayı olmalıdır.")
        elif Decimal(str(value)).as_tuple().exponent < (-2 if label == "Fatura tutarı" else -3):
            errors.append(f"{label} en fazla {2 if label == 'Fatura tutarı' else 3} ondalık basamak içerebilir.")
    if not valid_reading_date(reading_date):
        errors.append("Geçerli bir okuma tarihi giriniz (YYYY-AA-GG).")
    if errors:
        return {"errors": errors}

    lokanta_consumption = round(lokanta_end - lokanta_start, 3)
    koltukcu_consumption = round(koltukcu_end - koltukcu_start, 3)
    sub_total = round(lokanta_consumption + koltukcu_consumption, 3)
    emlak_consumption = round(main_meter - sub_total, 3)

    if lokanta_consumption < 0:
        errors.append("Lokanta bitiş endeksi başlangıçtan küçük olamaz.")
    if koltukcu_consumption < 0:
        errors.append("Koltukçu bitiş endeksi başlangıçtan küçük olamaz.")
    if emlak_consumption < 0:
        errors.append("Alt sayaç tüketimleri toplamı ana sayaç tüketimini aşamaz.")
    if errors:
        return {"errors": errors}

    unit_price = round(total_bill / main_meter, 6)

    # Calculate amounts
    bill = Decimal(str(total_bill))
    meter = Decimal(str(main_meter))
    cents = Decimal("0.01")
    lokanta_money = (Decimal(str(lokanta_consumption)) / meter * bill).quantize(cents, rounding=ROUND_HALF_UP)
    koltukcu_money = (Decimal(str(koltukcu_consumption)) / meter * bill).quantize(cents, rounding=ROUND_HALF_UP)
    # Very small bills can round both sub-meters up; do not make the residual negative.
    excess = max(Decimal(0), lokanta_money + koltukcu_money - bill)
    if excess:
        if lokanta_money >= koltukcu_money:
            lokanta_money -= excess
        else:
            koltukcu_money -= excess
    lokanta_amount = float(lokanta_money)
    koltukcu_amount = float(koltukcu_money)
    emlak_amount = float(bill - lokanta_money - koltukcu_money)

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
    img = img.convert("RGB")
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

    from PIL import ImageOps
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")

    # Focus between blue markers if detected
    marker_box = find_blue_marker_region(img)
    if marker_box:
        img = img.crop(marker_box)

    # Upscale narrow/low-DPI mobile screenshots so Tesseract reads small fonts cleanly
    if img.width < 1000:
        scale = max(2, int(1200 / img.width))
        img = img.resize((img.width * scale, img.height * scale), Image.Resampling.LANCZOS)

    try:
        text = pytesseract.image_to_string(img, lang="tur", timeout=60)
        return text
    except Exception:
        return None


def ocr_pdf(file_bytes):
    """Extract text from PDF. Falls back to OCR if no embedded text found."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None

    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        if len(doc) == 0:
            return None
        full_text = "\n".join(doc[i].get_text() for i in range(min(2, len(doc)))).strip()
        if len(full_text) > 100:
            return full_text
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72))
        return ocr_image(pix.tobytes("png")) or full_text or None


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.errorhandler(413)
def upload_too_large(error):
    return jsonify({"error": "Dosya en fazla 16 MB olabilir."}), 413


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
    ts = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex
    ext = os.path.splitext(file.filename)[1] or (".pdf" if is_pdf else ".jpg")
    save_path = os.path.join(UPLOAD_DIR, f"{ts}{ext}")
    with open(save_path, "wb") as f:
        f.write(file_bytes)

    # OCR
    try:
        if is_pdf:
            text = ocr_pdf(file_bytes)
        else:
            text = ocr_image(file_bytes)
    except Exception:
        app.logger.exception("Fatura dosyası okunamadı")
        return jsonify({"error": "Dosya okunamadı. Geçerli bir PDF veya resim seçiniz."}), 422

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
    data = request.get_json(silent=True)
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
        ORDER BY COALESCE(NULLIF(reading_date, ''), SUBSTR(created_at, 1, 10)) DESC, id DESC LIMIT 1
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
        ORDER BY effective_date DESC, id DESC
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
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"errors": ["Geçersiz istek."]}), 400

    result = calculate(data)
    if "errors" in result:
        return jsonify(result), 400

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    reading_date = result["readingDate"]
    shops = {s["id"]: s for s in result["shops"]}

    conn = get_db()
    # Serialize lookup and insertion so concurrent retries cannot create duplicates.
    conn.execute("BEGIN IMMEDIATE")
    duplicate = conn.execute(
        """SELECT id, created_at FROM calculations
           WHERE total_bill = ? AND main_meter = ?
             AND lokanta_start = ? AND lokanta_end = ?
             AND koltukcu_start = ? AND koltukcu_end = ?
             AND COALESCE(NULLIF(reading_date, ''), SUBSTR(created_at, 1, 10)) = ?
           LIMIT 1""",
        (result["totalBill"], result["mainMeter"],
         safe_float(data.get("lokantaStart")), safe_float(data.get("lokantaEnd")),
         safe_float(data.get("koltukcuStart")), safe_float(data.get("koltukcuEnd")), reading_date),
    ).fetchone()
    if duplicate:
        conn.close()
        result.update(id=duplicate["id"], createdAt=duplicate["created_at"], duplicate=True)
        return jsonify(result), 200
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
            safe_float(data.get("lokantaStart")), safe_float(data.get("lokantaEnd")),
            safe_float(data.get("koltukcuStart")), safe_float(data.get("koltukcuEnd")),
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

