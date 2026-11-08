import { Badge, Card, Eyebrow } from "@/components/ui";
import { fmtInt } from "@/lib/format";
import { fulfillmentRows, outcomeRows, type JourneyRow, type RequestJourney } from "@/lib/journey";

function Row({ row }: { row: JourneyRow }) {
  return (
    <li className="flex flex-col gap-1 text-sm">
      <div className="flex items-start justify-between gap-3">
        <span className="font-semibold">{row.label}</span>
        {row.value === null ? (
          <Badge tone="neutral">Indisponível</Badge>
        ) : (
          <span className="font-mono">{row.value}</span>
        )}
      </div>
      {row.note && <span className="text-xs text-muted">{row.note}</span>}
    </li>
  );
}

/** Jornada do solicitante: contagens das solicitações reais, sem quantidades nem valores. */
export function JourneyIndicators({ journey }: { journey: RequestJourney }) {
  const open = journey.open;
  return (
    <section className="mt-6" aria-labelledby="journey-title">
      <Eyebrow className="mb-4">
        <span id="journey-title">Jornada do solicitante</span>
      </Eyebrow>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs font-extrabold tracking-[0.04em] text-verde uppercase">
              Solicitações encerradas · como foram atendidas
            </p>
            <span className="text-xs text-muted">
              {fmtInt(journey.requests_total)} solicitações nos centros autorizados
            </span>
          </div>
          <ul className="mt-5 flex flex-col gap-4">
            {fulfillmentRows(journey).map((row) => (
              <Row key={row.key} row={row} />
            ))}
          </ul>
          {open && (
            <p className="mt-5 text-xs text-muted">
              Em andamento: {fmtInt(open.em_identificacao)} em identificação,{" "}
              {fmtInt(open.aguardando_cadastro)} aguardando cadastro e {fmtInt(open.em_atendimento)}{" "}
              em atendimento.
            </p>
          )}
        </Card>
        <Card>
          <p className="text-xs font-extrabold tracking-[0.04em] text-verde uppercase">
            Resultado da jornada
          </p>
          <ul className="mt-5 flex flex-col gap-4">
            {outcomeRows(journey).map((row) => (
              <Row key={row.key} row={row} />
            ))}
          </ul>
          <p className="mt-5 text-xs text-muted">
            Contagens de registros persistidos. Encaminhar a Compras não confirma compra nem
            recebimento; indicadores sem dados ficam indisponíveis, sem estimativa.
          </p>
        </Card>
      </div>
    </section>
  );
}
