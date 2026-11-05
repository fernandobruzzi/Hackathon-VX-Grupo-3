import { notFound } from "next/navigation";
import { Guard } from "@/components/shell/Guard";
import { ProposalReview } from "@/features/sanitization/ProposalReview";
import { proposals } from "@/mocks/queue";

// Static export: uma página por proposta mock. Na integração, trocar por /saneamento/revisao?id=… (client fetch).
export function generateStaticParams() {
  return proposals.map((p) => ({ id: p.id }));
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const proposal = proposals.find((p) => p.id === id);
  if (!proposal) notFound();
  return (
    <Guard perms={["queue:read", "queue:read_audit"]}>
      <ProposalReview proposal={proposal} />
    </Guard>
  );
}
