"""
IRD Nepal PAN Bulk Lookup
Reads PAN numbers from a CSV/Excel file, fetches details from ird.gov.np,
and writes structured results to an output file.

Usage:
    python pan.py input.csv
    python pan.py input.xlsx
    python pan.py input.xlsx --output results.xlsx
"""

import json
import re
import sys
import time
import argparse
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright


API_URL_PATTERN = "getPanSearch"


def read_input(filepath):
    path = Path(filepath)
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path, header=None, dtype=str)
    else:
        df = pd.read_csv(path, header=None, dtype=str)

    pans = df.iloc[:, 0].dropna().str.strip().tolist()
    pans = [p for p in pans if re.fullmatch(r"\d{9}", p)]
    return pans


def parse_result(data):
    row = {}

    details = data.get("panDetails", [])
    if details:
        d = details[0]
        row["PAN"] = d.get("pan", "")
        row["Name (English)"] = d.get("trade_Name_Eng", "")
        row["Name (Nepali)"] = d.get("trade_Name_Nep", "")
        row["Address"] = d.get("vdc_Town", "")
        row["Street"] = d.get("street_Name", "")
        row["Ward"] = d.get("ward_No", "")
        row["Phone"] = d.get("telephone", "")
        row["Mobile"] = d.get("mobile", "")
        row["Office"] = d.get("office_Name", "")
        row["Registration Date"] = d.get("eff_Reg_Date", "")
        row["Account Type"] = d.get("acctType", "")
        row["Account Status"] = d.get("account_Status", "")
        row["Is Personal"] = d.get("is_Personal", "")

    biz = data.get("businessDetail", [])
    if biz:
        names = [b.get("trade_Name_Eng", "") for b in biz]
        row["Business Names"] = " | ".join(names)

    reg = data.get("panRegistrationDetail", [])
    if reg:
        r = reg[0]
        row["Filing Period"] = r.get("filing_Period", "")

    tc = data.get("panTaxClearance", [])
    if tc:
        t = tc[0]
        row["Tax Clearance FY"] = t.get("fiscal_Year", "")
        row["Tax Clearance Date"] = t.get("return_Verified_Date", "")
        row["Tax Clearance Status"] = "Cleared" if t.get("exists_Yn") == "Y" else "Not Cleared"

    return row


def fetch_all(pans):
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("Loading PAN search page...")
        page.goto("https://ird.gov.np/pan-search", wait_until="networkidle", timeout=60000)

        total = len(pans)
        for i, pan in enumerate(pans, 1):
            print(f"[{i}/{total}] Looking up PAN {pan}...", end=" ")

            try:
                pan_input = page.locator("#pan")
                pan_input.fill("")
                pan_input.fill(pan)

                with page.expect_response(
                    lambda r: API_URL_PATTERN in r.url, timeout=30000
                ) as resp_info:
                    page.locator("#submit").click()

                response = resp_info.value
                body = response.body().decode("utf-8", errors="replace")
                api_data = json.loads(body)

                if api_data.get("code") == 1 and api_data.get("data"):
                    row = parse_result(api_data["data"])
                    row["Status"] = "Found"
                    print(row.get("Name (English)", "OK"))
                else:
                    row = {"PAN": pan, "Status": "Not Found"}
                    print("Not found")

            except Exception as e:
                row = {"PAN": pan, "Status": f"Error: {e}"}
                print(f"Error: {e}")

                # Reload page on error to reset state
                try:
                    page.goto("https://ird.gov.np/pan-search", wait_until="networkidle", timeout=60000)
                except Exception:
                    pass

            results.append(row)

            if i < total:
                time.sleep(1)

        browser.close()

    return results


def write_output(results, output_path):
    df = pd.DataFrame(results)

    columns = [
        "PAN", "Name (English)", "Name (Nepali)", "Address", "Street", "Ward",
        "Phone", "Mobile", "Office", "Registration Date", "Account Type",
        "Account Status", "Is Personal", "Business Names", "Filing Period",
        "Tax Clearance FY", "Tax Clearance Date", "Tax Clearance Status", "Status"
    ]
    existing = [c for c in columns if c in df.columns]
    df = df[existing]

    path = Path(output_path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        df.to_excel(path, index=False, engine="openpyxl")
    else:
        df.to_csv(path, index=False, encoding="utf-8-sig")

    print(f"\nResults saved to: {path.absolute()}")
    print(f"Total: {len(df)} | Found: {len(df[df['Status'] == 'Found'])} | Failed: {len(df[df['Status'] != 'Found'])}")


def main():
    parser = argparse.ArgumentParser(description="IRD Nepal PAN Bulk Lookup")
    parser.add_argument("input", help="Input CSV or Excel file with PAN numbers in the first column")
    parser.add_argument("--output", "-o", help="Output file path (default: pan_results.xlsx)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    output_path = args.output
    if not output_path:
        output_path = input_path.parent / "pan_results.xlsx"

    print(f"Reading PAN numbers from: {input_path}")
    pans = read_input(input_path)

    if not pans:
        print("Error: No valid 9-digit PAN numbers found in the file")
        sys.exit(1)

    print(f"Found {len(pans)} valid PAN numbers\n")

    results = fetch_all(pans)
    write_output(results, output_path)


if __name__ == "__main__":
    main()
