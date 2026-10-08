"""BHTTP v1: binary HTTP framing shared by bserve and bcurl. See SPEC.md.

Frame header (8 bytes, big-endian):
    Length(24) | Type(8) | Flags(8) | RequestID(24)
"""
import struct
from collections import namedtuple

HEADER_LEN = 8
MAX_FRAME = (1 << 24) - 1          # largest payload a 24-bit Length can express
MAX_ID = (1 << 24) - 1

T_REQUEST, T_RESPONSE, T_DATA = 0x01, 0x02, 0x03
TYPE_NAMES = {T_REQUEST: "REQUEST", T_RESPONSE: "RESPONSE", T_DATA: "DATA"}
F_END_STREAM = 0x01
M_GET = 0x01

STATIC_TABLE = {
    1: "host", 2: "user-agent", 3: "accept", 4: "content-length",
    5: "content-type", 6: "server", 7: "date", 8: "last-modified",
    9: "etag", 10: "connection",
}
NAME_TO_INDEX = {name: idx for idx, name in STATIC_TABLE.items()}

Frame = namedtuple("Frame", "type flags req_id payload raw")


class ProtocolError(Exception):
    """Payload is malformed, but framing is intact (stream still in sync)."""


class FatalFrameError(ProtocolError):
    """Framing itself is unusable (e.g. oversize frame); connection must close."""

    def __init__(self, msg, req_id=None):
        super().__init__(msg)
        self.req_id = req_id


class ConnectionClosed(Exception):
    """Peer closed the connection in the middle of a frame."""


# ---------------------------------------------------------------- framing
def read_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionClosed(f"EOF after {len(buf)} of {n} bytes")
        buf += chunk
    return bytes(buf)


def encode_frame(ftype, flags, req_id, payload=b""):
    if len(payload) > MAX_FRAME:
        raise ValueError("payload too large for one frame")
    if not 0 <= req_id <= MAX_ID:
        raise ValueError("request id out of range")
    return (len(payload).to_bytes(3, "big") + bytes([ftype, flags])
            + req_id.to_bytes(3, "big") + payload)


def read_frame(sock, max_payload=MAX_FRAME):
    """Return the next Frame, or None on a clean EOF at a frame boundary."""
    first = sock.recv(HEADER_LEN)
    if not first:
        return None
    header = first + read_exact(sock, HEADER_LEN - len(first))
    length = int.from_bytes(header[0:3], "big")
    ftype, flags = header[3], header[4]
    req_id = int.from_bytes(header[5:8], "big")
    if length > max_payload:
        raise FatalFrameError(f"frame of {length} bytes exceeds limit", req_id)
    payload = read_exact(sock, length) if length else b""
    return Frame(ftype, flags, req_id, payload, header + payload)


def describe(frame):
    name = TYPE_NAMES.get(frame.type, f"UNKNOWN(0x{frame.type:02x})")
    return (f"{name} id={frame.req_id} flags=0x{frame.flags:02x} "
            f"len={len(frame.payload)}")


# ----------------------------------------------------------- header block
def encode_headers(headers):
    if len(headers) > 255:
        raise ValueError("too many headers")
    out = bytearray([len(headers)])
    for name, value in headers:
        name = name.lower()
        val = value.encode("utf-8") if isinstance(value, str) else value
        if len(val) > 0xFFFF:
            raise ValueError("header value too long")
        idx = NAME_TO_INDEX.get(name)
        if idx:
            out.append(0x80 | idx)
        else:
            nb = name.encode("ascii")
            if not 0 < len(nb) <= 255:
                raise ValueError("bad header name length")
            out += b"\x00" + bytes([len(nb)]) + nb
        out += struct.pack(">H", len(val)) + val
    return bytes(out)


def _take(buf, pos, n):
    if pos + n > len(buf):
        raise ProtocolError("truncated payload")
    return buf[pos:pos + n], pos + n


def decode_headers(buf, pos=0):
    """Parse a header block starting at pos. Returns (list, new_pos)."""
    raw, pos = _take(buf, pos, 1)
    headers = []
    for _ in range(raw[0]):
        marker, pos = _take(buf, pos, 1)
        marker = marker[0]
        if marker & 0x80:
            name = STATIC_TABLE.get(marker & 0x7F)
            if name is None:
                raise ProtocolError(f"unknown header index {marker & 0x7F}")
        elif marker == 0x00:
            nlen, pos = _take(buf, pos, 1)
            nb, pos = _take(buf, pos, nlen[0])
            if not nb:
                raise ProtocolError("empty header name")
            try:
                name = nb.decode("ascii").lower()
            except UnicodeDecodeError:
                raise ProtocolError("non-ascii header name")
        else:
            raise ProtocolError(f"reserved header marker 0x{marker:02x}")
        vlen, pos = _take(buf, pos, 2)
        vb, pos = _take(buf, pos, struct.unpack(">H", vlen)[0])
        try:
            headers.append((name, vb.decode("utf-8")))
        except UnicodeDecodeError:
            raise ProtocolError("header value is not utf-8")
    return headers, pos


# ------------------------------------------------------- message payloads
def encode_request(req_id, path, headers, method=M_GET):
    pb = path.encode("utf-8")
    if len(pb) > 0xFFFF:
        raise ValueError("path too long")
    payload = bytes([method]) + struct.pack(">H", len(pb)) + pb + encode_headers(headers)
    return encode_frame(T_REQUEST, 0, req_id, payload)


def decode_request(payload):
    head, pos = _take(payload, 0, 3)
    method = head[0]
    pb, pos = _take(payload, pos, struct.unpack(">H", head[1:3])[0])
    try:
        path = pb.decode("utf-8")
    except UnicodeDecodeError:
        raise ProtocolError("path is not utf-8")
    headers, pos = decode_headers(payload, pos)
    if pos != len(payload):
        raise ProtocolError("trailing bytes after header block")
    return method, path, headers


def encode_response(req_id, status, headers):
    payload = struct.pack(">H", status) + encode_headers(headers)
    return encode_frame(T_RESPONSE, 0, req_id, payload)


def decode_response(payload):
    head, pos = _take(payload, 0, 2)
    headers, pos = decode_headers(payload, pos)
    if pos != len(payload):
        raise ProtocolError("trailing bytes after header block")
    return struct.unpack(">H", head)[0], headers


def encode_data(req_id, data, end=False):
    return encode_frame(T_DATA, F_END_STREAM if end else 0, req_id, data)


# ---------------------------------------------------------------- hexdump
def hexdump(data, prefix=""):
    lines = []
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        hexpart = " ".join(f"{b:02x}" for b in chunk).ljust(47)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{prefix}{off:08x}  {hexpart}  |{text}|")
    return "\n".join(lines)
