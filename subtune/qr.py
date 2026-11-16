"""A small QR code encoder (byte mode, error correction level M, versions 1-6), standard library only.

Used to show a code the owner scans with a phone to open the room builder: up to 106 bytes,
plenty for http://<address>:<port>/build?pair=<token>. Follows ISO/IEC 18004 the same way
Project Nayuki's reference encoder does (finder, timing and alignment patterns, Reed-Solomon
over GF(256) with 0x11D, interleaved blocks, the eight masks scored by the standard penalties).
"""
from __future__ import annotations

# version -> (ECC codewords per block, number of blocks, data codewords per block), level M
_M = {1: (10, 1, 16), 2: (16, 1, 28), 3: (26, 1, 44), 4: (18, 2, 32), 5: (24, 2, 43), 6: (16, 4, 27)}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}
_FMT_M = 0                 # the two error-correction bits for level M


def _gmul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z & 0xFF


def rs_divisor(degree: int) -> list[int]:
    out = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            out[j] = _gmul(out[j], root)
            if j + 1 < degree:
                out[j] ^= out[j + 1]
        root = _gmul(root, 0x02)
    return out


def rs_remainder(data: list[int], divisor: list[int]) -> list[int]:
    out = [0] * len(divisor)
    for b in data:
        f = b ^ out.pop(0)
        out.append(0)
        for i, c in enumerate(divisor):
            out[i] ^= _gmul(c, f)
    return out


def format_bits(mask: int, ecl: int = _FMT_M) -> int:
    """The 15 format bits (error level + mask, BCH-protected, XOR-masked)."""
    data = (ecl << 3) | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return ((data << 10) | rem) ^ 0x5412


def _codewords(text: bytes, ver: int) -> list[int]:
    ecc, nblk, dlen = _M[ver]
    cap = nblk * dlen
    bits = [0, 1, 0, 0] + [(len(text) >> i) & 1 for i in range(7, -1, -1)]
    for b in text:
        bits += [(b >> i) & 1 for i in range(7, -1, -1)]
    bits += [0] * min(4, cap * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(data) < cap:
        data.append(pad)
        pad ^= 0xEC ^ 0x11
    blocks = [data[k * dlen:(k + 1) * dlen] for k in range(nblk)]
    div = rs_divisor(ecc)
    eccs = [rs_remainder(b, div) for b in blocks]
    out = [b[i] for i in range(dlen) for b in blocks]
    out += [e[i] for i in range(ecc) for e in eccs]
    return out


def _mask_bit(m, x, y) -> bool:
    return [(x + y) % 2 == 0, y % 2 == 0, x % 3 == 0, (x + y) % 3 == 0, (x // 3 + y // 2) % 2 == 0,
            x * y % 2 + x * y % 3 == 0, (x * y % 2 + x * y % 3) % 2 == 0, ((x + y) % 2 + x * y % 3) % 2 == 0][m]


def _penalty(g) -> int:
    n, s = len(g), 0
    lines = [row for row in g] + [[g[y][x] for y in range(n)] for x in range(n)]
    for line in lines:                                   # N1: runs of 5+ of one color
        run, prev = 0, None
        for v in line:
            run = run + 1 if v == prev else 1
            prev = v
            if run == 5:
                s += 3
            elif run > 5:
                s += 1
        txt = "".join("1" if v else "0" for v in line)   # N3: finder-like patterns
        for pat in ("10111010000", "00001011101"):
            i = txt.find(pat)
            while i >= 0:
                s += 40
                i = txt.find(pat, i + 1)
    for y in range(n - 1):                               # N2: 2x2 blocks
        for x in range(n - 1):
            if g[y][x] == g[y][x + 1] == g[y + 1][x] == g[y + 1][x + 1]:
                s += 3
    dark = sum(map(sum, g))                              # N4: balance
    s += 10 * (abs(dark * 20 - n * n * 10) // (n * n))
    return s


def matrix(text: str | bytes) -> list[list[bool]]:
    """The QR code's modules (rows of booleans, True = dark), without the quiet zone."""
    data = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    ver = next((v for v in _M if len(data) <= _M[v][1] * _M[v][2] - 2), None)
    if ver is None:
        raise ValueError(f"too long for a small QR code ({len(data)} bytes, at most {_M[6][1] * _M[6][2] - 2})")
    n = 17 + 4 * ver
    g = [[False] * n for _ in range(n)]
    fn = [[False] * n for _ in range(n)]

    def put(x, y, dark):
        g[y][x] = dark
        fn[y][x] = True

    for i in range(n):                                   # timing patterns
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):      # finders with their light separators
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < n and 0 <= y < n:
                    put(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    al = _ALIGN[ver]
    for i, ax in enumerate(al):                          # alignment patterns (not over the finders)
        for j, ay in enumerate(al):
            if (i == 0 and j == 0) or (i == 0 and j == len(al) - 1) or (i == len(al) - 1 and j == 0):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    put(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)

    def draw_format(mask):
        b = format_bits(mask)
        bit = lambda i: (b >> i) & 1 == 1
        for i in range(6):
            put(8, i, bit(i))
        put(8, 7, bit(6))
        put(8, 8, bit(7))
        put(7, 8, bit(8))
        for i in range(9, 15):
            put(14 - i, 8, bit(i))
        for i in range(8):
            put(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            put(8, n - 15 + i, bit(i))
        put(8, n - 8, True)                              # the dark module

    draw_format(0)                                       # reserves the format areas
    cw = _codewords(data, ver)
    i, right = 0, n - 1
    while right >= 1:                                    # zigzag placement, two columns at a time
        if right == 6:
            right = 5
        for vert in range(n):
            for j in range(2):
                x = right - j
                up = ((right + 1) & 2) == 0
                y = n - 1 - vert if up else vert
                if not fn[y][x] and i < len(cw) * 8:
                    g[y][x] = (cw[i >> 3] >> (7 - (i & 7))) & 1 == 1
                    i += 1
        right -= 2
    best = None
    for m in range(8):
        t = [row[:] for row in g]
        for y in range(n):
            for x in range(n):
                if not fn[y][x] and _mask_bit(m, x, y):
                    t[y][x] = not t[y][x]
        g0 = g
        g = t
        draw_format(m)
        sc = _penalty(g)
        if best is None or sc < best[0]:
            best = (sc, [row[:] for row in g])
        g = g0
    return best[1]


def svg(text: str, px: int = 6, quiet: int = 4) -> str:
    """The QR code as an SVG image (black on white, with the standard quiet zone)."""
    m = matrix(text)
    n = len(m) + 2 * quiet
    d = "".join(f"M{x + quiet} {y + quiet}h1v1h-1z" for y, row in enumerate(m) for x, v in enumerate(row) if v)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{n * px}" height="{n * px}" '
            f'shape-rendering="crispEdges" role="img" aria-label="QR code"><rect width="{n}" height="{n}" fill="#fff"/>'
            f'<path d="{d}" fill="#000"/></svg>')
