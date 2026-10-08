"""bserve: BHTTP v1 file server.   Usage: bserve <root> <port> [host]"""
import mimetypes
import os
import socket
import sys
import threading

from proto import (ConnectionClosed, FatalFrameError, M_GET, ProtocolError,
                   T_REQUEST, decode_request, describe, encode_data,
                   encode_response, read_frame)

MAX_REQUEST_FRAME = 64 * 1024   # inbound frames larger than this are fatal
CHUNK = 64 * 1024               # body bytes per DATA frame
SERVER_NAME = "bserve/1"


def resolve(root, path):
    """Map a request path to a regular file under root, or None."""
    if not path.startswith("/") or "\x00" in path:
        return None
    root_real = os.path.realpath(root)
    full = os.path.realpath(os.path.join(root_real, path.lstrip("/") or "index.html"))
    if os.path.commonpath([full, root_real]) != root_real:
        return None
    if os.path.isdir(full):
        full = os.path.join(full, "index.html")
    return full if os.path.isfile(full) else None


def send_status(conn, req_id, status):
    conn.sendall(encode_response(req_id, status,
                                 [("server", SERVER_NAME), ("content-length", "0")]))
    conn.sendall(encode_data(req_id, b"", end=True))


def send_file(conn, req_id, full):
    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    conn.sendall(encode_response(req_id, 200, [
        ("server", SERVER_NAME),
        ("content-type", ctype),
        ("content-length", str(os.path.getsize(full))),
    ]))
    with open(full, "rb") as f:
        chunk = f.read(CHUNK)
        while True:
            nxt = f.read(CHUNK)
            conn.sendall(encode_data(req_id, chunk, end=not nxt))
            if not nxt:
                break
            chunk = nxt


def handle_connection(conn, root, log):
    with conn:
        try:
            while True:
                try:
                    frame = read_frame(conn, MAX_REQUEST_FRAME)
                except FatalFrameError as e:
                    if e.req_id is not None:
                        send_status(conn, e.req_id, 400)
                    log(f"fatal framing error, closing: {e}")
                    return
                if frame is None:
                    return
                if frame.type != T_REQUEST:
                    log(f"skipping {describe(frame)}")   # unknown/unexpected: MUST skip
                    continue
                try:
                    method, path, _headers = decode_request(frame.payload)
                    if method != M_GET:
                        raise ProtocolError("unsupported method")
                except ProtocolError as e:
                    log(f"400 id={frame.req_id}: {e}")
                    send_status(conn, frame.req_id, 400)
                    continue
                full = resolve(root, path)
                if full is None:
                    log(f"404 id={frame.req_id} {path}")
                    send_status(conn, frame.req_id, 404)
                else:
                    log(f"200 id={frame.req_id} {path}")
                    send_file(conn, frame.req_id, full)
        except (ConnectionClosed, OSError):
            return


def serve(listener, root, log=lambda m: None):
    while True:
        try:
            conn, addr = listener.accept()
        except OSError:
            return
        threading.Thread(target=handle_connection, args=(conn, root, log),
                         daemon=True).start()


def start_server(root, host="127.0.0.1", port=0, log=lambda m: None):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((host, port))
    listener.listen()
    t = threading.Thread(target=serve, args=(listener, root, log), daemon=True)
    t.start()
    return listener, t


def main(argv):
    if len(argv) not in (3, 4) or not os.path.isdir(argv[1]) or not argv[2].isdigit():
        print("usage: bserve <root-dir> <port> [host]", file=sys.stderr)
        return 2
    host = argv[3] if len(argv) == 4 else "0.0.0.0"
    listener, t = start_server(argv[1], host, int(argv[2]),
                               log=lambda m: print(m, file=sys.stderr, flush=True))
    print(f"bserve: serving {argv[1]} on {host}:{argv[2]}", file=sys.stderr, flush=True)
    try:
        t.join()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
