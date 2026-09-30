"""
daily_report_bot.py
===================
Gen AI Architect Program - Assignment 1 (PyAutoGUI Automation)
(Windows + Microsoft Excel, English version)
 
What this bot does:
  1. Opens Chrome (your chosen profile - no "Who's using Chrome?" screen)
     and goes to Google Finance for the stock (default: TCS).
  2. Copies all the important points: price, today's change, previous close,
     open, day range, 52-week high/low, volume, market cap, P/E ratio.
     Takes a screenshot of the Chrome finance page, then closes that window.
  3. Opens Microsoft Excel and a new blank workbook.
  4. Creates a row: date & time | all stock details | automatic comment,
     and pastes the Chrome screenshot below the row.
  5. Saves the file as  daily_report_YYYY-MM-DD.xlsx
  6. Takes a screenshot of the final Excel sheet, then CLOSES Excel.
 
SAFETY: While the bot runs, DO NOT touch the mouse or keyboard.
        Emergency stop: quickly move the mouse to the TOP-LEFT corner.
"""
 
import os
import re
import sys
import time
import subprocess
import urllib.parse
from datetime import datetime
 
import pyautogui          # core automation library (mouse + keyboard + screenshot)
import pyperclip          # helper: read / write text on the clipboard
import pygetwindow as gw  # helper: find and focus windows
from PIL import Image     # helper: resize the screenshot (installed with pyautogui)
 
 
# ======================================================================
# SETTINGS  (change these if you want)
# ======================================================================
# Chrome profile that is signed in to jackmani.mech@gmail.com.
# How to find it: open Chrome with that profile -> type  chrome://version
# in the address bar -> look at "Profile Path" -> the LAST part
# (for example "Default" or "Profile 1" or "Profile 3").
CHROME_PROFILE = "Default"
 
STOCK_NAME = "TCS"
GOOGLE_SYMBOL = "TCS:NSE"        # e.g. RELIANCE:NSE, INFY:NSE
FINANCE_URL = f"https://www.google.com/finance/quote/{GOOGLE_SYMBOL}"
 
GMAIL_ID = "jackmani.mech@gmail.com"   # used only to pick the right Chrome profile
 
# Files are saved in the same folder as this script
SAVE_FOLDER = os.path.dirname(os.path.abspath(__file__))
 
pyautogui.FAILSAFE = True   # move mouse to top-left corner to abort
pyautogui.PAUSE = 0.4       # small pause after every PyAutoGUI action
 
 
# ======================================================================
# HELPER FUNCTIONS
# ======================================================================
def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
 
 
def paste_text(text):
    """Put text on the clipboard and paste it (fast, no lost letters)."""
    pyperclip.copy(text)
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "v", interval=0.2)     # slower = Ctrl is surely held
    time.sleep(0.5)
 
 
def run_powershell(command):
    """Run a small PowerShell command (used to put images/files on the clipboard)."""
    subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-Command", command],
        capture_output=True, text=True,
    )
 
 
def image_to_clipboard(image_path):
    """Copy a picture to the clipboard, so Ctrl+V pastes the picture."""
    run_powershell(
        "Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
        f"[System.Windows.Forms.Clipboard]::SetImage([System.Drawing.Image]::FromFile('{image_path}'))"
    )
    time.sleep(0.5)
 
 
def find_chrome_profile(email):
    """Find the Chrome profile folder that is signed in with `email`
    (Chrome keeps this list in the 'Local State' file). Falls back to CHROME_PROFILE."""
    try:
        import json
        local_state = os.path.join(os.environ["LOCALAPPDATA"],
                                   "Google", "Chrome", "User Data", "Local State")
        with open(local_state, encoding="utf-8") as f:
            profiles = json.load(f)["profile"]["info_cache"]
        for folder, info in profiles.items():
            if info.get("user_name", "").lower() == email.lower():
                return folder
    except Exception as e:
        log(f"Could not auto-detect Chrome profile ({e}).")
    return CHROME_PROFILE
 
 
