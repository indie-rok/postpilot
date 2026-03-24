from pathlib import Path
from env_writer import write_env, read_env


def test_write_and_read_env(tmp_path):
    env_path = tmp_path / ".env"
    creds = {
        "LLM_API_KEY": "sk-test",
        "LLM_BASE_URL": "http://localhost:8000/v1",
        "LLM_MODEL": "gpt-4o-mini",
    }
    write_env(env_path, creds)
    assert env_path.exists()
    result = read_env(env_path)
    assert result["LLM_API_KEY"] == "sk-test"
    assert result["LLM_BASE_URL"] == "http://localhost:8000/v1"


def test_write_env_overwrites(tmp_path):
    env_path = tmp_path / ".env"
    write_env(env_path, {"LLM_API_KEY": "old"})
    write_env(env_path, {"LLM_API_KEY": "new"})
    result = read_env(env_path)
    assert result["LLM_API_KEY"] == "new"


def test_read_env_missing_file(tmp_path):
    result = read_env(tmp_path / "nonexistent")
    assert result == {}
