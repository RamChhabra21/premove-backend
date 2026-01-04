#!/usr/bin/env python3
"""Convert browser-use history to playwright_engine.py compatible format."""
import json
import re
import sys
from typing import Optional, Dict, Any, List, Union


def extract_interacted_element_from_history(history_entry: str, index: Optional[int] = None) -> Optional[str]:
    """Extract interacted_element string from history entry for a given index."""
    if index is None:
        return None
    
    pattern = rf"DOMInteractedElement\([^)]*backend_node_id={index}"
    match = re.search(pattern, history_entry)
    if not match:
        return None
    
    start = history_entry.rfind("DOMInteractedElement(", 0, match.end())
    if start == -1:
        return None
    
    paren_count = 0
    for i in range(start, len(history_entry)):
        if history_entry[i] == '(':
            paren_count += 1
        elif history_entry[i] == ')':
            paren_count -= 1
            if paren_count == 0:
                return history_entry[start:i+1]
    return None


def parse_action_from_history(history_entry: str) -> List[Dict[str, Any]]:
    """Extract all actions from history string and convert to playwright_engine format, preserving order."""
    actions = []
    
    user_match = re.search(r"<user_request>.*?Objective:.*?([^<]+)", history_entry, re.DOTALL)
    user_objective = re.sub(r'\s+', ' ', user_match.group(1).strip()) if user_match else None
    
    action_patterns = [
        (r"WaitActionModel\(wait=wait_Params\(seconds=(\d+)\)\)", "wait"),
        (r"NavigateAction\(url='([^']+)'(?:,\s*new_tab=(True|False))?", "navigate"),
        (r"SearchAction\(query='([^']+)'(?:,\s*engine='([^']+)')?", "search"),
        (r"InputTextAction\(index=(\d+),\s*text='([^']+)'", "input"),
        (r"ClickElementAction\(index=(\d+)(?:,\s*coordinate_x=(\d+))?(?:,\s*coordinate_y=(\d+))?", "click"),
        (r"SendKeysAction\(keys='([^']+)'", "send_keys"),
        (r"ScrollAction\(down=(True|False),\s*pages=([\d.]+)(?:,\s*index=(\d+))?", "scroll"),
        (r"ExtractAction\(query='([^']+)'(?:,\s*extract_links=(True|False))?", "extract"),
        (r"CloseTabAction\(tab_id='([^']+)'", "close_tab"),
        (r"SwitchTabAction\(tab_id='([^']+)'", "switch_tab"),
        (r"UploadFileAction\(index=(\d+),\s*path='([^']+)'", "upload_file"),
        (r"SelectDropdownOptionAction\(index=(\d+),\s*text='([^']+)'", "select_dropdown"),
        (r"GetDropdownOptionsAction\(index=(\d+)", "get_dropdown_options"),
    ]
    
    action_matches = []
    for pattern, action_type in action_patterns:
        for match in re.finditer(pattern, history_entry):
            action_matches.append((match.start(), action_type, match))
    
    action_matches.sort(key=lambda x: x[0])
    
    has_explicit_extract = False
    for pos, action_type, match in action_matches:
        if action_type == "wait":
            seconds = int(match.group(1))
            actions.append({"wait": {"seconds": seconds}, "interacted_element": None})
        elif action_type == "navigate":
            actions.append({"navigate": {"url": match.group(1), "new_tab": match.group(2) == "True"}, "interacted_element": None})
        elif action_type == "search":
            actions.append({"search": {"query": match.group(1), "engine": match.group(2) or "google"}, "interacted_element": None})
        elif action_type == "input":
            actions.append({
                "input": {"index": int(match.group(1)), "text": match.group(2), "clear": "clear=True" in history_entry},
                "interacted_element": extract_interacted_element_from_history(history_entry, int(match.group(1)))
            })
        elif action_type == "click":
            action = {"click": {"index": int(match.group(1))}, "interacted_element": extract_interacted_element_from_history(history_entry, int(match.group(1)))}
            if match.group(2) and match.group(3):
                action["click"].update({"coordinate_x": int(match.group(2)), "coordinate_y": int(match.group(3))})
            actions.append(action)
        elif action_type == "send_keys":
            actions.append({"send_keys": {"keys": match.group(1)}, "interacted_element": None})
        elif action_type == "scroll":
            action = {"scroll": {"down": match.group(1) == "True", "pages": float(match.group(2))}, "interacted_element": None}
            if match.group(3):
                action["scroll"]["index"] = int(match.group(3))
            actions.append(action)
        elif action_type == "extract":
            actions.append({"extract": {"query": match.group(1), "extract_links": match.group(2) == "True", "memory_instruction": "append"}, "interacted_element": None})
            has_explicit_extract = True
        elif action_type == "close_tab":
            actions.append({"close_tab": {"tab_id": match.group(1)}, "interacted_element": None})
        elif action_type == "switch_tab":
            actions.append({"switch_tab": {"tab_id": match.group(1)}, "interacted_element": None})
        elif action_type == "upload_file":
            idx = int(match.group(1))
            actions.append({"upload_file": {"index": idx, "path": match.group(2)}, "interacted_element": extract_interacted_element_from_history(history_entry, idx)})
        elif action_type == "select_dropdown":
            idx = int(match.group(1))
            actions.append({"select_dropdown": {"index": idx, "text": match.group(2)}, "interacted_element": extract_interacted_element_from_history(history_entry, idx)})
        elif action_type == "get_dropdown_options":
            idx = int(match.group(1))
            actions.append({"get_dropdown_options": {"index": idx}, "interacted_element": extract_interacted_element_from_history(history_entry, idx)})
    
    if match := re.search(r"DoneAction\(text='([^']+)'(?:,\s*success=(True|False))?", history_entry):
        content_match = re.search(r"extracted_content='([^']+)'", history_entry)
        extracted_content = content_match.group(1) if content_match else None
        
        if extracted_content and not has_explicit_extract and user_objective:
            is_meaningful = (not extracted_content.startswith(("Searched", "Clicked", "Typed", "Scrolled")) and len(extracted_content) > 20)
            if is_meaningful:
                actions.append({"extract": {"query": user_objective, "extract_links": False, "memory_instruction": "final"}, "interacted_element": None})
    
    return actions


