import asyncio
import json
import pandas as pd
from playwright.async_api import async_playwright

async def scrape_tmobile_catalog():
    target_url = "https://www.t-mobile.com/cell-phones"
    
    async with async_playwright() as p:
        # Launch browser with a standard Desktop User-Agent
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

        print(f"Loading {target_url}...")
        await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

        # Wait for product grid elements to load
        await page.wait_for_selector("a[href*='/cell-phone/']", timeout=15000)

        # Scroll down incrementally to trigger lazy-loaded product cards
        for _ in range(8):
            await page.mouse.wheel(0, 1500)
            await page.wait_for_timeout(1000)

        # Extract structured data from DOM context
        extracted_devices = await page.evaluate('''() => {
            const devices = [];
            // Target all links pointing to individual cell phone detail pages
            const productLinks = document.querySelectorAll('a[href*="/cell-phone/"]');

            productLinks.forEach(link => {
                const href = link.getAttribute('href');
                const fullUrl = href.startsWith('http') ? href : 'https://www.t-mobile.com' + href;
                
                // Get all text blocks within the product card
                const lines = link.innerText
                    .split('\\n')
                    .map(s => s.trim())
                    .filter(s => s.length > 0);

                if (lines.length > 0) {
                    devices.push({
                        url: fullUrl,
                        raw_card_info: lines
                    });
                }
            });

            // Deduplicate by URL
            const uniqueDevices = [];
            const seenUrls = new Set();
            for (const item of devices) {
                if (!seenUrls.has(item.url)) {
                    seenUrls.add(item.url);
                    uniqueDevices.push(item);
                }
            }

            return uniqueDevices;
        }''')

        await browser.close()
        return extracted_devices

async def main():
    devices = await scrape_tmobile_catalog()
    print(f"Successfully scraped {len(devices)} unique phone listings.\n")

    # Save output to JSON
    with open("tmobile_phone_specs.json", "w", encoding="utf-8") as f:
        json.dump(devices, f, indent=2)

    print("Data saved to 'tmobile_phone_specs.json'")

if __name__ == "__main__":
    asyncio.run(main())