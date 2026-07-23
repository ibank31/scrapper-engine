"""Decoder payload Next.js Flight (self.__next_f.push) + parser JSON balanced.
Dipakai reward_campaign; berguna untuk situs Next.js lain.
"""
import json, re

CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')


def decode_blob(html):
    parts = []
    for m in CHUNK_RE.finditer(html):
        c = m.group(1)
        try: parts.append(json.loads('"' + c + '"'))
        except Exception: parts.append(c.encode().decode("unicode_escape", "ignore"))
    return "\n".join(parts)


def parse_balanced(s, start):
    depth = 0; i = start; instr = False; esc = False
    while i < len(s):
        c = s[i]
        if instr:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': instr = False
        else:
            if c == '"': instr = True
            elif c in "{[": depth += 1
            elif c in "}]":
                depth -= 1
                if depth == 0: return s[start:i + 1]
        i += 1
    return None


def build_refmap(blob):
    refs = {}
    for m in re.finditer(r'([0-9a-f]{1,4}):T([0-9a-f]+),', blob):
        try: refs[m.group(1)] = blob[m.end(): m.end() + int(m.group(2), 16)]
        except ValueError: pass
    return refs
