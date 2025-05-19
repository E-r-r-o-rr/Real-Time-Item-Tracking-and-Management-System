#!/usr/bin/env python3
import os
import sys
import json
import datetime

from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import cv2
import numpy as np
import easyocr
import openai
from difflib import SequenceMatcher
from pyzbar.pyzbar import decode

from pathlib import Path
from models import Base, engine, SessionLocal, Order
from universal_receipt_ocr import extract_blocks, call_llm_extract  # your OCR+GPT routines

# ——— CONFIGURATION ———

# 1) Ensure OpenAI key is present
openai.api_key = os.getenv("OPENAI_API_KEY", "")
if not openai.api_key:
    print("❌ Missing OPENAI_API_KEY", file=sys.stderr)
    sys.exit(1)

# 2) Create all database tables if they don’t exist
Base.metadata.create_all(bind=engine)

# 3) Path to the single-row structured CSV (for scan/compare)
CSV_PATH = Path("structured_output.csv")
if not CSV_PATH.exists():
    print("❌ structured_output.csv not found – run your OCR+AI pipeline first", file=sys.stderr)
    sys.exit(1)

# Load that one row at startup
with CSV_PATH.open(newline="", encoding="utf-8") as f:
    import csv
    reader = csv.DictReader(f)
    try:
        structured_row = next(reader)
    except StopIteration:
        print("❌ structured_output.csv must contain at least one data row", file=sys.stderr)
        sys.exit(1)

# Initialize FastAPI and Jinja2 templates
app = FastAPI()
templates = Jinja2Templates(directory="templates")


# Dependency to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Helper: map GPT output keys to our Order model fields
def map_to_order_fields(gpt_dict: dict):
    return {
        "order_id": gpt_dict.get("Order ID", "").strip(),
        "date": gpt_dict.get("Date", "").strip(),
        "total": gpt_dict.get("Total", "").strip(),
        # … add or remove keys here to match your GPT’s output fields …
    }


# —————————— ROUTES ——————————

@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    """
    Simple homepage linking to Upload/Scan, Collect, and Live Scan.
    """
    return templates.TemplateResponse("home.html", {"request": request})


# ---------------------------------
# 1) UPLOAD & SCAN A RECEIPT
# ---------------------------------

@app.get("/upload-scan", response_class=HTMLResponse)
async def upload_scan_form(request: Request):
    """
    Render a form where the user can upload a receipt image to be OCR+GPT processed.
    """
    return templates.TemplateResponse("upload_scan.html", {"request": request})


