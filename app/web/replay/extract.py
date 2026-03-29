#!/usr/bin/env python3
"""Convert browser-use history to playwright_engine.py compatible format."""
import json
import re
import sys
from typing import Optional, Dict, Any, List, Tuple, Union


# ---------------------------------------------------------------------------
# interacted_element extraction
# ---------------------------------------------------------------------------

def _extract_interacted_elements_list(history_entry: str) -> List[Optional[str]]:
    """
    Extract the full interacted_element list from a history entry.

    browser_use stores interacted_element as a positional Python list aligned
    1:1 with the actions in that step, e.g.:
        interacted_element=[DOMInteractedElement(...), None, None]

    We parse that list in order so callers can do elements[action_position].
    """
    # Find the interacted_element=[ ... ] block in the state=BrowserStateHistory(...)
    last_match = None
    for m in re.finditer(r"interacted_element=\[", history_entry):
        last_match = m
    if not last_match:
        return []

    start = last_match.end()  # points just after the opening [
    depth = 1
    i = start
    while i < len(history_entry) and depth > 0:
        if history_entry[i] == '[':
            depth += 1
        elif history_entry[i] == ']':
            depth -= 1
        i += 1
    raw = history_entry[start:i - 1]  # contents between [ and ]

    # Split on top-level commas (not inside parentheses)
    elements: List[Optional[str]] = []
    current = ""
    depth = 0
    for ch in raw:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            elements.append(_parse_one_element(current.strip()))
            current = ""
        else:
            current += ch
    if current.strip():
        elements.append(_parse_one_element(current.strip()))

    return elements


def _parse_one_element(token: str) -> Optional[str]:
    """Return the DOMInteractedElement string, or None if the token is None/empty."""
    token = token.strip()
    if not token or token == "None":
        return None
    if token.startswith("DOMInteractedElement("):
        return token
    return None


# ---------------------------------------------------------------------------
# Action parsing
# ---------------------------------------------------------------------------

# All ActionModel wrappers that browser-use emits, in order of specificity.
# Each tuple: (regex, action_type, is_replayable)
# Non-replayable ones are included so we can correctly count positions for
# interacted_element alignment.
_ALL_ACTION_PATTERNS: List[Tuple[str, str, bool]] = [
    # --- replayable ---
    (r"WaitActionModel\(wait=wait_Params\(seconds=(\d+)\)\)",                                          "wait",                 True),
    (r"NavigateActionModel\(navigate=NavigateAction\(url='([^']+)'(?:,\s*new_tab=(True|False))?",      "navigate",             True),
    (r"SearchActionModel\(search=SearchAction\(query='([^']+)'(?:,\s*engine='([^']+)')?",              "search",               True),
    (r"InputTextActionModel\(input=InputTextAction\(index=(\d+),\s*text='([^']*)'",                    "input",                True),
    # ClickElementActionIndexOnly is used when no coordinates; ClickElementAction when coords present
    (r"ClickActionModel\(click=ClickElementAction(?:IndexOnly)?\(index=(\d+)(?:,\s*coordinate_x=([\d.]+))?(?:,\s*coordinate_y=([\d.]+))?", "click", True),
    (r"SendKeysActionModel\(send_keys=SendKeysAction\(keys='([^']+)'",                                 "send_keys",            True),
    (r"ScrollActionModel\(scroll=ScrollAction\(down=(True|False),\s*pages=([\d.]+)(?:,\s*index=(\d+))?","scroll",              True),
    (r"ExtractActionModel\(extract=ExtractAction\(query='([^']+)'(?:,\s*extract_links=(True|False))?", "extract",              True),
    (r"CloseTabActionModel\(close_tab=CloseTabAction\(tab_id='([^']+)'",                               "close_tab",            True),
    (r"SwitchActionModel\(switch=SwitchTabAction\(tab_id='([^']+)'",                                   "switch_tab",           True),
    (r"UploadFileActionModel\(upload_file=UploadFileAction\(index=(\d+),\s*path='([^']+)'",            "upload_file",          True),
    (r"SelectDropdownOptionActionModel\(.*?SelectDropdownOptionAction\(index=(\d+),\s*text='([^']+)'", "select_dropdown",      True),
    (r"GetDropdownOptionsActionModel\(.*?GetDropdownOptionsAction\(index=(\d+)",                       "get_dropdown_options", True),
    # --- non-replayable (counted for position alignment only) ---
    (r"WriteFileActionModel\(",                                                                         "write_file",           False),
    (r"ReplaceFileActionModel\(",                                                                       "replace_file",         False),
    (r"EvaluateActionModel\(",                                                                          "evaluate",             False),
    (r"DoneActionModel\(",                                                                              "done",                 False),
    # Fallback for any other ActionModel
    (r"ActionModel\(root=\w+ActionModel\(",                                                             "unknown",              False),
]

