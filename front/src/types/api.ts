/**
 * Tipos espelhando os contratos da seção 6 da Arquitetura.
 * Na integração, substituir por tipos gerados do OpenAPI (api/contracts/openapi.json)
 * em src/shared/api-types.ts — ver README.
 */

export type Role = "ROLE_SOLICITANTE" | "ROLE_GOVERNANCA_PDM" | "ROLE_AUDITOR_FISCAL";
export type PersonaLabel = "SOLICITANTE_OPERACAO" | "GESTOR_CADASTRO" | "AUDITOR_FISCAL";

export type Permission =
  | "chat:use"
  | "materials:read"
  | "inventory:read"
  | "orders:create"
  | "orders:read_own"
  | "orders:update_own"
  | "orders:decide"
  | "queue:read"
  | "queue:read_audit"
  | "merge:decide"
  | "enrichment:decide"
  | "ncm:decide"
  | "batch:run"
  | "metrics:quality"
  | "metrics:financial"
  | "audit:own"
  | "audit:technical"
  | "audit:fiscal";

export interface Me {
  user: { id: string; display_name: string; roles: Role[] };
  permissions: Permission[];
  scope: { center_codes: string[] };
  demo: { enabled: boolean; active_persona: PersonaLabel };
  csrf_token: string;
}

export type MaterialStatus = "ATIVO" | "BLOQUEADO" | "OBSOLETO";
export type ValidationStatus = "VALID" | "INCOMPLETE" | "INVALID" | "OUT_OF_SCOPE";
export type ChatStatus = "NEEDS_INPUT" | "EXISTING" | "READY_TO_SUBMIT" | "SUBMITTED" | "OUT_OF_SCOPE";

export interface ToolCall {
  id: string;
  name:
    | "search_similar_materials"
    | "get_pdm_template"
    | "validate_and_format_pdm"
    | "check_ncm_consistency"
    | "enrich_from_trusted_source";
  transport: "MCP_STDIO";
  input: Record<string, unknown>;
  status: "SUCCEEDED" | "FAILED" | "PENDING";
  duration_ms: number;
  result: Record<string, unknown>;
}

export interface InventoryRow { center_code: string; quantity: string; unit: string }

export interface ExistingMatch {
  material_code: string;
  status: MaterialStatus;
  pdm_description: string;
  match_type: string;
  reason: string;
  inventory: InventoryRow[];
}

export interface MaterialCardData {
  pdm_class_id: string;
  pdm_class_name: string;
  attributes: Record<string, string | null>;
  pdm_description: string | null;
  validation_status: ValidationStatus;
  missing_attributes: string[];
  ncm: { suggested: string | null; status: "PENDING_VALIDATION" | "CONSISTENT" | "REVIEW_REQUIRED" };
  duplicate_check_status: "PENDING" | "NO_MATCH" | "MATCH_FOUND";
  existing?: ExistingMatch;
  can_submit: boolean;
}

export interface ChatMessage {
  id: string;
  author: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ChatTurnResponse {
  request_id: string;
  session_id: string;
  session_version: number;
  order_id: string;
  status: ChatStatus;
  assistant_message: string;
  tool_calls: ToolCall[];
  material_card: MaterialCardData;
}

export type ProposalType = "MERGE" | "PDM_CORRECTION" | "UNIT_CORRECTION" | "NCM_CORRECTION" | "ENRICHMENT" | "COMPOSITE";
export type ReviewStatus = "PENDING" | "APPROVED" | "REJECTED" | "NOT_REQUIRED";
export type ProposalStatus = "PENDING" | "APPLIED" | "REJECTED" | "STALE";

export interface ProposalMember {
  material_code: string;
  status: MaterialStatus;
  description: string;
  unit: string;
  ncm: string | null;
  inventory: InventoryRow[];
  value_brl: string;
}

export interface Proposal {
  id: string;
  version: number;
  proposal_type: ProposalType;
  status: ProposalStatus;
  title: string;
  material_codes: string[];
  suggested_primary_code: string | null;
  identity: { mode: "MANUFACTURER_REFERENCE" | "TECHNICAL_ATTRIBUTES"; summary: string };
  members: ProposalMember[];
  after: { description: string; ncm: string | null; unit: string; attributes: Record<string, string> };
  changes: { field: string; before: string | null; after: string; source: string }[];
  technical_review_status: ReviewStatus;
  fiscal_review_status: ReviewStatus;
  conflicts: string[];
  ranking_score: number;
  created_at: string;
}

export interface EvidenceItem {
  attribute: string;
  current_value: string | null;
  proposed_value: string;
  source_title: string;
  source_url: string;
  source_excerpt: string;
  source_page: string | null;
  confidence: "ALTA" | "MEDIA" | "BAIXA";
  divergence: string | null;
}

export interface EnrichmentProposal {
  proposal_id: string;
  version: number;
  material_code: string;
  original_description: string;
  proposed_description: string;
  pdm_class_id: string;
  status: ProposalStatus;
  evidence: EvidenceItem[];
}

export type OrderStatus =
  | "DRAFT" | "INCOMPLETE" | "READY_FOR_REVIEW" | "EXISTING" | "OUT_OF_SCOPE"
  | "PENDING_FISCAL" | "REGISTERED" | "REJECTED";

export interface RegistrationOrder {
  id: string;
  origin: "CHAT" | "IMPORT";
  requester: string | null;
  original_text: string;
  center_code: string;
  pdm_class_id: string | null;
  status: OrderStatus;
  missing_attributes: string[];
  material_code: string | null;
  updated_at: string;
}

export interface BatchJob {
  id: string;
  job_type: "SANITIZE" | "IMPORT_ORDERS" | "ENRICH_REAL_PRODUCTS";
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  requested_by: string;
  pdm_version: string;
  ncm_version: string;
  progress: { processed: number; total: number };
  counts: { proposals: number; merges: number; ncm: number; enrichment: number };
  started_at: string;
  finished_at: string | null;
}

export interface AuditEvent {
  id: string;
  actor: string;
  effective_role: Role;
  action: string;
  entity: string;
  reason: string | null;
  request_id: string;
  created_at: string;
}

export interface DashboardMetrics {
  dataset_id: string;
  comparison_status: "AFTER_SNAPSHOT_NOT_AVAILABLE" | "AVAILABLE";
  before: { materials_total: number; active: number; blocked: number; obsolete: number; missing_ncm: number; noncanonical_unit: number };
  after: DashboardMetrics["before"] | null;
  pipeline: { proposals_total: number; pending: number; applied: number; rejected: number; stale: number };
  evaluation: { reviewed_pairs: number; merge_precision: number | null; duplicate_recall: number | null };
  financial: { currency: "BRL"; data_origin: string; inventory_book_value: string; realized_savings: string | null; estimated_savings: string | null };
}
