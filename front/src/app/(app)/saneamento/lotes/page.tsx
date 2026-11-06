import { Guard } from "@/components/shell/Guard";
import { LotsPage } from "@/features/sanitization/LotsPage";

export default function Page() {
  return (
    <Guard perms={["merge:decide"]}>
      <LotsPage />
    </Guard>
  );
}
