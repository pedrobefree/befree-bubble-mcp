#!/usr/bin/env python3
import json
import os
import re
import argparse
from typing import Dict, List, Any, Optional, Set

class TokenTransformer:
    def __init__(self, config_path: str = "figma_bridge/token_config.json"):
        self.config = self._load_json(config_path)
        self.naming_cfg = self.config.get("naming", {})
        self.weight_map = {
            "thin": 100,
            "hairline": 100,
            "extra-light": 200,
            "extralight": 200,
            "ultra-light": 200,
            "ultralight": 200,
            "light": 300,
            "normal": 400,
            "regular": 400,
            "medium": 500,
            "semi-bold": 600,
            "semibold": 600,
            "demi-bold": 600,
            "demibold": 600,
            "bold": 700,
            "extra-bold": 800,
            "extrabold": 800,
            "ultra-bold": 800,
            "ultrabold": 800,
            "black": 900,
            "heavy": 900
        }

    def normalize_font_weight(self, raw_weight: Any) -> Optional[str]:
        """Normalize token font weight to Bubble's numeric CSS weight strings."""
        if raw_weight is None:
            return None

        if isinstance(raw_weight, dict):
            raw_weight = raw_weight.get("value", raw_weight)

        if isinstance(raw_weight, (int, float)):
            return str(int(raw_weight))

        text = str(raw_weight).strip()
        if not text:
            return None

        if text.isdigit():
            return str(int(text))

        normalized = text.lower().replace("_", " ").strip()
        compact = re.sub(r"[^a-z0-9]+", "", normalized)

        direct_candidates = [
            normalized,
            normalized.replace(" ", "-"),
            compact,
        ]
        for candidate in direct_candidates:
            if candidate in self.weight_map:
                return str(self.weight_map[candidate])

        fuzzy_candidates = (
            ("thin", 100),
            ("hairline", 100),
            ("extralight", 200),
            ("ultralight", 200),
            ("light", 300),
            ("regular", 400),
            ("normal", 400),
            ("medium", 500),
            ("semibold", 600),
            ("demibold", 600),
            ("bold", 700),
            ("extrabold", 800),
            ("ultrabold", 800),
            ("black", 900),
            ("heavy", 900),
        )
        for label, value in fuzzy_candidates:
            if label in compact:
                return str(value)

        return text

    def _normalize_token_parts(self, path_parts: List[str], token_type: Optional[str] = None) -> List[str]:
        """Normalize duplicated top-level token prefixes from plugin exports."""
        parts = [str(part).strip() for part in path_parts if str(part).strip()]
        if not parts:
            return []

        duplicate_roots: Set[str] = {"color", "typography", "font"}
        if token_type == "color":
            duplicate_roots = {"color"}
        elif token_type in {"style", "font", "typography"}:
            duplicate_roots = {"typography", "font"}

        while len(parts) > 1 and parts[0].lower() in duplicate_roots and parts[1].lower() == parts[0].lower():
            parts = [parts[0]] + parts[2:]

        return parts

    def _load_json(self, path: str) -> Dict:
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
        return {}

    def hex_to_rgba(self, hex_str: str) -> str:
        """Convert #RRGGBBAA or #RRGGBB to rgba(r, g, b, a)"""
        if not isinstance(hex_str, str) or not hex_str.startswith('#'):
            return self.normalize_rgba(hex_str)
        hex_str = hex_str.lstrip('#')
        if len(hex_str) == 6:
            r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
            return self.normalize_rgba(f"rgba({r},{g},{b},1)")
        elif len(hex_str) == 8:
            r, g, b, a = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16), int(hex_str[6:8], 16)
            alpha = round(a / 255, 2)
            return self.normalize_rgba(f"rgba({r},{g},{b},{alpha})")
        return hex_str

    def normalize_rgba(self, rgba_str: str) -> str:
        """Standardize rgba string for comparison: rgba(r, g, b, a) with spaces."""
        if not rgba_str or not isinstance(rgba_str, str):
            return rgba_str

        # Extract numbers - handle rgba(r,g,b,a) or rgb(r,g,b)
        parts = re.findall(r"(\d+\.?\d*)", rgba_str)
        if len(parts) >= 3:
            r, g, b = parts[0], parts[1], parts[2]
            # Alpha defaults to 1 if not present
            a = parts[3] if len(parts) > 3 else "1"
            # Normalize alpha: "1.0" or "1" -> "1", "0.50" -> "0.5"
            a_val = float(a)
            a_str = f"{a_val:g}" # removes trailing zeros
            return f"rgba({r}, {g}, {b}, {a_str})"

        return rgba_str

    def format_name(self, path_parts: List[str], token_type: str = "color") -> str:
        """Convert path parts to Bubble-friendly name based on config"""
        path_parts = self._normalize_token_parts(path_parts, token_type=token_type)
        full_path = ".".join(path_parts)

        # Check for custom mapping first
        mapping_key = "color_mapping" if token_type == "color" else "font_mapping"
        mapping = self.config.get(mapping_key, {})
        if full_path in mapping:
            return mapping[full_path]

        separator = self.naming_cfg.get("separator", " ")
        case_type = self.naming_cfg.get("case", "title")

        # Skip top-level 'color' or 'typography' or 'font'
        parts = list(path_parts)
        if parts[0] in ['color', 'typography', 'font']:
            parts = parts[1:]

        name = separator.join(parts)

        if case_type == "title":
            name = name.title()
        elif case_type == "camel":
            parts = name.split(separator)
            name = parts[0].lower() + "".join(x.title() for x in parts[1:])

        return name

    def flatten_tokens(self, data: Any, current_path: List[str] = []) -> List[Dict]:
        """Recursively flatten the nested token structure"""
        tokens = []

        if isinstance(data, dict):
            # Check if this is a leaf token
            if "type" in data and "value" in data:
                token_type = data["type"]
                normalized_parts = self._normalize_token_parts(current_path, token_type=token_type)
                tokens.append({
                    "path": ".".join(normalized_parts),
                    "parts": normalized_parts,
                    "type": token_type,
                    "value": data["value"],
                    "description": data.get("description", "")
                })
            # Check if this is a typography/fontStyle object
            elif any(k in data for k in ["fontFamily", "fontSize", "fontWeight"]):
                 normalized_parts = self._normalize_token_parts(current_path, token_type="typography")
                 tokens.append({
                     "path": ".".join(normalized_parts),
                     "parts": normalized_parts,
                     "type": "typography",
                     "value": data if "value" not in data else data["value"],
                     "description": data.get("description", "")
                 })
            else:
                for key, value in data.items():
                    if key == "extensions": continue
                    tokens.extend(self.flatten_tokens(value, current_path + [key]))

        return tokens

    def filter_tokens(self, tokens: List[Dict]) -> Dict[str, List[Dict]]:
        """Filter and group tokens (color, font, button)"""
        filtered = {"color": [], "font": [], "style": [], "button": []}

        filter_cfg = self.config.get("filters", {})
        include_colors = filter_cfg.get("include_color_paths", ["color.*"])
        include_typography = filter_cfg.get("include_typography_paths", ["typography.*", "font.*"])
        include_buttons = filter_cfg.get("include_button_paths", ["button.*", "components.button.*"])

        for token in tokens:
            path = token["path"]

            # Match colors
            if token["type"] == "color":
                is_included = any(path.startswith(p.replace(".*", "")) for p in include_colors)
                if is_included:
                    filtered["color"].append(token)

            # Match typography (fonts AND styles)
            elif token["type"] in ["typography", "fontFamily", "custom-fontStyle"]:
                is_included = any(path.startswith(p.replace(".*", "")) for p in include_typography)
                if is_included:
                    if isinstance(token["value"], dict) and "fontSize" in token["value"]:
                        filtered["style"].append(token)
                        if "fontFamily" in token["value"]:
                            filtered["font"].append(token)
                    else:
                        filtered["font"].append(token)

            # Match buttons
            is_button = any(path.startswith(p.replace(".*", "")) for p in include_buttons)
            if is_button:
                filtered["button"].append(token)

        return filtered

    def get_default_color_mappings(self) -> Dict[str, List[str]]:
        """Determine which Figma paths map to Bubble's default colors"""
        mappings = self.config.get("default_color_mapping", {})
        processed = {}
        for k, v in mappings.items():
            targets = v if isinstance(v, list) else [v]
            processed[k] = targets
        return processed

    def get_available_groups(self, tokens: List[Dict]) -> Dict[str, List[str]]:
        """Identify available first-level groups for colors and styles"""
        groups = {"color": set(), "style": set()}

        for token in tokens:
            parts = self._normalize_token_parts(token["parts"], token_type=token["type"])
            if len(parts) > 1:
                # color.brand.600 -> brand
                # typography.display.bold -> display
                group_type = parts[0]
                group_name = parts[1]

                if group_type == "color" and token["type"] == "color":
                    groups["color"].add(group_name)
                elif group_type in ["typography", "font"] and isinstance(token["value"], dict) and "fontSize" in token["value"]:
                    groups["style"].add(group_name)

        return {k: sorted(list(v)) for k, v in groups.items()}

    def generate_commands(self, filtered_tokens: Dict, profile: str = "cli-test") -> List[str]:
        """Generate CLI commands from filtered tokens"""
        commands = []

        # Color commands
        for token in filtered_tokens["color"]:
            name = self.format_name(token["parts"], token_type="color")
            rgba = self.hex_to_rgba(token["value"])
            # Default to create-color
            commands.append(f"python3 bubble_cli.py --profile {profile} create-color \"{name}\" \"{rgba}\"")

        # Unique font families
        families = set()
        for token in filtered_tokens["font"]:
            val = token["value"]
            if isinstance(val, dict):
                family = val.get("fontFamily", {}).get("value") or val.get("fontFamily")
            else:
                family = val

            if family:
                families.add(family)

        for family in sorted(list(families)):
            commands.append(f"python3 bubble_cli.py --profile {profile} create-font \"{family}\" \"{family}\"")

        # Button Style Commands (Aggregated)
        button_themes = self.aggregate_button_themes(filtered_tokens["button"])
        for name, theme in button_themes.items():
            theme_json = json.dumps(theme)
            commands.append(f"python3 bubble_cli.py --profile {profile} create-button-style \"{name}\" '{theme_json}'")

        # Typography Style Commands (Aggregated)
        text_themes = self.aggregate_typography_themes(filtered_tokens["style"])
        for name, theme in text_themes.items():
            # For Text styles, we use create-style command with --element-type Text
            # We wrap the theme as "base" properties
            base_props = theme.get("base", {})
            args = []
            for k, v in base_props.items():
                # Map keys to CLI arguments
                if k == "bg_color": args.append(f"--bg-color \"{v}\"")
                elif k == "font_color": args.append(f"--font-color \"{v}\"")
                elif k == "font_size": args.append(f"--font-size {v}")
                elif k == "font_family": args.append(f"--font-family \"{v}\"")
                elif k == "font_weight": args.append(f"--font-weight \"{v}\"")
                elif k == "line_height": args.append(f"--line-height {v}")
                elif k == "letter_spacing": args.append(f"--letter-spacing {v}")
                else: args.append(f"--{k.replace('_', '-')} \"{v}\"")

            arg_str = " ".join(args)
            commands.append(f"python3 bubble_cli.py --profile {profile} create-style \"{name}\" Text {arg_str}")

        return commands

    def aggregate_button_themes(self, tokens: List[Dict]) -> Dict[str, Dict]:
        """
        Groups button tokens into theme objects by component name and state.
        Example path: button.primary.hover.bg -> { primary: { hover: { bg_color: ... } } }
        """
        themes = {}

        # Simple mapping of Figma property names to StyleBuilder property names
        prop_map = {
            "bg": "bg_color",
            "background": "bg_color",
            "color": "font_color",
            "text": "font_color",
            "font-size": "font_size",
            "fontSize": "font_size",
            "border": "border_color",
            "radius": "border_radius",
            "padding": "padding",
            "gap": "gap"
        }

        for token in tokens:
            parts = token["parts"]
            # Expected: ['button', 'primary', 'hover', 'bg'] or ['button', 'primary', 'bg']

            # Find the starting index of the component properties
            try:
                start_idx = parts.index('button') + 1
            except ValueError:
                continue

            property_parts = parts[start_idx:]
            if not property_parts: continue

            # Name follows 'button' (e.g. 'primary', 'secondary')
            comp_name = property_parts[0]

            # Detect state (default is 'base')
            state = "base"
            field = property_parts[-1]

            for s in ["hover", "pressed", "focus", "disabled"]:
                if s in property_parts:
                    state = s
                    break

            if comp_name not in themes:
                themes[comp_name] = {"base": {}, "hover": {}, "pressed": {}, "focus": {}, "disabled": {}}

            # Map the field
            style_prop = prop_map.get(field.lower(), field)
            val = token["value"]

            # Convert colors
            if token["type"] == "color":
                val = self.hex_to_rgba(val)

            themes[comp_name][state][style_prop] = val

        # Cleanup empty states
        for name in list(themes.keys()):
            themes[name] = {k: v for k, v in themes[name].items() if v}

        return themes

    def aggregate_typography_themes(self, tokens: List[Dict]) -> Dict[str, Dict]:
        """
        Groups typography tokens into Text style theme objects.
        Figma typography tokens usually contain a dictionary value with family, size, weight, etc.
        """
        themes = {}
        for token in tokens:
            name = self.format_name(token["parts"], token_type="font")
            val = token["value"]
            if not isinstance(val, dict): continue

            theme = {"base": {}}

            # Map Figma/Token properties to StyleBuilder
            if "fontFamily" in val:
                family = val["fontFamily"]
                if isinstance(family, dict): family = family.get("value", family)
                theme["base"]["font_family"] = family

            if "fontSize" in val:
                size = val["fontSize"]
                if isinstance(size, dict): size = size.get("value", size)
                # Ensure it's numeric
                try:
                    theme["base"]["font_size"] = int(float(str(size).replace("px", "")))
                except: pass

            if "fontWeight" in val:
                weight = self.normalize_font_weight(val["fontWeight"])
                if weight is not None:
                    theme["base"]["font_weight"] = weight

            if "lineHeight" in val:
                lh = val["lineHeight"]
                if isinstance(lh, dict): lh = lh.get("value", lh)
                # Bubble uses a multiplier (e.g. 1.2 or 1.5)
                # Figma tokens might be pixels ("24px") or percentage ("120%")
                if isinstance(lh, str):
                    if lh.endswith("%"):
                        theme["base"]["line_height"] = round(float(lh.replace("%", "")) / 100, 2)
                    elif "px" in lh or lh.replace(".", "").isdigit():
                        # If px, we need the font size to compute multiplier
                        px_val = float(lh.replace("px", ""))
                        fs_val = theme["base"].get("font_size")
                        if fs_val:
                            theme["base"]["line_height"] = round(px_val / fs_val, 2)
                elif isinstance(lh, (int, float)):
                    # If it's a large value, assume px. If small, assume multiplier.
                    if lh > 5:
                        fs_val = theme["base"].get("font_size")
                        if fs_val:
                            theme["base"]["line_height"] = round(lh / fs_val, 2)
                    else:
                        theme["base"]["line_height"] = lh

            if "letterSpacing" in val:
                ls = val["letterSpacing"]
                if isinstance(ls, dict): ls = ls.get("value", ls)
                # Bubble uses pixels
                if isinstance(ls, str):
                    if ls.endswith("%"):
                        # Percentage of font size
                        fs_val = theme["base"].get("font_size")
                        if fs_val:
                            theme["base"]["letter_spacing"] = round((float(ls.replace("%", "")) / 100) * fs_val, 1)
                    else:
                        try:
                            theme["base"]["letter_spacing"] = float(ls.replace("px", ""))
                        except: pass
                else:
                    theme["base"]["letter_spacing"] = ls

            themes[name] = theme

        return themes

