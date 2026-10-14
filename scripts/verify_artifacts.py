"""Check local beta archives for completeness and accidental runtime files."""
import hashlib
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path, PurePosixPath

root = Path(__file__).resolve().parent.parent
version = runpy.run_path(str(root / "matos/version.py"))["VERSION"]
source = root / "dist" / f"arcenal-matos-{version}.tar.gz"
with tarfile.open(source) as archive:
    names = archive.getnames()
    for member in archive.getmembers():
        parts = PurePosixPath(member.name).parts
        assert ".." not in parts and not member.name.startswith("/")
        assert not member.issym() and not member.islnk()
        assert not any(part in (".local", ".venv", "node_modules", "credentials.json") for part in parts)
        if parts[-1] == ".env":
            assert member.name.endswith("packaging/ynh/conf/.env")
            assert b"MATOS_MCP_TOKEN=__MCP_TOKEN__" in archive.extractfile(member).read()
    for expected in ("manage.py", "core/services.py", "matos/asgi.py", "matos/version.py", "static/theme.js", "static/app.css",
                     "static/fonts/inter-latin-400-normal.woff2", "static/scan.bundle.js", "static/THIRD_PARTY_NOTICES.txt"):
        assert any(name.endswith("/" + expected) for name in names)
with tarfile.open(root / "dist" / f"arcenal-matos-ynh-template-{version}.tar.gz") as archive:
    manifest = tomllib.loads(archive.extractfile("manifest.toml").read().decode())
    assert manifest["packaging_format"] == 2
    for name in ("install", "remove", "upgrade", "backup", "restore"):
        assert archive.getmember(f"scripts/{name}").mode & 0o111
with tempfile.TemporaryDirectory(dir=root / ".local") as directory:
    fixture = Path(directory)
    (fixture / "scripts").mkdir()
    (fixture / "dist").mkdir()
    (fixture / "matos").mkdir()
    shutil.copyfile(root / "matos/version.py", fixture / "matos/version.py")
    shutil.copyfile(root / "scripts/build_beta.py", fixture / "scripts/build_beta.py")
    shutil.copytree(root / "packaging/ynh", fixture / "packaging/ynh")
    copied = fixture / "dist" / source.name
    shutil.copyfile(source, copied)
    checksum = hashlib.sha256(copied.read_bytes()).hexdigest()
    subprocess.run([sys.executable, str(fixture / "scripts/build_beta.py"), "--source-url",
                    'https://example.invalid/beta.tar.gz?quoted="value"', "--license", "LicenseRef-VerificationOnly"],
                   capture_output=True, check=True)
    assert hashlib.sha256(copied.read_bytes()).hexdigest() == checksum
    with tarfile.open(fixture / "dist" / f"arcenal-matos-ynh-{version}.tar.gz") as archive:
        manifest = tomllib.loads(archive.extractfile("manifest.toml").read().decode())
        assert manifest["resources"]["sources"]["main"]["sha256"] == checksum
print("Archives vérifiées : sources et mentions tierces présentes, aucun fichier runtime/secret local, scripts du modèle exécutables.")
print("Finalisation de paquet vérifiée sur fixture isolée : archive distribuée conservée, SHA256 et échappement TOML corrects.")
