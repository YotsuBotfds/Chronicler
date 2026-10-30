"""One fixed, opt-in dispatch; no simulation or credential export."""
from pathlib import Path
import base64,datetime,hashlib,http.client,json,os,re,sys

REPOSITORY="YotsuBotfds/Chronicler"
RUN_BRANCH="lead/after-procedural-dispatch-relay-run-20261030"
WORKFLOW_PATH=".github/workflows/after-procedural-dispatch-relay.yml"
TARGET_REF="lead/validation-full-compact-body-20261030"
TARGET_SHA="88eb3d815d19f351ebac6bb40ee2d62d94dacc5a"
TARGET_WORKFLOW=".github/workflows/validation-gate.yml"
WORKFLOW_BYTES=38827
WORKFLOW_SHA256="71f36b00dd6f22dc6bf543afea61949c152e1df773d54a40548706d5a3f760d6"
WORKFLOW_BLOB="1d5e27c70ac3099484ef01809be39a2e44867ab3"
SOURCE_SHA="5122fad852535f1f70a281c5b0fbfef06dfa8f69"
NATIVE_TREE="a840fd12462deedf92b256878d474404eeac892d"
REQUEST_BYTES=295
REQUEST_SHA256="cd76d6b1951d0b656d0b117a31bf29785366b5bb99905e97302fa3582bd4a0a8"
REQUEST_BLOB="bd3b629a2e636930c5c438021e919425f518863d"
POST_PATH="/repos/"+REPOSITORY+"/actions/workflows/validation-gate.yml/dispatches"
API_ROOT="/repos/"+REPOSITORY
HEX=re.compile(r"[0-9a-f]{40}\Z")

def require(ok):
    if not ok:raise ValueError("fixed relay contract refused")

def sha(raw):return hashlib.sha256(raw).hexdigest()

def blob_sha(raw):return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()

def validate_request(raw):
    require(type(raw) is bytes and len(raw)==REQUEST_BYTES and sha(raw)==REQUEST_SHA256 and blob_sha(raw)==REQUEST_BLOB)
    require(json.loads(raw)=={"inputs":{"baseline_report":"","fail_on_regression":"false","profile":"full","require_strict_regression":"false","source_sha":SOURCE_SHA,"worldgen":"procedural"},"ref":TARGET_REF})

def validate_context(env,event):
    require(env.get("GITHUB_REPOSITORY")==REPOSITORY and env.get("GITHUB_EVENT_NAME")=="push")
    require(env.get("GITHUB_REF")=="refs/heads/"+RUN_BRANCH and env.get("GITHUB_RUN_ATTEMPT")=="1")
    head=env.get("GITHUB_SHA","");require(HEX.fullmatch(head))
    require(env.get("GITHUB_WORKFLOW_SHA")==head and env.get("GITHUB_WORKFLOW_REF")==REPOSITORY+"/"+WORKFLOW_PATH+"@refs/heads/"+RUN_BRANCH)
    require(type(event) is dict and event.get("after")==head and event.get("ref")==env["GITHUB_REF"])
    run_id=env.get("GITHUB_RUN_ID","");require(run_id.isascii() and run_id.isdecimal() and len(run_id)<=20)
    return {"relay_source":head,"relay_run_id":run_id,"relay_attempt":1,"relay_ref":env["GITHUB_REF"]}

def validate_workflow(item):
    require(type(item) is dict and item.get("type")=="file" and item.get("encoding")=="base64" and item.get("size")==WORKFLOW_BYTES and item.get("sha")==WORKFLOW_BLOB)
    require(type(item.get("content")) is str)
    raw=base64.b64decode("".join(item["content"].split()),validate=True)
    require(len(raw)==WORKFLOW_BYTES and sha(raw)==WORKFLOW_SHA256 and blob_sha(raw)==WORKFLOW_BLOB)

def preflight(api,identity):
    relay=api.get_json(API_ROOT+"/git/ref/heads/"+RUN_BRANCH)
    require(relay["ref"]=="refs/heads/"+RUN_BRANCH and relay["object"]["type"]=="commit" and relay["object"]["sha"]==identity["relay_source"])
    validate_workflow(api.get_json(API_ROOT+"/contents/"+TARGET_WORKFLOW+"?ref="+TARGET_SHA))
    source=api.get_json(API_ROOT+"/git/commits/"+SOURCE_SHA)
    require(source["sha"]==SOURCE_SHA and HEX.fullmatch(source["tree"]["sha"]))
    tree=api.get_json(API_ROOT+"/git/trees/"+source["tree"]["sha"])
    require(tree["sha"]==source["tree"]["sha"] and tree.get("truncated") is False)
    native=[row for row in tree["tree"] if row.get("path")=="chronicler-agents"]
    require(len(native)==1 and native[0].get("type")=="tree" and native[0].get("mode")=="040000" and native[0].get("sha")==NATIVE_TREE)
    # Last remote read before durable intent: dispatch still uses the original ref.
    target=api.get_json(API_ROOT+"/git/ref/heads/"+TARGET_REF)
    require(target["ref"]=="refs/heads/"+TARGET_REF and target["object"]["type"]=="commit" and target["object"]["sha"]==TARGET_SHA)

