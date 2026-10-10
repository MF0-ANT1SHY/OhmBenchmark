import json,glob,collections
rows=[]
for p in sorted(glob.glob('cases/*/case.json')):
    c=json.load(open(p))
    o=c.get('test_oracle',{})
    ev=o.get('evidence',{})
    rows.append((c['id'],o.get('metric','-'),ev.get('status','-'),ev.get('measured_as','')))
cnt=collections.Counter(r[2] for r in rows)
print(cnt)
for r in rows:
    print(f"{r[2]:<11} {r[1]:<26} {r[0]}")
