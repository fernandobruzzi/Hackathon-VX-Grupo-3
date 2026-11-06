"""Experimento manual x solução: planilha cega para revisores e chave separada (#207).

Partes, sorteadas com semente fixa em quadros ordenados por id, para o mesmo commit, dados e semente
gerarem o mesmo pacote:

- A: unificações propostas pelo sistema (o sistema diz: mesmo item);
- B: pares muito parecidos no texto que o sistema não une (sugestões do `tokens_v1`, desligado);
- C: correções de descrição de nível 2, as que vão para aprovação em lote;
- D: uma fatia de parafusos sextavados (PDM001) para agrupar à mão, com cronômetro.

A e B saem misturadas na mesma aba, sem a parte nem a decisão do sistema. A chave fica em outro
arquivo, que não vai para os revisores. Nada aqui altera dados, propostas ou decisões.
"""

import hashlib
import json
import random
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from pipelines.corrections import propose_corrections
from pipelines.evaluate_sanitization import implementation_fingerprint
from pipelines.merge_sample import sample_merges
from pipelines.sanitize import _catalog, analysis_signature, analyze_material, merge_proposals, read_csv_records
from repositories.candidates import get_candidate_repository
from repositories.candidates.tokens_v1 import TokensV1CandidateRepository
from repositories.classification import get_classification_repository
from repositories.corrections import get_correction_repository
from repositories.extraction import get_extraction_repository
from repositories.normalization import get_normalization_repository

SCHEMA = "experiment-v1"
SEED = 207
PAIRS_SIZE = 40
CORRECTIONS_SIZE = 40
SLICE_CLASS = "PDM001"
SLICE_SIZE = 120
SLICE_GROUPS = 15
NEAR_POOL = 200  # os pares mais parecidos são os que confundem; o sorteio sai deles
SHEET_PAIRS = "Mesmo item"
SHEET_CORRECTIONS = "Descrição"
SHEET_MANUAL = "Manual"
SHEET_GUIDE = "Como revisar"
PACKAGE_CELL = "B3"  # identificador do pacote, conferido contra a chave
REVIEWER_CELL = "B4"

_BOLD = Font(bold=True)
_ANSWER = PatternFill("solid", fgColor="FFF2CC")
_WRAP = Alignment(wrap_text=True, vertical="top")


def _pairs(codes) -> set[tuple[str, str]]:
    ordered = sorted(codes)
    return {(a, b) for i, a in enumerate(ordered) for b in ordered[i + 1 :]}


def _member_text(record) -> str:
    parts = [f"[{record.code}] {record.description}"]
    if record.manufacturer:
        parts.append(f"Fabricante: {record.manufacturer}")
    if record.reference:
        parts.append(f"Referência: {record.reference}")
    parts.append(f"Unidade: {record.unit}")
    return " | ".join(parts)


