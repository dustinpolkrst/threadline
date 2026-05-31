import re
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe


HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_THEME_PRESET = "threadline_light"


@dataclass(frozen=True)
class ThemeToken:
    key: str
    label: str


THEME_TOKENS = [
    ThemeToken("primary", "Primary"),
    ThemeToken("primary_hover", "Primary hover"),
    ThemeToken("background", "Background"),
    ThemeToken("panel", "Panel"),
    ThemeToken("text", "Text"),
    ThemeToken("muted_text", "Muted text"),
    ThemeToken("border", "Border"),
    ThemeToken("sidebar", "Sidebar"),
    ThemeToken("sidebar_text", "Sidebar text"),
    ThemeToken("success", "Success"),
    ThemeToken("warning", "Warning"),
    ThemeToken("danger", "Danger"),
    ThemeToken("info", "Info"),
]


THEME_PRESETS = {
    "threadline_light": {
        "label": "Threadline Light",
        "tokens": {
            "primary": "#155eef",
            "primary_hover": "#124ec7",
            "background": "#f6f8fb",
            "panel": "#ffffff",
            "text": "#172033",
            "muted_text": "#667085",
            "border": "#d9e2ef",
            "sidebar": "#0f172a",
            "sidebar_text": "#dbeafe",
            "success": "#047857",
            "warning": "#b45309",
            "danger": "#be123c",
            "info": "#1d4ed8",
        },
    },
    "github_dark": {
        "label": "GitHub Dark",
        "tokens": {
            "primary": "#58a6ff",
            "primary_hover": "#1f6feb",
            "background": "#0d1117",
            "panel": "#161b22",
            "text": "#f0f6fc",
            "muted_text": "#8b949e",
            "border": "#30363d",
            "sidebar": "#010409",
            "sidebar_text": "#f0f6fc",
            "success": "#3fb950",
            "warning": "#d29922",
            "danger": "#f85149",
            "info": "#58a6ff",
        },
    },
    "catppuccin_mocha": {
        "label": "Catppuccin Mocha",
        "tokens": {
            "primary": "#cba6f7",
            "primary_hover": "#b4befe",
            "background": "#1e1e2e",
            "panel": "#181825",
            "text": "#cdd6f4",
            "muted_text": "#a6adc8",
            "border": "#45475a",
            "sidebar": "#11111b",
            "sidebar_text": "#cdd6f4",
            "success": "#a6e3a1",
            "warning": "#f9e2af",
            "danger": "#f38ba8",
            "info": "#89b4fa",
        },
    },
    "nord": {
        "label": "Nord",
        "tokens": {
            "primary": "#5e81ac",
            "primary_hover": "#81a1c1",
            "background": "#2e3440",
            "panel": "#3b4252",
            "text": "#eceff4",
            "muted_text": "#d8dee9",
            "border": "#4c566a",
            "sidebar": "#242933",
            "sidebar_text": "#e5e9f0",
            "success": "#a3be8c",
            "warning": "#ebcb8b",
            "danger": "#bf616a",
            "info": "#88c0d0",
        },
    },
    "solarized_light": {
        "label": "Solarized Light",
        "tokens": {
            "primary": "#268bd2",
            "primary_hover": "#006d9c",
            "background": "#fdf6e3",
            "panel": "#eee8d5",
            "text": "#073642",
            "muted_text": "#657b83",
            "border": "#d7cfb7",
            "sidebar": "#073642",
            "sidebar_text": "#eee8d5",
            "success": "#859900",
            "warning": "#b58900",
            "danger": "#dc322f",
            "info": "#268bd2",
        },
    },
    "dracula": {
        "label": "Dracula",
        "tokens": {
            "primary": "#bd93f9",
            "primary_hover": "#ff79c6",
            "background": "#282a36",
            "panel": "#1f2030",
            "text": "#f8f8f2",
            "muted_text": "#c7c7d1",
            "border": "#44475a",
            "sidebar": "#191a21",
            "sidebar_text": "#f8f8f2",
            "success": "#50fa7b",
            "warning": "#f1fa8c",
            "danger": "#ff5555",
            "info": "#8be9fd",
        },
    },
    "high_contrast": {
        "label": "High Contrast",
        "tokens": {
            "primary": "#ffff00",
            "primary_hover": "#ffffff",
            "background": "#000000",
            "panel": "#101010",
            "text": "#ffffff",
            "muted_text": "#d0d0d0",
            "border": "#ffffff",
            "sidebar": "#000000",
            "sidebar_text": "#ffffff",
            "success": "#00ff66",
            "warning": "#ffff00",
            "danger": "#ff4444",
            "info": "#00ccff",
        },
    },
}


THEME_PRESET_CHOICES = [(key, preset["label"]) for key, preset in THEME_PRESETS.items()]
TOKEN_KEYS = [token.key for token in THEME_TOKENS]


CSS_VARIABLES = {
    "primary": "--tl-accent",
    "primary_hover": "--tl-accent-dark",
    "background": "--tl-bg",
    "panel": "--tl-panel",
    "text": "--tl-ink",
    "muted_text": "--tl-muted",
    "border": "--tl-line",
    "sidebar": "--tl-sidebar",
    "sidebar_text": "--tl-sidebar-text",
    "success": "--tl-success",
    "warning": "--tl-warning",
    "danger": "--tl-danger",
    "info": "--tl-info",
}


def validate_hex_color(value):
    if not value or not HEX_COLOR_RE.match(value):
        raise ValidationError("Enter a color as a 6-digit hex value, for example #155eef.")
    return value.lower()


def normalize_preset_key(preset_key):
    if preset_key in THEME_PRESETS:
        return preset_key
    return DEFAULT_THEME_PRESET


def preset_tokens(preset_key):
    preset = THEME_PRESETS[normalize_preset_key(preset_key)]
    return dict(preset["tokens"])


def clean_theme_custom_tokens(tokens):
    cleaned = {}
    for key, value in (tokens or {}).items():
        if key not in TOKEN_KEYS or value in ("", None):
            continue
        cleaned[key] = validate_hex_color(str(value).strip())
    return cleaned


def merged_theme_tokens(workspace=None, preset_key=None, custom_tokens=None):
    selected_preset = normalize_preset_key(preset_key or getattr(workspace, "theme_preset", DEFAULT_THEME_PRESET))
    tokens = preset_tokens(selected_preset)
    custom = custom_tokens if custom_tokens is not None else getattr(workspace, "theme_custom_tokens", {})
    tokens.update(clean_theme_custom_tokens(custom))
    return selected_preset, tokens


def theme_context_for_workspace(workspace=None):
    preset_key, tokens = merged_theme_tokens(workspace)
    return {
        "preset": preset_key,
        "preset_label": THEME_PRESETS[preset_key]["label"],
        "tokens": tokens,
        "css_variables": css_variables_for_tokens(tokens),
    }


def css_variables_for_tokens(tokens):
    declarations = []
    for key in TOKEN_KEYS:
        declarations.append(f"{CSS_VARIABLES[key]}: {conditional_escape(tokens[key])};")
    return mark_safe("\n      ".join(declarations))
