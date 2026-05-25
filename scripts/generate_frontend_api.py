"""Generate the frontend API client contract from FastAPI's OpenAPI schema."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    frontend_root = project_root / "frontend"
    generated_dir = frontend_root / "src" / "api" / "generated"
    schema_path = generated_dir / "openapi.json"
    types_path = generated_dir / "schema.d.ts"

    sys.path.insert(0, str(project_root / "src"))

    from onvify.api.app import create_app

    generated_dir.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n")

    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    subprocess.run(
        [
            npm,
            "exec",
            "openapi-typescript",
            "--",
            "src/api/generated/openapi.json",
            "-o",
            "src/api/generated/schema.d.ts",
        ],
        cwd=frontend_root,
        check=True,
    )
    print(f"Generated {types_path.relative_to(project_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
