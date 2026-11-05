import { notFound } from "next/navigation";
import { Guard } from "@/components/shell/Guard";
import { EvidenceReview } from "@/features/enrichment/EvidenceReview";
import { enrichment } from "@/mocks/data";

export function generateStaticParams() {
  return enrichment.map((e) => ({ id: e.proposal_id }));
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const proposal = enrichment.find((e) => e.proposal_id === id);
  if (!proposal) notFound();
  return (
    <Guard perms={["enrichment:decide", "queue:read_audit"]}>
      <EvidenceReview proposal={proposal} />
    </Guard>
  );
}
