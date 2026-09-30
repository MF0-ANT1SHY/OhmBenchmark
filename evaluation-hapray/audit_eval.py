from pathlib import Path
import json,datetime
B=Path(__file__).resolve().parent
names=[x['case'] for x in json.loads((B/'private-map.json').read_text())]
hits=[];requests=list((B/'api-audit').glob('eval1-*.request.json'))
for p in requests:
    s=p.read_text(encoding='utf-8')
    for needle in names+['private-map.json','grading-criteria.json','fix.patch','measurements/results.json']:
        if needle in s:hits.append({'request':p.name,'match':needle})
statuses=list((B/'results').glob('*/C*/status.json'))
predictions=list((B/'results').glob('*/C*/prediction.json'))
audit={'time':datetime.datetime.now().isoformat(),'formal_sessions':len(statuses),'predictions':len(predictions),'outgoing_requests_inspected':len(requests),'ground_truth_identifier_matches':hits,'scope':'Checks identifiers and known ground-truth paths in actual outbound payloads; isolation enforced separately by per-case read-only MCP. This is not a general proof against all semantic leakage.'}
(B/'blind-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(audit,ensure_ascii=False))
