import { handleValidation } from "@/lib/pythonBridge";
import { getValidationConfig } from "@/lib/validationRegistry";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const validation = getValidationConfig("cnd");

export async function POST(request) {
  return handleValidation(request, validation.endpoint, validation.fileFields);
}
