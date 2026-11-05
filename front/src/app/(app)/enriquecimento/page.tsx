import { Guard } from "@/components/shell/Guard";
import { EvidenceList } from "@/features/enrichment/EvidenceReview";

export default function Page() {
  return (
    <Guard perms={["enrichment:decide", "queue:read_audit"]}>
      <EvidenceList />
    </Guard>
  );
}
