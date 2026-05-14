import { handleValidation } from "@/lib/pythonBridge";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request) {
  return handleValidation(request, "seguro_vida", [
    { name: "comprovantes", multiple: true },
  ]);
}
