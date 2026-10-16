"""Read only a root-level string from unfinished JSON; never expose private fields."""
import json


def partial_root_string(raw: str, field: str) -> str:
    start = raw.find('{')
    if start < 0:
        return ''
    depth, i, key, expecting_key = 0, start, None, False
    while i < len(raw):
        ch = raw[i]
        if ch == '"':
            begin = i
            i += 1
            while i < len(raw):
                if raw[i] == '\\':
                    i += 2
                elif raw[i] == '"':
                    break
                else:
                    i += 1
            complete = i < len(raw)
            token = raw[begin:i + 1] if complete else raw[begin:]
            if depth == 1 and key == field and not expecting_key:
                if complete:
                    try:
                        return json.loads(token)
                    except ValueError:
                        return ''
                # Trim an unfinished escape, including split unicode escapes.
                content = token[1:]
                cut = len(content)
                j = 0
                while j < len(content):
                    if content[j] != '\\':
                        j += 1
                        continue
                    size = 6 if content[j:j+2] == '\\u' else 2
                    if j + size > len(content):
                        cut = j
                        break
                    j += size
                try:
                    value = json.loads('"' + content[:cut] + '"')
                    # A surrogate pair may be divided between transport chunks.
                    return value.rstrip(''.join(chr(c) for c in range(0xD800, 0xE000)))
                except ValueError:
                    return ''
            if not complete:
                return ''
            if depth == 1 and expecting_key:
                key = json.loads(token)
                expecting_key = False
            i += 1
            continue
        if ch in '{[':
            depth += 1
            if depth == 1:
                expecting_key = True
        elif ch in '}]':
            depth -= 1
        elif ch == ',' and depth == 1:
            key, expecting_key = None, True
        i += 1
    return ''
