
import json
import os
import sys

APP_FILE = "src/app.bubble"
METADATA_FILE = "bubble_metadata.json"

def scan_metadata(data=None):
    if data is None:
        if not os.path.exists(APP_FILE):
            print(f"❌ Error: {APP_FILE} not found.")
            return False

        try:
            print(f" Reading {APP_FILE}...")
            with open(APP_FILE, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(f"❌ Error reading {APP_FILE}: {e}")
            return False

    try:
        type_map = {}

        # 1. Option Sets
        option_sets = data.get("option_sets")
        if option_sets:
            print(f" Found {len(option_sets)} Option Sets")
            for os_id, os_data in option_sets.items():
                if not isinstance(os_data, dict): continue
                display_name = os_data.get("display", "")
                internal_id = f"option.{os_id}"

                if display_name:
                    type_map[display_name] = internal_id
                    # Also map the name without "OS:" prefix if present
                    if display_name.startswith("OS:"):
                        clean_name = display_name[3:].strip()
                        type_map[clean_name] = internal_id

        # 2. User Types (Custom Types)
        user_types = data.get("user_types")
        if user_types:
            print(f" Found {len(user_types)} User Types")
            for type_id, type_data in user_types.items():
                if not isinstance(type_data, dict): continue

                # Check multiple name sources
                display_name = type_data.get("display") or type_data.get("%d") or type_id

                # Determine prefix
                if type_id.lower() == "user":
                    internal_id = "user"
                else:
                    internal_id = f"custom.{type_id}"

                if display_name:
                    type_map[display_name] = internal_id

        # 3. Save to JSON
        with open(METADATA_FILE, 'w') as f:
            json.dump(type_map, f, indent=2)

        print(f"✅ Metadata saved to {METADATA_FILE} ({len(type_map)} entries)")
        return True

    except Exception as e:
        print(f"❌ Error scanning metadata: {e}")
        return False

if __name__ == "__main__":
    scan_metadata()