def open_chrome(url):
    """Open a NEW Chrome window in the chosen profile, directly at the URL.
    Using --profile-directory skips the "Who's using Chrome?" screen."""
    log(f"Opening Chrome (profile '{CHROME_PROFILE}') -> {url[:70]}...")
    os.startfile("chrome", arguments=f'--profile-directory="{CHROME_PROFILE}" --new-window "{url}"')
 
 
def wait_for_window(title_part, timeout=40):
    """Wait until a window with `title_part` in its title appears,
    then bring it to the front and maximize it."""
    log(f"Waiting for window '{title_part}' ...")
    start = time.time()
    while time.time() - start < timeout:
        windows = [w for w in gw.getWindowsWithTitle(title_part) if w.title.strip()]
        if windows:
            win = windows[0]
            try:
                if win.isMinimized:
                    win.restore()
                win.activate()
            except Exception:
                try:
                    win.minimize()
                    win.restore()
                except Exception:
                    pass
            time.sleep(0.8)
            try:
                win.maximize()
            except Exception:
                pass
            time.sleep(1)
            log(f"Window ready: '{win.title}'")
            return True
        time.sleep(1)
    log(f"WARNING: window '{title_part}' not found in {timeout}s. Continuing anyway.")
    return False
 
 
def close_active_window():
    pyautogui.hotkey("alt", "f4")
    time.sleep(2)
 
 
# ======================================================================
# READ THE STOCK DETAILS FROM THE COPIED PAGE TEXT
# ======================================================================
MONEY = r"₹\s?[\d,]+(?:\.\d+)?"
FIELDS = [
    # (column name, label on the page, value pattern)
    ("Previous Close", r"prev(?:ious)?\.? close", MONEY),
    ("Open",           r"open",                   MONEY),
    ("Day Range",      r"day range",              MONEY + r"\s*-\s*" + MONEY),
    ("Day High",       r"day high",               MONEY),
    ("Day Low",        r"day low",                MONEY),
    ("Year Range",     r"year range",             MONEY + r"\s*-\s*" + MONEY),
    ("52-Week High",   r"52[- ]?wk high|52[- ]?week high", MONEY),
    ("52-Week Low",    r"52[- ]?wk low|52[- ]?week low",   MONEY),
    ("Volume",         r"volume|avg\.? volume",   r"[\d,.]+\s?[KMBT]?"),
    ("Market Cap",     r"mkt cap|market cap",     r"[\d,.]+\s?[KMBT]?(?:\s?INR)?"),
    ("P/E Ratio",      r"p/e ratio",              r"[\d,.]+"),
    ("Dividend Yield", r"div(?:idend)? yield",    r"[\d.]+\s?%"),
]
 
 
def read_stock_details(text):
    """Returns a dict of details, or None if the price is not found yet."""
    price = re.search(MONEY, text)
    if not price:
        return None
    details = {"Price": price.group(0).replace(" ", "")}
 
    # today's change, e.g. "+1.15%" and "+23.30" just after the price
    after_price = text[price.end(): price.end() + 120]
    pct = re.search(r"([+-]?\d+(?:\.\d+)?)\s?%", after_price)
    amt = re.search(r"([+-][\d,]+\.\d+)(?![\d.]*\s?%)", after_price)   # not the % number
    details["Change %"] = float(pct.group(1)) if pct else None
    change_text = "-"
    if pct:
        change_text = f"{pct.group(1)}%" + (f" ({amt.group(1)})" if amt else "")
    details["Change Today"] = change_text
 
    # other fields: find the label, then the value in the next few pieces of text
    pieces = [p.strip() for p in re.split(r"[\n\t]+", text) if p.strip()]
    for name, label, value in FIELDS:
        for i, piece in enumerate(pieces):
            if re.fullmatch(label, piece, flags=re.IGNORECASE):
                for nxt in pieces[i + 1: i + 4]:
                    if re.fullmatch(value, nxt, flags=re.IGNORECASE):
                        details[name] = nxt
                        break
                if name in details:
                    break
        if name not in details:
            # label and value on the same line, e.g. "Open ₹2,069.00 Volume 3.66M"
            inline = re.search(rf"\b(?:{label})\s*:?\s*({value})(?![\d,.])", text, flags=re.IGNORECASE)
            if inline:
                details[name] = inline.group(1).strip()
    return details
 
 