# Also keep legacy patterns for older browser-use versions that omit the outer wrapper
_LEGACY_ACTION_PATTERNS: List[Tuple[str, str, bool]] = [
    (r"(?<!\w)NavigateAction\(url='([^']+)'(?:,\s*new_tab=(True|False))?",                             "navigate",             True),
    (r"(?<!\w)SwitchTabAction\(tab_id='([^']+)'",                                                      "switch_tab",           True),
    (r"(?<!\w)CloseTabAction\(tab_id='([^']+)'",                                                       "close_tab",            True),
    (r"(?<!\w)ClickElementAction(?:IndexOnly)?\(index=(\d+)(?:,\s*coordinate_x=([\d.]+))?(?:,\s*coordinate_y=([\d.]+))?", "click", True),
    (r"(?<!\w)InputTextAction\(index=(\d+),\s*text='([^']*)'",                                         "input",                True),
    (r"(?<!\w)ScrollAction\(down=(True|False),\s*pages=([\d.]+)(?:,\s*index=(\d+))?",                  "scroll",               True),
    (r"(?<!\w)ExtractAction\(query='([^']+)'(?:,\s*extract_links=(True|False))?",                      "extract",              True),
    (r"(?<!\w)SearchAction\(query='([^']+)'(?:,\s*engine='([^']+)')?",                                 "search",               True),
    (r"(?<!\w)SendKeysAction\(keys='([^']+)'",                                                          "send_keys",            True),
    (r"(?<!\w)WaitAction\(seconds=(\d+)\)",                                                             "wait",                 True),
    (r"(?<!\w)UploadFileAction\(index=(\d+),\s*path='([^']+)'",                                        "upload_file",          True),
    (r"(?<!\w)SelectDropdownOptionAction\(index=(\d+),\s*text='([^']+)'",                               "select_dropdown",      True),
    (r"(?<!\w)GetDropdownOptionsAction\(index=(\d+)",                                                   "get_dropdown_options", True),
    # non-replayable legacy
    (r"(?<!\w)WriteFileAction\(",                                                                        "write_file",           False),
    (r"(?<!\w)ReplaceFileAction\(",                                                                      "replace_file",         False),
    (r"(?<!\w)DoneAction\(",                                                                             "done",                 False),
]


def _find_all_action_positions(history_entry: str) -> List[Tuple[int, str, Any, bool]]:
    """
    Return list of (position, action_type, re_match, is_replayable) for every
    action found in history_entry, sorted by position.

    Tries primary (wrapper) patterns first; if none found at all, falls back to
    legacy patterns.
    """
    found: List[Tuple[int, str, Any, bool]] = []
    seen_positions = set()

    patterns = _ALL_ACTION_PATTERNS

    for pattern, action_type, replayable in patterns:
        for m in re.finditer(pattern, history_entry):
            pos = m.start()
            if pos not in seen_positions:
                seen_positions.add(pos)
                found.append((pos, action_type, m, replayable))

    # If we found nothing replayable with primary patterns, try legacy
    if not any(r for _, _, _, r in found):
        found = []
        seen_positions = set()
        for pattern, action_type, replayable in _LEGACY_ACTION_PATTERNS:
            for m in re.finditer(pattern, history_entry):
                pos = m.start()
                if pos not in seen_positions:
                    seen_positions.add(pos)
                    found.append((pos, action_type, m, replayable))

    found.sort(key=lambda x: x[0])
    return found


