"""Reject changed native city content and title pixels."""
import copy,json
from pathlib import Path
import pytest
from font_page_memory import BUNDLE,page_content

def layout():
    return {'attributes':{'bundleName':BUNDLE,'visible':'true','text':'城市管理','bounds':'[1,2][30,40]'},'children':[{'attributes':{'bundleName':BUNDLE,'visible':'true','text':t}} for t in ('北京','\ue66a')]}

def test_native_page_requires_city_and_navigation():
    value=layout();assert page_content(value)['title_box']==[1,2,30,40]
    value['children'].pop()
    with pytest.raises(ValueError,match='content missing'):page_content(value)

def test_foreign_or_hidden_title_does_not_verify():
    for key,value in [('bundleName','other.app'),('visible','false')]:
        tree=layout();tree['attributes'][key]=value
        with pytest.raises(ValueError,match='content missing'):page_content(tree)

def test_changed_title_pixels_are_rejected(tmp_path,monkeypatch):
    import hashlib
    from PIL import Image
    import font_page_memory as module
    from weather_icon_pixels import region_hashes
    tree=layout();content=page_content(tree);frames=[]
    for step in (1,40):
        p=tmp_path/f'page-{step}.png';Image.new('RGB',(50,50),'white').save(p)
        frames.append({'step':step,'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    reference={'page_content':content,'title_pixels':region_hashes(tmp_path/'page-1.png',[content['title_box']])}
    record={'status':'CAPTURED','warmup_count':1,'steps':[{'number':n,'layout':tree} for n in range(1,41)],'frames':frames,'final_layout':{'attributes':{'bundleName':BUNDLE,'id':'AddAddressBtn'}}}
    monkeypatch.setattr(module,'verify_window',lambda *_:123)
    assert module.verify_capture(record,tmp_path,reference)==123
    p=tmp_path/'page-40.png';Image.new('RGB',(50,50),'black').save(p);frames[-1]['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='title pixels differ'):module.verify_capture(record,tmp_path,reference)
