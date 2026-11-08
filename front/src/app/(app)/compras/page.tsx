import { Guard } from "@/components/shell/Guard";
import { PurchasingPage } from "@/features/purchasing/PurchasingPage";

export default function Page() {
  return (
    <Guard perms={["purchasing:read"]}>
      <PurchasingPage />
    </Guard>
  );
}
