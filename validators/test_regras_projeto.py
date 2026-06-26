import unittest
from pathlib import Path
from unittest.mock import patch

from utils.gemini_service import chamar_gemini
from utils.prompt_policy import aplicar_politica_prompt


class TestRegrasProjetoMDC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.general = cls.root / "general.mdc"
        cls.diretrizes = cls.root / "diretrizes.mdc"

    def test_arquivos_de_regra_existentes(self):
        self.assertTrue(self.general.is_file(), "general.mdc deve existir na raiz do projeto")
        self.assertTrue(self.diretrizes.is_file(), "diretrizes.mdc deve existir na raiz do projeto")

    def test_conteudo_minimo_das_regras(self):
        conteudo_general = self.general.read_text(encoding="utf-8")
        conteudo_diretrizes = self.diretrizes.read_text(encoding="utf-8")

        frases_general = [
            "Seguran\u00e7a sempre primeiro",
            "Escalabilidade obrigat\u00f3ria",
            "N\u00e3o alterar c\u00f3digo n\u00e3o solicitado",
            "Pedir antes de mexer em arquivos globais",
            "Verificar regress\u00f5es a cada altera\u00e7\u00e3o",
        ]
        frases_diretrizes = [
            "Extreme Ownership",
            "Anti-Sycophancy",
            "Chain of Thought",
            "Input Raso, Output Profundo",
        ]

        for frase in frases_general:
            self.assertIn(frase, conteudo_general)

        for frase in frases_diretrizes:
            self.assertIn(frase, conteudo_diretrizes)

    def test_prompt_com_politica_obrigatoria(self):
        prompt = aplicar_politica_prompt("PROMPT DE TESTE")
        self.assertIn("general.mdc", prompt)
        self.assertIn("diretrizes.mdc", prompt)
        self.assertIn("PROMPT DE TESTE", prompt)
        self.assertIn("Extreme Ownership", prompt)
        self.assertIn("Seguran\u00e7a sempre primeiro", prompt)

    def test_chamar_gemini_inclui_politica_no_prompt(self):
        class _FakeResponse:
            def __init__(self, text):
                self.text = text

        class _FakeModel:
            def __init__(self):
                self.last_prompt = None

            def generate_content(self, prompt, generation_config=None):
                self.last_prompt = prompt
                return _FakeResponse("{}")

        fake_model = _FakeModel()

        with (
            patch("utils.gemini_service.modelos_disponiveis", return_value=["gemini-teste"]),
            patch("utils.gemini_service.genai.GenerativeModel", return_value=fake_model),
        ):
            resultado = chamar_gemini("PROMPT BASE")

        self.assertEqual(resultado, {})
        self.assertIsNotNone(fake_model.last_prompt)
        self.assertIn("general.mdc", fake_model.last_prompt)
        self.assertIn("diretrizes.mdc", fake_model.last_prompt)
        self.assertIn("PROMPT BASE", fake_model.last_prompt)


if __name__ == "__main__":
    unittest.main()
