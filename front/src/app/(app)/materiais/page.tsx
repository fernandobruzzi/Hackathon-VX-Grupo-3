import { Guard } from "@/components/shell/Guard";
import { MaterialsPage } from "@/features/materials/MaterialsPage";

export default function Page() {
  return (
    <Guard perms={["materials:read"]}>
      <MaterialsPage />
    </Guard>
  );
}