def main():
    parser = argparse.ArgumentParser(description="Transform Figma tokens to Bubble CLI commands")
    parser.add_argument("--input", required=True, help="Path to figma tokens JSON")
    parser.add_argument("--output", help="Path to output script file")
    parser.add_argument("--profile", default="cli-test", help="Bubble CLI profile to use")
    parser.add_argument("--dry-run", action="store_true", help="Only log commands, don't write to file")

    args = parser.parse_args()

    transformer = TokenTransformer()

    print(f"Reading tokens from {args.input}...")
    with open(args.input, 'r') as f:
        data = json.load(f)

    all_tokens = transformer.flatten_tokens(data)
    print(f"Found {len(all_tokens)} raw tokens")

    filtered = transformer.filter_tokens(all_tokens)
    print(f"Filtered: {len(filtered['color'])} colors, {len(filtered['font'])} typography tokens")

    commands = transformer.generate_commands(filtered, profile=args.profile)

    if args.dry_run:
        print("\nGenerated Commands (Dry Run):")
        for cmd in commands:
            print(f"  {cmd}")
    elif args.output:
        with open(args.output, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write(f"# Generated from {args.input}\n\n")
            for cmd in commands:
                f.write(f"{cmd}\n")
        print(f"\nWritten {len(commands)} commands to {args.output}")
    else:
        for cmd in commands:
            print(cmd)

if __name__ == "__main__":
    main()
