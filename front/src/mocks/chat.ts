import type { ChatTurnResponse, MaterialCardData, ToolCall } from "@/types/api";

/**
 * Agente simulado para o wireframe. Integração: POST /api/v1/chat/message
 * (contrato 6.2) — o backend devolve exatamente este formato.
 */

const tc = (
  id: number,
  name: ToolCall["name"],
  input: ToolCall["input"],
  result: ToolCall["result"],
  duration_ms: number,
): ToolCall => ({
  id: `tool-call-${String(id).padStart(3, "0")}`,
  name,
  transport: "MCP_STDIO",
  input,
  status: "SUCCEEDED",
  duration_ms,
  result,
});

const PARAFUSO_BASE = {
  ROSCA: "METRICA GROSSA",
  BITOLA: "M12",
  COMPRIMENTO: "50MM",
  "CLASSE RESISTENCIA": null as string | null,
  MATERIAL: "ACO CARBONO",
  ACABAMENTO: "ZINCADO BRANCO",
  NORMA: "DIN 933",
};

export interface ChatState {
  step: "start" | "parafuso_needs_class" | "done";
  version: number;
}
export const initialChatState: ChatState = { step: "start", version: 0 };

const base = (state: ChatState) => ({
  request_id: `req-chat-${String(state.version + 1).padStart(3, "0")}`,
  session_id: "33333333-3333-4333-8333-333333333333",
  session_version: state.version + 1,
  order_id: "44444444-4444-4444-8444-444444444444",
});

