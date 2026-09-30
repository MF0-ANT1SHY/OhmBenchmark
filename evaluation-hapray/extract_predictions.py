from pathlib import Path
import json, sys
B=Path(__file__).resolve().parent
sys.path.insert(0,str(B/'bootstrap'))
def parse(text):
    text=text.strip()
    for start,c in enumerate(text):
        if c!='{':continue
        try:
            obj,_=json.JSONDecoder().raw_decode(text[start:])
            if isinstance(obj,dict) and isinstance(obj.get('summary'),str) and isinstance(obj.get('suspects'),list):return obj
        except ValueError:pass
    return None
def extract(r):
    if (r/'prediction.json').exists():return 'saved'
    p=r/'resume-events.jsonl' if (r/'resume-status.json').exists() else r/'events.jsonl'
    if not (r/'status.json').exists():return 'running'
    texts=[]
    for line in p.read_text(encoding='utf-8',errors='replace').splitlines():
        try:e=json.loads(line)
        except ValueError:continue
        if e.get('type')=='final':texts.append(e.get('text',''))
        if e.get('type')=='result':texts.append(e.get('result',''))
        if e.get('type')=='text':texts.append(e.get('part',{}).get('text',e.get('text','')))
        if e.get('type')=='assistant':
            texts.extend(c.get('text','') for c in e.get('message',{}).get('content',[]) if c.get('type')=='text')
    for text in reversed(texts):
        obj=parse(text)
        if obj is not None:
            (r/'prediction.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
            return 'valid'
    # Repair serialization only when the complete final object is present.
    if texts:
        raw=texts[-1].strip().removeprefix('```json').removesuffix('```').strip()
        if raw.startswith('{') and raw.endswith('}'):
            from json_repair import loads
            obj=loads(raw)
            if isinstance(obj,dict) and isinstance(obj.get('summary'),str) and isinstance(obj.get('suspects'),list) and all(isinstance(s,dict) and 'root_cause' in s for s in obj['suspects']):
                (r/'original-final.txt').write_text(raw,encoding='utf-8')
                (r/'prediction.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
                (r/'serialization-repair.json').write_text(json.dumps({'method':'json-repair; syntax recovery only, original retained','requires_review':True}),encoding='utf-8')
                return 'repaired-review-required'
    (r/'incomplete-final.txt').write_text(texts[-1] if texts else '',encoding='utf-8')
    return 'invalid-or-incomplete'
if __name__=='__main__':
    outcomes={}
    for r in sorted((B/'results').glob('*/C*')):outcomes[str(r.relative_to(B/'results'))]=extract(r)
    (B/'delivery-status.json').write_text(json.dumps(outcomes,indent=2),encoding='utf-8')
    from collections import Counter
    print(dict(Counter(outcomes.values())))
