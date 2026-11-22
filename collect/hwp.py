"""한글(HWP 5) 파일에서 글자만 뽑습니다(조례 별표용). olefile 필요."""
import io
import struct
import zlib

# 8칸(16바이트)을 차지하는 조판 부호
_EXT = set(range(1, 10)) | {11, 12} | set(range(14, 24))


def _para_text(b):
    out, i, n = [], 0, len(b) // 2
    while i < n:
        c = struct.unpack_from('<H', b, i * 2)[0]
        if c in _EXT:
            i += 8
            continue
        if c in (10, 13):
            out.append('\n')
        elif c == 9:
            out.append('\t')
        elif c >= 32:
            out.append(chr(c))
        i += 1
    return ''.join(out)


def hwp_text(data):
    import olefile
    ole = olefile.OleFileIO(io.BytesIO(data))
    hdr = ole.openstream('FileHeader').read()
    comp = bool(struct.unpack_from('<I', hdr, 36)[0] & 1)
    secs = sorted([s for s in ole.listdir() if s[0] == 'BodyText'], key=lambda s: int(s[1].replace('Section', '') or 0))
    paras = []
    for s in secs:
        raw = ole.openstream(s).read()
        if comp:
            raw = zlib.decompress(raw, -15)
        p = 0
        while p + 4 <= len(raw):
            h = struct.unpack_from('<I', raw, p)[0]
            tag, size = h & 0x3FF, (h >> 20) & 0xFFF
            p += 4
            if size == 0xFFF:
                size = struct.unpack_from('<I', raw, p)[0]
                p += 4
            if tag == 67:
                t = _para_text(raw[p:p + size]).strip()
                if t:
                    paras.append(t)
            p += size
    return '\n'.join(paras)
