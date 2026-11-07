/** Rótulos da apresentação; a autorização continua exclusivamente na API. */
const reasons: Record<string, string> = {
  SAFE_CORRECTION: "Correção elegível pela política",
  UNTRUSTED_CLASS: "Classe ou nome do item sem confirmação",
  PROPOSAL_NOT_REPRODUCIBLE: "A proposta não pôde ser reproduzida pelas regras atuais",
  MATERIAL_NOT_ACTIVE: "O material não está ativo",
  CONFLICT: "Há informações conflitantes ou pendentes",
  REVIEW_REASONS_PRESENT: "A triagem exige revisão",
  REFERENCE_CHANGED: "A referência PDM mudou",
  FISCAL_CHANGE: "A proposta altera o NCM",
  FISCAL_CONTEXT: "Há contexto fiscal a revisar",
  PHYSICAL_CONVERSION: "A mudança exige conversão de unidade ou embalagem",
  UNSUPPORTED_ATTRIBUTES: "Os atributos não correspondem à evidência atual",
  CURRENT_TECHNICAL_CONTRADICTION: "A proposta contradiz dados técnicos existentes",
  UNIT_NOT_SAFE_ALIAS: "A unidade não é um alias seguro da unidade da classe",
  OUT_OF_SCOPE_CHANGE: "A proposta inclui alterações fora do escopo automático",
  OUT_OF_SCOPE_EFFECT: "A aplicação alteraria outros campos ou o estoque",
  PDM_INCOMPLETE_OR_INVALID: "O cadastro não atende ao PDM completo",
  TEXT_LOSS: "A descrição pode perder informação do texto original",
  ALREADY_STANDARDIZED: "A descrição já está padronizada",
  HUMAN_LOT_REVIEW: "A proposta pertence a uma revisão humana de lote",
  PROPOSAL_OR_RULES_CHANGED: "A proposta, o material ou as regras mudaram",
  UNSUPPORTED_OR_FISCAL_PROPOSAL: "O tipo de proposta ou a revisão fiscal exige decisão humana",
  IDENTITY_OR_INTEGRITY_CONFLICT: "A identidade colide com outro cadastro ou viola a integridade",
  PROPOSAL_ALREADY_DECIDED: "A proposta já recebeu decisão",
};
export function automaticReasonLabel(code: string) {
  return `${reasons[code] ?? "É necessária uma nova conferência"} (${code})`;
}
export const automaticStatusLabel: Record<string, string> = {
  DISABLED: "Desativada",
  WAITING: "Aguardando avaliação",
  RUNNING: "Em avaliação",
  COMPLETED: "Avaliação concluída",
  POLICY_CHANGED: "Política alterada",
  PAUSED: "Pausada",
  ELIGIBLE: "Elegível na simulação",
  APPLIED: "Aplicada pelo sistema",
  REVIEW: "Revisão humana",
  STALE: "Desatualizada",
  ERROR: "Falha na execução",
  SKIPPED: "Já decidida",
};
