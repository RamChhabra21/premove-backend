#!/usr/bin/env python3
"""Playwright Engine for model_actions() - converts and executes browser actions."""
import json
import re
import asyncio
from typing import Optional, Dict, Any, List, Union
from playwright.async_api import async_playwright, Page


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
            (r"node_name='([^']+)'", "node_name")
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
                selector_info.update({k: attrs[k] for k in ["href", "id", "class", "name", "type", "role", "aria-label", "placeholder"] if k in attrs})
    
    return selector_info if selector_info else None


async def _try_interact_by_selector(page: Page, selector_info: Dict[str, str], action: str, text: str = None, clear: bool = False) -> bool:
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
                if is_submit_button:
                    await locator.first.scroll_into_view_if_needed()
                    await locator.first.click(timeout=2000)
                elif is_input:
                    await locator.first.focus()
                else:
                    await locator.first.scroll_into_view_if_needed()
                    await locator.first.click(timeout=2000)
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
                locator = page.locator(f".{value.replace(' ', '.')}" if attr == "class" else f"[{attr}='{value}']")
                if await locator.count() > 0:
                    if action == "click":
                        if is_submit_button:
                            await locator.first.scroll_into_view_if_needed()
                            await locator.first.click(timeout=2000)
                        elif is_input:
                            await locator.first.focus()
                        else:
                            await locator.first.scroll_into_view_if_needed()
                            await locator.first.click(timeout=2000)
                    elif action == "fill":
                        if clear:
                            await locator.first.clear()
                        await locator.first.fill(text)
                    return True
            except:
                continue
    return False


async def handle_search(page: Page, info: Dict[str, Any]) -> None:
    """Handle search action."""
    query = info.get("query", "").replace(" ", "+")
    engine = info.get("engine", "google")
    urls = {
        "google": f"https://www.google.com/search?q={query}",
        "duckduckgo": f"https://duckduckgo.com/?q={query}",
        "bing": f"https://www.bing.com/search?q={query}"
    }
    await page.goto(urls.get(engine, urls["google"]), wait_until="networkidle")
    await page.wait_for_timeout(2000)


async def handle_navigate(page: Page, info: Dict[str, Any]) -> Page:
    """Handle navigate action. Returns the page that was navigated to."""
    url = info.get("url")
    if not url:
        return page
    
    if info.get("new_tab", False):
        new_page = await page.context.new_page()
        await new_page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await new_page.wait_for_timeout(2000)
        return new_page
    else:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)
        return page


async def handle_click(page: Page, info: Dict[str, Any], interacted_element: Any, verbose: bool = False) -> Optional[Page]:
    """Handle click action. Returns new page if a new tab was opened, None otherwise."""
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
    return new_pages[-1] if new_pages else None


async def handle_input(page: Page, info: Dict[str, Any], interacted_element: Any) -> bool:
    """Handle input action."""
    text = info.get("text", "")
    clear = info.get("clear", False)
    
    selector_info = extract_selector_from_interacted_element(interacted_element)
    if selector_info and await _try_interact_by_selector(page, selector_info, "fill", text, clear):
        await page.wait_for_timeout(500)
        return True
    
    if index := info.get("index"):
        try:
            inputs = await page.query_selector_all('input, textarea')
            if index < len(inputs):
                if clear:
                    await inputs[index].clear()
                await inputs[index].fill(text)
                await page.wait_for_timeout(500)
                return True
        except:
            pass
    return False


async def handle_send_keys(page: Page, info: Dict[str, Any]) -> None:
    """Handle send_keys action."""
    keys = info.get("keys", "")
    await page.keyboard.press(keys)
    await page.wait_for_timeout(500)


async def handle_scroll(page: Page, info: Dict[str, Any]) -> None:
    """Handle scroll action."""
    down = info.get("down", True)
    pages = info.get("pages", 1.0)
    index = info.get("index")
    
    viewport_height = await page.evaluate("window.innerHeight")
    scroll_amount = int(pages * viewport_height)
    
    if index is not None:
        await page.evaluate(f"document.querySelectorAll('*')[{index}]?.scrollBy(0, {scroll_amount if down else -scroll_amount})")
    else:
        for _ in range(int(pages)):
            await page.evaluate(f"window.scrollBy(0, {viewport_height if down else -viewport_height})")
            await page.wait_for_timeout(300)
        if pages % 1 != 0:
            fractional = int((pages % 1) * viewport_height)
            await page.evaluate(f"window.scrollBy(0, {fractional if down else -fractional})")
    await page.wait_for_timeout(500)


