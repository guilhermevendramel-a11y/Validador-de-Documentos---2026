"use client";

import { useEffect, useState } from "react";

const validators = [
  {
    id: "pacote",
    title: "Importar Pasta de Documentos",
    action: "/validar_pacote_documentos",
    submitLabel: "Importar",
    files: [{
      name: "pacote",
      label: "Pasta com os documentos",
      required: true,
      multiple: true,
      directory: true,
      accept: ".pdf",
    }],
  },
  {
    id: "cartao",
    title: "Cartao Ponto",
    action: "/validar_cartao_ponto",
    fields: [
      { type: "text", name: "competencia", label: "Competencia", placeholder: "MM/AAAA", required: true },
    ],
    files: [{ name: "file", label: "Arquivo do cartao ponto", required: true }],
  },
  {
    id: "fgts",
    title: "Validador de FGTS Digital",
    action: "/validar_fgts",
    fields: [
      { type: "text", name: "competencia", label: "Competencia", placeholder: "MM/AAAA" },
      {
        type: "select",
        name: "tomador",
        label: "Tomador / CNO da Obra",
        options: [
          { label: "Selecione a obra", value: "" },
          { label: "Aguas do Cerrado - 90.010.30200/72", value: "90.010.30200/72" },
          { label: "CMAA - 08.057.019/0001-86", value: "08.057.019/0001-86" },
          { label: "CNPEM AUDITORIO - 90.025.44783/76", value: "90.025.44783/76" },
          { label: "CNPEM FASEADO - 90.025.44853/70", value: "90.025.44853/70" },
          { label: "COCAMAR - 90.024.82127/74", value: "90.024.82127/74" },
          { label: "Eurofarma - 90.002.42081/74", value: "90.002.42081/74" },
          { label: "ELKEM CHRONOS - 42.593.061/0004-00", value: "42.593.061/0004-00" },
          { label: "Elkem - 42.593.061/0004-00", value: "42.593.061/0004-00" },
          { label: "Fitesa - 90.018.20666/78", value: "90.018.20666/78" },
          { label: "Hitachi - 61.074.829/0011-03", value: "61.074.829/0011-03" },
          { label: "Itaipu Datacenter / Ed. Manutencao - 90.395.988/0012-98", value: "90.395.988/0012-98" },
          { label: "Mosaic - Cajati - SP - 90.008.11313/77", value: "90.008.11313/77" },
          { label: "Mosaic - Uberaba - MG - 90.014.58001/72", value: "90.014.58001/72" },
          { label: "Microsoft - Projeto Dante - 90.015.45785/79", value: "90.015.45785/79" },
          { label: "Nestle Belly Vargeao - 90.011.63044/76", value: "90.011.63044/76" },
          { label: "NEOENERGIA BRASILIA - 90.023.15827/75", value: "90.023.15827/75" },
          { label: "Novo Nordisk - 16.921.603/0001-66", value: "16.921.603/0001-66" },
          { label: "Novo Nordisk - Eletromecanica - 90.020.03790/74", value: "90.020.03790/74" },
          { label: "Scala - Barueri - 90.013.85869/70", value: "90.013.85869/70" },
          { label: "Scala - Campinas - 90.017.67555/74", value: "90.017.67555/74" },
          { label: "Scala - RJ - 90.012.24579/76", value: "90.012.24579/76" },
          { label: "Suzano - Veolia - 90.006.90387/77", value: "90.006.90387/77" },
          { label: "Predio Auditorio - MSE - 90.016.87236/74", value: "90.016.87236/74" },
          { label: "Porto de Itapoa - 90.023.43463/75", value: "90.023.43463/75" },
          { label: "Neoenergia - 90.022.53912/79", value: "90.022.53912/79" },
        ],
      },
    ],
    files: [
      { name: "relatorio_fgts", label: "Relatorio de trabalhadores (PDF)", required: true },
      { name: "guia_fgts", label: "Guia + comprovante (PDF)", required: true },
    ],
  },
  {
    id: "inss",
    title: "INSS (Guia + DCTFWeb)",
    action: "/validar_inss",
    fields: [{ type: "text", name: "competencia", label: "Competencia esperada", placeholder: "MM/AAAA", required: true }],
    files: [
      { name: "guia_inss", label: "Guia + comprovante de pagamento", required: true },
      { name: "dctfweb", label: "Relatorios da DCTFWeb", required: true },
    ],
  },
  {
    id: "folha",
    title: "Folha de Pagamento",
    action: "/validar_folha_pagamento",
    fields: [{ type: "text", name: "competencia", label: "Competencia", placeholder: "MM/AAAA", required: true }],
    files: [{ name: "file", label: "Arquivo da folha (PDF)", required: true }],
  },
  {
    id: "holerite",
    title: "Holerite + Comprovante",
    action: "/validar_holerite",
    fields: [{ type: "text", name: "competencia", label: "Competencia", placeholder: "MM/AAAA" }],
    files: [
      { name: "holerite", label: "Arquivo do holerite", required: true },
      { name: "comprovantes", label: "Comprovantes de pagamento", multiple: true, required: true },
    ],
  },
  {
    id: "rescisao",
    title: "Kit Rescisao",
    action: "/validar_kit_rescisao",
    fields: [{ type: "text", name: "nome_colaborador", label: "Colaborador", placeholder: "Nome completo", required: true }],
    files: [{ name: "kit_unico", label: "Upload do kit completo (PDF unico)", required: true }],
  },
  {
    id: "cnd_inss",
    title: "CND INSS / CND Federal",
    action: "/validar_cnd_inss",
    fields: [
      { type: "text", name: "cnpj_esperado", label: "CNPJ da empresa", placeholder: "00.000.000/0000-00" },
      { type: "text", name: "competencia", label: "Competencia", placeholder: "MM/AAAA" },
    ],
    files: [{ name: "cnd_inss", label: "CND INSS / CND Federal", required: true }],
  },
  {
    id: "cndt",
    title: "CNDT",
    action: "/validar_cndt",
    fields: [
      { type: "text", name: "cnpj_esperado", label: "CNPJ da empresa", placeholder: "00.000.000/0000-00" },
      { type: "text", name: "competencia", label: "Competencia", placeholder: "MM/AAAA" },
    ],
    files: [{ name: "cndt", label: "CNDT", required: true }],
  },
  {
    id: "crf_fgts",
    title: "CRF FGTS",
    action: "/validar_crf_fgts",
    fields: [
      { type: "text", name: "cnpj_esperado", label: "CNPJ da empresa", placeholder: "00.000.000/0000-00" },
      { type: "text", name: "competencia", label: "Competencia", placeholder: "MM/AAAA" },
    ],
    files: [{ name: "crf_fgts", label: "CRF FGTS", required: true }],
  },
  {
    id: "vt",
    title: "Gestao de Vale Transporte",
    action: "/validar_vt",
    files: [{ name: "comprovantes", label: "Arquivos VT", multiple: true, required: true }],
  },
  {
    id: "va",
    title: "Gestao de Vale Alimentacao",
    action: "/validar_va",
    files: [{ name: "comprovantes", label: "Arquivos VA", multiple: true, required: true }],
  },
  {
    id: "seguro",
    title: "Apólice do Seguro de Vida",
    action: "/validar_seguro_vida",
    files: [{ name: "comprovantes", label: "Ap\u00f3lice + comprovante", multiple: true, required: true }],
  },
];

