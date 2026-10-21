"""Match all nine native icon regions without application instrumentation."""
import hashlib
import re
from PIL import Image

BUNDLE='com.alatus.futureweather'


def icon_boxes(layout):
    boxes=[];texts=[]
    def visit(node,inherited=None):
        a=node.get('attributes',{});bundle=a.get('bundleName') or inherited
        if bundle==BUNDLE and a.get('visible')!='false':
            if a.get('type')=='Image':
                bounds=list(map(int,re.findall(r'\d+',a['bounds'])))
                if len(bounds)!=4 or bounds[2]<=bounds[0] or bounds[3]<=bounds[1]:raise ValueError('invalid icon bounds')
                boxes.append(bounds)
            if a.get('type')=='Text':texts.append(a.get('text',''))
        for child in node.get('children',[]):visit(child,bundle)
    visit(layout)
    if len(boxes)!=9 or len({tuple(b) for b in boxes})!=9:
        raise ValueError('all nine ordinary weather icon regions are required')
    for text in ('深圳市','近期天气','晴 28° 至 23°','东南风1-3级'):
        if text not in texts:raise ValueError('ordinary successful forecast text is missing')
    return boxes


def region_hashes(path,boxes):
    with Image.open(path) as source:
        frame=source.convert('RGB');size=list(frame.size);digests=[]
        for b in boxes:
            if not 0<=b[0]<b[2]<=size[0] or not 0<=b[1]<b[3]<=size[1]:raise ValueError('icon crop outside native screenshot')
            digests.append(hashlib.sha256(frame.crop(tuple(b)).tobytes()).hexdigest())
    return {'size':size,'regions':digests}


def matches(path,reference):
    actual=region_hashes(path,reference['boxes'])
    return actual==reference['pixels']