def _build_action_dict(action_type: str, m: Any, interacted_element: Optional[str]) -> Optional[Dict[str, Any]]:
    """Convert a regex match into a playwright_engine action dict."""
    try:
        if action_type == "wait":
            return {"wait": {"seconds": int(m.group(1))}, "interacted_element": None}

        elif action_type == "navigate":
            new_tab = False
            try:
                new_tab = m.group(2) == "True"
            except IndexError:
                pass
            return {"navigate": {"url": m.group(1), "new_tab": new_tab}, "interacted_element": None}

        elif action_type == "search":
            engine = "google"
            try:
                engine = m.group(2) or "google"
            except IndexError:
                pass
            return {"search": {"query": m.group(1), "engine": engine}, "interacted_element": None}

        elif action_type == "input":
            return {
                "input": {"index": int(m.group(1)), "text": m.group(2), "clear": False},
                "interacted_element": interacted_element,
            }

        elif action_type == "click":
            action: Dict[str, Any] = {"click": {"index": int(m.group(1))}, "interacted_element": interacted_element}
            try:
                if m.group(2) and m.group(3):
                    action["click"]["coordinate_x"] = float(m.group(2))
                    action["click"]["coordinate_y"] = float(m.group(3))
            except IndexError:
                pass
            return action

        elif action_type == "send_keys":
            return {"send_keys": {"keys": m.group(1)}, "interacted_element": None}

        elif action_type == "scroll":
            action = {"scroll": {"down": m.group(1) == "True", "pages": float(m.group(2))}, "interacted_element": None}
            try:
                if m.group(3):
                    action["scroll"]["index"] = int(m.group(3))
            except IndexError:
                pass
            return action

        elif action_type == "extract":
            extract_links = False
            try:
                extract_links = m.group(2) == "True"
            except IndexError:
                pass
            return {"extract": {"query": m.group(1), "extract_links": extract_links, "memory_instruction": "append"}, "interacted_element": None}

        elif action_type == "close_tab":
            return {"close_tab": {"tab_id": m.group(1)}, "interacted_element": None}

        elif action_type == "switch_tab":
            return {"switch_tab": {"tab_id": m.group(1)}, "interacted_element": None}

        elif action_type == "upload_file":
            return {"upload_file": {"index": int(m.group(1)), "path": m.group(2)}, "interacted_element": interacted_element}

        elif action_type == "select_dropdown":
            return {"select_dropdown": {"index": int(m.group(1)), "text": m.group(2)}, "interacted_element": interacted_element}

        elif action_type == "get_dropdown_options":
            return {"get_dropdown_options": {"index": int(m.group(1))}, "interacted_element": interacted_element}

    except Exception:
        pass

    return None


def parse_action_from_history(history_entry: str) -> List[Dict[str, Any]]:
    """
    Extract all REPLAYABLE actions from one history entry string.

    Key fixes vs original:
    - Uses positional interacted_element alignment (list position = action position)
      instead of trying to match backend_node_id to the DOM index
    - Counts non-replayable actions (write_file, evaluate, done, etc.) so that
      the positional index into interacted_element[] stays correct
    - Handles both new-style wrapper patterns and legacy bare patterns
    """
    user_match = re.search(r"<user_request>.*?Objective:.*?([^<]+)", history_entry, re.DOTALL)
    user_objective = re.sub(r'\s+', ' ', user_match.group(1).strip()) if user_match else None

    # interacted_element list — positionally aligned with ALL actions (incl. non-replayable)
    interacted_elements = _extract_interacted_elements_list(history_entry)

    all_positions = _find_all_action_positions(history_entry)

    actions: List[Dict[str, Any]] = []
    has_explicit_extract = False

    for action_idx, (pos, action_type, m, replayable) in enumerate(all_positions):
        # Get the interacted_element for this position if available
        elem = interacted_elements[action_idx] if action_idx < len(interacted_elements) else None

        if not replayable:
            # Still consumed a slot in interacted_element[] — do nothing else
            continue

        action_dict = _build_action_dict(action_type, m, elem)
        if action_dict is None:
            continue

        if action_type == "extract":
            has_explicit_extract = True

        actions.append(action_dict)

    # If the step ended with DoneAction and had meaningful extracted_content,
    # add a final extract so we capture it on replay.
    done_match = re.search(r"DoneAction\(text='([^']*)'", history_entry)
    if done_match and not has_explicit_extract and user_objective:
        content_match = re.search(r"extracted_content='([^']+)'", history_entry)
        extracted_content = content_match.group(1) if content_match else None
        if extracted_content and len(extracted_content) > 20 and not extracted_content.startswith(
            ("Searched", "Clicked", "Typed", "Scrolled", "Navigated", "Switched", "Waited",
             "Data written", "Successfully replaced", "🔗", "undefined")
        ):
            actions.append({
                "extract": {"query": user_objective, "extract_links": False, "memory_instruction": "final"},
                "interacted_element": None,
            })

    return actions


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------

