import json
from pathlib import Path

from app.main import create_app

DESTINO = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"


def generar() -> str:
    esquema = create_app().openapi()
    return json.dumps(esquema, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(generar(), encoding="utf-8", newline="\n")
    print(f"OpenAPI escrito en {DESTINO}")


if __name__ == "__main__":
    main()
