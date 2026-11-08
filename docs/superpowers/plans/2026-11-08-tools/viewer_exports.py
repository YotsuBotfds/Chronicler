"""Census of viewer exports: no consumer, test-only, or module-internal.

Run from viewer/src:  python3 ../../docs/superpowers/plans/2026-11-08-tools/viewer_exports.py
Word-match heuristic (type exports excluded): review every hit by hand before deleting.
"""
import re,pathlib,sys
root=pathlib.Path('.')
files=[p for p in root.rglob('*.ts*') ]
src={p:p.read_text() for p in files}
def istest(p): return '__tests__' in p.parts or p.name.endswith(('.test.ts','.test.tsx'))
pat=re.compile(r'^export\s+(?:async\s+)?(?:function|const|let|class)\s+([A-Za-z0-9_]+)',re.M)
none=[];testonly=[];internal=[]
for p,t in src.items():
    if istest(p) or 'demos' in p.parts or '__demo__' in p.parts: continue
    for m in pat.finditer(t):
        n=m.group(1); w=re.compile(r'\b'+n+r'\b')
        other=[q for q,u in src.items() if q!=p and w.search(u)]
        prod=[q for q in other if not istest(q)]
        own=len(w.findall(t))>1
        if prod: continue
        if other: testonly.append((str(p),n))
        elif own: internal.append((str(p),n))
        else: none.append((str(p),n))
for name,l in(('NOCONSUMER',none),('TESTONLY',testonly),('INTERNAL',internal)):
    print(name,len(l))
    for x in l: print('  ',*x)