def _is_duplicate_navigate(action: Dict, prev_actions: List[Dict]) -> bool:
    """
    Return True if this navigate action is a duplicate of a very recent one.
    browser_use sometimes emits the same URL twice (with/without trailing slash).
    """
    if "navigate" not in action:
        return False
    url = action["navigate"]["url"].rstrip("/")
    new_tab = action["navigate"].get("new_tab", False)

    # Look back through the last few actions (skip waits)
    lookback = 0
    for prev in reversed(prev_actions):
        if "wait" in prev:
            lookback += 1
            if lookback > 3:
                break
            continue
        if "navigate" in prev:
            prev_url = prev["navigate"]["url"].rstrip("/")
            prev_new_tab = prev["navigate"].get("new_tab", False)
            if prev_url == url and prev_new_tab == new_tab:
                return True
        break  # stop at first non-wait previous action

    return False


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def convert_history_to_playwright_format(
    history_data: Union[str, Dict[str, Any]],
    output_file: Optional[str] = None,
    save_to_file: bool = True,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """Convert browser-use history to playwright_engine.py compatible format."""
    if isinstance(history_data, str):
        with open(history_data, "r") as f:
            data = json.load(f)
        if output_file is None and save_to_file:
            output_file = (
                history_data.replace(".json", "_converted.json")
                if history_data.endswith(".json")
                else history_data + "_converted.json"
            )
    else:
        data = history_data

    replayable = {
        "navigate", "search", "input", "click", "send_keys", "scroll",
        "extract", "switch_tab", "close_tab", "upload_file",
        "select_dropdown", "get_dropdown_options", "wait",
    }

    def _make_extract(memory_instruction: str = "append") -> Dict:
        return {
            "extract": {
                "query": "Extract current tab content",
                "extract_links": False,
                "memory_instruction": memory_instruction,
            },
            "interacted_element": None,
        }

    def _make_wait(seconds: int = 2) -> Dict:
        return {"wait": {"seconds": seconds}, "interacted_element": None}

    history_entries = data.get("history", [])

    # ------------------------------------------------------------------
    # Step 1: Flatten all replayable actions from all entries
    # ------------------------------------------------------------------
    flat_actions: List[Dict] = []
    for history_entry in history_entries:
        entry_actions = parse_action_from_history(history_entry)
        for action in entry_actions:
            action_type = next(iter(action.keys()), None)
            if action_type and action_type in replayable:
                # Deduplicate consecutive navigate to same URL
                if _is_duplicate_navigate(action, flat_actions):
                    if verbose:
                        print(f"  ⚠️  Skipping duplicate navigate: {action['navigate']['url']}")
                    continue
                flat_actions.append(action)

    # ------------------------------------------------------------------
    # Step 2: Enrich with extract/wait injections
    # ------------------------------------------------------------------
    all_actions: List[Dict] = []

    def next_non_wait(start: int) -> Optional[str]:
        for j in range(start, len(flat_actions)):
            t = next(iter(flat_actions[j].keys()))
            if t != "wait":
                return t
        return None

    def last_meaningful_type(actions_so_far: List[Dict]) -> Optional[str]:
        """Type of the last non-wait action already appended."""
        for a in reversed(actions_so_far):
            t = next(iter(a.keys()))
            if t != "wait":
                return t
        return None

    i = 0
    while i < len(flat_actions):
        action = flat_actions[i]
        action_type = next(iter(action.keys()))
        all_actions.append(action)

        if action_type == "switch_tab":
            # Always wait after switch so the page can settle
            all_actions.append(_make_wait(2))
            nxt = next_non_wait(i + 1)
            # Only extract if we're staying on this tab for a while
            if nxt not in ("navigate", "switch_tab", "close_tab", None):
                all_actions.append(_make_extract("append"))

        elif action_type == "navigate":
            nav_info = action.get("navigate", {})
            if nav_info.get("new_tab"):
                # Leaving current tab — extract it first if not already done
                prev = last_meaningful_type(all_actions[:-1])  # exclude the navigate we just appended
                if prev not in ("extract", "switch_tab", "navigate", None):
                    all_actions.insert(len(all_actions) - 1, _make_extract("append"))
            else:
                # Same-tab navigate — leaving current page, extract before navigating away
                prev = last_meaningful_type(all_actions[:-1])
                if prev not in ("extract", "switch_tab", "navigate", None):
                    all_actions.insert(len(all_actions) - 1, _make_extract("append"))

        i += 1

    # ------------------------------------------------------------------
    # Step 3: Ensure a final extract
    # ------------------------------------------------------------------
    if all_actions:
        last_type = next(iter(all_actions[-1].keys()), None)
        if last_type != "extract":
            has_final = any(
                a.get("extract", {}).get("memory_instruction") == "final"
                for a in all_actions
                if "extract" in a
            )
            all_actions.append({
                "extract": {
                    "query": "Extract final page data",
                    "extract_links": False,
                    "memory_instruction": "final" if not has_final else "append",
                },
                "interacted_element": None,
            })

    # ------------------------------------------------------------------
    # Step 4: Save / return
    # ------------------------------------------------------------------
    if save_to_file and output_file:
        with open(output_file, "w") as f:
            json.dump(all_actions, f, indent=2, default=str)
        if verbose:
            print(f"✅ Extracted {len(all_actions)} actions from {len(history_entries)} entries → {output_file}")
    elif verbose:
        print(f"✅ Extracted {len(all_actions)} actions")

    return all_actions


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract.py <history_file.json> [output_file.json]")
        sys.exit(1)

    output_file = next((arg for arg in sys.argv[2:] if not arg.startswith("--")), None)
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    try:
        convert_history_to_playwright_format(sys.argv[1], output_file, save_to_file=True, verbose=verbose)
    except FileNotFoundError:
        print(f"❌ File '{sys.argv[1]}' not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()