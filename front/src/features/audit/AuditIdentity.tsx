import { Code, Td } from "@/components/ui";
import type { AuditEvent } from "@/types/api";

/** Eventos automáticos não recebem um usuário ou papel humano fictício. */
export function AuditIdentity({ event }: { event: AuditEvent }) {
  const system = event.actor_type === "SYSTEM";
  return (
    <>
      <Td className="font-semibold">{system ? "Sistema" : event.actor}</Td>
      <Td className="[overflow-wrap:anywhere]">
        <Code>{system ? "Processo automático" : (event.effective_role ?? "—")}</Code>
      </Td>
    </>
  );
}
