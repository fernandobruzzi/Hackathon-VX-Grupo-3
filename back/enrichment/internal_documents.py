"""Bundle interno versionado: texto fornecido e rastreável, nunca aprovação declarada."""

import hashlib
import json
import re
import unicodedata
from typing import TYPE_CHECKING

from domain.contracts import MaterialRecord, PdmCatalog
from pipelines.sanitize import analyze_material
from repositories.classification import get_classification_repository
from repositories.extraction import get_extraction_repository

if TYPE_CHECKING:
    from pipelines.internal_enrichment import InternalSource

SCHEMA_VERSION = "internal-documents-v1"
MAX_BYTES = 2_000_000
MAX_DOCUMENTS = 500
MAX_TEXT_CHARS = 20_000
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_BUNDLE_FIELDS = {"schema_version", "dataset_id", "documents"}
_REQUIRED_DOCUMENT_FIELDS = {"id", "title", "text", "kind"}
_OPTIONAL_DOCUMENT_FIELDS = {"short_description", "manufacturer", "manufacturer_reference"}


def _identifier(value):
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError("Identificador de documento ou dataset inválido")
    return value


def _content(content):
    if not isinstance(content, bytes) or not content or len(content) > MAX_BYTES:
        raise ValueError("Bundle documental vazio ou excede o limite de bytes")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Chave JSON repetida no bundle documental")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Constante JSON não permitida no bundle documental")


def _text(value, field, limit, *, required=False, multiline=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f"Campo documental inválido ou excede o limite: {field}")
    allowed_controls = "\n\r\t" if multiline else ""
    if any(unicodedata.category(char) in {"Cc", "Cs"} and char not in allowed_controls for char in value):
        raise ValueError(f"Caractere de controle no campo documental: {field}")


def parse_bundle(content: bytes, dataset_id: str) -> dict:
    """Valida sem corrigir ou completar bytes; campos desconhecidos são recusados."""
    _identifier(dataset_id)
    _content(content)
    try:
        bundle = json.loads(
            content.decode("utf-8-sig"), object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Bundle documental deve ser JSON UTF-8 válido") from error
    if not isinstance(bundle, dict) or set(bundle) != _BUNDLE_FIELDS:
        raise ValueError("Campos do bundle documental inválidos")
    if bundle["schema_version"] != SCHEMA_VERSION or bundle["dataset_id"] != dataset_id:
        raise ValueError("Versão ou dataset do bundle documental divergente")
    documents = bundle["documents"]
    if not isinstance(documents, list) or not 1 <= len(documents) <= MAX_DOCUMENTS:
        raise ValueError("Quantidade de documentos fora do limite")
    identifiers = set()
    for document in documents:
        if (
            not isinstance(document, dict)
            or not _REQUIRED_DOCUMENT_FIELDS <= set(document)
            or set(document) - (_REQUIRED_DOCUMENT_FIELDS | _OPTIONAL_DOCUMENT_FIELDS)
        ):
            raise ValueError("Campos do documento inválidos")
        identifier = _identifier(document["id"])
        if identifier in identifiers:
            raise ValueError("Identificador documental repetido")
        identifiers.add(identifier)
        if document["kind"] != "INTERNAL_DOCUMENT":
            raise ValueError("Tipo documental não permitido")
        _text(document["title"], "title", 200, required=True)
        _text(document["text"], "text", MAX_TEXT_CHARS, required=True, multiline=True)
        for field in _OPTIONAL_DOCUMENT_FIELDS & set(document):
            _text(document[field], field, 120 if field == "short_description" else 200)
    return bundle


def bundle_object_key(content: bytes, dataset_id: str) -> str:
    """Chave imutável dos bytes, vinculada ao dataset da importação."""
    _identifier(dataset_id)
    _content(content)
    return f"references/internal-sources/{dataset_id}/{hashlib.sha256(content).hexdigest()}.json"


def load_supplemental_sources(
    content: bytes, dataset_id: str, catalog: PdmCatalog, object_key: str
) -> list["InternalSource"]:
    """Converte somente texto validado; não acessa rede, armazenamento ou propostas."""
    from pipelines.internal_enrichment import InternalSource

    bundle = parse_bundle(content, dataset_id)
    if object_key != bundle_object_key(content, dataset_id):
        raise ValueError("Chave documental não corresponde ao dataset e aos bytes")
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    sha256 = hashlib.sha256(content).hexdigest()
    sources = []
    for document in bundle["documents"]:
        record = MaterialRecord(
            document["id"],
            "ATIVO",
            document["text"],
            short_description=document.get("short_description", ""),
            manufacturer=document.get("manufacturer", ""),
            reference=document.get("manufacturer_reference", ""),
        )
        sources.append(
            InternalSource(
                analyze_material(record, catalog, classifier, extractor),
                "internal-documents",
                sha256,
                object_key,
                title=document["title"],
            )
        )
    return sources
