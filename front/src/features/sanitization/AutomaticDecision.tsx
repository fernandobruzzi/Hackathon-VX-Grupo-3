import { automaticReasonLabel } from "@/lib/automatic-corrections";
import type { components } from "@/types/api.generated";

type Outcome = components["schemas"]["ProposalAutomation"];
export function AutomaticDecision({
  mode,
  automation,
  status,
}: {
  mode?: "HUMAN" | "AUTOMATIC";
  automation?: Outcome | null;
  status: string;
}) {
  return (
    <div className="mt-1 text-xs text-muted">
      {status === "APPLIED" && (
        <p>
          {mode === "AUTOMATIC" ? "Aplicado automaticamente pelo sistema" : "Aprovado por pessoa"}
        </p>
      )}
      {automation && (
        <>
          {automation.mode === "SIMULATE" && (
            <p>
              Simulação:{" "}
              {automation.status === "ELIGIBLE" ? "elegível, sem aplicação" : "revisão necessária"}
            </p>
          )}
          {automation.status !== "APPLIED" && automation.status !== "ELIGIBLE" && (
            <p>Motivos para revisão: {automation.reasons.map(automaticReasonLabel).join("; ")}</p>
          )}
          {automation.index_status === "PENDING" || automation.index_status === "FAILED" ? (
            <p role="status">Atualização da busca pendente</p>
          ) : null}
        </>
      )}
    </div>
  );
}
