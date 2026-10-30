"""Fixed relay fakes only; no real GET/POST, token, native, World or build."""
import base64,copy,hashlib,importlib.util,json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]

def module():
    spec=importlib.util.spec_from_file_location("_fixed_after_relay",ROOT/"scripts/relay_after_procedural_dispatch.py")
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

class Recorder:
    def __init__(self,fail=()):self.rows=[];self.calls=0;self.fail=fail
    def __call__(self,row):
        self.calls+=1
        if self.calls in self.fail:raise OSError("private exception detail")
        self.rows.append(copy.deepcopy(row))

@pytest.fixture
def case(monkeypatch):
    t=module();raw=(ROOT/".github/relay/after-full-procedural.json").read_bytes()
    # Tiny invented workflow bytes exercise the real decoder/hash join.
    wf=b"synthetic workflow\n";monkeypatch.setattr(t,"WORKFLOW_BYTES",len(wf));monkeypatch.setattr(t,"WORKFLOW_SHA256",t.sha(wf));monkeypatch.setattr(t,"WORKFLOW_BLOB",t.blob_sha(wf))
    head="a"*40;source_tree="b"*40
    env={"GITHUB_REPOSITORY":t.REPOSITORY,"GITHUB_EVENT_NAME":"push","GITHUB_REF":"refs/heads/"+t.RUN_BRANCH,"GITHUB_RUN_ATTEMPT":"1","GITHUB_SHA":head,"GITHUB_WORKFLOW_SHA":head,"GITHUB_WORKFLOW_REF":t.REPOSITORY+"/"+t.WORKFLOW_PATH+"@refs/heads/"+t.RUN_BRANCH,"GITHUB_RUN_ID":"123"}
    event={"after":head,"ref":env["GITHUB_REF"]}
    values={t.API_ROOT+"/git/ref/heads/"+t.RUN_BRANCH:{"ref":env["GITHUB_REF"],"object":{"type":"commit","sha":head}},t.API_ROOT+"/contents/"+t.TARGET_WORKFLOW+"?ref="+t.TARGET_SHA:{"type":"file","encoding":"base64","size":len(wf),"sha":t.WORKFLOW_BLOB,"content":base64.b64encode(wf).decode()},t.API_ROOT+"/git/commits/"+t.SOURCE_SHA:{"sha":t.SOURCE_SHA,"tree":{"sha":source_tree}},t.API_ROOT+"/git/trees/"+source_tree:{"sha":source_tree,"truncated":False,"tree":[{"path":"chronicler-agents","type":"tree","mode":"040000","sha":t.NATIVE_TREE}]},t.API_ROOT+"/git/ref/heads/"+t.TARGET_REF:{"ref":"refs/heads/"+t.TARGET_REF,"object":{"type":"commit","sha":t.TARGET_SHA}}}
    class API:
        def __init__(self):self.gets=[];self.posts=[];self.status=204;self.error=None
        def get_json(self,path):self.gets.append(path);return copy.deepcopy(values[path])
        def post_dispatch(self,body):
            self.posts.append(body)
            if self.error:raise self.error
            return {"status":self.status,"request_id":"safe-id"}
    return t,raw,env,event,values,API()

def test_fixed_original_request_source_and_native_constants():
    t=module();raw=(ROOT/".github/relay/after-full-procedural.json").read_bytes();t.validate_request(raw)
    assert len(raw)==295 and t.sha(raw)=="cd76d6b1951d0b656d0b117a31bf29785366b5bb99905e97302fa3582bd4a0a8"
    assert t.WORKFLOW_BYTES==38827 and t.WORKFLOW_SHA256=="71f36b00dd6f22dc6bf543afea61949c152e1df773d54a40548706d5a3f760d6"
    assert t.TARGET_SHA=="88eb3d815d19f351ebac6bb40ee2d62d94dacc5a" and t.SOURCE_SHA=="5122fad852535f1f70a281c5b0fbfef06dfa8f69"
    assert t.NATIVE_TREE=="a840fd12462deedf92b256878d474404eeac892d"

def test_success_forwards_the_same_raw_bytes_once_after_durable_intent(case):
    t,raw,env,event,values,api=case;record=Recorder();result=t.dispatch(raw,env,event,api,record)
    assert api.posts==[raw] and api.posts[0] is raw and len(api.gets)==5
    assert api.gets[-1].endswith(t.TARGET_REF)
    assert [(r["state"],r["post_attempts"])for r in record.rows]==[("NOT_ATTEMPTED",0),("ATTEMPTED_UNKNOWN",1),("API_ACCEPTED",1)]
    assert result["state"]=="API_ACCEPTED" and "run_id" not in result