def dispatch(raw,env,event,api,persist):
    receipt={"schema":1,"kind":"ORIGINAL_AFTER_PROCEDURAL_DISPATCH_RELAY","state":"NOT_ATTEMPTED","phase":"context","post_attempts":0,"at_utc":now(),"target_controller":TARGET_SHA,"simulation_source":SOURCE_SHA,"native_tree":NATIVE_TREE,"request_sha256":REQUEST_SHA256,"request_bytes":REQUEST_BYTES}
    persist(receipt)
    try:
        identity=validate_context(env,event);receipt.update(identity)
        receipt["phase"]="request";validate_request(raw)
        receipt["phase"]="preflight";preflight(api,identity)
        receipt.update(state="ATTEMPTED_UNKNOWN",phase="post",post_attempts=1,intent_at_utc=now())
        persist(receipt)  # Must be durably saved before the sole POST invocation.
    except Exception as error:
        receipt.update(state="NOT_ATTEMPTED",post_attempts=0,error_class=type(error).__name__)
        persist(receipt);return receipt
    try:
        response=api.post_dispatch(raw)
        receipt.update(response_status=response["status"],response_at_utc=now())
        if response.get("request_id") is not None:receipt["github_request_id"]=response["request_id"]
        if response["status"]==204:receipt.update(state="API_ACCEPTED",phase="accepted")
        else:receipt["phase"]="unexpected_post_status"
    except Exception as error:
        receipt.update(phase="post_transport_failure",error_class=type(error).__name__)
    persist(receipt)
    return receipt

class GitHubAPI:
    def __init__(self,token,connection=http.client.HTTPSConnection):
        require(type(token) is str and bool(token));self.token=token;self.connection=connection

    def exchange(self,method,path,body=None):
        require(method in ("GET","POST") and path.startswith(API_ROOT+"/") and (method!="POST" or path==POST_PATH))
        headers={"Authorization":"Bearer "+self.token,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","User-Agent":"Chronicler-fixed-after-procedural-relay"}
        if method=="POST":
            validate_request(body)
            headers.update({"Content-Type":"application/json","Content-Length":str(len(body))})
        conn=self.connection("api.github.com",443,timeout=15)
        try:
            conn.request(method,path,body=body,headers=headers)
            response=conn.getresponse();data=response.read(131073);require(len(data)<=131072)
            request_id=response.getheader("x-github-request-id")
            if request_id is not None:require(type(request_id) is str and len(request_id)<=128 and request_id.isascii() and all(32<=ord(c)<127 for c in request_id))
            return response.status,data,request_id
        finally:conn.close()

    def get_json(self,path):
        status,data,_=self.exchange("GET",path);require(status==200);return json.loads(data)

    def post_dispatch(self,raw):
        status,_,request_id=self.exchange("POST",POST_PATH,raw)
        return {"status":status,"request_id":request_id}

class ReceiptFile:
    def __init__(self,path):
        self.path=Path(path);self.path.mkdir(mode=0o700,parents=False,exist_ok=False)

    def __call__(self,receipt):
        raw=(json.dumps(receipt,sort_keys=True,separators=(",",":"))+"\n").encode();require(len(raw)<=4096)
        temporary=self.path/"receipt.next"
        with temporary.open("xb") as stream:
            require(stream.write(raw)==len(raw));stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,self.path/"receipt.json")
        fd=os.open(self.path,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)

def main():
    root=Path(__file__).resolve().parents[1]
    receipt=None
    try:
        receipt=ReceiptFile(Path(os.environ["RUNNER_TEMP"])/"after-procedural-relay")
        request=root/".github/relay/after-full-procedural.json"
        require(request.stat().st_size==REQUEST_BYTES);raw=request.read_bytes()
        event_path=Path(os.environ["GITHUB_EVENT_PATH"])
        require(event_path.stat().st_size<=65536);event=json.loads(event_path.read_bytes())
        result=dispatch(raw,os.environ,event,GitHubAPI(os.environ["GITHUB_TOKEN"]),receipt)
    except Exception as error:
        # No request/header/environment/exception-detail logging.
        result={"schema":1,"kind":"ORIGINAL_AFTER_PROCEDURAL_DISPATCH_RELAY","state":"NOT_ATTEMPTED","phase":"startup_or_receipt_failure","post_attempts":0,"error_class":type(error).__name__}
        # A durable prior intent takes precedence over a failed final write.
        if receipt is not None:
            prior=receipt.path/"receipt.json"
            if prior.exists():
                try:
                    saved=json.loads(prior.read_bytes())
                    if saved.get("post_attempts")==1:result.update(state="ATTEMPTED_UNKNOWN",phase="receipt_failure_after_attempt",post_attempts=1)
                except Exception:result.update(state="ATTEMPTED_UNKNOWN",phase="unreadable_prior_receipt")
            else:
                try:receipt(result)
                except Exception:pass
    print(json.dumps({"state":result["state"],"phase":result["phase"]},separators=(",",":")))
    return 0 if result["state"]=="API_ACCEPTED" else 1

if __name__=="__main__":raise SystemExit(main())