@app.post("/upload-scan", response_class=HTMLResponse)
async def handle_upload_scan(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    1) Read the uploaded image, run OCR→GPT to extract fields.
    2) Check if `order_id` already exists in DB:
         • If not, insert as a new row.
         • If yes but other data differs, show differences and ask for confirmation.
         • If yes and identical, inform user.
    """
    # a) Load image from UploadFile into OpenCV
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return templates.TemplateResponse("upload_result.html", {
            "request": request,
            "error": "Invalid image file."
        })

    # b) Run EasyOCR -> GPT
    tmp_file = f"tmp_upload_{datetime.datetime.utcnow().timestamp()}.png"
    cv2.imwrite(tmp_file, img)
    blocks = extract_blocks(Path(tmp_file))
    try:
        gpt_data = call_llm_extract(blocks)
    except Exception as e:
        os.remove(tmp_file)
        return templates.TemplateResponse("upload_result.html", {
            "request": request,
            "error": f"Error during OCR/GPT: {e}"
        })
    os.remove(tmp_file)

    # c) Map GPT output to our Order fields
    mapped = map_to_order_fields(gpt_data)
    oid = mapped.get("order_id")
    if not oid:
        return templates.TemplateResponse("upload_result.html", {
            "request": request,
            "error": "No Order ID detected – cannot proceed."
        })

    # d) Check if order exists
    existing = db.query(Order).filter_by(order_id=oid).first()
    if not existing:
        # Insert new order
        new_order = Order(
            filename=file.filename,
            order_id=oid,
            date=mapped.get("date", ""),
            total=mapped.get("total", ""),
            collected=False,
            last_updated=datetime.datetime.utcnow()
        )
        db.add(new_order)
        db.commit()
        return templates.TemplateResponse("upload_result.html", {
            "request": request,
            "message": f"New order inserted: Order ID {oid}.",
            "order": new_order,
            "action": None
        })
    else:
        # Compare each field for differences
        diffs = {}
        for fld, val in mapped.items():
            old_val = getattr(existing, fld, "")
            if str(old_val).strip() != str(val).strip():
                diffs[fld] = {"old": old_val or "", "new": val or ""}
        if not diffs:
            return templates.TemplateResponse("upload_result.html", {
                "request": request,
                "message": f"Order ID {oid} already exists with identical data.",
                "order": existing,
                "action": None
            })
        else:
            return templates.TemplateResponse("upload_result.html", {
                "request": request,
                "message": f"Order {oid} found but data differs. Please confirm updates.",
                "order": existing,
                "diffs": diffs,
                "action": "confirm_update",
                "new_data": json.dumps(mapped)
            })


@app.post("/confirm-update", response_class=HTMLResponse)
async def confirm_update(
    request: Request,
    order_id: str = Form(...),
    new_data: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    After showing diffs, user clicks “Confirm Update” to apply new GPT data.
    """
    mapped = json.loads(new_data)
    existing = db.query(Order).filter_by(order_id=order_id).first()
    if not existing:
        return templates.TemplateResponse("upload_result.html", {
            "request": request,
            "error": f"Order {order_id} not found."
        })

    # Update fields
    for fld, val in map_to_order_fields(mapped).items():
        setattr(existing, fld, val)
    existing.last_updated = datetime.datetime.utcnow()
    db.commit()
    return templates.TemplateResponse("upload_result.html", {
        "request": request,
        "message": f"Order {order_id} updated successfully.",
        "order": existing,
        "action": None
    })


# ---------------------------------
# 2) MARK AN ORDER AS “COLLECTED”
# ---------------------------------

@app.get("/collect", response_class=HTMLResponse)
async def collect_form(request: Request):
    """
    Render a form where user can paste Order ID or upload a barcode image to mark “collected.”
    """
    return templates.TemplateResponse("collect.html", {"request": request})


