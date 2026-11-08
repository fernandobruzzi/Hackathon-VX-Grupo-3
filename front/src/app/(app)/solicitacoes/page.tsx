import { Guard } from "@/components/shell/Guard";
import { RequestTracking } from "@/features/requests/RequestTracking";

export default function Page() {
  return (
    <Guard perms={["requests:read_own"]}>
      <RequestTracking />
    </Guard>
  );
}
