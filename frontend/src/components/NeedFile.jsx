import { useWorkspace } from "@/lib/workspace";
import { Empty } from "./ui";

export function NeedFile({ children }) {
  const { file, ready } = useWorkspace();
  if (!ready) return null;
  if (!file)
    return (
      <Empty title="Pick a file first" href="/upload" cta="Go to upload">
        Every step works on the current file.
      </Empty>
    );
  return <>{children}</>;
}
