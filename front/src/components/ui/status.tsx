import { Badge, type Tone } from "@/components/ui";
import type { MaterialStatus, OrderStatus, ProposalStatus, ProposalType, ReviewStatus, ValidationStatus } from "@/types/api";

const material: Record<MaterialStatus, [Tone, string]> = { ATIVO: ["success", "Ativo"], BLOQUEADO: ["danger", "Bloqueado"], OBSOLETO: ["neutral", "Obsoleto"] };
const validation: Record<ValidationStatus, [Tone, string]> = { VALID: ["success", "Válido"], INCOMPLETE: ["warning", "Incompleto"], INVALID: ["danger", "Inválido"], OUT_OF_SCOPE: ["neutral", "Fora do escopo"] };
const order: Record<OrderStatus, [Tone, string]> = {
  DRAFT: ["neutral", "Rascunho"], INCOMPLETE: ["warning", "Faltam dados"], READY_FOR_REVIEW: ["info", "Em revisão"],
  EXISTING: ["success", "Item já existe"], OUT_OF_SCOPE: ["neutral", "Fora do escopo"], PENDING_FISCAL: ["warning", "Pendente fiscal"],
  REGISTERED: ["success", "Cadastrado"], REJECTED: ["danger", "Rejeitado"],
};
const proposal: Record<ProposalStatus, [Tone, string]> = { PENDING: ["warning", "Pendente"], APPLIED: ["success", "Aplicada"], REJECTED: ["danger", "Rejeitada"], STALE: ["neutral", "Desatualizada"] };
const review: Record<ReviewStatus, [Tone, string]> = { PENDING: ["warning", "Pendente"], APPROVED: ["success", "Aprovada"], REJECTED: ["danger", "Rejeitada"], NOT_REQUIRED: ["neutral", "Não exigida"] };
export const proposalTypeLabel: Record<ProposalType, string> = {
  MERGE: "Unificação", PDM_CORRECTION: "Correção PDM", UNIT_CORRECTION: "Correção de unidade",
  NCM_CORRECTION: "Correção de NCM", ENRICHMENT: "Enriquecimento", COMPOSITE: "Composta",
};

const make = <K extends string>(map: Record<K, [Tone, string]>) => function S({ value }: { value: K }) {
  const [tone, label] = map[value];
  return <Badge tone={tone}>{label}</Badge>;
};
export const MaterialStatusBadge = make(material);
export const ValidationBadge = make(validation);
export const OrderStatusBadge = make(order);
export const ProposalStatusBadge = make(proposal);
export const ReviewBadge = make(review);
export const ProposalTypeBadge = ({ value }: { value: ProposalType }) => <Badge tone="brand">{proposalTypeLabel[value]}</Badge>;