def convert_history_to_playwright_format(
    history_data: Union[str, Dict[str, Any]], 
    output_file: Optional[str] = None, 
    save_to_file: bool = True,
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """Convert browser-use history to playwright_engine.py compatible format."""
    if isinstance(history_data, str):
        with open(history_data, 'r') as f:
            data = json.load(f)
        if output_file is None and save_to_file:
            output_file = history_data.replace('.json', '_converted.json') if history_data.endswith('.json') else history_data + '_converted.json'
    else:
        data = history_data
    
    all_actions = []
    replayable = {"navigate", "search", "input", "click", "send_keys", "scroll", "extract", "switch_tab", "close_tab", "upload_file", "select_dropdown", "get_dropdown_options", "wait"}
    
    history_entries = data.get("history", [])
    prev_entry_ended_with_switch_tab = False
    
    for entry_idx, history_entry in enumerate(history_entries):
        entry_actions = parse_action_from_history(history_entry)
        
        i = 0
        pending_extract_after_navigate = False
        
        while i < len(entry_actions):
            action = entry_actions[i]
            action_type = next(iter(action.keys())) if action else None
            
            if action_type != "done" and action_type in replayable:
                all_actions.append(action)
                
                if action_type == "switch_tab":
                    next_in_entry = next(iter(entry_actions[i + 1].keys())) if i + 1 < len(entry_actions) else None
                    next_entry_has_navigate = False
                    
                    if entry_idx + 1 < len(history_entries):
                        next_entry_actions = parse_action_from_history(history_entries[entry_idx + 1])
                        next_entry_has_navigate = any(
                            next(iter(a.keys())) == "navigate" for a in next_entry_actions
                        )
                    
                    if next_in_entry == "navigate" or next_entry_has_navigate:
                        all_actions.append({"wait": {"seconds": 2}, "interacted_element": None})
                        pending_extract_after_navigate = True
                        prev_entry_ended_with_switch_tab = True
                    else:
                        all_actions.append({"wait": {"seconds": 2}, "interacted_element": None})
                        all_actions.append({
                            "extract": {
                                "query": "Extract current tab content",
                                "extract_links": False,
                                "memory_instruction": "append"
                            },
                            "interacted_element": None
                        })
                        prev_entry_ended_with_switch_tab = False
                elif action_type == "navigate":
                    if pending_extract_after_navigate or prev_entry_ended_with_switch_tab:
                        all_actions.append({"wait": {"seconds": 2}, "interacted_element": None})
                        all_actions.append({
                            "extract": {
                                "query": "Extract current tab content",
                                "extract_links": False,
                                "memory_instruction": "append"
                            },
                            "interacted_element": None
                        })
                        pending_extract_after_navigate = False
                        prev_entry_ended_with_switch_tab = False
                else:
                    if action_type not in ["wait"]:
                        pending_extract_after_navigate = False
                        prev_entry_ended_with_switch_tab = False
            
            i += 1
    
    # Ensure extract action at the end to capture final page data
    if all_actions:
        last_action_type = next(iter(all_actions[-1].keys())) if all_actions[-1] else None
        if last_action_type != "extract":
            has_final_extract = any(
                action.get("extract", {}).get("memory_instruction") == "final" 
                for action in all_actions 
                if "extract" in action
            )
            memory_instruction = "final" if not has_final_extract else "append"
            all_actions.append({"extract": {"query": "Extract final page data", "extract_links": False, "memory_instruction": memory_instruction}, "interacted_element": None})
    
    if save_to_file and output_file:
        with open(output_file, 'w') as f:
            json.dump(all_actions, f, indent=2, default=str)
        if verbose:
            print(f"✅ Extracted {len(all_actions)} actions from {len(data.get('history', []))} entries → {output_file}")
    elif verbose:
        print(f"✅ Extracted {len(all_actions)} actions")
    
    return all_actions


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python extract.py <history_file.json> [output_file.json]")
        sys.exit(1)
    
    output_file = next((arg for arg in sys.argv[2:] if not arg.startswith("--")), None)
    
    try:
        convert_history_to_playwright_format(sys.argv[1], output_file, save_to_file=True, verbose=True)
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