export function runMockTurn(
  state: ChatState,
  message: string,
): { res: ChatTurnResponse; next: ChatState } {
  const m = message.toLowerCase();
  const next: ChatState = { ...state, version: state.version + 1 };

  // 2º turno do parafuso: usuário informa a classe
  if (state.step === "parafuso_needs_class") {
    const cls = m.match(/10[.,]9/)
      ? "10.9"
      : m.match(/12[.,]9/)
        ? "12.9"
        : m.match(/8[.,]8/)
          ? "8.8"
          : null;
    if (cls) {
      const attrs = { ...PARAFUSO_BASE, "CLASSE RESISTENCIA": cls };
      const desc = `PARAFUSO SEXTAVADO; ROSCA: METRICA GROSSA; BITOLA: M12; COMPRIMENTO: 50MM; CLASSE RESISTENCIA: ${cls}; MATERIAL: ACO CARBONO; ACABAMENTO: ZINCADO BRANCO; NORMA: DIN 933`;
      const card: MaterialCardData = {
        pdm_class_id: "PDM001",
        pdm_class_name: "PARAFUSO SEXTAVADO",
        attributes: attrs,
        pdm_description: desc,
        validation_status: "VALID",
        missing_attributes: [],
        ncm: { suggested: "7318.15.00", status: "CONSISTENT" },
        duplicate_check_status: "NO_MATCH",
        can_submit: true,
      };
      next.step = "done";
      return {
        next,
        res: {
          ...base(state),
          status: "READY_TO_SUBMIT",
          assistant_message: `Fechado: classe ${cls}. Procurei na base e não existe item ativo com a mesma identidade — o 17730415 é parecido, mas não tem classe de resistência e está em CX, então não dá para reutilizar com segurança. O pedido está pronto: confira a descrição no padrão e envie para revisão.`,
          tool_calls: [
            tc(
              3,
              "validate_and_format_pdm",
              { pdm_class_id: "PDM001", pdm_version: "pdm-kit-v1", attributes: attrs },
              { validation_status: "VALID", missing_attributes: [] },
              41,
            ),
            tc(
              4,
              "search_similar_materials",
              {
                query: "parafuso sextavado M12x50 8.8 zincado DIN 933",
                pdm_class_id: "PDM001",
                limit: 5,
              },
              {
                match_status: "NO_MATCH",
                candidates_reviewed: 3,
                closest: "17730415 (CLASSE RESISTENCIA ausente)",
              },
              212,
            ),
            tc(
              5,
              "check_ncm_consistency",
              { pdm_class_id: "PDM001", ncm: "7318.15.00", ncm_version: "ncm-demo-v1" },
              { format_ok: true, exists: true, coherent: true, review_required: false },
              58,
            ),
          ],
          material_card: card,
        },
      };
    }
    return {
      next: state,
      res: {
        ...base(state),
        status: "NEEDS_INPUT",
        assistant_message:
          "Ainda preciso da classe de resistência. As mais comuns são 8.8 (uso geral) e 10.9 (alta resistência). Se não souber, veja a marcação na cabeça do parafuso que vai ser trocado.",
        tool_calls: [],
        material_card: parafusoIncomplete(),
      },
    };
  }

  if (m.includes("parafuso")) {
    next.step = "parafuso_needs_class";
    return {
      next,
      res: {
        ...base(state),
        status: "NEEDS_INPUT",
        assistant_message:
          "Entendi: parafuso sextavado M12 x 50 mm, aço carbono, zincado branco, DIN 933. Falta a classe de resistência — ela define quanta força o parafuso aguenta e muda preço e uso. É 8.8 ou 10.9?",
        tool_calls: [
          tc(
            1,
            "get_pdm_template",
            { pdm_class_id: "PDM001", pdm_version: "pdm-kit-v1" },
            { noun: "PARAFUSO", qualifier: "SEXTAVADO", required_attributes_count: 7 },
            18,
          ),
          tc(
            2,
            "validate_and_format_pdm",
            { pdm_class_id: "PDM001", pdm_version: "pdm-kit-v1", attributes: PARAFUSO_BASE },
            { validation_status: "INCOMPLETE", missing_attributes: ["CLASSE RESISTENCIA"] },
            37,
          ),
        ],
        material_card: parafusoIncomplete(),
      },
    };
  }

  if (
    m.includes("fleetguard") ||
    m.includes("lf9009") ||
    m.includes("lf 9009") ||
    m.includes("filtro")
  ) {
    next.step = "done";
    return {
      next,
      res: {
        ...base(state),
        status: "EXISTING",
        assistant_message:
          "Esse item já existe: código 16031971, ativo. Mesmo fabricante (Fleetguard) e mesma referência (LF9009). Tem 4 peças no centro 1200. Não precisa abrir cadastro novo — use o código abaixo na sua requisição.",
        tool_calls: [
          tc(
            1,
            "search_similar_materials",
            {
              query: "filtro Fleetguard LF 9009",
              pdm_class_id: "PDM100",
              attributes: { FABRICANTE: "FLEETGUARD", "REFERENCIA FABRICANTE": "LF9009" },
              limit: 5,
            },
            {
              match_status: "REVIEW_REQUIRED",
              top: "16031971",
              match_type: "EXACT_MANUFACTURER_REFERENCE",
              ranking_score: 0.97,
            },
            188,
          ),
          tc(
            2,
            "get_pdm_template",
            { pdm_class_id: "PDM100", pdm_version: "pdm-kit-v1" },
            { identity_mode: "MANUFACTURER_REFERENCE" },
            15,
          ),
        ],
        material_card: {
          pdm_class_id: "PDM100",
          pdm_class_name: "FILTRO OLEO LUBRIFICANTE",
          attributes: { FABRICANTE: "FLEETGUARD", "REFERENCIA FABRICANTE": "LF9009" },
          pdm_description:
            "FILTRO OLEO LUBRIFICANTE; FABRICANTE: FLEETGUARD; REFERENCIA FABRICANTE: LF9009",
          validation_status: "VALID",
          missing_attributes: [],
          ncm: { suggested: "8421.23.00", status: "CONSISTENT" },
          duplicate_check_status: "MATCH_FOUND",
          can_submit: false,
          existing: {
            material_code: "16031971",
            status: "ATIVO",
            pdm_description: "FILTRO OLEO LUBRIFICANTE FLEETGUARD LF9009",
            match_type: "Fabricante + referência iguais",
            reason: "Classe PDM100 identifica o item por fabricante e referência.",
            inventory: [{ center_code: "1200", quantity: "4", unit: "PC" }],
          },
        },
      },
    };
  }

  return {
    next: state,
    res: {
      ...base(state),
      status: "NEEDS_INPUT",
      assistant_message:
        'Me diga o que você precisa como diria no almoxarifado: o tipo do item, medidas, material e, se tiver, fabricante e referência. Ex.: "filtro Fleetguard LF 9009" ou "parafuso sextavado M12x50 zincado".',
      tool_calls: [],
      material_card: {
        pdm_class_id: "—",
        pdm_class_name: "Classe ainda não identificada",
        attributes: {},
        pdm_description: null,
        validation_status: "INCOMPLETE",
        missing_attributes: [],
        ncm: { suggested: null, status: "PENDING_VALIDATION" },
        duplicate_check_status: "PENDING",
        can_submit: false,
      },
    },
  };
}

function parafusoIncomplete(): MaterialCardData {
  return {
    pdm_class_id: "PDM001",
    pdm_class_name: "PARAFUSO SEXTAVADO",
    attributes: PARAFUSO_BASE,
    pdm_description: null,
    validation_status: "INCOMPLETE",
    missing_attributes: ["CLASSE RESISTENCIA"],
    ncm: { suggested: "7318.15.00", status: "PENDING_VALIDATION" },
    duplicate_check_status: "PENDING",
    can_submit: false,
  };
}

export const SUGGESTIONS = [
  "Preciso de parafuso sextavado M12x50, aço carbono, zincado branco, DIN 933.",
  "filtro Fleetguard LF 9009",
];
