import re
import math
from typing import Dict, Any, Tuple, Optional, List

class ColorMapper:
    """
    Maps RGBA colors (from Figma or other sources) to Bubble App Variables.
    Handles fuzzy matching to account for floating-point differences.
    """

    def __init__(self, app_data: Dict[str, Any]):
        self.color_map: list[tuple[tuple[int, int, int, float], str]] = []
        self.var_to_friendly: Dict[str, str] = {}
        self.name_to_var: Dict[str, str] = {}
        app_id = app_data.get("_id") or "unknown"
        # print(f"[ColorMapper] Initializing for App: {app_id}")
        self._build_map(app_data)

    @staticmethod
    def _normalize_name_token(value: str) -> str:
        token = str(value or "").strip().lower()
        token = token.replace("-", " ").replace("_", " ")
        token = re.sub(r"\s+", " ", token).strip()
        return token

    def _register_name_alias(self, label: str, var_name: str) -> None:
        token = self._normalize_name_token(label)
        if not token:
            return
        self.name_to_var[token] = var_name
        if token.startswith("gray "):
            self.name_to_var[token.replace("gray ", "grey ", 1)] = var_name
        if token.startswith("grey "):
            self.name_to_var[token.replace("grey ", "gray ", 1)] = var_name

    def _build_map(self, app_data: Dict[str, Any]):
        """Parses app settings to build a lookup table of colors."""
        try:
            settings = app_data.get("settings", {})
            client_safe = settings.get("client_safe", {})

            # Reserved names for Bubble system colors in CSS variables
            RESERVED_COLOR_NAMES = {
                "%3": "text",
                "primary": "primary",
                "alert": "alert",
                "success": "success",
                "destructive": "destructive",
                "background": "background",
                "surface": "surface",
                "primary_contrast": "primary_contrast"
            }

            # 1. System Colors (e.g., "primary", "surface", "%3")
            system_tokens = client_safe.get("color_tokens", {})
            # print(f"[ColorMapper] Checking {len(system_tokens)} system tokens...")
            for name, token_data in system_tokens.items():
                friendly_name = RESERVED_COLOR_NAMES.get(name, name)

                rgba_str = None
                if isinstance(token_data, dict):
                    rgba_str = token_data.get("%d1") or token_data.get("default")
                elif isinstance(token_data, str):
                    rgba_str = token_data
                if rgba_str and isinstance(rgba_str, str) and ("rgb" in rgba_str.lower() or rgba_str.startswith("#")):
                    rgba = self._parse_rgba(rgba_str)
                    if rgba:
                        # Map to var(--color_name_default)
                        var_name = f"var(--color_{friendly_name}_default)"
                        self.var_to_friendly[var_name] = friendly_name
                        self._register_name_alias(friendly_name, var_name)
                        self._register_name_alias(name, var_name)
                        # print(f"[ColorMapper]  + SYSTEM: {name} -> {friendly_name} {rgba}")
                        self.color_map.append((rgba, var_name))

            # 2. Custom Colors (User defined)
            user_tokens_wrapper = client_safe.get("color_tokens_user", {})
            user_tokens = user_tokens_wrapper.get("%d1") or user_tokens_wrapper.get("default", {})

            if user_tokens:
                # print(f"[ColorMapper] Checking {len(user_tokens)} custom tokens...")
                for key, token_data in user_tokens.items():
                    if isinstance(token_data, dict) and bool(token_data.get("%del")):
                        continue
                    rgba_str = token_data.get("rgba")
                    friendly_name = token_data.get("%nm") or token_data.get("name") or key
                    if rgba_str and isinstance(rgba_str, str) and ("rgb" in rgba_str.lower() or rgba_str.startswith("#")):
                        rgba = self._parse_rgba(rgba_str)
                        if rgba:
                            # Map to var(--color_key_default) e.g., var(--color_b3vev_default)
                            var_name = f"var(--color_{key}_default)"
                            self.var_to_friendly[var_name] = friendly_name
                            self._register_name_alias(friendly_name, var_name)
                            self._register_name_alias(key, var_name)
                            # print(f"[ColorMapper]  + CUSTOM: {friendly_name} [{key}] {rgba}")
                            self.color_map.append((rgba, var_name))
            else:
                pass # print("[ColorMapper] No custom tokens found in color_tokens_user")

        except Exception as e:
            print(f"[ColorMapper] Error building map: {e}")
            import traceback
            traceback.print_exc()

    def _parse_rgba(self, rgba_str: str) -> Optional[Tuple[int, int, int, float]]:
        """Parses 'rgba(r,g,b,a)', 'rgb(r,g,b)' or '#RRGGBB' string into (r, g, b, a) tuple."""
        # Normalize whitespace
        rgba_str = rgba_str.replace(" ", "")

        # 1. Matches rgba(127, 86, 217, 1.0)
        match = re.search(r"rgba?\((\d+),(\d+),(\d+),?([0-9.]+)?\)", rgba_str)
        if match:
            r = int(match.group(1))
            g = int(match.group(2))
            b = int(match.group(3))
            a = float(match.group(4)) if match.group(4) else 1.0
            return (int(r), int(g), int(b), float(a))

        # 2. Matches hex #RRGGBB or #RGB
        if rgba_str.startswith("#"):
            hex_val = rgba_str.lstrip("#")
            if len(hex_val) == 3:
                hex_val = "".join([c*2 for c in hex_val])
            if len(hex_val) == 6:
                r = int(hex_val[0:2], 16)
                g = int(hex_val[2:4], 16)
                b = int(hex_val[4:6], 16)
                return (r, g, b, 1.0)

        return None

    def find_closest_token(self, r: float, g: float, b: float, a: float, tolerance: float = 10.0) -> Optional[str]:
        matches = self.find_all_matching_tokens(r, g, b, a, tolerance)
        return matches[0] if matches else None

    def find_all_matching_tokens(self, r: float, g: float, b: float, a: float, tolerance: float = 10.0) -> List[str]:
        """
        Finds all Bubble color variables within tolerance for the given RGBA values.
        Sorted by distance (closest first).
        """
        matches = []
        target_a = a

        for (cr, cg, cb, ca), var_name in self.color_map:
            # Check alpha first (must be very close)
            if abs(ca - target_a) > 0.05:
                continue

            # Calculate Euclidean distance in RGB
            dist = math.sqrt((r - cr)**2 + (g - cg)**2 + (b - cb)**2)

            if dist <= tolerance:
                matches.append((dist, var_name))

        # Sort by distance
        matches.sort(key=lambda x: x[0])
        return [m[1] for m in matches]

    def find_closest_token_rgb(self, r: float, g: float, b: float, tolerance: float = 10.0, preferred_key: Optional[str] = None) -> Optional[Tuple[str, tuple]]:
        """
        Finds the closest Bubble color variable ignoring alpha.
        Returns (var_name, (r, g, b, a)) of the match.

        If preferred_key is provided, and multiple matches exist within tolerance,
        it will prefer the one matching the friendly name or key.
        """
        matches = []

        for (cr, cg, cb, ca), var_name in self.color_map:
            # Euclidean distance in RGB only
            dist = math.sqrt((r - cr)**2 + (g - cg)**2 + (b - cb)**2)

            if dist <= tolerance:
                matches.append({
                    "dist": dist,
                    "var_name": var_name,
                    "tuple": (cr, cg, cb, ca),
                    "friendly": self.var_to_friendly.get(var_name, "").lower()
                })

        if not matches:
            return None

        # Sort by distance first
        matches.sort(key=lambda x: x["dist"])
        best_match = matches[0]

        # If we have a preference, see if any match within tolerance is the one we want
        if preferred_key:
            pref = preferred_key.lower()
            for m in matches:
                # Check if friendly name or the var_name itself contains the preferred key
                if pref in m["friendly"] or f"_{pref}_" in m["var_name"]:
                    # CRITICAL: Only allow preference to override if it's "close enough" to the best match.
                    # e.g. If Gray 50 is dist 1.4 and Background is dist 8.6, we keep Gray 50.
                    # If both are dist 0.0, we pick Background.
                    if m["dist"] <= best_match["dist"] + 5.0:
                        return m["var_name"], m["tuple"]

        # Default to the absolute closest
        return best_match["var_name"], best_match["tuple"]

    def add_token(self, key: str, rgba_str: str, friendly_name: Optional[str] = None):
        """Adds a new token to the map dynamically."""
        rgba = self._parse_rgba(rgba_str)
        if not rgba:
            if rgba_str.startswith("#"):
                try:
                    r, g, b = tuple(int(rgba_str.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
                    rgba = (r, g, b, 1.0)
                except:
                    return
            else:
                return

        var_name = f"var(--color_{key}_default)"
        friendly = friendly_name or key
        self.var_to_friendly[var_name] = friendly
        self.color_map.append((rgba, var_name))

    def find_variable_by_name(self, friendly_name: str) -> Optional[str]:
        """Finds the Bubble color variable name by its friendly name (case-insensitive).
        Normalizes hyphens to spaces to handle common naming variations (e.g., brand-50 vs Brand 50).
        """
        target = self._normalize_name_token(friendly_name)
        if not target:
            return None
        direct = self.name_to_var.get(target)
        if direct:
            return direct
        for var_name, name in self.var_to_friendly.items():
            if self._normalize_name_token(name) == target:
                return var_name
        return None
