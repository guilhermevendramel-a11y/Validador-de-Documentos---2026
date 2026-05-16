import { handleValidationFormData } from "@/lib/pythonBridge";
import { getValidationConfig } from "@/lib/validationRegistry";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function isAuthorized(request) {
  const token = process.env.VALIDATOR_API_TOKEN;

  if (!token) {
    return true;
  }

  return request.headers.get("authorization") === `Bearer ${token}`;
}

export async function POST(request) {
  if (!isAuthorized(request)) {
    return Response.json(
      {
        status: "Erro",
        mensagem: "Token invalido para API interna",
      },
      { status: 401 }
    );
  }

  const formData = await request.formData();
  const type = formData.get("tipo") || formData.get("tipo_documento") || formData.get("endpoint");
  const config = getValidationConfig(type);

  if (!config) {
    return Response.json(
      {
        status: "Erro",
        mensagem: `Tipo de documento desconhecido: ${type || ""}`,
      },
      { status: 400 }
    );
  }

  return handleValidationFormData(formData, config.endpoint, config.fileFields);
}