@app.post("/collect", response_class=HTMLResponse)
async def handle_collect(
    request: Request,
    order_id: str = Form(None),
    file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    """
    1) If user provided an Order ID in text, use that.
    2) If user uploaded a barcode image, decode it with pyzbar.
    3) If no record found: insert new row with only order_id and collected=True.
    4) If found: mark collected=True (if not already).
    """
    scanned_code = None
    # a) If a file was uploaded, try to decode barcode
    if file and file.filename:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return templates.TemplateResponse("collect_result.html", {
                "request": request,
                "error": "Invalid image file."
            })
        barcodes = decode(img)
        if not barcodes:
            return templates.TemplateResponse("collect_result.html", {
                "request": request,
                "error": "No barcode detected in the uploaded image."
            })
        scanned_code = barcodes[0].data.decode("utf-8").strip()

    elif order_id:
        scanned_code = order_id.strip()

    if not scanned_code:
        return templates.TemplateResponse("collect_result.html", {
            "request": request,
            "error": "Please provide an Order ID or upload a barcode image."
        })

    existing = db.query(Order).filter_by(order_id=scanned_code).first()
    if not existing:
        # Insert a minimal record with collected=True
        new_order = Order(
            order_id=scanned_code,
            collected=True,
            last_updated=datetime.datetime.utcnow()
        )
        db.add(new_order)
        db.commit()
        return templates.TemplateResponse("collect_result.html", {
            "request": request,
            "message": f"Order {scanned_code} added as new and marked collected."
        })
    else:
        if existing.collected:
            msg = f"Order {scanned_code} was already marked collected on {existing.last_updated}."
        else:
            existing.collected = True
            existing.last_updated = datetime.datetime.utcnow()
            db.commit()
            msg = f"Order {scanned_code} marked as collected."
        return templates.TemplateResponse("collect_result.html", {
            "request": request,
            "message": msg
        })


# ---------------------------------
# 3) LIVE SCAN + COMPARE (Barcode vs. structured_output.csv)
# ---------------------------------

@app.get("/scan", response_class=HTMLResponse)
async def scan_page():
    """
    Serve an HTML page that uses QuaggaJS to open the phone camera, scan a barcode,
    then call /compare to get per-field similarity against structured_output.csv.
    """
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Barcode vs OCR Comparison</title>
  <script src="https://unpkg.com/quagga/dist/quagga.min.js"></script>
  <style>
    body,html {{ margin:0; padding:0; background:#000; color:#0f0; font-family:sans-serif; }}
    #container {{ position:relative; width:100vw; height:70vh; }}
    #status {{ position:absolute; top:1em; left:1em; background:rgba(0,0,0,0.6); padding:0.5em; }}
    table {{ width:100%; border-collapse:collapse; margin-top:1em; }}
    th,td {{ border:1px solid #0f0; padding:0.5em; text-align:left; }}
    th {{ background:rgba(0,255,0,0.1); }}
  </style>
</head>
<body>
  <div id="container">
    <div id="status">Initializing camera…</div>
  </div>
  <script>
    const status = document.getElementById("status");
    window.addEventListener("load", () => {{
      Quagga.init({{
        inputStream: {{
          name: "Live",
          type: "LiveStream",
          target: document.getElementById('container'),
          constraints: {{ facingMode: "environment" }}
        }},
        decoder: {{
          readers: ["code_128_reader","ean_reader","upc_reader","upc_e_reader"]
        }},
        locate: true
      }}, err => {{
        if (err) {{
          status.textContent = "Camera error: " + err;
          return;
        }}
        Quagga.start();
        status.textContent = "Point at the barcode…";
      }});
      Quagga.onDetected(data => {{
        const code = data.codeResult.code;
        status.textContent = "Scanned: " + code;
        Quagga.stop();
        fetch(`/compare?code=${{encodeURIComponent(code)}}`)
          .then(res => res.json())
          .then(json => renderComparison(json))
          .catch(err => {{ status.textContent = "Error: " + err; }});
      }});
    }});

    function renderComparison({{ scanned, comparison }}) {{
      document.getElementById('container').remove();
      status.textContent = `Scanned: ${{scanned}}`;
      const tbl = document.createElement('table');
      const header = tbl.insertRow();
      ["Field","CSV Value","Scanned Code","Similarity"].forEach(h => {{
        const th = document.createElement('th');
        th.innerText = h;
        header.appendChild(th);
      }});
      comparison.forEach(row => {{
        const tr = tbl.insertRow();
        [row.column, row.csv_value, scanned, row.similarity].forEach(text => {{
          const td = tr.insertCell();
          td.innerText = text;
        }});
      }});
      document.body.appendChild(tbl);
    }}
  </script>
</body>
</html>
"""


@app.get("/compare")
async def compare(code: str = Query(..., description="Scanned barcode value")):
    """
    Compare the scanned barcode string against each column in structured_output.csv.
    Returns JSON: { scanned: <code>, comparison: [ {column, csv_value, similarity}, … ] }.
    """
    results = []
    for col, val in structured_row.items():
        val_str = val or ""
        sim = SequenceMatcher(None, val_str, code).ratio() if val_str else 0.0
        results.append({
            "column": col,
            "csv_value": val_str,
            "similarity": round(sim, 2)
        })
    return JSONResponse({"scanned": code, "comparison": results})


@app.get("/orders", response_class=HTMLResponse)
async def view_all_orders(request: Request, db: Session = Depends(get_db)):
    """
    Fetch every Order row from the database and display them in an HTML table.
    """
    all_orders = db.query(Order).order_by(Order.id).all()

    # We’ll pass `all_orders` into a template called "orders.html"
    return templates.TemplateResponse("orders.html", {
        "request": request,
        "orders": all_orders
    })