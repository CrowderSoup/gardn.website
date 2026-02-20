from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urlparse
from django.utils.html import escape


_ALLOWED_BIO_TAGS = {"p", "br", "strong", "em", "b", "i", "u", "a", "ul", "ol", "li", "blockquote", "code", "pre"}
_ALLOWED_BIO_ATTRS = {"a": {"href", "title"}}
_DROP_CONTENT_TAGS = {"script", "style", "iframe", "object", "embed", "noscript"}
_ALLOWED_HREF_SCHEMES = {"http", "https", "mailto"}


class _BioHtmlSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._out: list[str] = []
        self._drop_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if self._drop_depth:
            if lowered in _DROP_CONTENT_TAGS:
                self._drop_depth += 1
            return
        if lowered in _DROP_CONTENT_TAGS:
            self._drop_depth = 1
            return
        if lowered not in _ALLOWED_BIO_TAGS:
            return

        rendered_attrs: list[str] = []
        allowed_attrs = _ALLOWED_BIO_ATTRS.get(lowered, set())
        for name, raw_value in attrs:
            attr = name.lower()
            if attr not in allowed_attrs:
                continue
            value = (raw_value or "").strip()
            if not value:
                continue
            if lowered == "a" and attr == "href":
                parsed = urlparse(value)
                scheme = parsed.scheme.lower()
                if scheme and scheme not in _ALLOWED_HREF_SCHEMES:
                    continue
            rendered_attrs.append(f'{attr}="{escape(value)}"')

        if lowered == "a":
            rendered_attrs.append('rel="nofollow noopener noreferrer"')

        attrs_text = f" {' '.join(rendered_attrs)}" if rendered_attrs else ""
        self._out.append(f"<{lowered}{attrs_text}>")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if self._drop_depth:
            if lowered in _DROP_CONTENT_TAGS:
                self._drop_depth -= 1
            return
        if lowered in _ALLOWED_BIO_TAGS:
            self._out.append(f"</{lowered}>")

    def handle_data(self, data: str) -> None:
        if not self._drop_depth:
            self._out.append(escape(data))

    def handle_entityref(self, name: str) -> None:
        if not self._drop_depth:
            self._out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._drop_depth:
            self._out.append(f"&#{name};")

    def get_html(self) -> str:
        return "".join(self._out)


def slug_from_me_url(me_url: str) -> str:
    parsed = urlparse(me_url)
    base = f"{parsed.netloc}{parsed.path}".strip("/").replace("/", "-")
    clean = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in base.lower())
    return "-".join(segment for segment in clean.split("-") if segment)[:64] or "site"


def sanitize_user_bio_html(value: str) -> str:
    sanitizer = _BioHtmlSanitizer()
    sanitizer.feed(value or "")
    sanitizer.close()
    return sanitizer.get_html().strip()
