from __future__ import annotations

import re
import socket
import time


IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251
SB = 250
SE = 240
IS = 0
SEND = 1

OPT_SUPPRESS_GA = 3
OPT_TERM_TYPE = 24
OPT_NAWS = 31

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class TelnetError(RuntimeError):
    pass


class TelnetSession:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        connect_timeout: float = 12.0,
        read_timeout: float = 0.8,
        cols: int = 80,
        rows: int = 25,
    ) -> None:
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.cols = cols
        self.rows = rows
        self.sock: socket.socket | None = None
        self.state = "data"
        self.sb = bytearray()
        self.text = ""

    def __enter__(self) -> "TelnetSession":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.connect_timeout)
        self.sock.settimeout(self.read_timeout)
        # TWGS rejects plain TCP. This establishes that we are a telnet client.
        self.sock.sendall(bytes([IAC, DO, 246]))

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def send_line(self, line: str = "") -> None:
        self.send_raw(line.encode("ascii", "ignore") + b"\r")

    def send_raw(self, payload: bytes) -> None:
        if self.sock is None:
            raise TelnetError("not connected")
        self.sock.sendall(payload)

    def read_available(self, duration: float = 0.0) -> str:
        if self.sock is None:
            raise TelnetError("not connected")
        end = time.monotonic() + duration
        chunks: list[str] = []
        while True:
            try:
                raw = self.sock.recv(8192)
            except socket.timeout:
                if duration and time.monotonic() < end:
                    continue
                break
            if not raw:
                raise TelnetError("connection closed")
            chunk = self._process_telnet(raw)
            if chunk:
                cleaned = self._clean_text(chunk)
                self.text += cleaned
                chunks.append(cleaned)
            if not duration or time.monotonic() >= end:
                break
        return "".join(chunks)

    def wait_for(
        self,
        patterns: str | list[str],
        *,
        timeout: float = 20.0,
        auto_pause: bool = False,
        since: int | None = None,
    ) -> str:
        if isinstance(patterns, str):
            patterns = [patterns]
        start = len(self.text) if since is None else since
        deadline = time.monotonic() + timeout
        pause_ack_at = -1
        while time.monotonic() < deadline:
            window = self.text[start:]
            if any(pattern in window for pattern in patterns):
                return window
            if auto_pause:
                pause_at = window.rfind("[Pause]")
                if pause_at >= 0 and pause_at != pause_ack_at:
                    pause_ack_at = pause_at
                    self.send_line()
            try:
                self.read_available(0.15)
            except TelnetError:
                raise
        raise TelnetError(f"timed out waiting for {patterns!r} from {self.host}:{self.port}")

    def _process_telnet(self, raw: bytes) -> str:
        out = bytearray()
        for b in raw:
            if self.state == "data":
                if b == IAC:
                    self.state = "iac"
                else:
                    out.append(b)
            elif self.state == "iac":
                if b == IAC:
                    out.append(IAC)
                    self.state = "data"
                elif b == WILL:
                    self.state = "will"
                elif b == WONT:
                    self.state = "wont"
                elif b == DO:
                    self.state = "do"
                elif b == DONT:
                    self.state = "dont"
                elif b == SB:
                    self.sb.clear()
                    self.state = "sb"
                else:
                    self.state = "data"
            elif self.state == "will":
                self._on_will(b)
                self.state = "data"
            elif self.state == "wont":
                self.state = "data"
            elif self.state == "do":
                self._on_do(b)
                self.state = "data"
            elif self.state == "dont":
                self.state = "data"
            elif self.state == "sb":
                if b == IAC:
                    self.state = "sb_iac"
                else:
                    self.sb.append(b)
            elif self.state == "sb_iac":
                if b == SE:
                    self._handle_subnegotiation()
                    self.state = "data"
                else:
                    self.sb.append(IAC)
                    self.sb.append(b)
                    self.state = "sb"
        return out.decode("cp437", "replace")

    def _on_will(self, opt: int) -> None:
        self._send_iac(DO if opt == OPT_SUPPRESS_GA else DONT, opt)

    def _on_do(self, opt: int) -> None:
        if opt in (OPT_TERM_TYPE, OPT_NAWS, OPT_SUPPRESS_GA):
            self._send_iac(WILL, opt)
            if opt == OPT_NAWS:
                self._send_naws()
        else:
            self._send_iac(WONT, opt)

    def _handle_subnegotiation(self) -> None:
        if len(self.sb) >= 2 and self.sb[0] == OPT_TERM_TYPE and self.sb[1] == SEND:
            self.send_raw(bytes([IAC, SB, OPT_TERM_TYPE, IS]) + b"ANSI" + bytes([IAC, SE]))

    def _send_naws(self) -> None:
        payload = bytearray([IAC, SB, OPT_NAWS])
        for value in (self.cols >> 8, self.cols & 0xFF, self.rows >> 8, self.rows & 0xFF):
            payload.append(value)
            if value == IAC:
                payload.append(IAC)
        payload.extend([IAC, SE])
        self.send_raw(bytes(payload))

    def _send_iac(self, verb: int, opt: int) -> None:
        self.send_raw(bytes([IAC, verb, opt]))

    @staticmethod
    def _clean_text(text: str) -> str:
        text = ANSI_RE.sub("", text)
        text = text.replace("\x00", "")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return text

