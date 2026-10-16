"""Workflow contracts use fake account adapters; never spend account/API quota."""
import hashlib
import io
import json
import threading
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backend.app.main import create_app
from backend.providers.base import ProviderError
from backend.providers.generated import GeneratedImage
from backend.providers.grok import result_from_events
from extractor_core.io import png_bytes


def generated(transparent=True):
    im = Image.new("RGBA" if transparent else "RGB", (64, 64), (10, 10, 10, 0) if transparent else (10, 10, 10))
    if transparent:
        im.paste((200, 120, 80, 255), (16, 16, 48, 48))
        return GeneratedImage.from_image(im)
    stream=io.BytesIO();im.save(stream,"JPEG")
    return GeneratedImage.decode(stream.getvalue())


class Account:
    def __init__(self, transparent=True, failure=False):
        self.output=generated(transparent);self.calls=0;self.failure=failure
    def account_status(self): return {"authenticated": not self.failure}
    def generate(self, image, model):
        self.calls+=1
        if self.failure: raise ProviderError("登录已失效，请重新登录")
        return self.output
    def login(self, open_browser): return {"authenticated":True}


def client(tmp_path, account):
    c=TestClient(create_app(tmp_path/"tasks",config_path=tmp_path/"settings.json",account_providers={"gpt":account,"grok":account}),base_url="http://127.0.0.1:7860")
    task=c.post('/api/tasks',files={'file':('source.png',png_bytes(Image.new('RGBA',(64,64),'white')))}).json()
    return c,task


@pytest.mark.parametrize('name,model,transparent',[('gpt','gpt-image',True),('grok','grok-native',False),('gpt','gpt-image',False)])
def test_generated_original_to_refine_export_and_return(tmp_path,name,model,transparent):
    account=Account(transparent);c,task=client(tmp_path,account);base=f"/api/tasks/{task['id']}"
    before=c.get(base+'/preview?kind=original').content
    body={'model':model,'source_revision':task['rev'],'request_id':'a'*32,'allow_upload':True,'allow_account_usage':True}
    assert c.post(base+'/generations',json={**body,'allow_account_usage':False}).status_code==422
    assert account.calls==0
    assert c.post(f'/api/connections/{name}/check',json={}).json()['authenticated']
    result=c.post(base+'/generations',json=body).json()
    assert result['state']=='completed' and result['transparent']==transparent
    assert c.post(base+'/generations',json=body).json()==result and account.calls==1
    artifact=base+'/generations/'+'a'*32
    original=c.get(artifact+'/image')
    assert original.content==account.output.data
    assert original.headers['content-type']==account.output.media_type
    assert c.get(base).json()['rev']==task['rev'] and c.get(base+'/preview?kind=original').content==before
    refined=c.post(artifact+'/refine',json={}).json()
    assert refined['id']!=task['id'] and refined['provenance']['task_id']==task['id'] and refined['ai_used']
    refined_base=f"/api/tasks/{refined['id']}"
    if not transparent:
        # Padding cannot turn opaque output into a claimed extracted PNG.
        assert c.post(refined_base+'/export',json={'padding':12}).status_code==422
        mask=Image.new('L',(64,64),0);mask.paste(255,(16,16,48,48))
        assert c.put(refined_base+'/mask',files={'file':('mask.png',png_bytes(mask))}).status_code==200
    export=c.post(refined_base+'/export',json={'padding':12})
    assert export.status_code==200
    png=c.get(refined_base+'/download')
    assert Image.open(io.BytesIO(png.content)).getchannel('A').getextrema()==(0,255)
    assert c.get(artifact+'/image').content==original.content
    assert c.get(base+'/preview?kind=original').content==before
    # Importing twice keeps originals and both editing histories independent.
    other=c.post(artifact+'/refine',json={}).json()
    assert other['id'] not in {task['id'],refined['id']}


def test_expired_login_and_no_image_are_failures_not_replayed(tmp_path):
    account=Account(failure=True);c,task=client(tmp_path,account);base=f"/api/tasks/{task['id']}/generations"
    body={'model':'gpt-image','source_revision':task['rev'],'request_id':'b'*32,'allow_upload':True,'allow_account_usage':True}
    assert c.post('/api/connections/gpt/check',json={}).json()['state']=='signed_out'
    assert c.post(base,json=body).status_code==422
    record=c.get(base).json()[0]
    assert record['state']=='failed' and '登录' in record['error']
    assert c.post(base,json=body).status_code==409 and account.calls==1
    assert c.post(base+'/'+'b'*32+'/refine',json={}).status_code==404
    account.failure=False
    account.generate=lambda image,model: None
    assert c.post(base,json={**body,'request_id':'c'*32}).status_code==422
    assert c.get(base).json()[1]['state']=='failed'


def test_official_login_returns_before_user_finishes(tmp_path):
    account=Account();gate=threading.Event()
    def login(open_browser): gate.wait(5);return {'authenticated':True}
    account.login=login;c,_=client(tmp_path,account)
    response=c.post('/api/connections/gpt/login',json={})
    assert response.status_code==200 and response.json()['state']=='waiting'
    assert c.post('/api/connections/gpt/login',json={}).json()['state']=='waiting'
    gate.set()


def test_grok_accepts_only_matching_native_image_file(tmp_path):
    work=tmp_path/'work';work.mkdir();session='12345678-1234-1234-1234-123456789abc'
    root=tmp_path/'sessions'
    images=root/quote(str(work.resolve()),safe='')/session/'images';images.mkdir(parents=True)
    path=images/'1.jpg';output=generated(False);path.write_bytes(output.data)
    events=[{'type':'tool_call','toolName':'image_edit','toolCallId':'one'},
            {'type':'tool_call_update','toolCallId':'one','status':'completed','rawOutput':{'type':'ImageEdit','path':str(path)}}]
    assert result_from_events(events,work,session,root).data==output.data
    for change in [{'status':'failed'},{'toolCallId':'other'},{'rawOutput':{'type':'ImageEdit','path':str(tmp_path/'other.jpg')}}]:
        with pytest.raises(ProviderError): result_from_events([events[0],{**events[1],**change}],work,session,root)
    with pytest.raises(ProviderError): result_from_events([*events,events[0]],work,session,root)
    with pytest.raises(ProviderError): result_from_events([{'type':'text','data':'生成成功'}],work,session,root)


def test_invalid_and_empty_images_never_claim_success():
    for data in (b'',b'not-image',png_bytes(Image.new('RGBA',(32,32),(0,0,0,0)))):
        with pytest.raises(ProviderError): GeneratedImage.decode(data)