async def handle_extract(page: Page, info: Dict[str, Any], context=None) -> Optional[str]:
    """Handle extract action - extracts from all open tabs."""
    query = info.get("query", "").lower()
    all_extractions = []
    
    # Get all open pages/tabs
    pages_to_extract = [page]
    if context:
        pages_to_extract = context.pages
    
    for tab_page in pages_to_extract:
        try:
            if "star" in query:
                for sel in ["a[href*='/stargazers']", "[aria-label*='star']", ".social-count"]:
                    try:
                        locator = tab_page.locator(sel).first
                        if await locator.count() > 0:
                            tab_url = tab_page.url
                            extracted = await locator.inner_text()
                            all_extractions.append(f"[Tab: {tab_url}]\n{extracted}")
                            break
                    except:
                        continue
            
            # Extract full page text
            try:
                tab_url = tab_page.url
                extracted = await tab_page.inner_text("body")
                if extracted:
                    all_extractions.append(f"[Tab: {tab_url}]\n{extracted}")
            except:
                pass
        except:
            pass
    
    return "\n\n---\n\n".join(all_extractions) if all_extractions else None


async def handle_switch_tab(page: Page, info: Dict[str, Any]) -> Page:
    """Handle switch_tab action. Returns the switched-to page."""
    all_pages = page.context.pages
    if len(all_pages) > 1:
        for p in reversed(all_pages):
            if p != page:
                await p.bring_to_front()
                await page.wait_for_timeout(500)
                return p
    return page


async def handle_close_tab(page: Page, info: Dict[str, Any]) -> Page:
    """Handle close_tab action. Returns the new active page."""
    context = page.context
    if len(context.pages) > 1:
        page_to_close = page
        await page_to_close.close()
        await asyncio.sleep(0.5)
        remaining_pages = [p for p in context.pages if not p.is_closed()]
        if remaining_pages:
            new_page = remaining_pages[-1]
            await new_page.bring_to_front()
            return new_page
    return page


async def handle_upload_file(page: Page, info: Dict[str, Any], interacted_element: Any) -> bool:
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


async def handle_select_dropdown(page: Page, info: Dict[str, Any], interacted_element: Any) -> bool:
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
            selects = await page.query_selector_all('select')
            if index < len(selects):
                await selects[index].select_option(label=text)
                return True
        except:
            pass
    return False


async def handle_get_dropdown_options(page: Page, info: Dict[str, Any], interacted_element: Any) -> Optional[List[str]]:
    """Handle get_dropdown_options action."""
    selector_info = extract_selector_from_interacted_element(interacted_element)
    
    if selector_info and "xpath" in selector_info:
        try:
            locator = page.locator(f"xpath={selector_info['xpath']}")
            if await locator.count() > 0:
                return await locator.first.locator('option').all_text_contents()
        except:
            pass
    
    if index := info.get("index"):
        try:
            selects = await page.query_selector_all('select')
            if index < len(selects):
                return await selects[index].evaluate("el => Array.from(el.options).map(o => o.text)")
        except:
            pass
    return None


async def handle_wait(page: Page, info: Dict[str, Any]) -> None:
    """Handle wait action."""
    await page.wait_for_timeout(info.get("seconds", 1) * 1000)


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


