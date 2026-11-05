import { Guard } from "@/components/shell/Guard";
import { BatchPage } from "@/features/batch/BatchPage";

export default function Page() {
  return (
    <Guard perms={["batch:run"]}>
      <BatchPage />
    </Guard>
  );
}
