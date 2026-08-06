"""OSS NIB lookup via Browserbase + Playwright (no LLM)."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("kyb.automation")

OSS_URL = "https://oss.go.id/id"

# Label text as shown on oss.go.id modal → our registry field keys
_LABEL_MAP = {
    "NIB": "nib",
    "Nama Perusahaan": "nama_perusahaan",
    "Status Aktif": "status_aktif",
    "Status Migrasi": "status_migrasi",
    "Penanaman Modal": "penanaman_modal",
    "Skala Usaha": "skala_usaha",
}


def browserbase_configured() -> bool:
    return bool(os.environ.get("BROWSERBASE_API_KEY") and os.environ.get("BROWSERBASE_PROJECT_ID"))


def _dismiss_announcements(page) -> None:
    """
    Close the PEMBERITAHUAN carousel that always appears on oss.go.id/id.
    Close control is a Material Icons span with text "close" (top-right of popup).
    """
    # Wait briefly for the fixed overlay to mount
    try:
        page.wait_for_selector(
            'div.fixed.left-0.top-0 span.material-icons',
            timeout=8000,
            state="visible",
        )
    except Exception:
        pass

    def _overlay_visible() -> bool:
        try:
            return bool(page.evaluate(
                """() => {
                  return Array.from(document.querySelectorAll('div.fixed')).some((el) => {
                    const cls = el.className || '';
                    if (!cls.includes('z-[9999]')) return false;
                    const s = getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden' && el.offsetParent !== null;
                  });
                }"""
            ))
        except Exception:
            return False

    # Click visible close icon on the announcement carousel
    for _ in range(3):
        if not _overlay_visible():
            break
        try:
            close_icon = page.locator('span.material-icons.cursor-pointer:text-is("close")').first
            if not close_icon.is_visible(timeout=1500):
                close_icon = page.locator('span.material-icons:has-text("close")').first
            if close_icon.is_visible(timeout=800):
                close_icon.click(timeout=3000, force=True)
                page.wait_for_timeout(500)
        except Exception:
            break

    # Fallback selectors
    if _overlay_visible():
        for sel in (
            'span.material-icons.absolute.right-0.top-0',
            'button:has-text("Tutup")',
            'button[aria-label="Close"]',
            'button[aria-label="close"]',
        ):
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=800):
                    loc.click(timeout=2000, force=True)
                    page.wait_for_timeout(400)
                    if not _overlay_visible():
                        break
            except Exception:
                continue

    # Last resort: remove overlay so Cari NIB is interactable
    if _overlay_visible():
        try:
            page.evaluate(
                """() => {
                  document.querySelectorAll('div.fixed').forEach((el) => {
                    const cls = el.className || '';
                    if (cls.includes('z-[9999]')) el.remove();
                  });
                }"""
            )
        except Exception:
            pass


def _extract_modal_fields(page) -> dict:
    """Parse key/value rows inside Detail Data Pelaku Usaha modal."""
    page.wait_for_selector("text=Detail Data Pelaku Usaha", timeout=30000)
    rows = page.locator("div.flex.justify-between.gap-4")
    rows.first.wait_for(state="visible", timeout=15000)
    data: dict = {}
    count = rows.count()
    for i in range(count):
        row = rows.nth(i)
        try:
            label = (row.locator("span.font-bold").first.text_content() or "").strip()
            value = (row.locator("span.truncate").first.text_content() or "").strip()
        except Exception:
            continue
        if not label:
            continue
        key = _LABEL_MAP.get(label)
        if key:
            data[key] = value
        else:
            data[label] = value
    return data


def run_oss_nib_lookup(nib: str) -> dict:
    """
    Search NIB on oss.go.id and return structured registry data from the result modal.
    Requires BROWSERBASE_API_KEY and BROWSERBASE_PROJECT_ID.
    """
    nib = "".join(ch for ch in (nib or "") if ch.isdigit())
    if not nib:
        return {"success": False, "error": "NIB kosong", "source": "oss.go.id"}

    if not browserbase_configured():
        return {
            "success": False,
            "error": "Browserbase belum dikonfigurasi",
            "source": "oss.go.id",
        }

    from browserbase import Browserbase
    from playwright.sync_api import sync_playwright

    bb = Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])
    session = bb.sessions.create(project_id=os.environ["BROWSERBASE_PROJECT_ID"])
    session_id = getattr(session, "id", None)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(session.connect_url)
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(OSS_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1200)
            _dismiss_announcements(page)

            search = page.locator('input[placeholder="Cari NIB"]')
            search.wait_for(state="visible", timeout=20000)
            # Scroll footer search into view (Pencarian NIB sits at bottom)
            search.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            search.click()
            search.fill(nib)

            # Prefer the dedicated search button; fall back to Enter
            btn = page.get_by_role("button", name="Cari NIB")
            if btn.count() and btn.first.is_visible():
                btn.first.click()
            else:
                search.press("Enter")

            fields = _extract_modal_fields(page)
            if not fields.get("nib") and not fields.get("nama_perusahaan"):
                return {
                    "success": False,
                    "error": "Modal hasil NIB tidak berisi data yang diharapkan",
                    "source": "oss.go.id",
                    "raw": fields,
                    "session_id": session_id,
                }

            status_aktif = fields.get("status_aktif") or ""
            return {
                "success": True,
                "source": "oss.go.id",
                "found": True,
                "status": status_aktif or fields.get("status_migrasi") or "DITEMUKAN",
                "nib": fields.get("nib") or nib,
                "nama_perusahaan": fields.get("nama_perusahaan") or "",
                "status_aktif": status_aktif,
                "status_migrasi": fields.get("status_migrasi") or "",
                "penanaman_modal": fields.get("penanaman_modal") or "",
                "skala_usaha": fields.get("skala_usaha") or "",
                "session_id": session_id,
            }
        except Exception as err:
            logger.exception("OSS NIB lookup failed")
            try:
                page.screenshot(path=f"/tmp/oss-nib-error-{session_id or 'unknown'}.png")
            except Exception:
                pass
            return {
                "success": False,
                "error": str(err),
                "source": "oss.go.id",
                "found": False,
                "session_id": session_id,
            }
        finally:
            try:
                browser.close()
            except Exception:
                pass


def registry_from_oss_result(result: dict) -> dict:
    """Normalize Browserbase result into validation.nib.registry shape."""
    if not result:
        return {
            "source": "oss.go.id",
            "found": False,
            "status": "GAGAL",
            "lookup_status": "failed",
            "error": "Hasil kosong",
        }
    if not result.get("success"):
        return {
            "source": result.get("source") or "oss.go.id",
            "found": False,
            "status": "GAGAL",
            "lookup_status": "failed",
            "error": result.get("error") or "Lookup gagal",
            "session_id": result.get("session_id"),
        }
    return {
        "source": "oss.go.id",
        "found": True,
        "status": result.get("status_aktif") or result.get("status") or "DITEMUKAN",
        "lookup_status": "done",
        "nib": result.get("nib") or "",
        "nama_perusahaan": result.get("nama_perusahaan") or "",
        "status_aktif": result.get("status_aktif") or "",
        "status_migrasi": result.get("status_migrasi") or "",
        "penanaman_modal": result.get("penanaman_modal") or "",
        "skala_usaha": result.get("skala_usaha") or "",
        "session_id": result.get("session_id"),
    }


def run_automation_job(input_data: dict) -> dict:
    """Celery-compatible entry: expects {\"nib\": \"...\"}."""
    return run_oss_nib_lookup((input_data or {}).get("nib") or "")
