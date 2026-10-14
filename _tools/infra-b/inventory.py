import io, os, re

root = 'redesign-demo/src'
pats = {
    'ws-fold': r'ws-fold\b',
    'ws-context': r'ws-context\b',
    'plan-stage': r'plan-stage\b',
    'ws-task__details': r'ws-task__details\b',
}
print('=== 旧折叠用法 ===')
for dp, dn, fn in os.walk(root):
    if 'styles' in dp:
        continue
    for f in sorted(fn):
        if not f.endswith('.vue'):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, 'redesign-demo').replace('\\', '/')
        s = io.open(p, encoding='utf-8').read().split('\n')
        for i, l in enumerate(s, 1):
            for k, pt in pats.items():
                if re.search(pt, l):
                    idx = l.rfind('<details', 0, re.search(pt, l).start())
                    frag = l[idx:idx + 150].replace('\n', ' ') if idx >= 0 else l[:120]
                    print(u'%s:%d [%s] %s' % (rel, i, k, frag.strip()[:145]))

print()
print('=== InfoSheet 调用点 ===')
for dp, dn, fn in os.walk(root):
    for f in sorted(fn):
        if not f.endswith('.vue'):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, 'redesign-demo').replace('\\', '/')
        s = io.open(p, encoding='utf-8').read().split('\n')
        for i, l in enumerate(s, 1):
            for m in re.finditer(r'<InfoSheet[^>]*>', l):
                print(u'%s:%d %s' % (rel, i, m.group(0)[:180]))

print()
print('=== 其它折叠形态 ===')
for dp, dn, fn in os.walk(root):
    if 'styles' in dp:
        continue
    for f in sorted(fn):
        if not f.endswith('.vue'):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, 'redesign-demo').replace('\\', '/')
        s = io.open(p, encoding='utf-8').read().split('\n')
        for i, l in enumerate(s, 1):
            if 'exp-evidence' in l or re.search(r'<details', l):
                print(u'%s:%d %s' % (rel, i, l.strip()[:130]))
