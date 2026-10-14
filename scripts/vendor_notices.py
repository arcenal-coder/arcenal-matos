"""Preserve third-party licenses alongside the self-hosted scanner bundle."""
from pathlib import Path
from shutil import copyfile

root = Path(__file__).resolve().parent.parent
notices = []
for package in ("browser", "library"):
    license_file = root / "node_modules" / "@zxing" / package / "LICENSE"
    notices.append(f"@zxing/{package}\n\n{license_file.read_text()}\n")
font_package = root / "node_modules" / "@fontsource" / "inter"
notices.append(f"@fontsource/inter\n\n{(font_package / 'LICENSE').read_text()}\n")
fonts = root / "static" / "fonts"
fonts.mkdir(exist_ok=True)
for weight in (400, 600, 700, 800):
    name = f"inter-latin-{weight}-normal.woff2"
    copyfile(font_package / "files" / name, fonts / name)
(root / "static" / "THIRD_PARTY_NOTICES.txt").write_text("\n\n".join(notices).rstrip() + "\n")
