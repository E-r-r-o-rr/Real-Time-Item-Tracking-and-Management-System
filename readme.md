## Real-Time Receipt OCR & Order Management System

An end-to-end pipeline that lets you:

1. **OCR** printed receipts via [EasyOCR](https://github.com/JaidedAI/EasyOCR)
2. **Structure** the raw text into labeled fields using GPT-4
3. **Store** and **update** orders in a SQLite database via FastAPI
4. **Mark** orders “collected” by typing or scanning barcodes
5. **Live-scan** barcodes in your browser (QuaggaJS + getUserMedia)
6. **Batch-test** your OCR+AI accuracy against ground-truth

---

### 📋 Features

* **Upload & Scan**

  * Form to upload a receipt image
  * Runs EasyOCR → GPT-4 → SQL insert or update
* **Collect an Order**

  * Paste an Order ID or upload a barcode image
  * Marks `collected=True` in your DB
* **View All Orders**

  * Browse every record in `orders.db`
* **Live Barcode Comparison**

  * In-browser camera feed
  * QuaggaJS decodes barcode → compares to structured fields
* **Batch Accuracy Testing**

  * `generate_ground_truth.py` builds a CSV of GPT-extracted fields
  * `batch_test.py` compares predictions vs. ground-truth, outputs per-field similarity & overall exact-match rate

---

## 🛠️ Prerequisites

* **Python 3.11+**
* **Git** (to clone)
* **Optional GPU**: NVIDIA GPU + matching CUDA toolkit
* **ngrok** (for HTTPS camera access on mobile)

---

## 🚀 Installation & First Run

```bash
# 1. Clone this repo (or your fork)
git clone https://github.com/thorfinn22/Real-Time-Item-Tracking-and-Management-System.git
cd Real-Time-Item-Tracking-and-Management-System

# 2. Create & activate a virtualenv
python -m venv venv
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. (If you have CUDA) install GPU-enabled PyTorch
#    see https://pytorch.org for the right command, e.g.:
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu117

# 5. Set your OpenAI API key
#    Windows PowerShell:
$Env:OPENAI_API_KEY = "sk-<your-key-here>"

# 6. Run the FastAPI server
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

You should see:

```
INFO: Uvicorn running on http://0.0.0.0:8000
✅ OpenAI API detected and reachable.
```

---

## 🔒 Expose with HTTPS (for mobile camera)

Modern mobile browsers require **HTTPS** to allow camera access:

```bash
# In a second terminal (still inside project folder):
.\ngrok.exe http 8000
```

Copy the provided **HTTPS** URL, e.g.:

```
https://78e1-2405-6e00-22ee-de1c.ngrok-free.app
```

---

## 🎨 UI Endpoints

| URL path          | Description                                      |
| ----------------- | ------------------------------------------------ |
| `/`               | Homepage: links to each feature                  |
| `/upload-scan`    | Upload a receipt image & run OCR → GPT → DB      |
| `/collect`        | Mark an order “collected” via text or barcode    |
| `/orders`         | View all orders (HTML table)                     |
| `/scan`           | Live-scan barcode with your phone’s camera       |
| `/compare?code=…` | JSON compare: scanned code vs. structured fields |

---

## 📂 Templates

All HTML lives in the `templates/` folder. They use [Jinja2](https://jinja.palletsprojects.com/) but are vanilla, minimalistic, and easy to modify.

---

## 💡 Usage Walk-through

1. **Upload & Scan**

   * Go to `http://localhost:8000/upload-scan` (or `<ngrok-url>/upload-scan`)
   * Choose any receipt image under `receipts/` (e.g. `order_001.png`)
   * Click **Scan Receipt**
   * The page displays “New order inserted” or “Data differs—please confirm”

2. **Collect an Order**

   * Navigate to `/collect`
   * **Option A:** Paste the Order ID you just created → **Submit**
   * **Option B:** Upload a photo of its barcode → **Submit**
   * The page responds with a confirmation message

3. **View All Orders**

   * Visit `/orders`
   * Inspect every row in your `orders.db` table

4. **Live Barcode Comparison (Phone)**

   * On your **phone browser**, open:

     ```
     <ngrok-https-url>/scan
     ```
   * Tap **Allow Camera**
   * Point at any barcode (printed or on-screen)
   * A table appears, showing string-similarity between the scanned code and each structured field

---

## 📊 Batch Accuracy Testing

### 1. Generate ground truth

```bash
python generate_ground_truth.py
```

* Runs OCR → GPT on every image in `receipts/`
* Writes `ground_truth.csv` with header: `filename, Field1, Field2, …`

### 2. Run the batch test

```bash
python batch_test.py
```

* Re-runs OCR → GPT on each receipt
* Compares predicted fields vs. `ground_truth.csv` via character‐level similarity
* Outputs `batch_summary.csv` with:

  * **avg\_similarity** for each field
  * **exact\_match\_rate**, e.g. `60%`

---

## 🗄️ Inspecting the Database

```bash
python view_db.py
```

Prints a table of:

```
| id | filename      | order_id             | date       | total  | collected | last_updated           |
|----|---------------|----------------------|------------|--------|-----------|------------------------|
|  1 | order_001.png | 9876541123495878256  | 10/15/2025 | 123.45 |      1    | 2025-06-09T12:34:56    |
| …  | …             | …                    | …          | …      | …         | …                      |
```

---

## ⚙️ Customization

* **Fields mapping**: edit `map_to_order_fields()` in `app.py` to match GPT’s JSON keys → your DB schema.
* **AI model**: swap out the GPT-4 call in `universal_receipt_ocr.py` for any Hugging Face endpoint via `call_hf_model.py`.
* **UI look**: tweak the templates in `templates/` (they’re plain HTML + minimal CSS).

---

### 📄 License

This project is released under the MIT License.
Feel free to reuse, modify, and adapt!

---


