"""Análise dos pedidos de cadastro do kit (#24): classe, atributos e o que falta, sem gravar nada.

O texto do pedido e o anexo passam pelos mesmos classificador e extrator do saneamento, e o PDM diz
o que falta. A checagem de duplicidade contra a base fica com quem tem o banco (a API), porque
depende do índice de busca.
"""

import csv
import io
from dataclasses import dataclass, field

from domain.centers import split_center
from domain.contracts import ClassificationInput, ClassificationRepository, ExtractionRepository, PdmCatalog
from domain.identity import resolve_item_name
from domain.pdm_validator import validate_pdm

STATUS_OUT_OF_SCOPE = "OUT_OF_SCOPE"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_READY = "READY_FOR_REVIEW"


@dataclass(frozen=True)
class OrderRow:
    source_order_id: str
    original_text: str
    attachment_text: str | None
    center_code: str | None
    urgency: str | None


@dataclass(frozen=True)
class OrderAnalysis:
    status: str
    pdm_class_id: str | None = None
    item_name: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    missing_attributes: tuple[str, ...] = ()
    identity_key: str | None = None
    formatted_description: str | None = None
    # Evidência recebida: a descrição formatada pode omitir revisão e outros trechos não consumidos.
    source_text: str = ""


def read_orders(content: bytes) -> list[OrderRow]:
    rows = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
    return [
        OrderRow(
            source_order_id=row["ID_PEDIDO"],
            original_text=row["TEXTO_SOLICITACAO"],
            attachment_text=(row.get("CONTEUDO_ANEXO") or "").strip() or None,
            center_code=split_center(row.get("CENTRO"))[0] or None,
            urgency=(row.get("URGENCIA") or "").strip() or None,
        )
        for row in rows
    ]


def analyze_order(
    order: OrderRow, catalog: PdmCatalog, classifier: ClassificationRepository, extractor: ExtractionRepository
) -> OrderAnalysis:
    """Classe e atributos do pedido. Sem classe, fica fora de escopo; faltando atributo, incompleto."""
    text = " ".join(part for part in (order.original_text, order.attachment_text) if part)
    classification = classifier.classify(
        ClassificationInput(order.original_text, attachment_text=order.attachment_text)
    )
    class_id = classification.pdm_class_id
    if class_id is None:
        return OrderAnalysis(STATUS_OUT_OF_SCOPE, source_text=text)
    pdm_class = catalog.classes[class_id]
    item_name = resolve_item_name(pdm_class, [evidence.matched_name for evidence in classification.evidence])
    extraction = extractor.extract(pdm_class, text)
    attributes = {name: value.value for name, value in extraction.attributes.items()}
    validation = validate_pdm(catalog, class_id, attributes, item_name=item_name)
    missing = tuple(attribute.name for attribute in validation.missing_attributes)
    if item_name is None and len(pdm_class.item_names) > 1:
        missing = ("ITEM", *missing)
    if missing or not validation.can_submit or validation.identity_key is None:
        return OrderAnalysis(
            STATUS_INCOMPLETE, class_id, item_name, attributes, missing or ("REVISAO",), source_text=text
        )
    return OrderAnalysis(
        STATUS_READY,
        class_id,
        item_name,
        attributes,
        (),
        validation.identity_key,
        validation.formatted_description,
        source_text=text,
    )
