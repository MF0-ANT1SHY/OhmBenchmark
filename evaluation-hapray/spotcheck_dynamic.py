from pathlib import Path
import sqlite3,json
B=Path(__file__).resolve().parent
out=[]
for case,term in [('C05','Insert'),('C13','QuerySql')]:
    for p in sorted((B/'blind'/case/'hapray').rglob('trace.db')):
        con=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
        rows=con.execute('select name,count(*),sum(dur) from callstack where name like ? group by name',('%'+term+'%',)).fetchall()
        out.append({'id':case,'db':str(p.relative_to(B/'blind'/case)),'query_term':term,'name_count_sum_duration_ns':rows})
        con.close()
(B/'dynamic-spotchecks.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
