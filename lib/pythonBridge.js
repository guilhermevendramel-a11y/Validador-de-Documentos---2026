import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const POPPLER_BIN = path.join(process.cwd(), "tools", "poppler", "Library", "bin");

function safePathParts(name) {
  return String(name || "arquivo")
    .split(/[\\/]+/)
    .map((part) => part.replace(/[^\w.\- À-ÿ]+/g, "_"))
    .filter(Boolean);
}

async function saveFile(file, tempDir, preservePath = false) {
  if (!file || typeof file.arrayBuffer !== "function" || !file.name) {
    return null;
  }

  const parts = preservePath ? safePathParts(file.name) : [file.name.replace(/[^\w.\- À-ÿ]+/g, "_")];
  const filename = parts.pop() || "arquivo";
  const dir = parts.length ? path.join(tempDir, ...parts) : tempDir;
  await mkdir(dir, { recursive: true });

  const filePath = path.join(dir, `${randomUUID()}_${filename}`);
  const buffer = Buffer.from(await file.arrayBuffer());
  await writeFile(filePath, buffer);
  return filePath;
}

function runPython(payload) {
  const pythonBin = process.env.PYTHON_BIN || "python";

  return new Promise((resolve, reject) => {
    const child = spawn(
      /* turbopackIgnore: true */
      pythonBin,
      ["scripts/next_validator_bridge.py", JSON.stringify(payload)],
      {
        env: {
          ...process.env,
          PATH: `${POPPLER_BIN}${path.delimiter}${process.env.PATH || ""}`,
          PYTHONIOENCODING: "utf-8",
        },
        windowsHide: true,
      }
    );

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("error", reject);

    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr || stdout || `Python exited with code ${code}`));
        return;
      }

      try {
        resolve(JSON.parse(stdout));
      } catch (error) {
        reject(new Error(`Resposta Python invalida: ${stdout || stderr}`));
      }
    });
  });
}

export async function handleValidation(request, endpoint, fileFields = []) {
  const formData = await request.formData();
  const tempDir = path.join(os.tmpdir(), `mse-next-${randomUUID()}`);
  await mkdir(tempDir, { recursive: true });

  try {
    const fields = {};
    const files = {};

    for (const [key, value] of formData.entries()) {
      if (typeof value === "string") {
        fields[key] = value;
      }
    }

    for (const field of fileFields) {
      const name = typeof field === "string" ? field : field.name;
      const multiple = typeof field === "object" && field.multiple;
      const preservePath = typeof field === "object" && field.preservePath;
      const values = formData.getAll(name).filter((value) => value?.name);

      if (multiple) {
        files[name] = [];
        for (const value of values) {
          const filePath = await saveFile(value, tempDir, preservePath);
          if (filePath) files[name].push(filePath);
        }
      } else {
        files[name] = await saveFile(values[0], tempDir, preservePath);
      }
    }

    const result = await runPython({ endpoint, fields, files });
    return Response.json(result);
  } catch (error) {
    return Response.json(
      {
        status: "Erro",
        mensagem: "Erro ao processar requisicao no servidor Next.js",
        detalhe: error.message,
      },
      { status: 500 }
    );
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}
