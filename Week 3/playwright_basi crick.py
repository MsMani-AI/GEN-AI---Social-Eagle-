from pathlib import Path
from playwright.sync_api import sync_playwright

# Today's match: India vs Sri Lanka, 1 October 2026
SCORECARD_URL = (
    "https://www.cricbuzz.com/live-cricket-scorecard/"
    "171060/ind-vs-sl-2nd-semi-final-asian-games-2026"
)

# Save files beside this Python script
folder = Path(__file__).resolve().parent
screenshot_file = folder / "IND_vs_SL_scorecard.png"
text_file = folder / "IND_vs_SL_scorecard.txt"

with sync_playwright() as p:
    # Launch installed Google Chrome
    browser = p.chromium.launch(
        channel="chrome",
        headless=False
    )

    try:
        page = browser.new_page(
            viewport={"width": 1440, "height": 900}
        )

        # Open Google, then Cricbuzz
        page.goto("https://www.google.com", wait_until="load")
        page.goto("https://www.cricbuzz.com", wait_until="load")

        # Open today's match scorecard
        page.goto(SCORECARD_URL, wait_until="load")

        # Wait until the scorecard heading is visible
        page.get_by_role(
            "heading",
            name="India vs Sri Lanka",
            exact=False
        ).first.wait_for(state="visible", timeout=30000)

        # Save a full-page screenshot
        page.screenshot(
            path=str(screenshot_file),
            full_page=True
        )

        # Read and save the visible page text
        scorecard_text = page.locator("body").inner_text()
        text_file.write_text(scorecard_text, encoding="utf-8")

        print(scorecard_text)
        print(f"\nScreenshot saved: {screenshot_file}")
        print(f"Scorecard text saved: {text_file}")

    finally:
        browser.close()