"""Static reachability of src/chronicler modules from the production roots.

Run from the repo root:  python3 docs/superpowers/plans/2026-11-08-tools/lab_reachability.py [src/chronicler]
Follows absolute, relative, `from chronicler import x`, literal import_module and in-function imports.
It cannot see import_module("chronicler." + name) string building (livelihoods, expansion_features,
local_budgets, wealth_accounting): learning_cohorts, remittances, timber_orders and wealth_accounting
show as unreachable here but are loaded that way. Review every result.
"""
import ast, sys, pathlib, collections
root=pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'src/chronicler')
mods={p.stem for p in root.glob('*.py')}
subs={p.name for p in root.iterdir() if p.is_dir() and (p/'__init__.py').exists()}
print("subpackages",subs)
def deps(path, modname):
    t=ast.parse(path.read_text()); out=set(); dyn=set()
    pkgdepth = 0
    for n in ast.walk(t):
        if isinstance(n,ast.Import):
            for a in n.names:
                if a.name.startswith('chronicler.'): out.add(a.name.split('.')[1])
        elif isinstance(n,ast.ImportFrom):
            if n.level==0 and n.module:
                if n.module=='chronicler':
                    for a in n.names: out.add(a.name)
                elif n.module.startswith('chronicler.'): out.add(n.module.split('.')[1])
            elif n.level==1:
                if n.module: out.add(n.module.split('.')[0])
                else:
                    for a in n.names: out.add(a.name)
        elif isinstance(n,ast.Call):
            f=n.func
            nm=getattr(f,'attr',getattr(f,'id',''))
            if nm in('import_module','__import__') and n.args and isinstance(n.args[0],ast.Constant):
                v=n.args[0].value
                dyn.add(v)
                if v.startswith('chronicler.'): out.add(v.split('.')[1])
    return out&(mods|subs), dyn
# subpackage files: treat as module name = subpackage
graph={}; dynall={}
for p in root.glob('*.py'):
    graph[p.stem],d=deps(p,p.stem); 
    if d: dynall[p.stem]=d
for s in subs:
    o=set();
    for p in (root/s).rglob('*.py'):
        # relative imports inside subpackage level>=2 refer to chronicler.X
        t=ast.parse(p.read_text())
        a,d=deps(p,s); o|=a
        for n in ast.walk(t):
            if isinstance(n,ast.ImportFrom) and n.level==2 and n.module: o.add(n.module.split('.')[0])
            if isinstance(n,ast.ImportFrom) and n.level==2 and not n.module:
                for x in n.names:o.add(x.name)
        if d: dynall[s+'/'+p.name]=d
    graph[s]=o&(mods|subs)
roots=['main','live','validate','narration_audit']
seen=set(); st=list(roots)
while st:
    m=st.pop()
    if m in seen: continue
    seen.add(m); st+=[x for x in graph.get(m,()) if x not in seen]
un=sorted(m for m in mods if m not in seen and m!='__init__')
print(len(un),"unreachable")
import subprocess
for m in un:
    n=len((root/(m+'.py')).read_text().splitlines())
    print(m,n)
print("total",sum(len((root/(m+'.py')).read_text().splitlines()) for m in un))
print("dyn",dynall)
