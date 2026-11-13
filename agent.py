#!/usr/bin/env python3
"""AIProve autonomous agent — stdlib only, no dependencies.

Reads aiprove.fun/skill.md, signs in with its own secp256k1 keypair
(EIP-191 challenge/response), lists open bounties, enters them, and
completes the forecast/trading-signal bounties with a simple
momentum rule over public price data. Repo-based and link-based
bounties are entered and logged as out of scope for this agent.

Usage:
  python3 agent.py [--key agent.key] [--api https://aiprove.fun]

The key file holds one hex private key. If it does not exist, a fresh
keypair is generated and saved there. Every step is traced to stdout.
"""
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------- keccak-256
_RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
       0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
       0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
       0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
       0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
       0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
_R = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
      [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_MASK = (1 << 64) - 1


def _rol(x, n):
    return ((x << n) | (x >> (64 - n))) & _MASK if n else x


def _keccak_f(state):
    for rc in _RC:
        c = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20]
             for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] ^= d[x]
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rol(state[x + 5 * y], _R[x][y])
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] = b[x + 5 * y] ^ ((~b[(x + 1) % 5 + 5 * y]) & b[(x + 2) % 5 + 5 * y])
        state[0] ^= rc


def keccak256(data: bytes) -> bytes:
    rate = 136
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != rate - 1:
        padded.append(0x00)
    padded.append(0x80)
    state = [0] * 25
    for off in range(0, len(padded), rate):
        block = padded[off:off + rate]
        for i in range(rate // 8):
            state[i] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        _keccak_f(state)
    out = bytearray()
    while len(out) < 32:
        for i in range(rate // 8):
            out += state[i].to_bytes(8, "little")
        if len(out) < 32:
            _keccak_f(state)
    return bytes(out[:32])

# ---------------------------------------------------------------- secp256k1
_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
      0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)


def _add(p, q):
    if p is None:
        return q
    if q is None:
        return p
    if p[0] == q[0]:
        if (p[1] + q[1]) % _P == 0:
            return None  # p == -q (includes doubling a y=0 point)
        lam = (3 * p[0] * p[0]) * pow(2 * p[1], _P - 2, _P) % _P  # doubling
    else:
        lam = (q[1] - p[1]) * pow((q[0] - p[0]) % _P, _P - 2, _P) % _P
    x = (lam * lam - p[0] - q[0]) % _P
    return (x, (lam * (p[0] - x) - p[1]) % _P)


def _mul(k, point=_G):
    r = None
    while k:
        if k & 1:
            r = _add(r, point)
        point = _add(point, point)
        k >>= 1
    return r


def address_of(priv: int) -> str:
    x, y = _mul(priv)
    pub = x.to_bytes(32, "big") + y.to_bytes(32, "big")
    return "0x" + keccak256(pub)[-20:].hex()


def _rfc6979(priv: int, digest: bytes) -> int:
    bx = priv.to_bytes(32, "big")
    bh = (int.from_bytes(digest, "big") % _N).to_bytes(32, "big")
    v, k = b"\x01" * 32, b"\x00" * 32
    k = hmac.new(k, v + b"\x00" + bx + bh, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    k = hmac.new(k, v + b"\x01" + bx + bh, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    while True:
        v = hmac.new(k, v, hashlib.sha256).digest()
        cand = int.from_bytes(v, "big")
        if 1 <= cand < _N:
            return cand
        k = hmac.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac.new(k, v, hashlib.sha256).digest()


def sign_eip191(priv: int, message: str) -> str:
    raw = message.encode()
    digest = keccak256(b"\x19Ethereum Signed Message:\n" + str(len(raw)).encode() + raw)
    z = int.from_bytes(digest, "big")
    k = _rfc6979(priv, digest)
    rx, ry = _mul(k)
    r = rx % _N
    s = (pow(k, _N - 2, _N) * (z + r * priv)) % _N
    rec = ry & 1
    if s > _N // 2:
        s = _N - s
        rec ^= 1
    sig = r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([27 + rec])
    return "0x" + sig.hex()

# ---------------------------------------------------------------- http
def http(method, url, body=None, token=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for _ in range(tries):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": "aiprove-agent/1.0"})
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode() or "{}")
            except Exception:
                return e.code, {}
        except Exception as e:  # flaky connections: retry
            last = e
            time.sleep(3)
    raise last


def http_text(url, tries=4):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "aiprove-agent/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(3)
    raise last

# ---------------------------------------------------------------- market data
def kraken_daily_closes(pair):
    txt = http_text(f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval=1440")
    res = json.loads(txt)["result"]
    key = [k for k in res if k != "last"][0]
    return [float(row[4]) for row in res[key]]


def yahoo_closes(symbol):
    txt = http_text(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d")
    closes = json.loads(txt)["chart"]["result"][0]["indicators"]["quote"][0]["close"]
    return [c for c in closes if c]


def trend_call(closes):
    """(answer, confidence) from recent daily closes."""
    if len(closes) < 4:
        return "yes", 0.52
    move = closes[-1] / closes[-4] - 1.0
    strength = min(0.60, 0.52 + min(0.08, abs(move) * 1.2))
    return ("yes", round(strength, 2)) if move >= 0 else ("no", round(strength, 2))

# ---------------------------------------------------------------- agent
FORECAST_PLAN = {
    "btc-tomorrow":         ("direction", "BTC"),
    "forecast-btc-7d":      ("direction", "BTC"),
    "forecast-eth-24h":     ("direction", "ETH"),
    "signal-eth-pnl-24h":   ("signal", "ETH"),
    "spy-close-1dollar":    ("number", "SPY"),
    "forecast-gold-tomorrow": ("number", "GLD"),
    "forecast-nvda-3d":     ("number", "NVDA"),
}
KRAKEN = {"BTC": "XBTUSD", "ETH": "ETHUSD"}


def main(argv):
    key_path, api = "agent.key", "https://aiprove.fun"
    args = argv[1:]
    if "--key" in args:
        key_path = args[args.index("--key") + 1]
    if "--api" in args:
        api = args[args.index("--api") + 1]

    if os.path.exists(key_path):
        priv = int(open(key_path).read().strip(), 16)
        print(f"[key] loaded existing keypair from {key_path}")
    else:
        priv = secrets.randbelow(_N - 1) + 1
        with open(key_path, "w") as f:
            f.write("%064x" % priv)
        os.chmod(key_path, 0o600)
        print(f"[key] generated a fresh keypair, saved to {key_path}")
    addr = address_of(priv)
    print(f"[key] agent address: {addr}")

    print("[skill] reading https://aiprove.fun/skill.md ...")
    try:
        skill = http_text(api + "/skill.md")
        print(f"[skill] read {len(skill)} chars; following its REST flow")
    except Exception as e:
        print(f"[skill] WARNING: skill.md fetch failed ({e}); continuing with the known REST flow")

    st, ch = http("GET", f"{api}/api/auth/challenge?address={addr}")
    sig = sign_eip191(priv, ch["challenge"])
    st, v = http("POST", api + "/api/auth/verify", {"address": addr, "signature": sig})
    token = v.get("token")
    if not token:
        print(f"[auth] FAILED: {st} {json.dumps(v)[:200]}")
        return 1
    print(f"[auth] signed in (session expires {v.get('expiresAt')})")

    st, board = http("GET", api + "/api/bounties?status=open")
    bounties = board.get("bounties", [])
    print(f"[board] {len(bounties)} open bounties")

    entered, completed, skipped = 0, 0, 0
    closes_cache = {}
    for b in bounties:
        slug = b["slug"]
        st, r = http("POST", f"{api}/api/bounties/{slug}/enter", {}, token=token)
        if st in (200, 201):
            entered += 1
        plan = FORECAST_PLAN.get(slug)
        if not plan:
            print(f"[skip] {slug}: not a forecast this agent completes (entered only)")
            skipped += 1
            continue
        kind, asset = plan
        try:
            if asset not in closes_cache:
                closes_cache[asset] = (kraken_daily_closes(KRAKEN[asset])
                                       if asset in KRAKEN else yahoo_closes(asset))
            closes = closes_cache[asset]
            if kind == "direction":
                ans, conf = trend_call(closes)
                payload = {"prediction": {"answer": ans, "confidence": conf}}
                desc = f"{ans} @ {conf}"
            elif kind == "signal":
                ans, _ = trend_call(closes)
                payload = {"prediction": {"answer": "long" if ans == "yes" else "short"}}
                desc = payload["prediction"]["answer"]
            else:
                last = closes[-1]
                drift = (closes[-1] - closes[-2]) * 0.3 if len(closes) > 1 else 0
                payload = {"prediction": {"answer": round(last + drift, 2)}}
                desc = str(payload["prediction"]["answer"])
            st, r = http("POST", f"{api}/api/bounties/{slug}/submit", payload, token=token)
            ok = st in (200, 201) and r.get("status")
            print(f"[submit] {slug}: {desc} -> {st} {r.get('status', json.dumps(r)[:120])}")
            completed += 1 if ok else 0
        except Exception as e:
            print(f"[submit] {slug}: FAILED ({e})")
    print(f"[done] entered {entered}, completed {completed}, entered-only {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
