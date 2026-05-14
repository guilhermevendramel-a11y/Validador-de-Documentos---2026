import { handleValidation } from "@/lib/pythonBridge";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request) {
  return handleValidation(request, "vt", [{ name: "comprovantes", multiple: true }]);
}
