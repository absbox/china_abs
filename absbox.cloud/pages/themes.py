'''
    Theme definitions for Absbox Cloud.
    
    Every design value (colors, borders, shadows, fonts) lives in a
    dictionary below. To switch the site theme, change ACTIVE_THEME to
    the name of any dict in THEMES.
'''

DEFAULT_LIGHT = {
    "id": "default-light",
    "name": "Default Bulma (Light)",
    "colors": {
        "bg": "#f5f5f5",
        "surface": "#ffffff",
        "surface_alt": "#f0f0f0",
        "text": "#363636",
        "text_muted": "#767676",
        "primary": "#00d1b2",
        "primary_light": "#4de1c8",
        "accent": "#3273dc",
        "link": "#3273dc",
        "link_hover": "#2366d1",
        "border": "#dbdbdb",
        "border_light": "#e8e8e8",
        "success": "#48c774",
        "warning": "#ffdd57",
        "danger": "#f14668",
        "info": "#3e8ed0",
        "shadow": "rgba(0,0,0,0.15)",
        "selected_row": "#f5f5f5",
        "table_stripe": "#fafafa",
        "table_header": "#eef3f3",
        "navbar_bg": "#ffffff",
        "navbar_text": "#363636",
        "button_bg": "#00d1b2",
        "button_text": "#ffffff",
        "input_border": "#dbdbdb",
        "input_bg": "#ffffff",
        "tab_active": "#00d1b2",
        "tab_inactive": "#f5f7f9",
        "heading": "#363636",
    },
    "border": {
        "width": "0px",
        "style": "solid",
        "color": "#dbdbdb",
        "radius": "4px",
    },
    "shadow": {
        "offset_x": "0px",
        "offset_y": "0px",
        "blur": "0px",
        "color": "rgba(0,0,0,0)",
    },
    "font": {
        "family": "BlinkMacSystemFont,-apple-system,'Segoe UI',Roboto,Oxygen,Ubuntu,Cantarell,'Open Sans','Helvetica Neue',sans-serif",
        "heading_family": "BlinkMacSystemFont,-apple-system,'Segoe UI',Roboto,Oxygen,Ubuntu,Cantarell,'Open Sans','Helvetica Neue',sans-serif",
        "size_base": "16px",
        "heading_weight": "400",
    },
}


NEO_BRUTALISM_LITE_BROWN = {
    "id": "neo-brutalism-brown",
    "name": "Neo-Brutalism Lite (Brown)",
    "colors": {
        "bg": "#f2ead9",
        "surface": "#fdf9f0",
        "surface_alt": "#e6d8bf",
        "text": "#2c1a0e",
        "text_muted": "#6b5138",
        "primary": "#8b5e34",
        "primary_light": "#c9a06a",
        "accent": "#d9a441",
        "link": "#7a4a23",
        "link_hover": "#4f2c10",
        "border": "#3d2914",
        "border_light": "#a5825f",
        "success": "#5c7a3c",
        "warning": "#d9a441",
        "danger": "#b03a1e",
        "info": "#4a6f8a",
        "shadow": "#3d2914",
        "selected_row": "#e6d8bf",
        "table_stripe": "#f7efe1",
        "table_header": "#dfc9a6",
        "navbar_bg": "#3d2914",
        "navbar_text": "#f2ead9",
        "button_bg": "#8b5e34",
        "button_text": "#fdf9f0",
        "input_border": "#a5825f",
        "input_bg": "#fdf9f0",
        "tab_active": "#8b5e34",
        "tab_inactive": "#efe4cf",
        "heading": "#2c1a0e",
        "quoted": "#fdf9f0",
    },
    "border": {
        "width": "2px",
        "style": "solid",
        "color": "#3d2914",
        "radius": "2px",
    },
    "shadow": {
        "offset_x": "4px",
        "offset_y": "4px",
        "blur": "0px",
        "color": "#3d2914",
    },
    "font": {
        "family": "'Space Mono','Courier New',monospace",
        "heading_family": "'Space Grotesk','Arial Black',sans-serif",
        "size_base": "15px",
        "heading_weight": "700",
    },
    # optional: values used only for the `.dark-mode` override
    "dark": {
        "bg": "#241812",
        "surface": "#33241b",
        "surface_alt": "#3f2d21",
        "text": "#f2ead9",
        "text_muted": "#c4a98c",
        "heading": "#f2ead9",
        "link": "#d9a441",
        "link_hover": "#f0c96f",
        "accent": "#d9a441",
        "primary": "#b07d3f",
        "primary_light": "#d9a441",
        "button_bg": "#d9a441",
        "button_text": "#241812",
        "navbar_bg": "#120b06",
        "navbar_text": "#f2ead9",
        "tab_active": "#d9a441",
        "tab_inactive": "#3f2d21",
        "border": "#d9a441",
        "border_light": "#8a6a4a",
        "shadow": "#120b06",
        "table_stripe": "#2e2118",
        "table_header": "#4a3322",
        "input_bg": "#33241b",
        "input_border": "#8a6a4a",
        "selected_row": "#462f1e",
        "quoted": "#33241b",
    },
}


themes = {
    "default": DEFAULT_LIGHT,
    "neo_brutalism_lite_brown": NEO_BRUTALISM_LITE_BROWN,
}

NEO_BRUTALISM_LITE_BROWN["font_href"] = "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Space+Mono&display=swap"

# --------------------------------------------------------------------------
#  Select which theme to render. Change this string to switch the whole site.
# --------------------------------------------------------------------------
ACTIVE_THEME = "neo_brutalism_lite_brown"


def _flatten(prefix, d, out):
    for k, v in d.items():
        part = k.replace("_", "-")
        key = f"--absbox-{prefix}-{part}" if prefix else f"--absbox-{part}"
        if isinstance(v, dict):
            _flatten(f"{prefix}-{part}", v, out)
        else:
            out[key] = v


def css_vars(theme: dict) -> str:
    """Turn the nested theme dict into a CSS `:root { ... }` block."""
    flat = {}
    _flatten("colors", theme["colors"], flat)
    _flatten("border", theme["border"], flat)
    _flatten("shadow", theme["shadow"], flat)
    _flatten("font", theme["font"], flat)
    body = "\n".join(f"        {k}: {v};" for k, v in flat.items())
    return ":root {\n" + body + "\n    }"


def dark_css_vars(theme: dict) -> str:
    """Generate a `.dark-mode { ... }` override block from theme['dark']."""
    dark = theme.get("dark")
    if not dark:
        return ""
    flat = {}
    _flatten("colors", dark, flat)
    body = "\n".join(f"        {k}: {v};" for k, v in flat.items())
    return ".dark-mode {\n" + body + "\n    }"


def theme_style(theme: dict) -> str:
    """Full <style> content for the given theme (light vars + dark override)."""
    return css_vars(theme) + "\n    " + dark_css_vars(theme)


def theme_fonts_href(theme: dict) -> str | None:
    """Google Font <link> href if the theme asks for web fonts, else None."""
    return theme.get("font_href")


def active_theme() -> dict:
    return themes.get(ACTIVE_THEME, themes["default"])


def set_theme(name: str) -> dict:
    """Set the active theme by name (from the main file) and return it."""
    global ACTIVE_THEME
    if name not in themes:
        raise KeyError(f"Unknown theme {name!r}. Available: {list(themes)}")
    ACTIVE_THEME = name
    return themes[name]