def select(
    csv_path: str,
    pdm_workbook: str,
    seed: int = SEED,
    pairs_size: int = PAIRS_SIZE,
    corrections_size: int = CORRECTIONS_SIZE,
    slice_size: int = SLICE_SIZE,
) -> dict:
    """Escolhe os casos e devolve a chave completa, sem gerar a planilha."""
    catalog = _catalog(pdm_workbook)
    classifier, extractor = get_classification_repository(catalog), get_extraction_repository()
    normalizer = get_normalization_repository()
    records = read_csv_records(csv_path)
    by_code = {record.code: record for record in records}
    analyzed = [analyze_material(record, catalog, classifier, extractor) for record in records]
    active = {m.record.code for m in analyzed if m.record.status == "ATIVO"}
    rng = random.Random(seed)

    merges = merge_proposals(analyzed, catalog, get_candidate_repository(), normalizer)
    merged = set().union(*(_pairs(p.material_codes) for p in merges)) if merges else set()
    part_a = sample_merges(merges, size=pairs_size, seed=seed)

    near = sorted(
        {
            (group.score, a, b)
            for group in TokensV1CandidateRepository().find(analyzed, catalog)
            for a, b in _pairs(group.codes)
            if (a, b) not in merged and a in active and b in active
        },
        key=lambda item: (-item[0], item[1], item[2]),
    )
    pool = near[: max(pairs_size * 5, NEAR_POOL)]
    part_b = rng.sample(pool, min(pairs_size, len(pool)))

    corrections, _ = propose_corrections(analyzed, catalog, normalizer, get_correction_repository())
    tier2 = sorted(
        (
            p
            for p in corrections
            if p.proposal_type == "PDM_CORRECTION"
            and (p.changeset.get("review_lane") or {}).get("tier") == 2
            and any(change["field"] == "description" for change in p.changeset["changes"])
        ),
        key=lambda p: p.id,
    )
    part_c = rng.sample(tier2, min(corrections_size, len(tier2)))

    in_class = {m.record.code: m for m in analyzed if m.pdm_class_id == SLICE_CLASS and m.record.code in active}
    class_groups = sorted((p for p in merges if all(code in in_class for code in p.material_codes)), key=lambda p: p.id)
    # Grupos de duplicidade escondidos na fatia, enquanto couberem no tamanho pedido.
    chosen: set[str] = set()
    for proposal in rng.sample(class_groups, min(SLICE_GROUPS, len(class_groups))):
        if len(chosen) + len(proposal.material_codes) <= slice_size:
            chosen.update(proposal.material_codes)
    grouped = {code for p in class_groups for code in p.material_codes}
    others = sorted(set(in_class) - grouped)
    chosen |= set(rng.sample(others, min(len(others), max(0, slice_size - len(chosen)))))
    part_d = sorted(chosen)
    rng.shuffle(part_d)

    cases = [("A", sorted(p.material_codes)) for p in part_a] + [("B", [a, b]) for _, a, b in part_b]
    rng.shuffle(cases)
    rng.shuffle(part_c)
    key = {
        "schema": SCHEMA,
        "seed": seed,
        "sizes": {"pairs": pairs_size, "corrections": corrections_size, "slice": slice_size},
        "dataset_sha256": hashlib.sha256(Path(csv_path).read_bytes()).hexdigest(),
        "analysis_signature": analysis_signature(catalog, classifier, extractor),
        "implementation": implementation_fingerprint(),
        "frames": {
            "merges": len(merges),
            "near_pairs_not_merged": len(near),
            "near_pool": len(pool),
            "tier2_descriptions": len(tier2),
            "slice_class_active": len(in_class),
            "slice_class_groups": len(class_groups),
        },
        "pairs": {
            f"P{i:03d}": {
                "part": part,
                "codes": codes,
                "system_same_item": part == "A",
                "members": [_member_text(by_code[code]) for code in codes],
            }
            for i, (part, codes) in enumerate(cases, 1)
        },
        "corrections": {},
        "slice": {},
    }
    for i, proposal in enumerate(part_c, 1):
        code = proposal.material_codes[0]
        key["corrections"][f"D{i:03d}"] = {
            "code": code,
            "proposal_id": proposal.id,
            "lot_key": proposal.changeset["review_lane"]["lot_key"],
            "original": by_code[code].description,
            "proposed": next(c["after"] for c in proposal.changeset["changes"] if c["field"] == "description"),
        }
    for code in part_d:
        record = by_code[code]
        key["slice"][code] = {
            "identity_key": in_class[code].identity_key,
            "description": record.description,
            "unit": record.unit,
        }
    key["package_id"] = package_id(key)
    return key


def package_id(key: dict) -> str:
    """Identifica o conteúdo do pacote; a planilha leva o mesmo valor para ser conferida."""
    content = {name: key[name] for name in ("schema", "seed", "analysis_signature", "dataset_sha256", "pairs")}
    content["corrections"] = key["corrections"]
    content["slice"] = key["slice"]
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _style(sheet, widths: dict[str, int], answer_columns: str, first_row: int = 2) -> None:
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    for row in sheet.iter_rows(min_row=first_row):
        for cell in row:
            cell.alignment = _WRAP
            if cell.column_letter in answer_columns:
                cell.fill = _ANSWER


def _choices(sheet, options: str, cells: str) -> None:
    validation = DataValidation(type="list", formula1=options, allow_blank=True)
    sheet.add_data_validation(validation)
    validation.add(cells)


GUIDE = [
    "Antes de começar, escreva seu nome na célula B4. Não consulte o sistema, o código nem colegas até terminar.",
    "",
    "Aba 'Mesmo item': cada linha traz 2 ou mais materiais. SIM se são o mesmo item físico (podem ser trocados",
    "  sem nenhuma diferença), NAO se são itens diferentes, NAO SEI se o texto não permite decidir.",
    "  Fabricantes diferentes de peças equivalentes contam como NAO. Escreva a evidência em poucas palavras.",
    "Aba 'Descrição': a proposta está CORRETA se descreve o mesmo item sem errar nenhum valor.",
    "  PERDEU INFORMAÇÃO se algo útil do original sumiu, como uma medida, um material ou uma aplicação.",
    "Aba 'Manual': tarefa cronometrada. Anote a hora de início e de fim (hh:mm). Em até 40 minutos, dê o mesmo",
    "  número na coluna GRUPO aos parafusos que são o mesmo item. Pare quando o tempo acabar e anote a linha.",
    "",
    "A ordem foi embaralhada. Tempo estimado: 1 h a 1 h 30 nas duas primeiras abas, mais 40 min no Manual.",
]


