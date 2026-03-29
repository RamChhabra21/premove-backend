#!/usr/bin/env python3
"""Playwright Engine for model_actions() - converts and executes browser actions."""
import json
import re
import asyncio
from typing import Optional, Dict, Any, List, Union
from playwright.async_api import async_playwright, Page, BrowserContext


# ---------------------------------------------------------------------------
# Selector helpers
# ---------------------------------------------------------------------------

def extract_selector_from_interacted_element(interacted_element: Any) -> Optional[Dict[str, str]]:
    """Extract selectors from interacted_element, prioritizing id > xpath > href > other attributes."""
    if not interacted_element:
        return None

    selector_info = {}
    if isinstance(interacted_element, str):
        for pattern, key in [
            (r"'id':\s*'([^']+)'", "id"),
            (r"x_path='([^']+)'", "xpath"),
            (r"'href':\s*'([^']+)'", "href"),
            (r"node_name='([^']+)'", "node_name"),
        ]:
            if match := re.search(pattern, interacted_element):
                selector_info[key] = match.group(1)

        if attrs_match := re.search(r"attributes=\{([^}]+)\}", interacted_element):
            for attr in ["class", "name", "type", "role", "aria-label", "placeholder"]:
                if attr_match := re.search(rf"'{attr}':\s*'([^']+)'", attrs_match.group(1)):
                    selector_info[attr] = attr_match.group(1)

    elif isinstance(interacted_element, dict):
        if "x_path" in interacted_element:
            selector_info["xpath"] = interacted_element["x_path"]
        if "attributes" in interacted_element:
            attrs = interacted_element["attributes"]
            if isinstance(attrs, dict):
                selector_info.update(
                    {k: attrs[k] for k in
                     ["href", "id", "class", "name", "type", "role", "aria-label", "placeholder"]
                     if k in attrs}
                )

    return selector_info if selector_info else None


async def _try_interact_by_selector(
    page: Page, selector_info: Dict[str, str], action: str,
    text: str = None, clear: bool = False
) -> bool:
    """Try interacting with element using selector strategies. Returns True if successful."""
    node_name = selector_info.get("node_name", "").upper()
    input_type = selector_info.get("type", "").lower()
    is_input = node_name == "INPUT"
    is_submit_button = is_input and input_type == "submit"

    for strategy in ["xpath", "href", "id"]:
        if strategy not in selector_info:
            continue
        try:
            if strategy == "xpath":
                locator = page.locator(f"xpath={selector_info['xpath']}")
            elif strategy == "href":
                locator = page.locator(f"a[href='{selector_info['href']}']")
            else:
                locator = page.locator(f"#{selector_info['id']}")

            if await locator.count() == 0:
                await locator.wait_for(state="visible", timeout=2000)

            if action == "click":
                if is_submit_button or not is_input:
                    await locator.first.scroll_into_view_if_needed()
                    await locator.first.click(timeout=2000)
                else:
                    await locator.first.focus()
            elif action == "fill":
                if clear:
                    await locator.first.clear()
                await locator.first.fill(text)
            return True
        except:
            continue

    for attr, value in selector_info.items():
        if attr in ["class", "name", "type", "role", "aria-label"]:
            try:
                locator = page.locator(
                    f".{value.replace(' ', '.')}" if attr == "class" else f"[{attr}='{value}']"
                )
                if await locator.count() > 0:
                    if action == "click":
                        if is_submit_button or not is_input:
                            await locator.first.scroll_into_view_if_needed()
                            await locator.first.click(timeout=2000)
                        else:
                            await locator.first.focus()
                    elif action == "fill":
                        if clear:
                            await locator.first.clear()
                        await locator.first.fill(text)
                    return True
            except:
                continue

    return False


# ---------------------------------------------------------------------------
# Tab ID pre-mapping
# ---------------------------------------------------------------------------

