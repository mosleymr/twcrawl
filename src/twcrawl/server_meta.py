from __future__ import annotations

import re


OPENTW_GAMEOP = "Kairos Bridger"


def is_opentw_server(server: dict) -> bool:
    values = [
        server.get("name"),
        server.get("slug"),
        server.get("telnet"),
        server.get("registered_to"),
        server.get("server_software"),
        server.get("type"),
        server.get("tradewars_version"),
    ]
    return any("opentw" in str(value or "").casefold() for value in values)


def server_display_type(server: dict) -> str:
    if is_opentw_server(server):
        return "OpenTW"
    return str(server.get("type") or "twgs2").upper()


def server_display_version(server: dict) -> str:
    version = str(server.get("tradewars_version") or "").strip()
    if is_opentw_server(server):
        if version.lower().startswith("opentw"):
            return canonical_opentw_version(version)
        match = re.search(r"\b(\d+(?:\.\d+)?[A-Za-z]?)\b", version)
        return f"OpenTW {match.group(1)}" if match else "OpenTW"
    return version


def server_display_gameop(server: dict) -> str:
    gameop = str(server.get("gameop") or "").strip()
    if gameop:
        return gameop
    return OPENTW_GAMEOP if is_opentw_server(server) else ""


def normalize_server_metadata(server: dict) -> None:
    if not is_opentw_server(server):
        return
    server["type"] = "opentw"
    server["server_software"] = "OpenTW"
    server["tradewars_version"] = server_display_version(server)
    if not server.get("gameop"):
        server["gameop"] = OPENTW_GAMEOP


def canonical_opentw_version(value: str) -> str:
    match = re.search(r"\bopentw\s+(.+)", value, re.IGNORECASE)
    if not match:
        return "OpenTW"
    return f"OpenTW {match.group(1).strip()}"