def make_comment(change_pct):
    if change_pct is None:
        return "Price fetched - change not available"
    if change_pct >= 1:
        return f"Strong day - up {change_pct:.2f}%"
    if change_pct >= 0:
        return f"Slightly up ({change_pct:+.2f}%) - holding steady"
    if change_pct > -1:
        return f"Slightly down ({change_pct:.2f}%) - no big worry"
    return f"Big fall ({change_pct:.2f}%) - watch closely"
 
 
# ======================================================================
# STEP 1 + 2 : CHROME -> COPY DETAILS -> SCREENSHOT -> CLOSE
# ======================================================================
def fetch_stock_from_chrome(chrome_image_path):
    open_chrome(FINANCE_URL)
    wait_for_window("Google Finance", timeout=40)
    screen_w, screen_h = pyautogui.size()
 
    details = None
    for attempt in range(1, 11):
        time.sleep(2)
        pyautogui.click(screen_w - 30, screen_h // 2)   # right edge: page gets focus, no link
        pyperclip.copy("")
        pyautogui.hotkey("ctrl", "a")                   # select all text
        pyautogui.hotkey("ctrl", "c")                   # copy
        time.sleep(0.5)
        details = read_stock_details(pyperclip.paste())
        if details:
            log(f"Copied (attempt {attempt}): {details}")
            break
        log(f"Page not ready yet (attempt {attempt}/10) ...")
 
    if not details:
        log("WARNING: could not read the stock price.")
        details = {"Price": "not available", "Change Today": "-", "Change %": None}
 
    # Clean screenshot of the Chrome page (reload removes the blue selection)
    pyautogui.press("f5")
    time.sleep(5)
    pyautogui.screenshot(chrome_image_path)
    log(f"Chrome screenshot saved: {chrome_image_path}")
 
    close_active_window()                               # close this Chrome window
    log("Chrome finance window closed.")
    return details
 
 
# ======================================================================
# STEP 3 + 4 : EXCEL -> WRITE ROW + PASTE CHROME SCREENSHOT
# ======================================================================
def build_table(date_time_text, details, comment):
    columns = ["Date & Time", "Stock", "Price", "Change Today"]
    columns += [name for name, _, _ in FIELDS if name in details]
    columns += ["Comment"]
    values = {"Date & Time": date_time_text, "Stock": f"{STOCK_NAME} (NSE)",
              "Comment": comment, **details}
    row = [str(values.get(c, "-")).replace("₹", "Rs ") for c in columns]
    return columns, row
 
 
def write_in_excel(columns, row, chrome_image_path):
    log("Opening Excel ...")
    os.system("start excel /e")                     # /e = skip the Excel start screen
    wait_for_window("Excel", timeout=60)
    time.sleep(5)
 
    screen_w, screen_h = pyautogui.size()
 
    def workbook_is_open():
        return any(w.title.endswith(" - Excel") for w in gw.getAllWindows())
 
    log("Creating a new blank workbook ...")
    for attempt in range(1, 5):
        if workbook_is_open():
            break
        if attempt == 1:
            pyautogui.hotkey("ctrl", "n", interval=0.2)       # new workbook
        elif attempt == 2:
            # click the "Blank workbook" picture on the Excel start/New page
            pyautogui.click(int(355 * screen_w / 1920), int(250 * screen_h / 1080))
        elif attempt == 3:
            pyautogui.press("enter")
        else:
            pyautogui.hotkey("ctrl", "n", interval=0.2)
        time.sleep(4)
    wait_for_window(" - Excel", timeout=20)          # e.g. "Book1 - Excel"
 
    pyautogui.click(screen_w // 2, screen_h // 2)   # click inside the sheet
    pyautogui.hotkey("ctrl", "home")                # go to A1
 
    time.sleep(1)
    # TYPE header + row cell by cell (Tab = next column, Enter = next row)
    for line in (columns, row):
        for cell in line:
            pyautogui.write(cell, interval=0.04)
            pyautogui.press("tab")
        pyautogui.press("enter")
    log("Row typed in Excel.")
 
    # AutoFit all columns (Home > Format > AutoFit Column Width)
    pyautogui.hotkey("ctrl", "a")
    for key in ["alt", "h", "o", "i"]:
        pyautogui.press(key)
        time.sleep(0.3)
 
    # Paste a smaller copy of the Chrome screenshot at cell A5
    small_path = chrome_image_path.replace(".png", "_small.png")
    img = Image.open(chrome_image_path)
    img.resize((img.width // 2, img.height // 2)).save(small_path)
 
    pyautogui.hotkey("ctrl", "g")                   # Go To box
    time.sleep(1)
    pyautogui.write("A5")
    pyautogui.press("enter")
    time.sleep(0.5)
    image_to_clipboard(small_path)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(2)
    pyautogui.press("esc")                          # un-select the picture
    pyautogui.hotkey("ctrl", "home")
    os.remove(small_path)
    log("Chrome screenshot pasted in Excel.")
 
 
# ======================================================================
# STEP 5 + 6 : SAVE, SCREENSHOT, CLOSE EXCEL
# ======================================================================
def save_screenshot_close_excel(excel_path, excel_image_path):
    if os.path.exists(excel_path):
        try:
            os.remove(excel_path)                   # avoid the "Replace?" pop-up
        except PermissionError:
            log("ERROR: the old report file is open. Close it and run again.")
            sys.exit(1)
 
    log(f"Saving as {excel_path}")
    pyautogui.press("f12")                          # Save As dialog
    time.sleep(3)
    pyautogui.hotkey("alt", "n", interval=0.2)      # jump to the "File name" box
    time.sleep(0.5)
    pyautogui.hotkey("ctrl", "a", interval=0.2)     # select old name
    pyautogui.press("backspace")                    # clear it completely
    pyautogui.write(excel_path, interval=0.03)      # type the full path
    time.sleep(0.5)
    pyautogui.press("enter")
 
    for _ in range(20):
        if os.path.exists(excel_path):
            log("Excel file saved.")
            break
        time.sleep(1)
    else:
        log("WARNING: could not confirm that the Excel file was saved.")
 
    time.sleep(2)
    wait_for_window(" - Excel", timeout=15)   # NOT VS Code
    pyautogui.screenshot(excel_image_path)
    log(f"Excel screenshot saved: {excel_image_path}")
 
    close_active_window()                           # close Excel
    log("Excel closed.")
 
 
# ======================================================================
# MAIN
# ======================================================================
def main():
    print("=" * 60)
    print(" DAILY REPORT BOT")
    print(" Do NOT touch the mouse/keyboard while it runs.")
    print(" Emergency stop: move mouse to the TOP-LEFT corner.")
    print("=" * 60)
    global CHROME_PROFILE
    CHROME_PROFILE = find_chrome_profile(GMAIL_ID)
    log(f"Chrome profile for {GMAIL_ID}: '{CHROME_PROFILE}'")
 
    for sec in range(5, 0, -1):
        print(f"Starting in {sec} ...")
        time.sleep(1)
 
    now = datetime.now()                            # generated at run time
    date_time_text = now.strftime("%Y-%m-%d %H:%M:%S")
    today = now.strftime("%Y-%m-%d")                # YYYY-MM-DD
 
    excel_path = os.path.join(SAVE_FOLDER, f"daily_report_{today}.xlsx")
    excel_image = os.path.join(SAVE_FOLDER, f"daily_report_{today}.png")
    chrome_image = os.path.join(SAVE_FOLDER, f"chrome_finance_{today}.png")
 
    details = fetch_stock_from_chrome(chrome_image)             # Steps 1-2
    comment = make_comment(details.get("Change %"))
    details.pop("Change %", None)
    columns, row = build_table(date_time_text, details, comment)
 
    write_in_excel(columns, row, chrome_image)                  # Steps 3-4
    save_screenshot_close_excel(excel_path, excel_image)        # Steps 5-6
 
    print("\n" + "=" * 60)
    print(" DONE!")
    print(f" Excel file        : {excel_path}")
    print(f" Excel screenshot  : {excel_image}")
    print(f" Chrome screenshot : {chrome_image}")
    print("=" * 60)
 
 
if __name__ == "__main__":
    try:
        main()
    except pyautogui.FailSafeException:
        print("\nBot stopped: mouse moved to the top-left corner (fail-safe).")
 