import { Suspense } from "react";
import { Guard } from "@/components/shell/Guard";
import { RemoteEvidenceReview } from "@/features/enrichment/RemoteEvidenceReview";

export default function Page() {
  return (
    <Guard perms={["enrichment:decide", "queue:read_audit"]}>
      <Suspense fallback={<p>Consultando evidências…</p>}>
        <RemoteEvidenceReview />
      </Suspense>
    </Guard>
  );
}
