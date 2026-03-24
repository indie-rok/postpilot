from pathlib import Path


def write_env(path: Path, creds: dict[str, str]) -> None:
    lines = []
    for key, value in creds.items():
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n")


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result
