from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
ARQUIVOS_OBRIGATORIOS = (
    ROOT_DIR / "general.mdc",
    ROOT_DIR / "diretrizes.mdc",
)
MARCADOR_POLITICA = "[[POLITICAS_OBRIGATORIAS_DO_PROJETO]]"


@lru_cache(maxsize=1)
def carregar_politica_prompts():
    partes = []
    for caminho in ARQUIVOS_OBRIGATORIOS:
        if not caminho.is_file():
            raise FileNotFoundError(f"Arquivo de politica nao encontrado: {caminho.name}")

        conteudo = caminho.read_text(encoding="utf-8").strip()
        if not conteudo:
            raise ValueError(f"Arquivo de politica vazio: {caminho.name}")

        partes.append(f"### {caminho.name}\n{conteudo}")

    return "\n\n".join(partes)


def aplicar_politica_prompt(prompt):
    texto = str(prompt or "").strip()
    politica = carregar_politica_prompts()

    if not texto:
        return f"{MARCADOR_POLITICA}\n\n{politica}"

    if texto.startswith(MARCADOR_POLITICA):
        return texto

    return f"{MARCADOR_POLITICA}\n\n{politica}\n\n{texto}"
