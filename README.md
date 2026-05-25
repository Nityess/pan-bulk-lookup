# PAN Bulk Lookup — IRD Nepal

A Windows desktop app that looks up many PAN (Permanent Account Number) records in bulk
from the [Inland Revenue Department of Nepal](https://ird.gov.np/pan-search), and exports
the results to Excel or CSV.

![Status](https://img.shields.io/badge/platform-Windows-blue)

## Download & run (for users)

You do **not** need Python — just download the ready-to-run app.

1. Go to the [**Releases**](../../releases/latest) page.
2. Download **`PAN-Lookup.zip`**.
3. Right-click the zip → **Extract All…**
4. Open the extracted **`PAN Lookup`** folder and double-click **`PAN Lookup.exe`**.

> Windows SmartScreen may warn that the publisher is unknown (the app isn't code-signed).
> Click **More info → Run anyway**. The app is open source — you can read all the code here.

### How to use it

1. Click **Browse…** and pick a `.csv` or `.xlsx` file with **9-digit PAN numbers in the first column**
   (see [`test_pans.csv`](test_pans.csv) for the format).
2. Click **Start Lookup**. Results stream into the table, color-coded:
   green = found, yellow = not found, red = error.
3. Click **Export Results** to save everything to Excel/CSV.

**Settings:** *Parallel tabs* (1–6) controls how many lookups run at once — higher is faster
but hits the IRD server harder. *Delay* adds a pause between lookups if you get rate-limited.

## Run from source (for developers)

Requires Python 3.10+.

```bash
pip install pandas playwright openpyxl
python -m playwright install chromium
python pan_app.py
```

There's also a command-line version:

```bash
python pan.py input.csv --output results.xlsx
```

## Building the .exe yourself

The app bundles a headless Chromium browser, so the build is large (~365 MB).

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm pan_app.spec
```

The result lands in `dist/PAN Lookup/`.

## Notes

- The IRD search is protected by Google reCAPTCHA, so each lookup drives a real browser
  session — there's no way to call the API directly. Lookups take a couple of seconds each.
- Be respectful of the IRD server: keep parallel tabs modest and add a delay for large lists.

## License

[MIT](LICENSE)
