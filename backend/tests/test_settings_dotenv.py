import os

from app import settings as S


def test_dotenv_loads_without_overriding(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\nGEMINI_API_KEY="from-file"  # trailing\nexport GEMINI_MODEL=gemini-x\nLLM_PROVIDER=gemini\n')
    monkeypatch.setattr(S, "BASE", tmp_path / "backend")
    (tmp_path / "backend").mkdir()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "extractive")  # already set: must win over the file
    S._load_dotenv()
    assert os.environ["GEMINI_API_KEY"] == "from-file"
    assert os.environ["GEMINI_MODEL"] == "gemini-x"
    assert os.environ["LLM_PROVIDER"] == "extractive"
    monkeypatch.delenv("GEMINI_API_KEY"); monkeypatch.delenv("GEMINI_MODEL")
