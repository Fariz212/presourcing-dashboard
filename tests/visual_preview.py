"""Browser-driven visual preview for the KHS dashboard.

Runs only in GitHub Actions against a disposable database populated with
synthetic data. Screenshots and a self-contained HTML gallery are written
to artifacts/visual-preview.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from time import time

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("VISUAL_PREVIEW_URL", "http://127.0.0.1:8000").rstrip("/")
OUTPUT_DIR = Path(os.environ.get("VISUAL_PREVIEW_OUTPUT", "artifacts/visual-preview"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CAPTURES = [
    ("overview", "desktop", 1440, 1000),
    ("overview", "tablet", 1024, 900),
    ("overview", "mobile", 390, 844),
    ("requests", "desktop", 1440, 1000),
    ("register", "desktop", 1440, 1000),
    ("register", "mobile", 390, 844),
    ("lp", "desktop", 1440, 1000),
    ("lp", "mobile", 390, 844),
    ("contracts", "desktop", 1440, 1000),
    ("workflow", "desktop", 1440, 1000),
    ("imports", "desktop", 1440, 1000),
    ("activity", "desktop", 1440, 1000),
]


def main() -> int:
    api_failures: list[dict[str, object]] = []
    page_errors: list[str] = []
    console_errors: list[str] = []
    capture_errors: list[str] = []
    captures: list[dict[str, object]] = []
    overflow_warnings: list[dict[str, object]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1440, "height": 1000},
            device_scale_factor=1,
            reduced_motion="reduce",
        )

        def inspect_response(response) -> None:
            if "/api/" in response.url and response.status >= 400:
                api_failures.append({
                    "status": response.status,
                    "url": response.url,
                })

        page.on("response", inspect_response)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )

        current_page: str | None = None

        for page_name, viewport_name, width, height in CAPTURES:
            file_name = f"{page_name}-{viewport_name}.png"
            target = OUTPUT_DIR / file_name
            try:
                if current_page is None:
                    response = page.goto(
                        f"{BASE_URL}/dashboard",
                        wait_until="networkidle",
                        timeout=45_000,
                    )
                    if response is None or response.status != 200:
                        status = response.status if response is not None else "no response"
                        raise RuntimeError(f"Dashboard returned {status}")
                    current_page = "overview"
                elif page_name != current_page:
                    navigation_link = page.locator(
                        f'a.nav-link[data-page="{page_name}"]'
                    ).first
                    navigation_link.click(timeout=10_000)
                    current_page = page_name

                active_view = page.locator(f"#page-{page_name}.active")
                active_view.wait_for(state="visible", timeout=15_000)
                page.wait_for_load_state("networkidle", timeout=20_000)
                page.set_viewport_size({"width": width, "height": height})
                page.wait_for_timeout(500)

                dimensions = page.evaluate(
                    """() => ({
                        viewportWidth: window.innerWidth,
                        documentWidth: Math.max(
                            document.documentElement.scrollWidth,
                            document.body.scrollWidth
                        ),
                        documentHeight: Math.max(
                            document.documentElement.scrollHeight,
                            document.body.scrollHeight
                        )
                    })"""
                )
                overflow = int(dimensions["documentWidth"]) - int(dimensions["viewportWidth"])
                if overflow > 3:
                    overflow_warnings.append({
                        "page": page_name,
                        "viewport": viewport_name,
                        "horizontal_overflow_px": overflow,
                        "dimensions": dimensions,
                    })

                page.screenshot(
                    path=str(target),
                    full_page=True,
                    animations="disabled",
                )
                captures.append({
                    "page": page_name,
                    "viewport": viewport_name,
                    "width": width,
                    "height": height,
                    "file": file_name,
                    "document_width": dimensions["documentWidth"],
                    "document_height": dimensions["documentHeight"],
                    "horizontal_overflow_px": max(0, overflow),
                })
                print(f"Captured {file_name}")
            except Exception as error:
                capture_errors.append(f"{file_name}: {error}")
                print(f"FAILED {file_name}: {error}")

        browser.close()

    report = {
        "base_url": BASE_URL,
        "generated_at_unix": int(time()),
        "capture_count": len(captures),
        "expected_capture_count": len(CAPTURES),
        "captures": captures,
        "api_failures": api_failures,
        "uncaught_page_errors": page_errors,
        "console_errors": console_errors,
        "capture_errors": capture_errors,
        "responsive_overflow_warnings": overflow_warnings,
    }
    (OUTPUT_DIR / "visual-preview-report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "browser-console.log").write_text(
        "\n".join(
            ["=== Console errors ===", *console_errors,
             "", "=== Uncaught page errors ===", *page_errors,
             "", "=== API failures ===",
             *[f'{item["status"]} {item["url"]}' for item in api_failures],
             "", "=== Capture errors ===", *capture_errors]
        ),
        encoding="utf-8",
    )

    gallery_items = "\n".join(
        (
            f'<article><h2>{item["page"].title()} · {item["viewport"].title()}</h2>'
            f'<p>{item["width"]} × {item["height"]} viewport · '
            f'{item["document_width"]} px document width · '
            f'{item["horizontal_overflow_px"]} px horizontal overflow</p>'
            f'<a href="{item["file"]}"><img loading="lazy" src="{item["file"]}" '
            f'alt="{item["page"]} {item["viewport"]} screenshot"></a></article>'
        )
        for item in captures
    )
    gallery = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KHS Visual Preview</title>
<style>
:root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
body {{ margin: 0; padding: 32px; background: #f5f3ed; color: #1f382e; }}
header {{ max-width: 1200px; margin: 0 auto 28px; }}
h1 {{ margin: 0 0 8px; font-size: clamp(28px, 4vw, 42px); }}
header p {{ color: #657268; margin: 0; }}
main {{ max-width: 1200px; margin: 0 auto; display: grid; grid-template-columns: repeat(auto-fit,minmax(320px,1fr)); gap: 22px; }}
article {{ min-width: 0; padding: 16px; border-radius: 16px; background: white; box-shadow: 0 8px 28px #20392b12; }}
h2 {{ font-size: 16px; margin: 0 0 6px; }}
article p {{ margin: 0 0 12px; font-size: 12px; color: #68766d; }}
img {{ display: block; width: 100%; height: auto; border: 1px solid #e8e7e0; border-radius: 9px; }}
@media (max-width: 600px) {{ body {{ padding: 16px; }} main {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<header>
<h1>KHS · Visual Preview</h1>
<p>{len(captures)} browser captures · Synthetic CI data · Not connected to production</p>
</header>
<main>{gallery_items}</main>
</body>
</html>"""
    (OUTPUT_DIR / "index.html").write_text(gallery, encoding="utf-8")

    print(json.dumps({
        "captures": len(captures),
        "api_failures": len(api_failures),
        "page_errors": len(page_errors),
        "capture_errors": len(capture_errors),
        "responsive_overflow_warnings": len(overflow_warnings),
    }, indent=2))

    if api_failures or page_errors or capture_errors:
        return 1
    if len(captures) != len(CAPTURES):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