function statusClass(status) {
  if (status === "Aprovado") return "status-ok";
  if (status === "Parcial") return "status-parcial";
  return "status-erro";
}

function Value({ value }) {
  if (value === true) return "OK";
  if (value === false) return "Pendente";
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return value.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
  if (Array.isArray(value)) return `${value.length} item(ns)`;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Money({ value, prefix = "" }) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  return `${prefix}${number.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function CheckMark({ ok }) {
  return <span className={ok ? "check-ok" : "check-fail"}>{ok ? "OK" : "Pendente"}</span>;
}

function normalizeText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase();
}

function filePath(file) {
  return file.webkitRelativePath || file.name;
}

function detectCompetencia(files) {
  for (const file of files) {
    const match = normalizeText(filePath(file)).match(/COMP\.\s*(\d{2})-(\d{4})/);
    if (match) return `${match[1]}/${match[2]}`;
  }
  return "";
}

function emptyPackageGroups() {
  return {
    cartao_ponto: [],
    folha_pagamento: [],
    holerite: [],
    inss: [],
    fgts: [],
    cnd: [],
    vt: [],
    va: [],
    seguro_vida: [],
    rescisao: [],
    nao_classificados: [],
  };
}

function classifyPackageFiles(files) {
  const grupos = emptyPackageGroups();
  const uploads = {
    cartao: { file: [] },
    folha: { file: [] },
    holerite: { holerite: [], comprovantes: [] },
    inss: { guia_inss: [], dctfweb: [] },
    fgts: { relatorio_fgts: [], guia_fgts: [] },
    cnd: { cnds: [] },
    vt: { comprovantes: [] },
    va: { comprovantes: [] },
    seguro: { comprovantes: [] },
    rescisao: { kit_unico: [] },
  };

  for (const file of files) {
    const path = normalizeText(filePath(file));
    const name = normalizeText(file.name);

    if (!name.endsWith(".PDF")) {
      grupos.nao_classificados.push(file);
      continue;
    }

    if (path.includes("CARTAO PONTO")) {
      uploads.cartao.file = [file];
      grupos.cartao_ponto.push(file);
    } else if (path.includes("FOLHA DE PAGAMENTO")) {
      uploads.folha.file = [file];
      grupos.folha_pagamento.push(file);
    } else if (path.includes("HOLERITE")) {
      if (path.includes("COMPROVANTE")) uploads.holerite.comprovantes.push(file);
      else uploads.holerite.holerite.push(file);
      grupos.holerite.push(file);
    } else if (path.includes("INSS") || path.includes("DCTFWEB")) {
      if (path.includes("DCTFWEB")) uploads.inss.dctfweb = [file];
      else uploads.inss.guia_inss = [file];
      grupos.inss.push(file);
    } else if (path.includes("FGTS")) {
      if (name.includes("DIGITAL")) uploads.fgts.relatorio_fgts = [file];
      else uploads.fgts.guia_fgts = [file];
      grupos.fgts.push(file);
    } else if (path.includes("CERTID") || name.includes("CND") || name.includes("CNDT") || name.includes("CRF")) {
      uploads.cnd.cnds.push(file);
      grupos.cnd.push(file);
    } else if (path.includes("VALE TRANSPORTE")) {
      uploads.vt.comprovantes.push(file);
      grupos.vt.push(file);
    } else if (path.includes("VALE ALIMENTACAO")) {
      uploads.va.comprovantes.push(file);
      grupos.va.push(file);
    } else if (path.includes("SEGURO") || path.includes("APOLICE")) {
      uploads.seguro.comprovantes.push(file);
      grupos.seguro_vida.push(file);
    } else if (path.includes("RESCIS")) {
      uploads.rescisao.kit_unico = [file];
      grupos.rescisao.push(file);
    } else {
      grupos.nao_classificados.push(file);
    }
  }

  return { grupos, uploads };
}

function setInputFiles(configId, fieldName, files) {
  const input = document.getElementById(`${configId}-${fieldName}`);
  if (!input || !files?.length) return false;

  const transfer = new DataTransfer();
  const selected = input.multiple ? files : files.slice(0, 1);
  selected.forEach((file) => transfer.items.add(file));
  input.files = transfer.files;
  input.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

function setCompetenciaFields(competencia) {
  if (!competencia) return;
  document.querySelectorAll('input[name="competencia"]').forEach((input) => {
    input.value = competencia;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

function attachPackageFiles(files) {
  const selected = Array.from(files || []);
  if (!selected.length) {
    return { status: "Erro", mensagem: "Selecione uma pasta com documentos PDF." };
  }

  if (selected.some((file) => normalizeText(file.name).endsWith(".ZIP"))) {
    return {
      status: "Erro",
      mensagem: "Extraia o ZIP e selecione a pasta normal com os documentos.",
    };
  }

  const competencia = detectCompetencia(selected);
  const { grupos, uploads } = classifyPackageFiles(selected);
  const anexos = [];

  Object.entries(uploads).forEach(([configId, fields]) => {
    Object.entries(fields).forEach(([fieldName, fieldFiles]) => {
      if (setInputFiles(configId, fieldName, fieldFiles)) {
        anexos.push({
          destino: `${configId}.${fieldName}`,
          arquivos: fieldFiles.map((file) => file.name),
        });
      }
    });
  });

  setCompetenciaFields(competencia);

  return {
    status: "Aprovado",
    mensagem: `${anexos.length} campo(s) preenchido(s). PDFs separados com sucesso.`,
    competencia,
    documentos_classificados: Object.fromEntries(
      Object.entries(grupos).map(([tipo, files]) => [tipo, files.map((file) => file.name)])
    ),
    anexos,
  };
}

function FgtsResult({ result }) {
  const documentos = result?.documentos || {};
  const colaboradores = result?.colaboradores || result?.trabalhadores || [];
  const documentosOrdenados = [
    "Relação de Trabalhadores",
    "Relação de Categorias",
    "Relação de Estabelecimentos",
    "Relação de Tipos de Valor",
    "Relação de Tomadores de Serviço",
  ];

  const valorFgts = result.valor_fgts_digital ?? result.valor_a_pagar;

  return (
    <>
      <div className="fgts-resumo">
        <div><strong>Status:</strong> {result.status || "-"}</div>
        <div><strong>Mensagem:</strong> {result.mensagem || "-"}</div>
        <br />
        <div><strong>Empresa:</strong> {result.empresa || "-"}</div>
        <div className="fgts-resumo-status">
          <span><strong>Competencia:</strong> {result.competencia || "-"}</span>
          <CheckMark ok={Boolean(result.competencia_ok)} />
        </div>
        <div className="fgts-resumo-status">
          <span><strong>Valor FGTS:</strong> <Money value={valorFgts} /></span>
          <CheckMark ok={Boolean(result.valor_ok)} />
        </div>
        <div className="fgts-resumo-status">
          <span><strong>Valor Guia:</strong> <Money value={result.valor_guia} /></span>
          <CheckMark ok={Boolean(result.valor_ok)} />
        </div>
        <div className="fgts-resumo-status">
          <span><strong>Valor Comprovante:</strong> <Money value={result.valor_comprovante} /></span>
          <CheckMark ok={Boolean(result.guia_comprovante_ok)} />
        </div>
        <div><strong>Data Pagamento:</strong> {result.data_pagamento || "-"}</div>
      </div>

      <h3 className="fgts-section-title">Documentos FGTS</h3>
      <table className="tabela-fgts">
        <thead>
          <tr>
            <th>Documento</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {documentosOrdenados.map((documento) => (
            <tr key={documento}>
              <td>{documento}</td>
              <td className="status-center">
                <span className={documentos[documento] ? "cell-ok" : "cell-fail"}>
                  {documentos[documento] ? "OK" : "Pendente"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 className="fgts-section-title">Colaboradores</h3>
      <table className="tabela-fgts">
        <thead>
          <tr>
            <th>Nome</th>
            <th>Tomador</th>
          </tr>
        </thead>
        <tbody>
          {colaboradores.length ? colaboradores.map((colaborador, index) => (
            <tr key={`${colaborador.nome || "colaborador"}-${index}`}>
              <td>{colaborador.nome || "-"}</td>
              <td>{colaborador.tomador || result.tomador_informado || "-"}</td>
            </tr>
          )) : (
            <tr>
              <td colSpan={2}>Nenhum colaborador encontrado.</td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}

function InssResult({ result }) {
  const validacoes = Array.isArray(result.validacoes) ? result.validacoes : [
    { item: "Valor Guia vs DCTF", ok: result.valor_ok },
    { item: "Valor Guia vs Comprovante", ok: result.comprovante_ok },
    { item: "Empresa", ok: result.empresa_ok },
    { item: "Competência Guia", ok: result.competencia_guia_ok },
    { item: "Competência DCTF", ok: result.competencia_dctf_ok },
    { item: "Estrutura DCTF", ok: result.estrutura_dctf_ok },
    { item: "Relatório de Créditos DCTFWeb", ok: result.relatorio_creditos_ok },
    { item: "Pagamento Identificado", ok: result.pagamento_identificado },
  ];

  const statusLabel = (valor) => {
    if (valor === "NA") return "NA";
    return valor ? "OK" : "Pendente";
  };

  return (
    <>
      <div className="inss-resumo">
        <div><strong>Status:</strong> {result.status || "-"}</div>
        <div><strong>Mensagem:</strong> {result.mensagem || "-"}</div>
        <div><strong>Empresa:</strong> {result.empresa || "-"}</div>
        <div><strong>Competencia:</strong> {result.competencia || "-"}</div>
        <div><strong>Valor INSS:</strong> <Money value={result.valor_inss ?? result.valor_guia} /></div>
        <div><strong>Valor Guia:</strong> <Money value={result.valor_guia} /></div>
        <div><strong>Valor Comprovante:</strong> <Money value={result.valor_comprovante} /></div>
        <div><strong>Valor DCTF:</strong> <Money value={result.valor_dctf} /></div>
        <div><strong>Data Pagamento:</strong> {result.data_pagamento || "-"}</div>
      </div>

      <table className="tabela-inss">
        <thead>
          <tr>
            <th>Item Validado</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {validacoes.map((validacao) => (
            <tr key={validacao.item}>
              <td>{validacao.item}</td>
              <td>
                <span
                  className={
                    validacao.ok === "NA"
                      ? "cell-neutral"
                      : validacao.ok
                        ? "cell-ok"
                        : "cell-fail"
                  }
                >
                  {statusLabel(validacao.ok)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function FolhaResult({ result }) {
  const colaboradores = result?.colaboradores || [];

  return (
    <>
      <div className="folha-resumo">
        <div><strong>Status:</strong> {result.status || "-"}</div>
        <div><strong>Mensagem:</strong> {result.mensagem || "-"}</div>
        <br />
        <div><strong>Empresa:</strong> {result.empresa || "-"}</div>
        <div className="fgts-resumo-status">
          <span><strong>Competencia:</strong> {result.competencia || "-"}</span>
          <CheckMark ok={result.competencia_ok !== false} />
        </div>
      </div>

      <h3 className="fgts-section-title">Colaboradores</h3>
      <table className="tabela-fgts">
        <thead>
          <tr>
            <th>Nome</th>
          </tr>
        </thead>
        <tbody>
          {colaboradores.length ? colaboradores.map((colaborador, index) => {
            const nome = typeof colaborador === "string" ? colaborador : colaborador?.nome;
            return (
              <tr key={`${nome || "colaborador"}-${index}`}>
                <td style={{ color: "#000000" }}>{nome || "-"}</td>
              </tr>
            );
          }) : (
            <tr>
              <td>Nenhum colaborador encontrado.</td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}

function PacoteResult({ result }) {
  const anexos = Array.isArray(result?.anexos) ? result.anexos : [];

  return (
    <>
      <div className="pacote-resumo-compacto">
        <strong>{result.mensagem || "-"}</strong>
        {result.competencia && <span>Competencia: {result.competencia}</span>}
      </div>

      {anexos.length ? (
        <ul className="pacote-anexos">
          {anexos.map((anexo, index) => (
            <li key={`${anexo.destino}-${index}`}>
              <strong>{anexo.destino}</strong>
              <span>{(anexo.arquivos || []).join(", ") || "-"}</span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="muted">Nenhum campo preenchido.</div>
      )}
    </>
  );
}

function HoleriteResult({ result }) {
  const colaboradores = result?.colaboradores || [];
  const pendencias = [
    ...(Array.isArray(result?.erros) ? result.erros : []),
    ...(Array.isArray(result?.avisos) ? result.avisos : []),
  ];

  return (
    <>
      <div className="holerite-resumo">
        <div><strong>Status:</strong> {result.status || "-"}</div>
        <div><strong>Mensagem:</strong> {result.mensagem || "-"}</div>
        <br />
        <div><strong>Competencia:</strong> {result.competencia || "-"}</div>
        <div><strong>Valor no holerite:</strong> <Money value={result.valor_holerite} prefix="R$ " /></div>
        <div><strong>Valor no comprovante:</strong> <Money value={result.valor_comprovante} prefix="R$ " /></div>
      </div>

      <div className="table-wrap">
        <table className="tabela-ocr tabela-holerite">
          <thead>
            <tr>
              <th>Colaborador</th>
              <th>Competencia</th>
              <th>Assinatura</th>
              <th>Holerite</th>
              <th>Comprovante</th>
              <th>Diferenca</th>
              <th>Conferencia</th>
            </tr>
          </thead>
          <tbody>
            {colaboradores.length ? colaboradores.map((colaborador, index) => (
              <tr key={`${colaborador.nome || "colaborador"}-${index}`}>
                <td>{colaborador.nome || "-"}</td>
                <td className={colaborador.competencia_ok === false ? "cell-fail" : "cell-ok"}>
                  {colaborador.competencia || "-"}
                </td>
                <td>
                  <StatusCell
                    ok={Boolean(colaborador.assinatura)}
                    failLabel="Pendente"
                    label={assinaturaLabel(colaborador)}
                  />
                </td>
                <td>
                  <span className={Number(colaborador.valor_holerite || colaborador.valor_liquido) > 0 ? "cell-ok" : "cell-fail"}>
                    <Money value={colaborador.valor_holerite ?? colaborador.valor_liquido} prefix="R$ " />
                  </span>
                </td>
                <td>
                  <span className={Number(colaborador.valor_comprovante || colaborador.valor_pago) > 0 ? "cell-ok" : "cell-fail"}>
                    <Money value={colaborador.valor_comprovante ?? colaborador.valor_pago} prefix="R$ " />
                  </span>
                </td>
                <td>
                  <span className={colaborador.valor_ok ? "cell-ok" : "cell-fail"}>
                    <Money value={colaborador.diferenca} prefix="R$ " />
                  </span>
                </td>
                <td>
                  <StatusCell ok={Boolean(colaborador.valor_ok)} failLabel="DIVERGENTE" label="CONFERE" />
                </td>
              </tr>
            )) : (
              <tr>
                <td colSpan={7}>Nenhum colaborador encontrado.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {colaboradores.length > 0 && (
        <div className="pendencias">
          <strong>Assinatura:</strong>
          <ul>
            {colaboradores.map((colaborador, index) => (
              <li key={`${colaborador.nome || "colaborador"}-assinatura-${index}`}>
                {(colaborador.nome || "Colaborador sem nome")}: {colaborador.assinatura_status || assinaturaLabel(colaborador)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {colaboradores.length > 0 && (
        <div className="pendencias">
          <strong>Data Manual:</strong>
          <ul>
            {colaboradores.map((colaborador, index) => {
              const dataManualOk = colaborador.datado === "Sim";
              const statusData = dataManualOk ? "Informada manualmente" : "Nao informada manualmente";
              return (
                <li key={`${colaborador.nome || "colaborador"}-data-${index}`}>
                  {(colaborador.nome || "Colaborador sem nome")}: {statusData} | {colaborador.data_detalhe || "Data nao identificada"}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {pendencias.length > 0 && (
        <div className="pendencias">
          <strong>Pendencias identificadas:</strong>
          <ul>
            {pendencias.map((pendencia, index) => (
              <li key={`${pendencia}-${index}`}>{pendencia}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

function rowStatus(data, key, value) {
  const statusByKey = {
    empresa: "empresa_ok",
    competencia: "competencia_ok",
    tomador_informado: "tomador_ok",
    valor_fgts: "valor_ok",
    valor_guia: "guia_comprovante_ok",
    valor_comprovante: "guia_comprovante_ok",
    valor_conferido: "valor_conferido",
    valor_ok: "valor_ok",
    empresa_ok: "empresa_ok",
    competencia_ok: "competencia_ok",
    tomador_ok: "tomador_ok",
  };

  const statusKey = statusByKey[key];
  if (statusKey && data[statusKey] !== undefined) return Boolean(data[statusKey]);
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value > 0;
  return value !== null && value !== undefined && value !== "";
}

function resultRows(data) {
  const rows = [];
  const add = (key, label, value, okKey = null) => {
    if (value === undefined || value === "") return;
    rows.push({ key, label, value, ok: okKey ? Boolean(data[okKey]) : rowStatus(data, key, value) });
  };

  add("empresa", "empresa", data.empresa);
  add("competencia", "competencia", data.competencia);
  add("tomador_informado", "tomador informado", data.tomador_informado);

  const valorFgts = data.valor_fgts_digital ?? data.valor_a_pagar;
  add("valor_fgts", "valor FGTS Digital / valor a pagar", valorFgts, "valor_ok");
  add("valor_guia", "valor guia", data.valor_guia, "guia_comprovante_ok");
  add("valor_comprovante", "valor comprovante", data.valor_comprovante, "guia_comprovante_ok");
  add("valor", "valor", data.valor);
  add("data_pagamento", "data pagamento", data.data_pagamento);

  [
    "valor_inss",
    "pagamento_identificado",
  ].forEach((key) => {
    if (data[key] !== undefined && data[key] !== "") {
      add(key, key.replaceAll("_", " "), data[key]);
    }
  });

  return rows.filter((row) => !(row.key === "valor" && Number(row.value || 0) === 0));
}

function ResultTable({ data }) {
  const rows = resultRows(data);

  if (!rows.length) return null;

  return (
    <table className="tabela-resultado">
      <tbody>
        {rows.map(({ key, label, value, ok }) => (
          <tr key={key}>
            <td className="row-status">
              <span className={`status-marker ${ok ? "marker-ok" : "marker-fail"}`} aria-hidden="true" />
            </td>
            <th>{label}</th>
            <td><Value value={value} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ItemsTable({ title, items }) {
  if (!Array.isArray(items) || items.length === 0) return null;
  const columns = Array.from(items.reduce((set, item) => {
    Object.keys(item || {}).forEach((key) => set.add(key));
    return set;
  }, new Set()));

  return (
    <>
      <h3 className="muted">{title}</h3>
      <div className="table-wrap">
        <table className="tabela-resultado">
          <thead>
            <tr>{columns.map((column) => <th key={column}>{column.replaceAll("_", " ")}</th>)}</tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <tr key={index}>
                {columns.map((column) => (
                  <td key={column}><Value value={item?.[column]} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function itemsWithoutValue(items) {
  if (!Array.isArray(items)) return [];
  return items.map((item) => {
    if (!item || typeof item !== "object") return item;
    return { nome: item.nome ?? item.nome_colaborador ?? item.colaborador ?? "" };
  });
}

function VaValoresBox({ result }) {
  const resumo = result?.resumo_financeiro || {};
  const somaRecibo = Number(resumo.soma_recibo || 0);
  const somaComprovante = Number(resumo.soma_comprovante || 0);
  const encontrados = Boolean(resumo.valores_encontrados);
  const conferem = Boolean(resumo.valores_conferem);
  const valoresSeparados = Array.isArray(resumo.valores_separados) ? resumo.valores_separados : [];

  return (
    <div className="inss-resumo" style={{ marginTop: "12px" }}>
      <div><strong>Conferencia de Valores (VA)</strong></div>
      <div><strong>Valores encontrados:</strong> {encontrados ? "Sim" : "Nao"}</div>
      <div><strong>Soma recibos:</strong> <Money value={somaRecibo} prefix="R$ " /></div>
      <div><strong>Soma comprovantes:</strong> <Money value={somaComprovante} prefix="R$ " /></div>
      <div>
        <strong>Resultado:</strong> {encontrados ? (conferem ? "Correto" : "Divergente") : "Pendente"}
      </div>
      {valoresSeparados.length > 1 && (
        <div style={{ marginTop: "12px" }}>
          <strong>Valores separados:</strong>
          <div className="table-wrap" style={{ marginTop: "8px" }}>
            <table className="tabela-resultado">
              <thead>
                <tr>
                  <th>Nome</th>
                  <th>Recibo</th>
                  <th>Comprovante</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {valoresSeparados.map((item, index) => (
                  <tr key={`${item?.nome || "colaborador"}-${index}`}>
                    <td>{item?.nome || "-"}</td>
                    <td><Money value={item?.valor_recibo || 0} prefix="R$ " /></td>
                    <td><Money value={item?.valor_comprovante || 0} prefix="R$ " /></td>
                    <td>{item?.status || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function statusText(ok, failLabel = "Pendente") {
  return ok ? "OK" : `${failLabel}`;
}

function StatusCell({ ok, failLabel = "Pendente", label = "OK" }) {
  return (
    <span className={ok ? "cell-ok" : "cell-fail"}>
      {ok ? `${label}` : `${failLabel}`}
    </span>
  );
}

function assinaturaLabel(colaborador) {
  if (!colaborador?.assinatura) return "Pendente";
  const tipo = String(colaborador.assinatura_tipo || "").toLowerCase();
  if (tipo.includes("digital")) return "Digital";
  if (tipo.includes("manual") || tipo.includes("rubrica")) return "Manual";
  return "Manual";
}

function CartaoPontoTable({ result, colaboradores = [] }) {
  const lista = Array.isArray(colaboradores) ? colaboradores : [];
  const resumo = result?.assinaturas || {};
  const avisosGlobais = Array.isArray(result?.avisos_globais) ? result.avisos_globais : [];

  const pendencias = lista.flatMap((colaborador) => {
    const nome = colaborador.nome || "Colaborador sem nome";
    const itens = [];

    if (!colaborador.assinatura) itens.push(`${nome}: assinatura ausente`);
    if (!colaborador.marcacoes) itens.push(`${nome}: marcações incompletas`);
    if (colaborador.competencia_ok === false) {
      itens.push(`${nome}: competência divergente (${colaborador.competencia || "-"})`);
    }

    return itens;
  });

  return (
    <>
      <div className="assinatura-resumo">
        <strong>Assinatura:</strong> {resumo.tipo_predominante || "-"}
        <span>
          Digital: {resumo.assinatura_digital || 0} | Manual/Rubrica: {resumo.assinatura_manual_rubrica || 0} | Ausente: {resumo.assinatura_ausente || 0}
        </span>
      </div>

      <div className="cartao-status">
        <div><strong>Status:</strong> {result?.status || "-"}</div>
        <div><strong>Mensagem:</strong> {result?.mensagem || "-"}</div>
      </div>

      {lista.length > 0 ? (
        <div className="table-wrap">
          <table className="tabela-ocr">
            <thead>
              <tr>
                <th>Colaborador</th>
                <th>Competência</th>
                <th>Assinatura</th>
                <th>Marcações</th>
              </tr>
            </thead>
            <tbody>
              {lista.map((colaborador, index) => (
                <tr key={`${colaborador.nome || "colaborador"}-${index}`}>
                  <td>{colaborador.nome || "-"}</td>
                  <td className={colaborador.competencia_ok === false ? "cell-fail" : "cell-ok"}>
                    {colaborador.competencia || "-"}
                  </td>
                  <td>
                    <StatusCell ok={Boolean(colaborador.assinatura)} label={assinaturaLabel(colaborador)} />
                  </td>
                  <td>
                    <StatusCell ok={Boolean(colaborador.marcacoes)} failLabel="INCOMPLETO" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="muted" style={{ marginTop: "8px" }}>
          Nenhum colaborador com nome válido foi identificado neste cartão ponto.
        </div>
      )}

      {avisosGlobais.length > 0 && (
        <div className="pendencias">
          <strong>Avisos globais:</strong>
          <ul>
            {avisosGlobais.map((aviso, index) => (
              <li key={`${aviso}-${index}`}>{aviso}</li>
            ))}
          </ul>
        </div>
      )}

      {pendencias.length > 0 && (
        <div className="pendencias">
          <strong>Pendências identificadas:</strong>
          <ul>
            {pendencias.map((pendencia) => (
              <li key={pendencia}>{pendencia}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
function appendCardFields(body, form, config) {
  for (const field of config.fields || []) {
    const input = form.elements.namedItem(field.name);
    if (!input) continue;
    body.append(field.name, input.value || "");
  }
}

function appendCardFiles(body, form, config) {
  for (const file of config.files || []) {
    const input = form.elements.namedItem(file.name);
    if (!input?.files?.length) continue;

    for (const selected of Array.from(input.files)) {
      body.append(config.id === "cnd" ? "cnds" : file.name, selected);
    }
  }
}

function buildCardFormData(form, config) {
  const body = new FormData();
  appendCardFields(body, form, config);
  appendCardFiles(body, form, config);
  return body;
}

function ValidatorCard({
  config,
  onPackageReady,
  externalResult,
  editMode = false,
}) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (externalResult !== undefined) {
      setResult(externalResult);
    }
  }, [externalResult]);

  async function onSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setResult({
      status: "Processando",
      mensagem: config.id === "pacote" ? "Processando documentos..." : "Validando documento...",
    });

    try {
      if (config.id === "pacote") {
        const input = event.currentTarget.querySelector('input[name="pacote"]');
        const files = Array.from(input?.files || []);
        const importResult = attachPackageFiles(files);
        setResult(importResult);
        if (typeof onPackageReady === "function") {
          onPackageReady(files);
        }
        return;
      }

      const body = buildCardFormData(event.currentTarget, config);
      const response = await fetch(config.action, {
        method: "POST",
        body,
      });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      setResult({ status: "Erro", mensagem: "Falha na comunicacao com o servidor", detalhe: error.message });
    } finally {
      setLoading(false);
    }
  }

  const colaboradores = result?.colaboradores || result?.trabalhadores || [];
  const colaboradoresDetalhados = config.id === "vt"
    ? (result?.colaboradores_detalhados || [])
    : colaboradores;
  const isCartaoPontoResult = (
    config.id === "cartao" ||
    colaboradores.some((item) => (
      item &&
      Object.prototype.hasOwnProperty.call(item, "assinatura") &&
      Object.prototype.hasOwnProperty.call(item, "marcacoes")
    ))
  );

  return (
    <section className="card">
      <h2>{config.title}</h2>
      <form onSubmit={onSubmit}>
        {(config.fields || []).map((field) => {
          const { label, options, ...inputProps } = field;
          return (
          <div className="field" key={field.name}>
            <label htmlFor={`${config.id}-${field.name}`}>{label}</label>
            {field.type === "select" ? (
              <select id={`${config.id}-${field.name}`} name={field.name} required={field.required}>
                {(options || []).map((option, optionIndex) => (
                  <option key={`${field.name}-${option.value}-${optionIndex}`} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            ) : (
              <input id={`${config.id}-${field.name}`} {...inputProps} />
            )}
          </div>
          );
        })}

        {(config.files || []).map((file) => (
          <div className="field" key={file.name}>
            <label htmlFor={`${config.id}-${file.name}`}>{file.label}</label>
            <input
              id={`${config.id}-${file.name}`}
              type="file"
              name={file.name}
              multiple={file.multiple}
              required={file.required}
              accept={file.accept || ".pdf,.png,.jpg,.jpeg"}
              {...(file.directory ? { webkitdirectory: "true", directory: "" } : {})}
            />
          </div>
        ))}

        <button className="btn" type="submit" disabled={loading}>
          {loading
            ? (config.id === "pacote" ? "Importando..." : "Validando...")
            : (config.submitLabel || "Validar")}
        </button>
      </form>

      {result && (
        <div className={`resultado ${statusClass(result.status)}`}>
          {config.id !== "fgts" && config.id !== "folha" && config.id !== "pacote" && config.id !== "cartao" && config.id !== "holerite" && (
            <>
              <strong>Status:</strong> {result.status || "-"}
              <br />
              <strong>Mensagem:</strong> {result.mensagem || "-"}
            </>
          )}
          {result.detalhe && (
            <>
              {config.id !== "fgts" && config.id !== "folha" && <br />}
              <strong>Detalhe:</strong> {result.detalhe}
            </>
          )}
          {config.id === "fgts" ? (
            <FgtsResult result={result} />
          ) : config.id === "inss" ? (
            <InssResult result={result} />
          ) : config.id === "folha" ? (
            <FolhaResult result={result} />
          ) : config.id === "pacote" ? (
            <PacoteResult result={result} />
          ) : config.id === "holerite" ? (
            <HoleriteResult result={result} />
          ) : !isCartaoPontoResult && config.id !== "va" && (
            <ResultTable data={result} />
          )}
          {config.id === "fgts" || config.id === "inss" || config.id === "folha" || config.id === "holerite" || config.id === "pacote" ? null : isCartaoPontoResult ? (
            <CartaoPontoTable result={result} colaboradores={colaboradores} />
          ) : (
            <ItemsTable
              title="Colaboradores"
              items={config.id === "va" ? itemsWithoutValue(colaboradores) : colaboradores}
            />
          )}
          {config.id === "vt" && colaboradoresDetalhados.length > 0 && (
            <ItemsTable title="Conferência VT" items={colaboradoresDetalhados} />
          )}
          {config.id !== "fgts" && config.id !== "inss" && config.id !== "folha" && config.id !== "holerite" && config.id !== "pacote" && config.id !== "va" && config.id !== "vt" && <ItemsTable title="Validacoes" items={result.validacoes} />}
          {config.id === "va" && <VaValoresBox result={result} />}
        </div>
      )}
    </section>
  );
}

export default function ValidatorDashboard() {
  const [packageFiles, setPackageFiles] = useState([]);
  const [validateLoading, setValidateLoading] = useState(false);
  const [resultsByCard, setResultsByCard] = useState({});

  function mapDocumentoToCardId(documento) {
    const texto = String(documento || "").toLowerCase();
    if (texto.includes("cartao")) return "cartao";
    if (texto.includes("folha")) return "folha";
    if (texto.includes("holerite")) return "holerite";
    if (texto.includes("fgts")) return "fgts";
    if (texto.includes("inss")) return "inss";
    if (texto.includes("rescis")) return "rescisao";
    if (texto.includes("cnd")) return "cnd";
    if (texto.includes("vale transporte") || texto.includes(" vt")) return "vt";
    if (texto.includes("vale alimentacao") || texto.includes(" va")) return "va";
    if (texto.includes("seguro")) return "seguro";
    return null;
  }

  async function validarTudo() {
    setValidateLoading(true);
    setResultsByCard((prev) => ({
      ...prev,
      pacote: { status: "Processando", mensagem: "Validando documentos..." },
    }));

    try {
      const next = {};
      let algumaValidacaoExecutada = false;

      if (packageFiles.length) {
        const body = new FormData();
        packageFiles.forEach((file) => body.append("pacote", file));

        const response = await fetch("/validar_pacote_documentos", {
          method: "POST",
          body,
        });
        const data = await response.json();

        next.pacote = {
          status: data.status || "Processado",
          mensagem: data.mensagem || "Validação concluída.",
        };

        (data.validacoes || []).forEach((item) => {
          const cardId = mapDocumentoToCardId(item?.documento);
          if (!cardId) return;
          algumaValidacaoExecutada = true;
          next[cardId] = item?.resultado || {
            status: item?.status || "Processado",
            mensagem: item?.mensagem || "",
          };
        });
      } else {
        for (const validator of validators) {
          if (validator.id === "pacote") continue;

          const fileInputs = (validator.files || []).map((file) =>
            document.getElementById(`${validator.id}-${file.name}`)
          );
          const temArquivo = fileInputs.some((input) => input?.files?.length);
          if (!temArquivo) continue;

          const body = new FormData();

          for (const field of validator.fields || []) {
            const input = document.getElementById(`${validator.id}-${field.name}`);
            if (!input) continue;
            body.append(field.name, input.value || "");
          }

          for (const file of validator.files || []) {
            const input = document.getElementById(`${validator.id}-${file.name}`);
            if (!input?.files?.length) continue;
            for (const selected of Array.from(input.files)) {
              if (validator.id === "cnd") {
                body.append("cnds", selected);
              } else {
                body.append(file.name, selected);
              }
            }
          }

          const response = await fetch(validator.action, {
            method: "POST",
            body,
          });
          const data = await response.json();
          next[validator.id] = data;
          algumaValidacaoExecutada = true;
        }

        next.pacote = algumaValidacaoExecutada
          ? { status: "Processado", mensagem: "Validação concluída com os arquivos informados manualmente." }
          : { status: "Erro", mensagem: "Nenhum arquivo foi informado para validar." };
      }

      setResultsByCard((prev) => ({ ...prev, ...next }));
    } catch (error) {
      setResultsByCard((prev) => ({
        ...prev,
        pacote: {
          status: "Erro",
          mensagem: "Falha na comunicacao com o servidor",
          detalhe: error.message,
        },
      }));
    } finally {
      setValidateLoading(false);
    }
  }

  return (
    <>
      <header className="main-header">
        <img src="/img/logo-mse.png" alt="MSE Engenharia" />
        <strong>MSE ENGENHARIA - Validador Gestao Documental</strong>
      </header>
      <main className="container">
        <div className="grid">
          {validators.map((validator) => (
            <ValidatorCard
              key={validator.id}
              config={validator}
              onPackageReady={validator.id === "pacote" ? setPackageFiles : undefined}
              externalResult={resultsByCard[validator.id]}
            />
          ))}
        </div>
        <section className="card" style={{ marginTop: 16 }}>
          <h2>Validacao Geral</h2>
          <button className="btn" type="button" disabled={validateLoading} onClick={validarTudo}>
            {validateLoading ? "Validando..." : "Validar"}
          </button>
          <p className="muted" style={{ marginTop: 8 }}>
            O retorno da validacao sera exibido em cada card de documento correspondente.
          </p>
        </section>
      </main>
    </>
  );
}


