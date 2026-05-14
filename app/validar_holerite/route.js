import { handleValidation } from "@/lib/pythonBridge";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request) {
  return handleValidation(request, "holerite", [
    "holerite",
    { name: "comprovantes", multiple: true },
  ]);
}
