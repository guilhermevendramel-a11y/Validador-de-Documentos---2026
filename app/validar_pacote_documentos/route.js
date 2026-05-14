import { handleValidation } from "@/lib/pythonBridge";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request) {
  return handleValidation(request, "pacote_documentos", [
    { name: "pacote", multiple: true, preservePath: true },
  ]);
}