@pytest.mark.parametrize("fault",["attempt","lint_ref","event_head","relay_head","target_head","workflow_hash","source","native","truncated","raw_whitespace"])
def test_refusals_never_post_and_remain_not_attempted(case,fault):
    t,raw,env,event,values,api=case
    if fault=="attempt":env["GITHUB_RUN_ATTEMPT"]="2"
    elif fault=="lint_ref":env["GITHUB_REF"]="refs/heads/lead/after-procedural-relay-semantics-20261030"
    elif fault=="event_head":event["after"]="f"*40
    elif fault=="relay_head":values[t.API_ROOT+"/git/ref/heads/"+t.RUN_BRANCH]["object"]["sha"]="f"*40
    elif fault=="target_head":values[t.API_ROOT+"/git/ref/heads/"+t.TARGET_REF]["object"]["sha"]="f"*40
    elif fault=="workflow_hash":values[t.API_ROOT+"/contents/"+t.TARGET_WORKFLOW+"?ref="+t.TARGET_SHA]["content"]=base64.b64encode(b"changed").decode()
    elif fault=="source":values[t.API_ROOT+"/git/commits/"+t.SOURCE_SHA]["sha"]="f"*40
    elif fault=="native":values[t.API_ROOT+"/git/trees/"+"b"*40]["tree"][0]["sha"]="f"*40
    elif fault=="truncated":values[t.API_ROOT+"/git/trees/"+"b"*40]["truncated"]=True
    else:raw=raw[:-1]+b" "
    result=t.dispatch(raw,env,event,api,Recorder());assert result["state"]=="NOT_ATTEMPTED" and result["post_attempts"]==0 and api.posts==[]

@pytest.mark.parametrize("status",[200,301,401,403,429,500])
def test_non204_is_unknown_and_never_retried(case,status):
    t,raw,env,event,values,api=case;api.status=status;result=t.dispatch(raw,env,event,api,Recorder())
    assert result["state"]=="ATTEMPTED_UNKNOWN" and result["response_status"]==status and api.posts==[raw]

def test_timeout_keeps_unknown_without_exception_detail_or_retry(case):
    t,raw,env,event,values,api=case;api.error=TimeoutError("PRIVATE_TOKEN_DETAIL");record=Recorder();result=t.dispatch(raw,env,event,api,record)
    assert result["state"]=="ATTEMPTED_UNKNOWN" and api.posts==[raw]
    assert "PRIVATE_TOKEN_DETAIL" not in json.dumps(record.rows) and result["error_class"]=="TimeoutError"

def test_failed_intent_write_prevents_post(case):
    t,raw,env,event,values,api=case;result=t.dispatch(raw,env,event,api,Recorder(fail=(2,)))
    assert result["state"]=="NOT_ATTEMPTED" and api.posts==[]

def test_failed_final_write_leaves_the_saved_unknown_intent(case):
    t,raw,env,event,values,api=case;record=Recorder(fail=(3,))
    with pytest.raises(OSError):t.dispatch(raw,env,event,api,record)
    assert api.posts==[raw] and record.rows[-1]["state"]=="ATTEMPTED_UNKNOWN"

def test_direct_transport_has_one_raw_POST_and_no_redirect_replay():
    t=module();raw=(ROOT/".github/relay/after-full-procedural.json").read_bytes();calls=[]
    class Response:
        status=301
        def read(self,limit):assert limit==131073;return b"redirect"
        def getheader(self,name):assert name=="x-github-request-id";return None
    class Connection:
        def __init__(self,host,port,timeout):assert(host,port,timeout)==("api.github.com",443,15)
        def request(self,method,path,body,headers):calls.append((method,path,body,headers))
        def getresponse(self):return Response()
        def close(self):pass
    result=t.GitHubAPI("invented-token",Connection).post_dispatch(raw)
    assert result["status"]==301 and len(calls)==1 and calls[0][:3]==("POST",t.POST_PATH,raw)
    assert calls[0][2] is raw and calls[0][3]["Content-Length"]=="295" and calls[0][3]["Content-Type"]=="application/json"
    with pytest.raises(ValueError):t.GitHubAPI("invented-token",Connection).post_dispatch(b"x"*295)
    assert len(calls)==1

def test_workflow_is_opt_in_scoped_and_retains_failures():
    t=module();wf=(ROOT/".github/workflows/after-procedural-dispatch-relay.yml").read_text()
    assert "branches: ["+t.RUN_BRANCH+"]" in wf and "permissions: {}" in wf
    assert "      contents: read\n      actions: write" in wf and "if: always()" in wf
    assert "GITHUB_TOKEN: ${{ github.token }}" in wf and "persist-credentials: false" in wf
    assert not any(s in wf for s in("pull_request:","workflow_dispatch:","schedule:","workflow_call:"))
    lint=(ROOT/".github/workflows/workflow-semantics.yml").read_text()
    assert lint.split("jobs:\n",1)[0] == 'name: Workflow semantics\n\non:\n  push:\n    branches: [lead/workflow-semantics-20261030, lead/after-procedural-relay-semantics-20261030]\n  pull_request:\n    paths:\n      - .github/workflows/**\n      - .github/actionlint.yaml\n      - .github/actionlint.yml\n  workflow_dispatch:\n\npermissions:\n  contents: read\n\n'
    assert sum(line.startswith("    if:") for line in lint.splitlines()) == 1
    assert next(line for line in lint.splitlines() if line.startswith("    if:")) == "    if: github.event_name == 'pull_request' || github.ref == 'refs/heads/lead/workflow-semantics-20261030' || (github.event_name == 'push' && github.ref == 'refs/heads/lead/after-procedural-relay-semantics-20261030' && github.run_attempt == 1)"
    assert "actions: write" not in lint
    assert t.RUN_BRANCH not in lint and "v1.7.12" in lint and "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8" in lint
