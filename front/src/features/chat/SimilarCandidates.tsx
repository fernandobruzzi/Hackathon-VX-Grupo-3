import { Button, Card, Code } from "@/components/ui";
import { MaterialStatusBadge } from "@/components/ui/status";
import type { ChatAction, SimilarCandidate } from "@/types/api";

/** Texto que aparece na conversa. O Agent decide pela ação, então o texto pode mudar livremente. */
const DISMISS_MESSAGE = "Nenhum desses é o meu item";
const pickMessage = (code: string) => `É o item ${code}`;

/** Itens parecidos sem identidade verificada: o solicitante confirma um deles ou descarta todos. */
export function SimilarCandidates({
  candidates,
  onReply,
  disabled,
}: {
  candidates: SimilarCandidate[];
  onReply: (message: string, action: ChatAction) => void;
  disabled?: boolean;
}) {
  return (
    <Card className="flex flex-col gap-3">
      <div>
        <p className="text-xs font-extrabold tracking-[0.04em] text-aviso uppercase">
          Itens parecidos na base
        </p>
        <p className="mt-1 text-sm leading-6 text-muted">
          Confira se o seu item é um destes antes de pedir um cadastro novo.
        </p>
      </div>
      <ul className="flex flex-col gap-2">
        {candidates.map((item) => (
          <li key={item.material_code} className="flex flex-col gap-2 rounded-sm bg-ink p-3">
            <div className="flex items-baseline justify-between gap-3">
              <Code className="text-base">{item.material_code}</Code>
              <MaterialStatusBadge value={item.status} />
            </div>
            <p className="text-sm leading-5">{item.pdm_description}</p>
            {item.status === "BLOQUEADO" && item.active_code_target && (
              <p className="text-xs leading-5 text-muted">
                Bloqueado: o código a usar é <Code>{item.active_code_target}</Code>
              </p>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="self-start"
              disabled={disabled}
              onClick={() =>
                onReply(pickMessage(item.material_code), {
                  type: "PICK_CANDIDATE",
                  material_code: item.material_code,
                })
              }
            >
              É este
            </Button>
          </li>
        ))}
      </ul>
      <Button
        variant="secondary"
        size="sm"
        className="self-start"
        disabled={disabled}
        onClick={() => onReply(DISMISS_MESSAGE, { type: "DISMISS_CANDIDATES" })}
      >
        Nenhum desses é o meu item
      </Button>
    </Card>
  );
}
