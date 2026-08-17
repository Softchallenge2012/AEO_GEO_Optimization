import asyncio
import json
from playwright.async_api import async_playwright

async def scrape_device_specs(page, url: str) -> dict:
    """Navigates to an individual device page and extracts technical specifications."""
    print(f"Navigating to: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # Wait for primary content container to render
        await page.wait_for_selector("body", timeout=15000)

        # Scroll down to trigger lazy loading of specification sections/accordions
        await page.mouse.wheel(0, 1000)
        await page.wait_for_timeout(1500)

        # Look for expandable "Specs" accordions and click them open if present
        await page.evaluate('''() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            buttons.forEach(btn => {
                const text = (btn.innerText || btn.textContent || '').trim();
                const ariaControls = btn.getAttribute('aria-controls') || '';
                if (ariaControls.toLowerCase().includes('spec') || /specs|specifications/i.test(text)) {
                    try { btn.click(); } catch(e) {}
                }
            });
        }''')
        await page.wait_for_timeout(1000)

        # Extract structured spec text and key-value details from DOM
        device_data = await page.evaluate('''() => {
            const title = document.querySelector('h1')?.innerText.trim() || '';
            const specs = {};

            // Target spec tables, cards, or definition lists
            const specContainers = document.querySelectorAll('[id*="spec"], [class*="spec"], [aria-label*="spec"], section');

            specContainers.forEach((container, idx) => {
                const text = container.innerText.trim();
                if (text.length > 20 && (text.includes(':') || text.includes('\\n'))) {
                    specs[`section_${idx}`] = text;
                }
            });

            // Fallback: collect all key specs listed on the page body
            if (Object.keys(specs).length === 0) {
                specs['full_page_text'] = document.body.innerText.slice(0, 4000);
            }

            return {
                title: title,
                specs: specs
            };
        }''')

        return {
            "url": url,
            "title": device_data.get("title"),
            "specs": device_data.get("specs"),
            "status": "success"
        }

    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return {
            "url": url,
            "status": "error",
            "error_message": str(e)
        }

async def main():
    # Load previously extracted catalog URLs or provide fallback target list
    try:
        with open("tmobile_phone_specs.json", "r", encoding="utf-8") as f:
            catalog_data = json.load(f)
            urls = [item["url"] for item in catalog_data if "url" in item]
    except FileNotFoundError:
        print("Catalog file not found. Using sample URLs...")
        urls = [
            "https://www.t-mobile.com/cell-phone/samsung-galaxy-z-fold8",
            "https://www.t-mobile.com/cell-phone/google-pixel-11-pro-xl",
            "https://www.t-mobile.com/cell-phone/apple-iphone-17-pro-max"
        ]

    all_specs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        print(f"Starting detailed extraction for {len(urls)} device pages...\n")

        for idx, url in enumerate(urls, start=1):
            print(f"[{idx}/{len(urls)}]")
            result = await scrape_device_specs(page, url)
            all_specs.append(result)

            # Politeness delay between requests to avoid rate limiting
            delay_seconds = 3
            print(f"Waiting {delay_seconds} seconds before the next page...\n")
            await page.wait_for_timeout(delay_seconds * 1000)

        await browser.close()

    # Save all detailed specifications into a JSON file
    output_filename = "tmobile_detailed_specs.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(all_specs, f, indent=2)

    print(f"Extraction complete! Saved specifications for {len(all_specs)} devices to '{output_filename}'.")

if __name__ == "__main__":
    asyncio.run(main())