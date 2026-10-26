# ⚡ AI Trading Copilot (HFM MT5 + Web UI)

Asisten trading semi-otomatis (**Human-in-the-Loop**) berbasis web modern dengan arsitektur bertenaga LLM (OpenAI / Claude), analisis multi-timeframe kuantitatif, deteksi berita ekonomi (Forex Factory, ForexLive, Yahoo Finance, Google News), formula lot **Anti-Margin Call**, dan koneksi langsung ke broker HFM via MetaTrader 5 (MT5).

Sistem dirancang khusus untuk berjalan langsung di **Windows Native (Tanpa Docker)** agar dapat mengakses terminal MetaTrader 5 secara langsung, dengan opsi database **Remote MySQL** atau SQLite lokal.

---

## 🪟 Panduan Menjalankan di Windows (Tanpa Docker)

Karena terminal MT5 memerlukan integrasi Win32 API native melalui library `MetaTrader5`, aplikasi ini dijalankan langsung di lingkungan Windows tanpa Docker.

### Langkah 1: Persiapan Python
1. Pastikan komputer/VPS Windows Anda telah terinstal **Python 3.10, 3.11, atau 3.12** dari [python.org](https://www.python.org/downloads/).
2. ⚠️ **Penting:** Saat instalasi Python di Windows, **centang kotak "Add Python to PATH"**.

### Langkah 2: Setup 1-Klik di Windows
Cukup klik dua kali berkas:
👉 **`setup_windows.bat`**

Script ini akan otomatis:
- Membuat folder virtual environment (`venv`).
- Mengupgrade `pip`.
- Menginstal seluruh dependensi di [`requirements.txt`](file:///Users/0x4f/Documents/Projects/Projects/ai-trade/requirements.txt) termasuk `MetaTrader5` native untuk Windows.

### Langkah 3: Menjalankan Server di Windows
Setelah instalasi selesai, cukup klik dua kali berkas:
👉 **`run.bat`**

Server akan langsung menyala di:
```
http://localhost:8000
```

---

## 🌐 Konfigurasi Remote MySQL

Aplikasi mendukung koneksi langsung ke server MySQL remote (misal di VPS, cPanel, Cloud SQL, atau server hosting terpisah).

### 1. Import Skema ke Remote MySQL
Jalankan file query [`schema.sql`](file:///Users/0x4f/Documents/Projects/Projects/ai-trade/schema.sql) pada remote database MySQL Anda (misal via phpMyAdmin, DBeaver, atau MySQL Workbench).

### 2. Atur Koneksi Remote
Ada 2 cara mudah:

#### Cara A: Langsung dari Web Dashboard (Direkomendasikan)
1. Buka dashboard di browser: `http://localhost:8000`.
2. Masuk dengan login default (`admin` / `password123`).
3. Buka tab **Pengaturan** (ikon gear) -> Bagian **5. Konfigurasi Basis Data (Remote MySQL)**.
4. Pilih Tipe Database: **MySQL (Remote Server)**.
5. Masukkan **Host Remote**, **Port (3306)**, **Username**, **Password**, dan **Nama Database**.
6. Klik tombol **[ Test DB Connection ]** untuk menguji apakah remote MySQL Anda dapat dijangkau.
7. Klik **[ Simpan Semua Pengaturan ]**.

#### Cara B: Edit Berkas `config.json`
Buka file [`config.json`](file:///Users/0x4f/Documents/Projects/Projects/ai-trade/config.json):
```json
{
  "database": {
    "type": "mysql",
    "host": "ip-atau-domain-remote-mysql.com",
    "port": 3306,
    "user": "db_user",
    "password": "db_password",
    "database": "ai_trade"
  }
}
```

> [!NOTE]
> Jika server MySQL remote sedang offline atau terjadi gangguan jaringan, aplikasi secara cerdas akan otomatis beralih ke SQLite lokal sementara agar bot tidak crash.

---

## 📱 Fitur Tampilan Mobile-Friendly

- **Responsive Mobile Layout:** Tampilan otomatis menyesuaikan layar HP (iPhone/Android) dengan tombol dan kartu yang sentuh-sentuh (touch-friendly).
- **Mobile Bottom Navigation Bar:** Navigasi cepat di bagian bawah layar:
  - 🔍 **Analisa:** Pilihan simbol, eksekusi tombol `Hit Analyze`, kartu hasil rekomendasi AI, tombol `Pasang Order ke MT5`.
  - 📊 **Riwayat:** Jurnal histori analisa & tiket order MT5 yang terpasang.
  - ⚙️ **Pengaturan:** MT5 credentials, LLM API Key, Remote DB, checklist berita, whitelist simbol.
  - 🔑 **Password:** Ganti password login kapan saja.
- **Top Header Status:** Indikator koneksi MT5 (*Active/Bridge*), Balance modal, Equity, dan Jam Sesi Pasar (*Tokyo, London 14-18 WIB, NY 19-23 WIB*).

---

## 🔑 Kredensial Login
- **Username:** `admin`
- **Password Default:** `password123`
*(Password dapat diubah kapan saja dari tab Password di UI atau langsung diedit di `config.json`)*

---

## 🤖 Dukungan Custom LLM Base URL (OpenAI-Compatible)
Aplikasi mendukung custom endpoint API yang kompatibel dengan format OpenAI. Anda dapat menggunakan:
- **DeepSeek API:** `https://api.deepseek.com/v1` (Model: `deepseek-chat` / `deepseek-reasoner`)
- **OpenRouter:** `https://openrouter.ai/api/v1`
- **Ollama / Local LLM:** `http://localhost:11434/v1`
- **vLLM / Groq / Together AI / dll.**

Cukup atur **LLM Base URL** di menu Pengaturan (Web UI) atau di `config.json` pada field `"llm_base_url"`. Klik tombol **[ Test AI Connection ]** untuk memastikan API key dan endpoint berfungsi dengan baik.

---

## 📰 Berita Real-Time FinancialJuice & Pantauan Index Dollar (DXY)
- **FinancialJuice.com:** Terintegrasi langsung dengan feed berita breaking & squawk real-time (`https://www.financialjuice.com/feed.ashx`), melengkapi Forex Factory Calendar, ForexLive RSS, dan Yahoo Finance.
- **Index Dollar (DXY):**
  - **Live Header Badge:** Menampilkan level DXY terkini dan persentase perubahan harian (contoh: `DXY: 103.45 (+0.25%)`).
  - **Analisis Korelasi Otomatis:** Pergerakan DXY dianalisis oleh AI dalam prompt analisa trading. Jika DXY mengalami reli/bullish, AI secara otomatis memperhitungkan tekanan bearish terhadap Gold (XAUUSD) dan mata uang berpasangan USD (seperti EURUSD, GBPUSD).

---

## 📈 Panduan Membaca Saldo Real-Time dari MetaTrader 5
Agar saldo (**Balance** & **Equity**) terbaca langsung dari akun MT5 Anda:
1. **Buka Aplikasi MetaTrader 5 di Windows:**
   - Pastikan aplikasi desktop MT5 (misal: HFM MT5) sudah terbuka dan ter-login ke akun trading Anda.
2. **Deteksi Otomatis Terminal:**
   - Library `MetaTrader5` di Windows akan langsung mengaitkan (*hook*) ke proses `terminal64.exe` yang sedang berjalan.
   - Anda **tidak wajib memasukkan password** jika terminal MT5 di Windows sudah dalam keadaan login! Saldo real akan otomatis terbaca.
3. **Tombol Refresh Saldo:**
   - Klik ikon 🔄 pada kartu **Balance & Equity** di header atas, atau klik tombol **`[ Cek Saldo Real-Time ]`** di menu **Pengaturan**.
4. **Path Terminal Kustom (Jika Diperlukan):**
   - Jika MT5 tidak terdeteksi otomatis karena dipasang di direktori khusus, isi kolom **Path Terminal64.exe (Opsional)** di menu Pengaturan (contoh: `C:\Program Files\HFM MetaTrader 5\terminal64.exe`).
   - Sistem juga secara otomatis memindai lokasi umum seperti:
     - `C:\Program Files\HFM MetaTrader 5\terminal64.exe`
     - `C:\Program Files\MetaTrader 5\terminal64.exe`
     - `C:\Program Files (x86)\...`