def workbook(key: dict) -> Workbook:
    wb = Workbook()
    wb.properties.creator = "vx-back experiment-packets"
    guide = wb.active
    guide.title = SHEET_GUIDE
    guide["A1"] = "Experimento manual x solução: revisão às cegas"
    guide["A1"].font = Font(bold=True, size=13)
    guide["A3"], guide[PACKAGE_CELL] = "Pacote", key["package_id"]
    guide["A4"], guide[REVIEWER_CELL] = "Revisor (nome)", None
    guide[REVIEWER_CELL].fill = _ANSWER
    for row, line in enumerate(GUIDE, 6):
        guide.cell(row=row, column=1, value=line)
    guide.column_dimensions["A"].width = 120

    pairs = wb.create_sheet(SHEET_PAIRS)
    pairs.append(["Caso", "Materiais (descrição | fabricante | referência | unidade)", "MESMO ITEM?", "Evidência"])
    for case_id, case in key["pairs"].items():
        pairs.append([case_id, "\n".join(case["members"]), None, None])
    _choices(pairs, '"SIM,NAO,NAO SEI"', f"C2:C{len(key['pairs']) + 1}")
    _style(pairs, {"A": 7, "B": 110, "C": 14, "D": 40}, "CD")

    corrections = wb.create_sheet(SHEET_CORRECTIONS)
    corrections.append(
        ["Caso", "Código", "Descrição original", "Descrição proposta", "CORRETA?", "PERDEU INFORMAÇÃO?", "O que"]
    )
    for case_id, case in key["corrections"].items():
        corrections.append([case_id, case["code"], case["original"], case["proposed"], None, None, None])
    last = len(key["corrections"]) + 1
    _choices(corrections, '"SIM,NAO,NAO SEI"', f"E2:E{last}")
    _choices(corrections, '"SIM,NAO"', f"F2:F{last}")
    _style(corrections, {"A": 7, "B": 11, "C": 60, "D": 60, "E": 12, "F": 14, "G": 35}, "EFG")

    manual = wb.create_sheet(SHEET_MANUAL)
    manual.append(["Início (hh:mm)", None, "Fim (hh:mm)", None, "Parei na linha", None])
    manual.append([])
    manual.append(["Linha", "Código", "Descrição original", "Unidade", "GRUPO", "Descrição padronizada (opcional)"])
    for line, (code, item) in enumerate(key["slice"].items(), 1):
        manual.append([line, code, item["description"], item["unit"], None, None])
    _style(manual, {"A": 7, "B": 11, "C": 80, "D": 8, "E": 12, "F": 60}, "EF", first_row=4)
    for cell in ("B1", "D1", "F1"):
        manual[cell].fill = _ANSWER

    for sheet in (pairs, corrections, manual):
        header = sheet[3] if sheet is manual else sheet[1]
        for cell in header:
            cell.font = _BOLD
        sheet.freeze_panes = "C4" if sheet is manual else "B2"
    return wb


def experiment_packets(csv_path: str, pdm_workbook: str, out_dir: str, seed: int = SEED, **sizes) -> dict:
    """Grava a planilha e a chave; devolve o resumo, sem textos dos casos."""
    key = select(csv_path, pdm_workbook, seed, **sizes)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sheet_path = out / f"experimento-{key['package_id']}.xlsx"
    key_path = out / f"chave-{key['package_id']}-NAO-ENVIAR.json"
    buffer = BytesIO()
    workbook(key).save(buffer)
    sheet_path.write_bytes(buffer.getvalue())
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=1, sort_keys=True))
    return {
        "package_id": key["package_id"],
        "sheet": str(sheet_path),
        "key": str(key_path),
        "analysis_signature": key["analysis_signature"],
        "frames": key["frames"],
        "cases": {"pairs": len(key["pairs"]), "corrections": len(key["corrections"]), "slice": len(key["slice"])},
    }
