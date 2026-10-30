"""Preview or apply a backed-up Apache HTTPS API proxy configuration."""
from __future__ import annotations

import argparse
import difflib
import re
import subprocess
from datetime import datetime
from pathlib import Path


def enable_module(text: str, module: str) -> str:
    pattern = rf"(?mi)^\s*#?\s*(LoadModule\s+{re.escape(module)}\s+[^\r\n]+)$"
    result, count = re.subn(pattern, r"\1", text)
    if count != 1:
        raise ValueError(f"expected exactly one LoadModule directive for {module}; found {count}")
    return result


def add_include(text: str, server_name: str) -> str:
    if 'Include "conf/extra/twcrawl-api.conf"' in text:
        return text
    pattern = re.compile(r"(?mis)^\s*<VirtualHost\b[^>]*>.*?^\s*</VirtualHost>")
    matches = [m for m in pattern.finditer(text) if re.search(
        rf"(?mi)^\s*ServerName\s+{re.escape(server_name)}(?::\d+)?\s*$", m.group())]
    if len(matches) != 1:
        raise ValueError(f"expected one HTTPS virtual host named {server_name}; found {len(matches)}")
    match = matches[0]
    block = match.group()
    opening = block.index(">") + 1
    block = block[:opening] + '\nInclude "conf/extra/twcrawl-api.conf"\n' + block[opening:]
    return text[:match.start()] + block + text[match.end():]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apache-root", type=Path, required=True)
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    root = args.apache_root.resolve()
    main_conf = root / "conf" / "httpd.conf"
    ssl_conf = root / "conf" / "extra" / "httpd-ssl.conf"
    proxy_conf = root / "conf" / "extra" / "twcrawl-api.conf"
    main_text = main_conf.read_text(encoding="utf-8")
    ssl_text = ssl_conf.read_text(encoding="utf-8")
    updated = enable_module(enable_module(main_text, "proxy_module"), "proxy_http_module")
    plan = {
        main_conf: updated,
        ssl_conf: add_include(ssl_text, args.server_name),
        proxy_conf: Path(__file__).with_name("apache-api.conf").read_text(encoding="utf-8"),
    }
    for path, content in plan.items():
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        print("".join(difflib.unified_diff(old.splitlines(True), content.splitlines(True),
                                         fromfile=str(path), tofile=str(path))), end="")
    if not args.apply:
        print("Preview only. Use --apply after reviewing the changes.")
        return
    executable = root / "bin" / "httpd.exe"
    if not executable.exists():
        executable = root / "bin" / "httpd"
    subprocess.run([str(executable), "-t"], cwd=root, check=True)
    originals = {path: path.read_bytes() if path.exists() else None for path in plan}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        for path, content in plan.items():
            if originals[path] is not None:
                backup = path.with_name(path.name + f".twcrawl-{stamp}.bak")
                backup.write_bytes(originals[path])
                print(f"Backup: {backup}")
            path.write_text(content, encoding="utf-8")
        subprocess.run([str(executable), "-t"], cwd=root, check=True)
    except Exception:
        for path, content in originals.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        print("Configuration test failed; restored original files.")
        raise
    if args.restart:
        subprocess.run([str(executable), "-k", "restart"], cwd=root, check=True)
    print("Apache API configuration installed and validated.")


if __name__ == "__main__":
    main()