def _prebuild_tab_id_map(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Pre-scan actions to map agent-assigned tab_ids correctly.

    Tab IDs that appear in switch_tab but have NO corresponding new_tab navigate
    are pre-existing tabs (initial page, speedtest.net etc).
    Only the LAST n tab_ids (where n = number of new_tab navigates) are new tabs.
    """
    # Collect switch_tab ids in first-seen order
    switch_tab_ids_ordered: List[str] = []
    for action in actions:
        if "switch_tab" in action:
            tab_id = action["switch_tab"].get("tab_id")
            if tab_id and tab_id not in switch_tab_ids_ordered:
                switch_tab_ids_ordered.append(tab_id)

    # Count new_tab navigates
    num_new_tabs = sum(
        1 for a in actions
        if "navigate" in a and a["navigate"].get("new_tab")
    )

    # Split: first (total - num_new_tabs) are pre-existing, rest are new
    num_preexisting = len(switch_tab_ids_ordered) - num_new_tabs
    preexisting_ids = switch_tab_ids_ordered[:num_preexisting]
    new_tab_ids = switch_tab_ids_ordered[num_preexisting:]

    return {
        "new_tab_map": {tab_id: i for i, tab_id in enumerate(new_tab_ids)},
        "preexisting_ids": preexisting_ids,
    }

# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

async def handle_search(page: Page, info: Dict[str, Any], **kwargs) -> None:
    """Handle search action."""
    query = info.get("query", "").replace(" ", "+")
    engine = info.get("engine", "google")
    urls = {
        "google": f"https://www.google.com/search?q={query}",
        "duckduckgo": f"https://duckduckgo.com/?q={query}",
        "bing": f"https://www.bing.com/search?q={query}",
    }
    await page.goto(urls.get(engine, urls["google"]), wait_until="networkidle")
    await page.wait_for_timeout(2000)


async def handle_navigate(page: Page, info: Dict[str, Any], **kwargs) -> Page:
    """
    Handle navigate action. Returns the page navigated to.

    For new_tab=True:
      - Deduplicates: reuses an existing tab if the same URL is already open.
      - Registers the new tab using the agent tab_id derived from the pre-scan map,
        so that subsequent switch_tab actions can find it by the original ID.
    """
    url = info.get("url")
    if not url:
        return page

    tab_registry: Dict[str, Page] = kwargs.get("tab_registry", {})
    new_tab_counter: List[int] = kwargs.get("new_tab_counter", [0])
    index_to_agent_id: Dict[int, str] = kwargs.get("index_to_agent_id", {})
    verbose: bool = kwargs.get("verbose", False)

    if info.get("new_tab", False):
        # Deduplication: reuse existing tab with same URL
        for tab_id, existing_page in list(tab_registry.items()):
            try:
                if not existing_page.is_closed() and existing_page.url == url:
                    if verbose:
                        print(f"♻️  Reusing existing tab [{tab_id}] for URL: {url}")
                    await existing_page.bring_to_front()
                    return existing_page
            except:
                continue

        new_page = await page.context.new_page()
        await new_page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await new_page.wait_for_timeout(2000)

        # Assign the agent's original tab_id if known, else auto-generate
        current_index = new_tab_counter[0]
        new_tab_counter[0] += 1

        agent_id = index_to_agent_id.get(current_index)
        assigned_id = agent_id if agent_id else format(len(tab_registry), "X").zfill(4)
        tab_registry[assigned_id] = new_page

        if verbose:
            suffix = " (mapped from agent)" if agent_id else " (auto-id)"
            print(f"📑 Registered new tab [{assigned_id}]{suffix}: {url}")

        return new_page
    else:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)
        return page


async def handle_click(page: Page, info: Dict[str, Any], interacted_element: Any, **kwargs) -> Optional[Page]:
    """Handle click action. Returns new page if a new tab was opened, None otherwise."""
    tab_registry: Dict[str, Page] = kwargs.get("tab_registry", {})
    new_tab_counter: List[int] = kwargs.get("new_tab_counter", [0])
    index_to_agent_id: Dict[int, str] = kwargs.get("index_to_agent_id", {})
    verbose: bool = kwargs.get("verbose", False)

    initial_pages = set(page.context.pages)
    coord_x, coord_y = info.get("coordinate_x"), info.get("coordinate_y")
    clicked = False

    if coord_x is not None and coord_y is not None:
        try:
            await page.mouse.click(coord_x, coord_y)
            clicked = True
            if verbose:
                print(f"✅ Clicked at coordinates ({coord_x}, {coord_y})")
        except Exception as e:
            if verbose:
                print(f"❌ Coordinate click failed: {e}")
    else:
        selector_info = extract_selector_from_interacted_element(interacted_element)
        if selector_info:
            clicked = await _try_interact_by_selector(page, selector_info, "click")
            if clicked and verbose:
                print(f"✅ Clicked via selector: {list(selector_info.keys())}")
            elif verbose:
                print(f"❌ Selector click failed, trying index fallback")

        if not clicked and (index := info.get("index")):
            try:
                await page.evaluate(f"document.querySelectorAll('*')[{index}].click()")
                clicked = True
                if verbose:
                    print(f"✅ Clicked via index: {index}")
            except Exception as e:
                if verbose:
                    print(f"❌ Index click failed: {e}")

    if not clicked and verbose:
        print(f"⚠️  Click action failed - no successful click method")

    await page.wait_for_timeout(1000)
    new_pages = [p for p in page.context.pages if p not in initial_pages]
    if new_pages:
        new_page = new_pages[-1]
        current_index = new_tab_counter[0]
        new_tab_counter[0] += 1
        agent_id = index_to_agent_id.get(current_index)
        assigned_id = agent_id if agent_id else format(len(tab_registry), "X").zfill(4)
        tab_registry[assigned_id] = new_page
        if verbose:
            print(f"📑 Registered click-opened tab [{assigned_id}]: {new_page.url}")
        return new_page
    return None


async def handle_input(page: Page, info: Dict[str, Any], interacted_element: Any, **kwargs) -> bool:
    """Handle input action."""
    text = info.get("text", "")
    clear = info.get("clear", False)

    selector_info = extract_selector_from_interacted_element(interacted_element)
    if selector_info and await _try_interact_by_selector(page, selector_info, "fill", text, clear):
        await page.wait_for_timeout(500)
        return True

    if index := info.get("index"):
        try:
            inputs = await page.query_selector_all("input, textarea")
            if index < len(inputs):
                if clear:
                    await inputs[index].clear()
                await inputs[index].fill(text)
                await page.wait_for_timeout(500)
                return True
        except:
            pass
    return False


async def handle_send_keys(page: Page, info: Dict[str, Any], **kwargs) -> None:
    """Handle send_keys action."""
    keys = info.get("keys", "")
    await page.keyboard.press(keys)
    await page.wait_for_timeout(500)


async def handle_scroll(page: Page, info: Dict[str, Any], **kwargs) -> None:
    """Handle scroll action."""
    down = info.get("down", True)
    pages = info.get("pages", 1.0)
    index = info.get("index")

    viewport_height = await page.evaluate("window.innerHeight")

    if index is not None:
        scroll_amount = int(pages * viewport_height)
        await page.evaluate(
            f"document.querySelectorAll('*')[{index}]?.scrollBy(0, {scroll_amount if down else -scroll_amount})"
        )
    else:
        for _ in range(int(pages)):
            await page.evaluate(f"window.scrollBy(0, {viewport_height if down else -viewport_height})")
            await page.wait_for_timeout(300)
        if pages % 1 != 0:
            fractional = int((pages % 1) * viewport_height)
            await page.evaluate(f"window.scrollBy(0, {fractional if down else -fractional})")
    await page.wait_for_timeout(500)


async def handle_extract(page: Page, info: Dict[str, Any], **kwargs) -> Optional[str]:
    """
    Handle extract action.
    Extracts from the current active page only — tab switching is done via switch_tab.
    """
    query = info.get("query", "").lower()
    all_extractions = []

    try:
        if "star" in query:
            for sel in ["a[href*='/stargazers']", "[aria-label*='star']", ".social-count"]:
                try:
                    locator = page.locator(sel).first
                    if await locator.count() > 0:
                        extracted = await locator.inner_text()
                        all_extractions.append(f"[Tab: {page.url}]\n{extracted}")
                        break
                except:
                    continue

        extracted = await page.inner_text("body")
        if extracted:
            all_extractions.append(f"[Tab: {page.url}]\n{extracted}")
    except:
        pass

    return "\n\n---\n\n".join(all_extractions) if all_extractions else None


async def handle_switch_tab(page: Page, info: Dict[str, Any], **kwargs) -> Page:
    """
    Handle switch_tab action.
    Looks up tab_id in the registry (populated at navigate/click time).
    Falls back to cycling through open pages if not found.
    """
    tab_registry: Dict[str, Page] = kwargs.get("tab_registry", {})
    verbose: bool = kwargs.get("verbose", False)
    tab_id = info.get("tab_id")

    # Primary: registry lookup by agent tab_id
    if tab_id and tab_registry:
        target = tab_registry.get(tab_id)
        if target and not target.is_closed():
            await target.bring_to_front()
            await target.wait_for_timeout(500)
            if verbose:
                try:
                    print(f"🔄 Switched to registered tab [{tab_id}]: {target.url}")
                except:
                    print(f"🔄 Switched to registered tab [{tab_id}]")
            return target
        elif verbose:
            print(f"⚠️  Tab [{tab_id}] not found in registry or is closed. Falling back.")

    # Fallback: any other open non-closed tab
    for p in reversed(page.context.pages):
        if p != page and not p.is_closed():
            await p.bring_to_front()
            await p.wait_for_timeout(500)
            if verbose:
                try:
                    print(f"🔄 Fallback switched to tab: {p.url}")
                except:
                    print(f"🔄 Fallback switched to tab")
            return p

    return page


async def handle_close_tab(page: Page, info: Dict[str, Any], **kwargs) -> Page:
    """Handle close_tab action. Returns the new active page."""
    tab_registry: Dict[str, Page] = kwargs.get("tab_registry", {})
    verbose: bool = kwargs.get("verbose", False)
    context = page.context

    if tab_registry:
        keys_to_remove = [k for k, v in tab_registry.items() if v == page]
        for k in keys_to_remove:
            del tab_registry[k]
            if verbose:
                print(f"🗑️  Removed tab [{k}] from registry")

    if len(context.pages) > 1:
        await page.close()
        await asyncio.sleep(0.5)
        remaining_pages = [p for p in context.pages if not p.is_closed()]
        if remaining_pages:
            new_page = remaining_pages[-1]
            await new_page.bring_to_front()
            return new_page
    return page


async def handle_upload_file(page: Page, info: Dict[str, Any], interacted_element: Any, **kwargs) -> bool:
    """Handle upload_file action."""
    path = info.get("path", "")
    selector_info = extract_selector_from_interacted_element(interacted_element)

    if selector_info and "xpath" in selector_info:
        try:
            locator = page.locator(f"xpath={selector_info['xpath']}")
            if await locator.count() > 0:
                await locator.first.set_input_files(path)
                return True
        except:
            pass

    if index := info.get("index"):
        try:
            file_inputs = await page.query_selector_all('input[type="file"]')
            if index < len(file_inputs):
                await file_inputs[index].set_input_files(path)
                return True
        except:
            pass
    return False


async def handle_select_dropdown(page: Page, info: Dict[str, Any], interacted_element: Any, **kwargs) -> bool:
    """Handle select_dropdown action."""
    text = info.get("text", "")
    selector_info = extract_selector_from_interacted_element(interacted_element)

    if selector_info and "xpath" in selector_info:
        try:
            locator = page.locator(f"xpath={selector_info['xpath']}")
            if await locator.count() > 0:
                await locator.first.select_option(label=text)
                return True
        except:
            pass

    if index := info.get("index"):
        try:
            selects = await page.query_selector_all("select")
            if index < len(selects):
                await selects[index].select_option(label=text)
                return True
        except:
            pass
    return False


async def handle_get_dropdown_options(page: Page, info: Dict[str, Any], interacted_element: Any, **kwargs) -> Optional[List[str]]:
    """Handle get_dropdown_options action."""
    selector_info = extract_selector_from_interacted_element(interacted_element)

    if selector_info and "xpath" in selector_info:
        try:
            locator = page.locator(f"xpath={selector_info['xpath']}")
            if await locator.count() > 0:
                return await locator.first.locator("option").all_text_contents()
        except:
            pass

    if index := info.get("index"):
        try:
            selects = await page.query_selector_all("select")
            if index < len(selects):
                return await selects[index].evaluate("el => Array.from(el.options).map(o => o.text)")
        except:
            pass
    return None


async def handle_wait(page: Page, info: Dict[str, Any], **kwargs) -> None:
    """Handle wait action."""
    await page.wait_for_timeout(info.get("seconds", 1) * 1000)


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

ACTION_HANDLERS = {
    "search": handle_search,
    "navigate": handle_navigate,
    "click": handle_click,
    "input": handle_input,
    "send_keys": handle_send_keys,
    "scroll": handle_scroll,
    "extract": handle_extract,
    "switch_tab": handle_switch_tab,
    "close_tab": handle_close_tab,
    "upload_file": handle_upload_file,
    "select_dropdown": handle_select_dropdown,
    "get_dropdown_options": handle_get_dropdown_options,
    "wait": handle_wait,
}


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------

async def execute_model_actions(
    actions: Union[List[Dict[str, Any]], str],
    headless: bool = False,
    verbose: bool = False,
    keep_browser_open: bool = False,
) -> Dict[str, Any]:
    """Execute model_actions() list as Playwright commands."""
    if isinstance(actions, str):
        with open(actions, "r") as f:
            actions = json.load(f)

    extracted_data: List[Dict] = []
    errors: List[str] = []
    memory: List[str] = []

    # Pre-scan: split tab IDs into pre-existing vs newly created
    tab_id_info = _prebuild_tab_id_map(actions)
    new_tab_map: Dict[str, int] = tab_id_info["new_tab_map"]
    preexisting_ids: List[str] = tab_id_info["preexisting_ids"]

    # Reverse: new_tab open index -> agent tab_id string
    index_to_agent_id: Dict[int, str] = {v: k for k, v in new_tab_map.items()}

    # Tab registry: agent-id or auto-id -> live Page object
    tab_registry: Dict[str, Page] = {}
    # Mutable counter: how many new_tab navigates/clicks have fired
    new_tab_counter: List[int] = [0]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        # Register initial page under "0000" AND all pre-existing agent tab IDs
        tab_registry["0000"] = page
        for pid in preexisting_ids:
            tab_registry[pid] = page
            if verbose:
                print(f"📑 Registered initial tab as [{pid}] (pre-existing agent tab)")
        if verbose:
            print(f"📑 Registered initial tab [0000]")
            if new_tab_map:
                print(f"🗺️  New tab map: {new_tab_map}")
            if preexisting_ids:
                print(f"🗺️  Pre-existing tab IDs mapped to initial page: {preexisting_ids}")

        def make_kwargs() -> Dict[str, Any]:
            return {
                "tab_registry": tab_registry,
                "new_tab_counter": new_tab_counter,
                "index_to_agent_id": index_to_agent_id,
                "verbose": verbose,
            }

        try:
            for i, action_dict in enumerate(actions):
                if verbose:
                    print(f"\n{'='*60}\nAction {i + 1}/{len(actions)}\n{'='*60}")

                action_type = next((k for k in ACTION_HANDLERS if k in action_dict), None)
                if not action_type:
                    error_msg = f"Action {i+1}: Unknown type {list(action_dict.keys())}"
                    errors.append(error_msg)
                    if verbose:
                        print(f"⚠️  {error_msg}")
                    continue

                handler = ACTION_HANDLERS[action_type]
                action_info = action_dict[action_type]
                interacted_element = action_dict.get("interacted_element")

                if verbose:
                    print(f"📋 {action_type.upper()}: {json.dumps(action_info, indent=2)}")

                try:
                    # Recover from a closed page
                    if page.is_closed():
                        remaining = [p for p in context.pages if not p.is_closed()]
                        if remaining:
                            page = remaining[-1]
                            await page.bring_to_front()
                            if verbose:
                                try:
                                    print(f"⚠️  Page was closed, switched to: {page.url}")
                                except:
                                    print(f"⚠️  Page was closed, switched to new page")
                        else:
                            error_msg = f"Action {i+1}: All pages closed"
                            errors.append(error_msg)
                            if verbose:
                                print(f"❌ {error_msg}")
                            break

                    kw = make_kwargs()

                    if action_type == "navigate":
                        page = await handler(page, action_info, **kw)

                    elif action_type == "click":
                        new_page = await handler(page, action_info, interacted_element, **kw)
                        if new_page:
                            page = new_page
                            if verbose:
                                print(f"📑 Active page -> new tab: {page.url}")

                    elif action_type == "switch_tab":
                        new_page = await handler(page, action_info, **kw)
                        if new_page and not new_page.is_closed():
                            page = new_page
                        elif verbose:
                            print(f"⚠️  Warning: No valid page after switch_tab")

                    elif action_type == "close_tab":
                        new_page = await handler(page, action_info, **kw)
                        if new_page and not new_page.is_closed():
                            page = new_page
                            if verbose:
                                try:
                                    print(f"🗙 Closed tab, now on: {page.url}")
                                except:
                                    print(f"🗙 Closed tab, switched to new page")
                        elif verbose:
                            print(f"⚠️  Warning: No valid page after close_tab")

                    elif action_type in ["input", "upload_file", "select_dropdown", "get_dropdown_options"]:
                        await handler(page, action_info, interacted_element, **kw)

                    elif action_type == "extract":
                        extracted_text = await handler(page, action_info, **kw)
                        if extracted_text:
                            extracted_data.append({
                                "query": action_info.get("query", ""),
                                "data": extracted_text,
                                "action_index": i + 1,
                            })
                            if verbose:
                                print(f"\n📄 EXTRACTED DATA:\n{extracted_text}\n")

                            memory_instruction = action_info.get("memory_instruction")
                            if memory_instruction in ("append", "final"):
                                memory.append(extracted_text)
                                label = "Final extraction" if memory_instruction == "final" else "Appended"
                                if verbose:
                                    print(f"💾 {label} to memory (total items: {len(memory)})")

                    else:
                        await handler(page, action_info, **kw)

                    try:
                        if not page.is_closed():
                            await page.wait_for_timeout(300)
                    except Exception:
                        pass

                except Exception as e:
                    error_msg = f"Action {i+1} ({action_type}): {str(e)}"
                    errors.append(error_msg)
                    if verbose:
                        print(f"❌ {error_msg}")

            if keep_browser_open:
                try:
                    await page.wait_for_timeout(5000)
                except Exception:
                    pass

        finally:
            await browser.close()

    if memory:
        final_result = "\n\n".join(memory)
    else:
        all_extractions = [item["data"] for item in extracted_data if item.get("data")]
        final_result = "\n\n".join(all_extractions) if all_extractions else "No data extracted."

    return {
        "success": len(errors) == 0,
        "extracted_data": extracted_data,
        "total_extractions": len(extracted_data),
        "final_result": final_result,
        "errors": errors,
    }

# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    import sys

    if len(sys.argv) > 1:
        results = await execute_model_actions(
            sys.argv[1], headless=False, verbose=True, keep_browser_open=True
        )
        print(f"\n{'='*60}\nEXECUTION SUMMARY\n{'='*60}")
        print(f"✅ Success: {results['success']}\n📊 Extractions: {results['total_extractions']}")
        if results.get("final_result"):
            print(f"\n{'='*60}\nFINAL RESULT\n{'='*60}")
            print(results["final_result"])
        if results["extracted_data"]:
            for i, ext in enumerate(results["extracted_data"], 1):
                print(f"\n{'='*60}\nExtraction {i}/{results['total_extractions']}\n{'='*60}")
                print(f"Query: {ext['query']}")
                print(f"\nFull Extracted Data:\n{ext['data']}\n")
        if results["errors"]:
            print(f"❌ Errors ({len(results['errors'])}):")
            for err in results["errors"]:
                print(f"   - {err}")
    else:
        print("Usage: python playwright_engine.py <actions.json>")


if __name__ == "__main__":
    asyncio.run(main())