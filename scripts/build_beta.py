#!/usr/bin/env python3
"""Build local source and packaging artifacts, with no publication."""
import argparse
import hashlib
import json
import runpy
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--source-url", help="URL HTTPS de l'archive effectivement publiée, pour finaliser le manifest")
parser.add_argument("--license", help="Identifiant SPDX choisi pour la distribution")
args = parser.parse_args()
if args.source_url and (not args.source_url.startswith("https://") or not args.license):
    parser.error("La finalisation du paquet exige une URL HTTPS de source et une licence déclarée.")
dist = root / "dist"
dist.mkdir(exist_ok=True)
version = runpy.run_path(str(root / "matos/version.py"))["VERSION"]
source = dist / f"arcenal-matos-{version}.tar.gz"
allowed = ["manage.py", "LICENSE", "requirements.txt", "requirements-dev.txt", "pyproject.toml", "README.md", "TEST_REPORT.md", "matos", "core",
           "templates", "static", "frontend", "scripts", "tests", "playwright.config.js", "package.json", "package-lock.json", "packaging"]
if not args.source_url or not source.exists():
    with tarfile.open(source, "w:gz") as archive:
        for name in allowed:
            path = root / name
            files = sorted(path.rglob("*")) if path.is_dir() else [path]
            for file in files:
                if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
                    archive.add(file, arcname=f"arcenal-matos-{version}/{file.relative_to(root)}")
checksum = hashlib.sha256(source.read_bytes()).hexdigest()
print(f"Source : {source.relative_to(root)}")
print(f"SHA256 : {checksum}")
package = dist / (f"arcenal-matos-ynh-{version}.tar.gz" if args.source_url else f"arcenal-matos-ynh-template-{version}.tar.gz")
with tarfile.open(package, "w:gz") as archive:
    for file in sorted((root / "packaging/ynh").rglob("*")):
        if not file.is_file():
            continue
        relative = file.relative_to(root / "packaging/ynh")
        if relative.name == "manifest.toml" and args.source_url:
            import io
            content = file.read_text().replace('"__SOURCE_URL__"', json.dumps(args.source_url)).replace("__SOURCE_SHA256__", checksum).replace('"__LICENSE_SPDX__"', json.dumps(args.license)).encode()
            info = tarfile.TarInfo(str(relative))
            info.size = len(content)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(content))
        else:
            info = archive.gettarinfo(str(file), arcname=str(relative))
            info.mode = 0o755 if relative.parts[0] == "scripts" else 0o644
            with file.open("rb") as handle:
                archive.addfile(info, handle)
print(f"Paquet {'candidat' if args.source_url else 'modèle à finaliser'} : {package.relative_to(root)}")