async def execute_model_actions(
    actions: Union[List[Dict[str, Any]], str], 
    headless: bool = False,
    verbose: bool = False,
    keep_browser_open: bool = False
) -> Dict[str, Any]:
    """Execute model_actions() list as Playwright commands."""
    if isinstance(actions, str):
        with open(actions, 'r') as f:
            actions = json.load(f)
    
    extracted_data = []
    errors = []
    memory = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        context = page.context
        
        try:
            for i, action_dict in enumerate(actions):
                if verbose:
                    print(f"\n{'='*60}\nAction {i + 1}/{len(actions)}\n{'='*60}")
                
                action_type = next((k for k in ACTION_HANDLERS.keys() if k in action_dict), None)
                if not action_type:
                    error_msg = f"Action {i+1}: Unknown type {list(action_dict.keys())}"
                    errors.append(error_msg)
                    if verbose:
                        print(f"⚠️  {error_msg}")
                    continue
                
                handler = ACTION_HANDLERS[action_type]
                action_info = action_dict[action_type]
                interacted_element = action_dict.get("interacted_element")
                
                # Log action description
                if verbose:
                    action_desc = f"{action_type.upper()}: {json.dumps(action_info, indent=2)}"
                    print(f"📋 {action_desc}")
                
                try:
                    if page.is_closed():
                        remaining_pages = [p for p in context.pages if not p.is_closed()]
                        if remaining_pages:
                            page = remaining_pages[-1]
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
                    
                    if action_type == "navigate":
                        page = await handler(page, action_info)
                    elif action_type == "click":
                        new_page = await handler(page, action_info, interacted_element, verbose)
                        if new_page:
                            page = new_page
                            if verbose:
                                print(f"📑 New tab opened: {page.url}")
                    elif action_type == "switch_tab":
                        new_page = await handler(page, action_info)
                        if new_page and not new_page.is_closed():
                            page = new_page
                            if verbose:
                                try:
                                    print(f"🔄 Switched to tab: {page.url}")
                                except:
                                    print(f"🔄 Switched to new tab")
                        elif verbose:
                            print(f"⚠️  Warning: No valid page after switching tab")
                    elif action_type == "close_tab":
                        new_page = await handler(page, action_info)
                        if new_page and not new_page.is_closed():
                            page = new_page
                            if verbose:
                                try:
                                    print(f"🗙 Closed tab, switched to: {page.url}")
                                except:
                                    print(f"🗙 Closed tab, switched to new page")
                        elif verbose:
                            print(f"⚠️  Warning: No valid page after closing tab")
                    elif action_type in ["input", "upload_file", "select_dropdown", "get_dropdown_options"]:
                        await handler(page, action_info, interacted_element)
                    elif action_type == "extract":
                        if extracted_text := await handler(page, action_info, page.context):
                            extracted_data.append({
                                "query": action_info.get("query", ""), 
                                "data": extracted_text, 
                                "action_index": i + 1
                            })
                            if verbose:
                                print(f"\n📄 EXTRACTED DATA (Full - All Tabs):\n{extracted_text}\n")
                            
                            # Handle memory instructions
                            memory_instruction = action_info.get("memory_instruction")
                            if memory_instruction == "append":
                                memory.append(extracted_text)
                                if verbose:
                                    print(f"💾 Appended to memory (total items: {len(memory)})")
                            elif memory_instruction == "final":
                                memory.append(extracted_text)
                                if verbose:
                                    print(f"💾 Final extraction appended to memory (total items: {len(memory)})")
                    else:
                        await handler(page, action_info)
                    
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
    
    # Assemble final result from memory
    if memory:
        final_result = "\n\n".join(memory)
    else:
        # Fallback: combine all extracted data if no memory was accumulated
        all_extractions = [item.get("data", "") for item in extracted_data if item.get("data")]
        final_result = "\n\n".join(all_extractions) if all_extractions else "No data extracted."
    
    return {
        "success": len(errors) == 0,
        "extracted_data": extracted_data,
        "total_extractions": len(extracted_data),
        "final_result": final_result,
        "errors": errors
    }


async def main():
    """CLI entry point."""
    import sys
    
    if len(sys.argv) > 1:
        results = await execute_model_actions(sys.argv[1], headless=False, verbose=True, keep_browser_open=True)
        print(f"\n{'='*60}\nEXECUTION SUMMARY\n{'='*60}")
        print(f"✅ Success: {results['success']}\n📊 Extractions: {results['total_extractions']}")
        if results.get('final_result'):
            print(f"\n{'='*60}\nFINAL RESULT\n{'='*60}")
            print(results['final_result'])
        if results['extracted_data']:
            for i, ext in enumerate(results['extracted_data'], 1):
                print(f"\n{'='*60}\nExtraction {i}/{results['total_extractions']}\n{'='*60}")
                print(f"Query: {ext['query']}")
                print(f"\nFull Extracted Data:\n{ext['data']}\n")
        if results['errors']:
            print(f"❌ Errors ({len(results['errors'])}):")
            for err in results['errors']:
                print(f"   - {err}")
    else:
        print("Usage: python playwright_engine.py <actions.json>")


if __name__ == "__main__":
    asyncio.run(main())
