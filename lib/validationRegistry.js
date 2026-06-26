export const validationRegistry = {
  cartao_ponto: {
    endpoint: "cartao_ponto",
    fileFields: ["file"],
  },
  cnd: {
    endpoint: "cnd",
    fileFields: [{ name: "cnds", multiple: true }],
  },
  cnd_inss: {
    endpoint: "cnd_inss",
    fileFields: ["cnd_inss"],
  },
  cndt: {
    endpoint: "cndt",
    fileFields: ["cndt"],
  },
  crf_fgts: {
    endpoint: "crf_fgts",
    fileFields: ["crf_fgts"],
  },
  fgts: {
    endpoint: "fgts",
    fileFields: ["relatorio_fgts", "guia_fgts"],
  },
  folha_pagamento: {
    endpoint: "folha_pagamento",
    fileFields: ["file"],
  },
  holerite: {
    endpoint: "holerite",
    fileFields: [{ name: "holerite", multiple: true }, { name: "comprovantes", multiple: true }],
  },
  inss: {
    endpoint: "inss",
    fileFields: ["guia_inss", "dctfweb"],
  },
  kit_rescisao: {
    endpoint: "kit_rescisao",
    fileFields: ["kit_unico"],
  },
  pacote_documentos: {
    endpoint: "pacote_documentos",
    fileFields: [{ name: "pacote", multiple: true, preservePath: true }],
  },
  seguro_vida: {
    endpoint: "seguro_vida",
    fileFields: [{ name: "comprovantes", multiple: true }],
  },
  va: {
    endpoint: "va",
    fileFields: [{ name: "comprovantes", multiple: true }],
  },
  vt: {
    endpoint: "vt",
    fileFields: [{ name: "comprovantes", multiple: true }],
  },
};

export const validationAliases = {
  cartao: "cartao_ponto",
  folha: "folha_pagamento",
  rescisao: "kit_rescisao",
};

export function getValidationConfig(type) {
  const normalizedType = String(type || "").trim().toLowerCase();
  const registryKey = validationAliases[normalizedType] || normalizedType;
  const config = validationRegistry[registryKey];

  if (!config) {
    return null;
  }

  return {
    type: registryKey,
    ...config,
  };
}
