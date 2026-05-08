import bleach
import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

ALLOWED_TAGS = [
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
]
ALLOWED_ATTRIBUTES = {"a": ["href", "title", "rel", "target"]}


@register.filter
def render_markdown(value):
    html = markdown.markdown(value or "", extensions=["extra", "sane_lists"])
    clean = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, protocols=["http", "https", "mailto"])
    clean = bleach.linkify(clean)
    return mark_safe(clean)
