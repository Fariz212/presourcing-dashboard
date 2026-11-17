"""Browser-driven visual preview for the KHS dashboard.

Runs only in GitHub Actions against a disposable database populated with
synthetic data. Screenshots and a self-contained HTML gallery are written
to artifacts/visual-preview.
"""

from __future__ import annotations

import json
import os
import re
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
    ("requests", "mobile", 390, 844),
    ("register", "desktop", 1440, 1000),
    ("register", "mobile", 390, 844),
    ("lp", "desktop", 1440, 1000),
    ("lp", "mobile", 390, 844),
    ("contracts", "desktop", 1440, 1000),
    ("workflow", "desktop", 1440, 1000),
    ("workflow", "mobile", 390, 844),
    ("contracts", "mobile", 390, 844),
    ("imports", "desktop", 1440, 1000),
    ("imports", "mobile", 390, 844),
    ("activity", "desktop", 1440, 1000),
    ("activity", "mobile", 390, 844),
]




def assert_stage_and_age(page, body_id, khs_id, stage_text, expected_age_text,
                         stage_cell_index, age_cell_index):
    row = page.locator(f"#{body_id} tr").filter(has_text=khs_id).first
    row.wait_for(state="visible", timeout=15_000)
    cells = row.locator("td")
    actual_stage = cells.nth(stage_cell_index).inner_text()
    actual_age = cells.nth(age_cell_index).inner_text()
    if stage_text not in actual_stage:
        raise AssertionError(
            f"{body_id} {khs_id}: expected stage {stage_text!r}, got {actual_stage!r}"
        )
    age_match = re.search(r"\b\d+ days? in stage\b", actual_age)
    if not age_match:
        raise AssertionError(
            f"{body_id} {khs_id}: expected a numeric stage age, got {actual_age!r}"
        )
    if expected_age_text is not None and age_match.group(0) != expected_age_text:
        raise AssertionError(
            f"{body_id} {khs_id}: expected age {expected_age_text!r}, got {age_match.group(0)!r}"
        )
    return age_match.group(0)


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
                page.set_viewport_size({"width": width, "height": height})
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
                    if width <= 760:
                        page.locator("#mobileNavToggle").click(timeout=10_000)
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

                if page_name == "overview" and viewport_name == "mobile":
                    total_attention_rows = page.locator("#attentionBody tr").count()
                    visible_attention_rows = page.locator("#attentionBody tr:visible").count()
                    if total_attention_rows > 3 and visible_attention_rows != 3:
                        raise AssertionError(
                            f"Mobile priority queue should show three rows, found {visible_attention_rows}"
                        )

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
                        ),
                        tableOverflows: Array.from(document.querySelectorAll(".table-wrap"))
                            .filter((element) => element.scrollWidth > element.clientWidth + 3)
                            .map((element) => ({
                                className: element.className,
                                scrollWidth: element.scrollWidth,
                                clientWidth: element.clientWidth
                            }))
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
                if width <= 760 and dimensions.get("tableOverflows"):
                    overflow_warnings.append({
                        "page": page_name,
                        "viewport": viewport_name,
                        "responsive_table_overflow": dimensions["tableOverflows"],
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

        # Verify the mobile navigation exposes every page without horizontal menu hunting.
        try:
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator("#mobileNavToggle").click(timeout=10_000)
            page.locator('#dataSideNav a[data-page="activity"]').wait_for(state="visible", timeout=10_000)
            page.locator('#primarySideNav a[data-page="workflow"]').wait_for(state="visible", timeout=10_000)
            page.locator("#mobileNavToggle").click(timeout=10_000)
            if page.locator("#dataSideNav a[data-page='activity']:visible").count() != 0:
                raise AssertionError("Mobile navigation did not collapse after closing the menu")
        except Exception as error:
            capture_errors.append(f"Mobile navigation interaction: {error}")
            print(f"FAILED mobile navigation interaction: {error}")

        # Verify workflow stage summaries open the matching KHS Register filter.
        try:
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator("#mobileNavToggle").click(timeout=10_000)
            page.locator('a.nav-link[data-page="workflow"]').first.click(timeout=10_000)
            current_page = "workflow"
            page.locator("#page-workflow.active").wait_for(state="visible", timeout=15_000)
            default_stage_count = page.locator("#workflowCards [data-workflow-stage]").count()
            if default_stage_count == 0:
                raise AssertionError("Workflow should show stages that currently contain records")
            stage_toggle = page.locator("#workflowEmptyToggle")
            if stage_toggle.is_visible():
                default_summary = page.locator("#workflowStageSummary").inner_text()
                if "stages have records" not in default_summary:
                    raise AssertionError(f"Workflow occupancy summary is unclear: {default_summary}")
                stage_toggle.click(timeout=10_000)
                expanded_stage_count = page.locator("#workflowCards [data-workflow-stage]").count()
                if expanded_stage_count <= default_stage_count:
                    raise AssertionError("Showing empty stages did not expand the workflow")
                if stage_toggle.get_attribute("aria-expanded") != "true":
                    raise AssertionError("Empty-stage toggle did not expose its expanded state")
                stage_toggle.click(timeout=10_000)
                collapsed_stage_count = page.locator("#workflowCards [data-workflow-stage]").count()
                if collapsed_stage_count != default_stage_count:
                    raise AssertionError("Workflow empty stages did not collapse back to the occupied stages")

            stage_card = page.locator("#workflowCards [data-workflow-stage]").first
            stage_card.wait_for(state="visible", timeout=15_000)
            stage_card.click(timeout=10_000)
            current_page = "register"
            page.locator("#page-register.active").wait_for(state="visible", timeout=15_000)
            page.wait_for_load_state("networkidle", timeout=20_000)
            page.locator("#registerBody tr").first.wait_for(state="visible", timeout=15_000)
            page.locator("#activeRegisterFilters:not([hidden])").wait_for(
                state="visible", timeout=15_000
            )
            page.locator("#resetFilters").click(timeout=10_000)
            page.wait_for_load_state("networkidle", timeout=20_000)
            page.locator('#registerBody [data-view-khs="KHS-VIS-004"]').wait_for(
                state="visible", timeout=15_000
            )

            # The register must show overall workflow stages before LP and
            # after LP, while retaining the fine-grained LP stage during LP.
            page.set_viewport_size({"width": 1440, "height": 1000})
            mi_gm_age = assert_stage_and_age(
                page, "registerBody", "KHS-VIS-002",
                "MI Approval - GM", None, 1, 1,
            )
            injection_age = assert_stage_and_age(
                page, "registerBody", "KHS-VIS-009",
                "KHS Inject", None, 1, 1,
            )

            # The priority queue must use the same workflow stage and age
            # derivation, including a record that has completed LP but not injection.
            page.locator('a.nav-link[data-page="overview"]').first.click(timeout=10_000)
            current_page = "overview"
            page.locator("#page-overview.active").wait_for(state="visible", timeout=15_000)
            page.wait_for_load_state("networkidle", timeout=20_000)
            assert_stage_and_age(
                page, "attentionBody", "KHS-VIS-002",
                "MI Approval - GM", mi_gm_age, 2, 4,
            )
            assert_stage_and_age(
                page, "attentionBody", "KHS-VIS-009",
                "KHS Inject", injection_age, 2, 4,
            )

            page.locator('a.nav-link[data-page="register"]').first.click(timeout=10_000)
            current_page = "register"
            page.locator("#page-register.active").wait_for(state="visible", timeout=15_000)
            page.wait_for_load_state("networkidle", timeout=20_000)
            page.locator('#registerBody [data-view-khs="KHS-VIS-004"]').wait_for(
                state="visible", timeout=15_000
            )
        except Exception as error:
            capture_errors.append(f"Workflow stage drilldown: {error}")
            print(f"FAILED workflow stage drilldown: {error}")

        # Capture the interaction surfaces that carry the LP workflow:
        # the KHS detail journey and the grouped KHS form.
        try:
            if current_page != "register":
                page.locator('a.nav-link[data-page="register"]').first.click(timeout=10_000)
                current_page = "register"
            page.locator("#page-register.active").wait_for(state="visible", timeout=15_000)
            page.wait_for_load_state("networkidle", timeout=20_000)

            # Use a synthetic record with three completed milestones and an
            # active Senior Manager approval stage, so Current Stage, Stage
            # Age, and Upcoming are exercised rather than showing a not-started LP.
            detail_button = page.locator('#registerBody [data-view-khs="KHS-VIS-004"]')
            detail_button.wait_for(state="visible", timeout=15_000)
            detail_button.click(timeout=10_000)
            page.locator("#detailDialog[open]").wait_for(state="visible", timeout=10_000)
            page.locator("#lpTimeline .lp-timeline-item").first.wait_for(state="visible", timeout=10_000)

            current_stage = page.locator("#lpCurrentStage").inner_text()
            stage_age = page.locator("#lpStageAge").inner_text()
            upcoming_stage = page.locator("#lpUpcomingStage").inner_text()
            if "Senior Manager Strategic Sourcing" not in current_stage:
                raise AssertionError(f"Unexpected Current Stage: {current_stage}")
            if "day" not in stage_age.lower():
                raise AssertionError(f"Stage Age is not displayed: {stage_age}")
            if "GM SCM" not in upcoming_stage:
                raise AssertionError(f"Unexpected Upcoming stage: {upcoming_stage}")
            if page.locator("#lpTimeline .lp-timeline-item.current").count() != 1:
                raise AssertionError("Expected exactly one current LP stage marker")

            def capture_dialog(name: str, viewport_name: str, width: int, height: int) -> None:
                page.set_viewport_size({"width": width, "height": height})
                page.wait_for_timeout(300)
                file_name = f"{name}-{viewport_name}.png"
                target = OUTPUT_DIR / file_name
                page.screenshot(path=str(target), full_page=False, animations="disabled")
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
                        "page": name,
                        "viewport": viewport_name,
                        "horizontal_overflow_px": overflow,
                        "dimensions": dimensions,
                    })
                captures.append({
                    "page": name,
                    "viewport": viewport_name,
                    "width": width,
                    "height": height,
                    "file": file_name,
                    "document_width": dimensions["documentWidth"],
                    "document_height": dimensions["documentHeight"],
                    "horizontal_overflow_px": max(0, overflow),
                })
                print(f"Captured {file_name}")

            capture_dialog("khs-detail", "desktop", 1440, 1000)
            capture_dialog("khs-detail", "mobile", 390, 844)
            page.locator("#closeDialog").click()
            page.locator("#detailDialog").wait_for(state="hidden", timeout=10_000)

            page.set_viewport_size({"width": 1440, "height": 1000})
            page.locator("#createKhsButton").click(timeout=10_000)
            page.locator("#recordDialog[open]").wait_for(state="visible", timeout=10_000)
            lp_form_section = page.locator("#dialogFields .form-section-lp-circulation")
            lp_form_section.wait_for(state="visible", timeout=10_000)
            lp_form_section.scroll_into_view_if_needed()
            capture_dialog("khs-form", "desktop", 1440, 1000)
            capture_dialog("khs-form", "mobile", 390, 844)
            page.locator("#cancelRecord").click()
        except Exception as error:
            capture_errors.append(f"KHS detail/form interaction captures: {error}")
            print(f"FAILED KHS detail/form interaction captures: {error}")

        try:
            # Use desktop navigation for this interaction check; mobile navigation
            # is intentionally collapsed until its menu toggle is opened.
            page.set_viewport_size({"width": 1440, "height": 1000})
            # Verify both languages on real, API-backed pages and persist the choice.
            page.goto(f"{BASE_URL}/dashboard", wait_until="networkidle", timeout=45_000)
            language_button = page.locator("#languageToggle")
            language_button.wait_for(state="visible", timeout=10_000)
            language_button.click()
            page.wait_for_function("document.documentElement.lang === 'id'", timeout=10_000)
            overview_nav = page.locator('a.nav-link[data-page="overview"]')
            if "Pemantauan Kontrak" not in overview_nav.inner_text():
                raise AssertionError("Bahasa Indonesia did not translate the overview navigation.")
            page.locator('a.nav-link[data-page="requests"]').click()
            page.locator("#page-requests.active h1").wait_for(state="visible", timeout=10_000)
            if page.locator("#page-requests h1").inner_text() != "Manajemen Permintaan":
                raise AssertionError("Bahasa Indonesia did not translate the Request Management page.")
            if page.locator("#requestSearch").get_attribute("placeholder") != "Cari subjek, vendor, atau PIC…":
                raise AssertionError("Bahasa Indonesia did not translate the request search placeholder.")
            page.reload(wait_until="networkidle", timeout=45_000)
            page.wait_for_function("document.documentElement.lang === 'id'", timeout=10_000)
            if page.locator("#languageToggle").inner_text() != "EN":
                raise AssertionError("Language preference did not persist after reload.")
            page.locator('a.nav-link[data-page="register"]').click()
            page.locator("#page-register.active h1").wait_for(state="visible", timeout=10_000)
            if page.locator("#page-register h1").inner_text() != "Daftar KHS":
                raise AssertionError("Bahasa Indonesia did not translate the KHS Register.")
            detail_row = page.locator("#registerBody tr").filter(has_text="KHS-VIS-002").first
            detail_row.wait_for(state="visible", timeout=15_000)
            detail_row.locator('[data-view-khs="KHS-VIS-002"]').click()
            page.locator("#detailDialog[open]").wait_for(state="visible", timeout=10_000)
            if page.locator("#processDurationTitle").inner_text() != "Riwayat Durasi Proses":
                raise AssertionError("Bahasa Indonesia did not translate process-duration detail content.")
            if page.locator("#closeKhsButton").inner_text() != "Tutup KHS":
                raise AssertionError("Bahasa Indonesia did not translate the KHS closure action.")
            page.locator("#closeKhsButton").click()
            page.locator("#closureDialog[open]").wait_for(state="visible", timeout=10_000)
            if page.locator("#closureDialog h2").inner_text() != "Tutup KHS sebagai Tidak Dilanjutkan":
                raise AssertionError("Bahasa Indonesia did not translate the closure dialog.")
            if page.locator('#closureReason option[value="NO_MUTUAL_AGREEMENT"]').inner_text() != "Tidak tercapai kesepakatan":
                raise AssertionError("Bahasa Indonesia did not translate closure-reason options.")
            page.locator("#cancelClosure").click()
            page.locator("#closeDialog").click()
            page.locator("#languageToggle").click()
            page.wait_for_function("document.documentElement.lang === 'en'", timeout=10_000)
            if page.locator("#page-register h1").inner_text() != "KHS Register":
                raise AssertionError("Switching back to English did not restore the original text.")
            print("Bilingual browser check passed: navigation, API-backed detail, closure dialog, placeholder, and preference persistence.")

            # End-to-end workbench: advance one milestone, schedule a follow-up,
            # complete it, then verify the workflow aging/SLA analytics load.
            detail_row = page.locator("#registerBody tr").filter(has_text="KHS-VIS-002").first
            detail_row.locator('[data-view-khs="KHS-VIS-002"]').click()
            page.locator("#detailDialog[open]").wait_for(state="visible", timeout=10_000)
            progress_button = page.locator("#updateProgressButton")
            progress_button.wait_for(state="visible", timeout=10_000)
            progress_button.click()
            page.locator("#progressDialog[open]").wait_for(state="visible", timeout=10_000)
            if page.locator("#progressMilestoneLabel").input_value() != "MI Senior Manager approval recorded":
                raise AssertionError("Guided progress did not select the next MI Senior Manager milestone.")
            jakarta_today = page.evaluate(
                "() => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Jakarta',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())"
            )
            page.locator("#progressMilestoneDate").fill(jakarta_today)
            page.locator("#progressNote").fill("Synthetic CI guided-progress validation.")
            with page.expect_response(lambda response: "/progress" in response.url and response.request.method == "POST") as progress_response:
                page.locator("#confirmProgress").click()
            if progress_response.value.status != 200:
                raise AssertionError(f"Guided progress returned {progress_response.value.status}.")
            page.locator("#progressDialog").wait_for(state="hidden", timeout=10_000)
            page.locator("#detailDialog[open]").wait_for(state="visible", timeout=10_000)
            if not page.locator("#updateProgressButton").inner_text().startswith("Update: MI GM approval recorded"):
                raise AssertionError("Guided progress did not advance to the next MI GM milestone.")

            page.locator("#followUpDueDate").fill(jakarta_today)
            page.locator("#followUpTo").fill("CI Operations Owner")
            page.locator("#followUpNote").fill("Synthetic CI follow-up validation.")
            with page.expect_response(lambda response: "/follow-ups" in response.url and response.request.method == "POST") as followup_response:
                page.locator("#saveFollowUpButton").click()
            if followup_response.value.status != 201:
                raise AssertionError(f"Follow-up scheduling returned {followup_response.value.status}.")
            page.locator("#followUpList").get_by_text("Synthetic CI follow-up validation.").wait_for(timeout=10_000)
            complete_followup = page.locator("#followUpList [data-complete-followup]").first
            with page.expect_response(lambda response: "/complete" in response.url and response.request.method == "POST") as completed_response:
                complete_followup.click()
            if completed_response.value.status != 200:
                raise AssertionError(f"Follow-up completion returned {completed_response.value.status}.")
            page.locator("#followUpList").get_by_text("COMPLETED").wait_for(timeout=10_000)
            page.locator("#closeDialog").click()

            page.locator('a.nav-link[data-page="workflow"]').click()
            page.locator("#page-workflow.active").wait_for(state="visible", timeout=10_000)
            page.locator("#operationsStageBody tr").first.wait_for(state="visible", timeout=15_000)
            if page.locator("#slaConfigurationStatus").inner_text() != "SLA not configured":
                raise AssertionError("Unconfigured SLA thresholds were incorrectly presented as approved.")
            if page.locator("#opsActiveWip").inner_text() in ("—", ""):
                raise AssertionError("WIP analytics did not return an active WIP total.")
            print("Operations browser check passed: guided milestone, assigned follow-up, completion, WIP aging, and safe unconfigured-SLA state.")
        except Exception as error:
            capture_errors.append(f"Bilingual language switch interaction: {error}")
            print(f"FAILED bilingual language switch interaction: {error}")

        browser.close()

    report = {
        "base_url": BASE_URL,
        "generated_at_unix": int(time()),
        "capture_count": len(captures),
        "expected_capture_count": len(CAPTURES) + 4,
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
    if len(captures) != len(CAPTURES) + 4:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
