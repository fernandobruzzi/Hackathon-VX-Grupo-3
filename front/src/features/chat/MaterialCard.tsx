import { CheckCircle2, CircleDashed, Copy, Send } from "lucide-react";
import { Badge, Button, Card, Code } from "@/components/ui";
import { MaterialStatusBadge, ValidationBadge } from "@/components/ui/status";
import { cn } from "@/lib/format";
import type { MaterialCardData } from "@/types/api";

/** Ficha do pedido em construção. Espelha material_card do contrato 6.2. */
export function MaterialCard({
  card,
  onSubmit,
  submitted,
}: {
  card: MaterialCardData;
  onSubmit?: () => void;
  submitted?: boolean;
}) {
  const entries = Object.entries(card.attributes);
  return (
    <div className="flex flex-col gap-4">
      {card.existing && (
        <Card tone="block" className="flex flex-col gap-3">
          <span className="text-xs font-extrabold tracking-[0.04em] text-esmeralda uppercase">
            Item já existe na base
          </span>
          <div className="flex items-baseline justify-between gap-3">
            <Code className="text-2xl font-medium text-esmeralda">
              {card.existing.material_code}
            </Code>
            <MaterialStatusBadge value={card.existing.status} />
          </div>
          <p className="text-sm leading-6">{card.existing.pdm_description}</p>
          <p className="text-xs leading-5 text-on-profundo/80">
            {card.existing.match_type} · {card.existing.reason}
          </p>
          <div className="rounded-sm bg-white/8 p-3">
            <p className="mb-1 text-[11px] font-bold tracking-[0.06em] text-on-profundo/70 uppercase">
              Estoque nos seus centros
            </p>
            {card.existing.inventory.map((i) => (
              <p key={i.center_code} className="font-mono text-sm">
                Centro {i.center_code} · {i.quantity} {i.unit}
              </p>
            ))}
          </div>
          <Button variant="primary" size="sm" className="self-start">
            <Copy className="size-4" /> Copiar código
          </Button>
        </Card>
      )}

      <Card className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-extrabold tracking-[0.04em] text-verde uppercase">
              Ficha do pedido
            </p>
            <p className="mt-1 text-lg font-bold">{card.pdm_class_name}</p>
            <Code className="text-muted">{card.pdm_class_id} · pdm-kit-v1</Code>
          </div>
          <ValidationBadge value={card.validation_status} />
        </div>

        {entries.length > 0 ? (
          <dl className="divide-y divide-surface-2 rounded-sm ring-1 ring-surface-2 ring-inset">
            {entries.map(([k, v]) => {
              const missing = v === null;
              return (
                <div
                  key={k}
                  className={cn(
                    "grid grid-cols-[1fr_1.2fr] gap-3 px-3 py-2 text-sm",
                    missing && "bg-ink",
                  )}
                >
                  <dt className="font-semibold text-muted">{k}</dt>
                  <dd
                    className={cn("font-mono text-[13px]", missing ? "font-bold text-aviso" : "")}
                  >
                    {missing ? "faltando" : v}
                  </dd>
                </div>
              );
            })}
          </dl>
        ) : (
          <p className="text-sm text-muted">
            Os atributos aparecem aqui conforme a conversa avança.
          </p>
        )}

        <div className="grid grid-cols-2 gap-3 text-sm">
          <Check
            label="Duplicidade"
            state={card.duplicate_check_status === "PENDING" ? "pending" : "done"}
            detail={
              {
                PENDING: "não verificada",
                NO_MATCH: "nenhum item igual",
                MATCH_FOUND: "item encontrado",
              }[card.duplicate_check_status]
            }
          />
          <Check
            label="NCM"
            state={card.ncm.status === "CONSISTENT" ? "done" : "pending"}
            detail={
              card.ncm.suggested
                ? `${card.ncm.suggested}${card.ncm.status === "CONSISTENT" ? "" : " · a validar"}`
                : "—"
            }
          />
        </div>

        {card.pdm_description && (
          <div className="rounded-sm bg-ink p-3">
            <p className="mb-1 text-[11px] font-bold tracking-[0.06em] text-muted uppercase">
              Descrição no padrão PDM
            </p>
            <p className="font-mono text-[13px] leading-5">{card.pdm_description}</p>
          </div>
        )}

        {!card.existing &&
          (submitted ? (
            <Badge tone="info" className="self-start">
              Enviado para revisão · Governança PDM
            </Badge>
          ) : (
            <div className="flex flex-col gap-2">
              <Button onClick={onSubmit} disabled={!card.can_submit}>
                <Send className="size-4" /> Enviar pedido para revisão
              </Button>
              {!card.can_submit && (
                <p className="text-xs text-muted">
                  Libera quando a ficha estiver válida e sem duplicidade.
                </p>
              )}
            </div>
          ))}
      </Card>
    </div>
  );
}

function Check({
  label,
  state,
  detail,
}: {
  label: string;
  state: "done" | "pending";
  detail: string;
}) {
  return (
    <div className="flex items-start gap-2 rounded-sm bg-ink p-3">
      {state === "done" ? (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-verde" />
      ) : (
        <CircleDashed className="mt-0.5 size-4 shrink-0 text-muted" />
      )}
      <div>
        <p className="font-semibold">{label}</p>
        <p className="font-mono text-xs text-muted">{detail}</p>
      </div>
    </div>
  );
}
