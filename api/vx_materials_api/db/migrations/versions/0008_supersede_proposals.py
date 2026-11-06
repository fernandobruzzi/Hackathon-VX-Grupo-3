"""Proposta nova do batch substitui a pendente anterior dos mesmos tipo e membros.

O batch não tem acesso a `audit_logs`. Esta função, com os privilégios de quem migra, faz só uma
coisa: marca como STALE, com auditoria de sistema, as propostas PENDING que uma proposta recém-gravada
substitui. Propostas APPLIED, REJECTED ou já STALE nunca mudam.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_MEMBER_IDS = "(SELECT array_agg(m->>'material_id' ORDER BY m->>'material_id') FROM jsonb_array_elements({}) m)"

FUNCTION = f"""
CREATE FUNCTION supersede_proposals(new_ids uuid[]) RETURNS integer
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    WITH fresh AS (
        SELECT id, tenant_id, job_id, proposal_type, changeset_hash, changeset->>'dataset_id' AS dataset_id,
               {_MEMBER_IDS.format("members")} AS member_ids
        FROM sanitization_proposals
        WHERE id = ANY(new_ids) AND status = 'PENDING'
    ), pending AS (
        SELECT id, tenant_id, proposal_type, changeset_hash, changeset->>'dataset_id' AS dataset_id,
               {_MEMBER_IDS.format("members")} AS member_ids
        FROM sanitization_proposals
        WHERE status = 'PENDING' AND id <> ALL(new_ids)
          AND tenant_id IN (SELECT tenant_id FROM fresh) AND proposal_type IN (SELECT proposal_type FROM fresh)
    ), replaced AS (
        SELECT DISTINCT ON (p.id) p.id, f.id AS superseded_by, f.job_id
        FROM pending p
        JOIN fresh f ON f.tenant_id = p.tenant_id AND f.proposal_type = p.proposal_type
            AND f.dataset_id = p.dataset_id AND f.member_ids = p.member_ids
        WHERE f.changeset_hash <> p.changeset_hash
        ORDER BY p.id, f.id
    ), stale AS (
        UPDATE sanitization_proposals s
        SET status = 'STALE', version = s.version + 1, updated_at = now()
        FROM replaced r
        WHERE s.id = r.id AND s.status = 'PENDING'
        RETURNING s.id, s.tenant_id, s.version, s.members, s.changeset, r.superseded_by, r.job_id
    ), audited AS (
        INSERT INTO audit_logs (
            tenant_id, actor_type, action, entity_type, entity_id, before_json, after_json, reason, job_id
        )
        SELECT tenant_id, 'SYSTEM', 'PROPOSAL_SUPERSEDED', 'sanitization_proposal', id::text,
               jsonb_build_object('status', 'PENDING', 'version', version - 1, 'members', members,
                                  'changeset', changeset),
               jsonb_build_object('status', 'STALE', 'version', version, 'superseded_by', superseded_by::text),
               'Substituida por proposta mais recente do batch para os mesmos tipo e membros',
               job_id
        FROM stale
        RETURNING 1
    )
    SELECT count(*)::integer FROM audited
$$
"""


def upgrade():
    op.execute(FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION supersede_proposals(uuid[]) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION supersede_proposals(uuid[]) TO batch_user")


def downgrade():
    op.execute("DROP FUNCTION supersede_proposals(uuid[])")
