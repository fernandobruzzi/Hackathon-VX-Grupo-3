"""Texto de documentos limitados; conteúdo remoto é dado, nunca instrução executável."""

import io
import re
from html.parser import HTMLParser

from pypdf import PdfReader

from enrichment.trusted_sources import SourceDocument, SourceError


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts = []
        self.headings = {"title": [], "h1": [], "h2": []}
        self.heading = None
        self.seen_headings = set()

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self.skip += 1
        if tag in self.headings:
            self.heading = tag
        if tag in ("td", "th", "p", "div", "li", "br", "tr", "h1", "h2", "h3"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template") and self.skip:
            self.skip -= 1
        if tag == self.heading:
            self.seen_headings.add(tag)
            self.heading = None
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)
            if self.heading and self.heading not in self.seen_headings:
                self.headings[self.heading].append(data)


def document_pages(document: SourceDocument) -> tuple[str, ...]:
    if len(document.content) > 2_000_000:
        raise SourceError("Documento excede o limite de tamanho")
    if document.content_type == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(document.content))
            if reader.is_encrypted or len(reader.pages) > 10:
                raise SourceError("PDF protegido ou com mais de dez páginas")
            pages = []
            for page in reader.pages:
                stream = page.get_contents()
                if stream is not None and len(stream.get_data()) > 2_000_000:
                    raise SourceError("Página PDF excede o limite de conteúdo")
                pages.append(page.extract_text() or "")
            return tuple(pages)
        except SourceError:
            raise
        except Exception as error:
            raise SourceError("PDF sem texto utilizável") from error
    text = document.content.decode("utf-8", errors="replace")
    if document.content_type == "text/plain":
        return (text,)
    if document.content_type != "text/html":
        raise SourceError("Tipo de documento não permitido")
    parser = _HTMLText()
    parser.feed(text)
    heading = parser.headings["h1"] or parser.headings["h2"] or parser.headings["title"]
    anchor = " ".join(heading)
    return (
        "HTML_PRODUCT_TITLE: "
        + re.sub(r"\s+", " ", anchor).strip()
        + "\n"
        + re.sub(r"\s+", " ", "".join(parser.parts)).strip(),
    )
