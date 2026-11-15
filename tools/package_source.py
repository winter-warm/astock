"""Create a reproducible-scope source archive without environments or user data."""
from pathlib import Path
import hashlib
import zipfile

from astock import __version__


def main():
    root = Path(__file__).resolve().parents[1]
    files = [root / name for name in (
        ".gitignore", "pyproject.toml", "uv.lock", "README.md", "AStock.spec",
        "Build-AStock.ps1", "Start-AStock.ps1", "启动AStock.ps1", "启动数据改进版.ps1",
        "开始使用.md", "desktop_entry.py")]
    for directory in ("src", "tests", "docs", "assets", "tools"):
        files.extend(path for path in (root / directory).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    target = root / "dist" / f"AStock-{__version__}-source.zip"
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, "AStock-source/" + path.relative_to(root).as_posix())
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("源码归档校验失败")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(digest + "  " + target.name + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
