"""Dormant job contracts: fake HTTP, tiny ZIPs, no historical audit or probes."""
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from fnmatch import fnmatchcase
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import urllib.error
import urllib.request
import zipfile

import pytest
from scripts import wealth_floor_baseline_audit_job as J

pytestmark = pytest.mark.skipif(os.name != "posix", reason="dormant audit requires safe POSIX IO")


class Clock:
    wall = 0.0
    cpu = 0.0
    def overall(self): return J.OverallClock(clock=lambda: self.wall)
    def budget(self): return J.TransportBudget(self.overall(), wall=lambda: self.wall, cpu=lambda: self.cpu)


class Response(io.BytesIO):
    def __init__(self, raw=b"{}", *, url=J.API, headers=None, status=200, step=None):
        super().__init__(raw)
        self.url, self.headers, self.status, self.step = url, headers or {}, status, step
        self.read_sizes = []
    def geturl(self): return self.url
    def getcode(self): return self.status
    def read(self, *args): pytest.fail("network read must use bounded read1")
    def read1(self, count):
        assert 0 < count <= J.A.BLOCK_BYTES
        self.read_sizes.append(count)
        if self.step: self.step()
        return super().read(count)


def client(response, *, budget=None):
    calls = []
    def factory(handler):
        def opened(request, timeout):
            calls.append(request)
            if request.full_url.endswith("/zip"): handler.followed = True
            return response
        return SimpleNamespace(open=opened)
    result = J.OfficialClient("never-log-test-token", run_id=7, attempt=1,
                              budget=budget or Clock().budget(), opener_factory=factory)
    return result, calls


def pin_for(path, name="fixture", artifact_id=3):
    raw = path.read_bytes()
    return J.InputPin(artifact_id, name, len(raw), hashlib.sha256(raw).hexdigest(), "2026-11-28T01:00:00Z")


def publication(pin):
    return dict(id=pin.artifact_id, name=pin.name, size_in_bytes=pin.size, digest="sha256:" + pin.sha256,
                expired=False, expires_at=pin.expires_at,
                workflow_run=dict(id=J.A.OLD_RUN, head_sha=J.A.OLD_CONTROL,
                                  repository_id=J.REPOSITORY_ID, head_repository_id=J.REPOSITORY_ID))


def test_default_is_inert_and_never_reads_token_resources_or_network(monkeypatch, capsys):
    def forbidden(*a, **k): pytest.fail("default must be inert")
    monkeypatch.setattr(J, "run_job", forbidden)
    monkeypatch.setattr(J.A, "_resources", forbidden)
    monkeypatch.setattr(J.D, "hosted_vm_precondition", forbidden)
    assert J.main([]) == 0
    row = json.loads(capsys.readouterr().out)
    assert row["status"] == "inactive" and row["candidate_worlds_enabled"] is False
    assert row["artifact_ids"] == [12868832709,12864154643,12868305362,12865287568,12867956553]


def test_closed_registration_and_original_roles():
    assert sum(J.INPUTS[k].size for k in ("template-raw", "procedural-raw")) == 2126779694
    assert J.MAX_DOWNLOAD == 2133433148
    assert len(J.AUTHORITY_NAMES) == 23
    assert all("candidate" in p.name for k,p in J.INPUTS.items() if k != "comparison")
    assert all(v is None for v in J.A.REVIEWED_CANDIDATE_PROOFS.values())


@pytest.mark.parametrize("wrong_path", ["docs/CONTINUATION.md", "scripts/wealth_floor_baseline_audit_job.py",
    "docs/experiments/wealth-floor-baseline-audit-job.yml.inactive", ".github/workflows/other.yml"])
def test_dormant_push_paths_exclude_unrelated_changes(wrong_path):
    template=Path(__file__).parents[1]/"docs/experiments/wealth-floor-baseline-audit-job.yml.inactive"
    line=next(line.strip() for line in template.read_text().splitlines() if line.strip().startswith("paths:"))
    paths=[value.strip().strip("'\"") for value in line.partition("[")[2].rpartition("]")[0].split(",")]
    assert paths==[J.WORKFLOW_PATH]
    assert fnmatchcase(J.WORKFLOW_PATH,paths[0])
    assert not any(fnmatchcase(wrong_path,pattern) for pattern in paths)


@pytest.mark.parametrize("field,value", [("id",True),("name","other"),("size_in_bytes",0),
    ("digest","sha256:"+"0"*64),("expired",True),("expires_at","2027-01-01T00:00:00Z")])
def test_publication_substitution_refuses(field,value):
    pin=J.INPUTS["template-raw"]; row=publication(pin); row[field]=value
    with pytest.raises(J.A.AdmissionError): J.validate_input_publication(row,pin,datetime(2026,10,29,tzinfo=timezone.utc))


@pytest.mark.parametrize("field,value", [("id",1),("head_sha","0"*40),("repository_id",True),("head_repository_id",2),
    ("repository_id",float(J.REPOSITORY_ID))])
def test_publication_origin_is_closed(field,value):
    pin=J.INPUTS["template-light"]; row=publication(pin); row["workflow_run"][field]=value
    with pytest.raises(J.A.AdmissionError): J.validate_input_publication(row,pin,datetime(2026,10,29,tzinfo=timezone.utc))


def test_expiry_and_sanitized_metadata():
    pin=J.INPUTS["comparison"]; row=publication(pin); row["archive_download_url"]="never-retain"
    result=J.validate_input_publication(row,pin,datetime(2026,10,29,tzinfo=timezone.utc))
    assert "never-retain" not in json.dumps(result)
    with pytest.raises(J.A.AdmissionError): J.validate_input_publication(row,pin,datetime(2026,12,1,tzinfo=timezone.utc))


def current():
    run=dict(id=7,head_sha="1"*40,run_attempt=1,status="in_progress",event="push",head_branch=J.PRODUCER_BRANCH,path=J.WORKFLOW_PATH,
             repository=dict(id=J.REPOSITORY_ID))
    job=dict(id=8,run_id=7,head_sha="1"*40,run_attempt=1,status="in_progress",name=J.JOB_NAME)
    return run,dict(total_count=1,jobs=[job])


@pytest.mark.parametrize("fault", ["missing","bool-job","wrong-job-run","attempt","duplicate","workflow","event","done","branch"])
def test_current_job_numeric_origin_is_required(fault):
    run,jobs=current()
    if fault=="missing": jobs["jobs"][0].pop("id")
    elif fault=="bool-job": jobs["jobs"][0]["id"]=True
    elif fault=="wrong-job-run": jobs["jobs"][0]["run_id"]=8
    elif fault=="attempt": jobs["jobs"][0]["run_attempt"]=2
    elif fault=="duplicate": jobs["jobs"]*=2
    elif fault=="workflow": run["path"]=".github/workflows/other.yml"
    elif fault=="event": run["event"]="workflow_dispatch"
    elif fault=="done": run["status"]="completed"
    elif fault=="branch": run["head_branch"]="main"
    with pytest.raises(J.A.AdmissionError): J.validate_current_producer(run,jobs,control_sha="1"*40,run_id=7,attempt=1)


def test_current_producer_valid():
    run,jobs=current()
    assert J.validate_current_producer(run,jobs,control_sha="1"*40,run_id=7,attempt=1)["job_id"]==8


def test_redirect_real_header_preparation_does_not_forward_origin_host():
    endpoint=J.artifact_endpoint(J.INPUTS["template-raw"])+"/zip"
    r=urllib.request.Request(endpoint,headers={"Authorization":"secret","Cookie":"secret","X-Origin":"secret"})
    h=urllib.request.HTTPHandler(); h.parent=SimpleNamespace(addheaders=[]); h.do_request_(r)
    assert r.get_header("Host")=="api.github.com"
    handler=J.OfficialRedirect(endpoint)
    redirected=handler.redirect_request(r,None,302,"secret",{},"https://unit.blob.core.windows.net/path?sig=secret")
    assert {k.lower() for k,v in redirected.header_items()}=={"user-agent"}
    h.do_request_(redirected)
    assert redirected.get_header("Host")=="unit.blob.core.windows.net"
    assert all(v!="secret" for k,v in redirected.header_items())
    with pytest.raises(J.A.AdmissionError): handler.redirect_request(redirected,None,302,"",{},"https://unit.blob.core.windows.net/again")


@pytest.mark.parametrize("url,code", [("https://example.com/path",302),("http://unit.blob.core.windows.net/path",302),
    ("https://unit.blob.core.windows.net:444/path",302),("https://user@unit.blob.core.windows.net/path",302),
    ("https://unit.blob.core.windows.net/path#frag",302),("https://unit.blob.core.windows.net/path",307)])
def test_redirect_refuses_alternate_routes(url,code):
    endpoint=J.artifact_endpoint(J.INPUTS["comparison"])+"/zip"
    with pytest.raises(J.A.AdmissionError): J.OfficialRedirect(endpoint).redirect_request(urllib.request.Request(endpoint),None,code,"",{},url)


def test_redirect_closes_body_without_reading():
    endpoint=J.artifact_endpoint(J.INPUTS["comparison"])+"/zip"
    closed=[]
    response=SimpleNamespace(close=lambda:closed.append(True),read=lambda *a:pytest.fail("no redirect body reads"))
    h=J.OfficialRedirect(endpoint)
    h.parent=SimpleNamespace(open=lambda request,timeout:"followed")
    request=urllib.request.Request(endpoint); request.timeout=15
    assert h.http_error_302(request,response,302,"",{"Location":"https://unit.blob.core.windows.net/path"})=="followed"
    assert closed==[True]


def test_metadata_is_bounded_and_cannot_request_arbitrary_endpoint():
    response=Response(b'{"ok":true}',url=J.API+"/actions/runs/7/attempts/1")
    c,calls=client(response)
    assert c.metadata(c.current_run)=={"ok":True}
    assert response.read_sizes
    with pytest.raises(J.A.AdmissionError): c.metadata("https://example.com")
    assert len(calls)==1


@pytest.mark.parametrize("headers", [{"Content-Length":"1048577"},{"Content-Encoding":"gzip"},{"Link":"more"}])
def test_bad_metadata_headers_refuse_without_body_reads(headers):
    response=Response(url=J.API+"/actions/runs/7/attempts/1",headers=headers)
    c,_=client(response)
    with pytest.raises(J.A.AdmissionError): c.metadata(c.current_run)
    assert not response.read_sizes


def test_denied_http_body_is_never_read_or_retried():
    body=SimpleNamespace(close=lambda:None,read=lambda *a:pytest.fail("denied body read"))
    calls=[]
    def factory(handler):
        def opened(request,timeout):
            calls.append(request)
            raise urllib.error.HTTPError(request.full_url,403,"secret",{},body)
        return SimpleNamespace(open=opened)
    c=J.OfficialClient("secret",run_id=7,attempt=1,budget=Clock().budget(),opener_factory=factory)
    with pytest.raises(J.JobRefused,match="official HTTP request refused"): c.metadata(c.current_run)
    assert len(calls)==1


@pytest.mark.parametrize("fault", [None,"short","extra","digest","length","encoding"])
def test_download_streams_exact_bytes_to_exclusive_file(tmp_path,monkeypatch,fault):
    raw=b"x"*(J.A.BLOCK_BYTES+7); pin=J.InputPin(3,"fixture",len(raw),hashlib.sha256(raw).hexdigest(),"2026-11-28T01:00:00Z")
    monkeypatch.setattr(J,"INPUTS",{"fixture":pin})
    payload=raw[:-1] if fault=="short" else raw+b"!" if fault=="extra" else raw
    headers={"Content-Length":str(pin.size)}
    if fault=="digest": payload=b"y"+raw[1:]
    if fault=="length": headers["Content-Length"]="1"
    if fault=="encoding": headers["Content-Encoding"]="gzip"
    response=Response(payload,url="https://unit.blob.core.windows.net/path?sig=secret",headers=headers)
    c,_=client(response); path=tmp_path/"download.zip"
    if fault:
        with pytest.raises(J.A.AdmissionError): J.download(c,"fixture",path)
    else:
        result=J.download(c,"fixture",path)
        assert path.read_bytes()==raw and result["sha256"]==pin.sha256
        assert max(response.read_sizes)<=J.A.BLOCK_BYTES
        with pytest.raises(J.A.AdmissionError):
            with J.fresh_file(path,Clock().budget()): pass


@pytest.mark.parametrize("clock,value", [("wall",1201),("cpu",301)])
def test_transport_checks_after_network_read(clock,value):
    t=Clock(); response=Response(url=J.API+"/actions/runs/7/attempts/1",step=lambda:setattr(t,clock,value))
    c,_=client(response,budget=t.budget())
    with pytest.raises(J.A.AdmissionError,match="transport"): c.metadata(c.current_run)


def test_overall_and_transport_and_audit_clocks_are_distinct(monkeypatch):
    t=Clock(); overall=t.overall(); transport=J.TransportBudget(overall,wall=lambda:t.wall,cpu=lambda:t.cpu)
    t.wall=1200;t.cpu=300
    assert transport.check()==dict(wall_seconds=1200,cpu_seconds=300)
    t.wall=1201
    assert overall.check()==1201
    with pytest.raises(J.A.AdmissionError):transport.check()
    t.wall=3301
    with pytest.raises(J.A.AdmissionError):overall.check()


def test_nested_hard_wall_restores_charged_outer_deadline(monkeypatch):
    t=Clock(); timer=[0.0]; calls=[]; handlers=[None]
    monkeypatch.setattr(J.time,"monotonic",lambda:t.wall)
    monkeypatch.setattr(J.signal,"getitimer",lambda which:(timer[0],0))
    monkeypatch.setattr(J.signal,"getsignal",lambda which:handlers[0])
    monkeypatch.setattr(J.signal,"signal",lambda which,handler:handlers.__setitem__(0,handler))
    def set_timer(which,seconds):timer[0]=seconds;calls.append(seconds)
    monkeypatch.setattr(J.signal,"setitimer",set_timer)
    with J.hard_wall(3300):
        t.wall=100;timer[0]=3200
        with J.hard_wall(1200): t.wall=300
        assert timer[0]==3000
    assert calls==[3300,1200,0,3000,0]


def test_blocking_wall_handler_refuses(monkeypatch):
    handler=[]
    monkeypatch.setattr(J.signal,"getitimer",lambda which:(0,0))
    monkeypatch.setattr(J.signal,"getsignal",lambda which:None)
    monkeypatch.setattr(J.signal,"signal",lambda which,value:handler.append(value))
    monkeypatch.setattr(J.signal,"setitimer",lambda *a:None)
    with pytest.raises(J.JobRefused,match="blocking"):
        with J.hard_wall(1200): handler[-1](None,None)


def test_small_archive_requires_whole_digest_before_any_write(tmp_path,monkeypatch):
    path=tmp_path/"input.zip"
    with zipfile.ZipFile(path,"w") as z:z.writestr("file.json",b"{}")
    pin=pin_for(path); bad=J.InputPin(pin.artifact_id,pin.name,pin.size,"0"*64,pin.expires_at)
    def forbidden(*a,**k):pytest.fail("unverified archive reached file write")
    monkeypatch.setattr(J,"fresh_file",forbidden)
    with pytest.raises(J.A.AdmissionError):J.stage_selected(path,bad,{"file.json":J.A.FilePin(2,hashlib.sha256(b"{}").hexdigest())},
        {"file.json":tmp_path/"staged"},Clock().budget(),closed=True)


@pytest.mark.parametrize("fault", [None,"extra","missing","hash","unsafe","prefix"])
def test_small_staging_is_finite_crc_read_and_never_extracts(tmp_path,monkeypatch,fault):
    path=tmp_path/"input.zip"; raw=b'{"synthetic":true}'
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as z:
        if fault!="missing":z.writestr("file.json",raw)
        if fault=="extra":z.writestr("extra",b"x")
        if fault=="unsafe":z.writestr("../escape",b"x")
        if fault=="prefix":z.writestr("file.json/child",b"x")
    p=pin_for(path);expected={"file.json":J.A.FilePin(len(raw),"0"*64 if fault=="hash" else hashlib.sha256(raw).hexdigest())}
    def forbidden(*a,**k):pytest.fail("general extraction forbidden")
    monkeypatch.setattr(zipfile.ZipFile,"extract",forbidden);monkeypatch.setattr(zipfile.ZipFile,"extractall",forbidden)
    if fault:
        with pytest.raises(J.A.AdmissionError):J.stage_selected(path,p,expected,{"file.json":tmp_path/"out"},Clock().budget(),closed=True)
    else:
        result=J.stage_selected(path,p,expected,{"file.json":tmp_path/"out"},Clock().budget(),closed=True)
        assert (tmp_path/"out").read_bytes()==raw and result["file.json"]["bytes"]==len(raw)


def test_publication_unexpected_directory_refused_without_descent(tmp_path,monkeypatch):
    (tmp_path/"file").write_bytes(b"ok");(tmp_path/"unexpected").mkdir();calls=[]
    original=J.os.scandir
    def scan(fd):calls.append(fd);return original(fd)
    monkeypatch.setattr(J.os,"scandir",scan)
    with pytest.raises(J.A.AdmissionError,match="unexpected"):J.publication_inventory(tmp_path,{"file"},Clock().budget())
    assert len(calls)==1


def test_publication_total_bound_and_no_symlinks(tmp_path,monkeypatch):
    (tmp_path/"file").write_bytes(b"123")
    monkeypatch.setattr(J,"MAX_PUBLICATION",2)
    with pytest.raises(J.A.AdmissionError,match="publication byte"):J.publication_inventory(tmp_path,{"file"},Clock().budget())
    (tmp_path/"link").symlink_to(tmp_path/"file")
    with pytest.raises(J.A.AdmissionError,match="not regular"):J.publication_inventory(tmp_path,{"file","link"},Clock().budget())


def test_shared_helper_identity_and_admission_all_floor_checks_use_it(monkeypatch,tmp_path):
    from scripts import wealth_floor_build_resources as R
    calls=[]
    monkeypatch.setattr(R,"memory_admission",lambda:calls.append(True) or dict(available_bytes=2*1024**3))
    monkeypatch.setattr(J.A.shutil,"disk_usage",lambda path:SimpleNamespace(free=12*1024**3))
    initial=J.A._resources(tmp_path,admission=True)
    t=Clock();budget=t.budget();budget.floor_probe=lambda:J.A._resources(tmp_path)
    budget.check();t.wall=1;budget.check()
    audit=J.AuditBudget(J.OverallClock());audit.floor_probe=lambda:J.A._resources(tmp_path);audit.check()
    assert initial["ram_available_bytes"]==2*1024**3 and len(calls)==4
    p=Path(__file__).parents[1]/"scripts/wealth_floor_build_resources.py"
    assert hashlib.sha256(p.read_bytes()).hexdigest()==J.RESOURCE_SOURCE


@pytest.mark.parametrize("disk,ram,admission", [(12*1024**3-1,2*1024**3,True),(12*1024**3,2*1024**3-1,True),
    (3*1024**3-1,1024**3,False),(3*1024**3,1024**3-1,False)])
def test_resource_thresholds_never_lowered(monkeypatch,tmp_path,disk,ram,admission):
    from scripts import wealth_floor_build_resources as R
    monkeypatch.setattr(R,"memory_admission",lambda:dict(available_bytes=ram))
    monkeypatch.setattr(J.A.shutil,"disk_usage",lambda path:SimpleNamespace(free=disk))
    with pytest.raises(J.A.AdmissionError):J.A._resources(tmp_path,admission=admission)


def test_late_fsync_crossing_refuses_even_when_file_was_written(monkeypatch,tmp_path):
    t=Clock();budget=t.budget()
    monkeypatch.setattr(J.os,"fsync",lambda fd:setattr(t,"wall",1201))
    with pytest.raises(J.A.AdmissionError):J.save_bytes(tmp_path/"pending.json",b"{}",budget)
    assert (tmp_path/"pending.json").exists()


def test_cli_error_never_prints_exception_token_signed_url_or_body(monkeypatch,capsys,tmp_path):
    def refused(*a,**k):raise ValueError("secret https://unit.blob.core.windows.net/?sig=secret body=secret")
    monkeypatch.setattr(J,"run_job",refused)
    assert J.main(["--execute","--output",str(tmp_path/"new"),"--control-sha","1"*40,"--run-id","7","--attempt","1"])==1
    out=capsys.readouterr()
    assert out.out=="" and "secret" not in out.err and json.loads(out.err)["status"]=="refused"


@pytest.fixture
def synthetic_job(tmp_path,monkeypatch):
    """Exercise the real controller/plan/auditor over two tiny fake cohorts.

    Only immutable data pins/counts become synthetic; no production IO grant,
    resource floor override on historical data or decoded scientific bundle.
    """
    from types import MappingProxyType
    pins,raw_pins,counts,sealed,archives={},{},{},{},{}
    def encoded(row):return J.A.json_bytes(row)
    def archive_bytes(members):
        out=io.BytesIO()
        with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as z:
            for name,raw in members.items():z.writestr(name,raw)
        return out.getvalue()
    for world in J.A.ARCHIVES:
        payload={"raw/synthetic.bin":b"tiny unparsed fixture "+world.encode()}
        inventory=dict(complete=True,file_count=1,total_bytes=sum(map(len,payload.values())),
            files={n:dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for n,b in payload.items()})
        light={name:encoded(dict(synthetic=name)) for name in J.A.LIGHT_NAMES}
        light["raw-inventory.json"]=encoded(inventory)
        light["result.json"]=encoded(dict(arm="candidate",source_sha=J.A.OLD_SOURCE,control_sha=J.A.OLD_CONTROL,
            native_sha256=J.A.OLD_NATIVE,github_run_id=str(J.A.OLD_RUN),github_run_attempt="1",
            execution_complete=True,identities_stable=True,qualified=True,gate_pass=True,stage="full",worldgen=world))
        sealed[world+"-candidate"]={n:dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for n,b in light.items()}
        raw_members={**payload,**{n:light[n] for n in ("result.json","provenance.json","raw-inventory.json")},
                     **{"light/"+n:b for n,b in light.items()}}
        counts[world]=(len(raw_members),sum(map(len,raw_members.values())))
        for suffix,members in (("light",light),("raw",raw_members)):
            key=world+"-"+suffix; original=J.INPUTS[key]; data=archive_bytes(members);archives[key]=data
            pins[key]=J.InputPin(original.artifact_id,original.name,len(data),hashlib.sha256(data).hexdigest(),original.expires_at)
            if suffix=="raw":raw_pins[world]=J.A.ArchivePin(pins[key].artifact_id,world+"-candidate",len(data),pins[key].sha256,pins[key].expires_at)
    comparison=encoded(dict(control_sha=J.A.OLD_CONTROL,github_run_id=str(J.A.OLD_RUN),github_run_attempt="1",
        pipeline_qualified=True,scientific_comparison_pass=True,inputs=sealed))
    comparison+=b" "*(71201-len(comparison));assert len(comparison)==71201
    comparison_sha=hashlib.sha256(comparison).hexdigest()
    archives["comparison"]=archive_bytes({"full-gates-comparison/comparison.json":comparison})
    old=J.INPUTS["comparison"];data=archives["comparison"]
    pins["comparison"]=J.InputPin(old.artifact_id,old.name,len(data),hashlib.sha256(data).hexdigest(),old.expires_at)
    # Preserve production ordering and logical role boundaries in the fixture.
    pins=MappingProxyType({key:pins[key] for key in J.INPUTS})
    monkeypatch.setattr(J,"INPUTS",pins);monkeypatch.setattr(J,"MAX_DOWNLOAD",sum(p.size for p in pins.values()))
    monkeypatch.setattr(J.A,"ARCHIVES",MappingProxyType(raw_pins));monkeypatch.setattr(J.A,"RAW_COUNTS",MappingProxyType(counts))
    monkeypatch.setattr(J.A,"OLD_COMPARISON",comparison_sha)
    resources=[]
    monkeypatch.setattr(J.A,"_resources",lambda path,admission=False:resources.append(admission) or dict(fixture=True))
    monkeypatch.setattr(J.D,"hosted_vm_precondition",lambda:dict(fixture_only=True,scope="injected; no actual probe"))
    monkeypatch.setattr(J,"hard_wall",lambda seconds:nullcontext())
    requests=[]
    class FixtureClient:
        def __init__(self,token,*,run_id,attempt,budget,progress=None):
            self.budget=budget;self.progress=progress;self.old_run="old";self.current_run="current";self.current_jobs="jobs"
        def metadata(self,url):
            requests.append(url)
            if url==self.old_run:return dict(id=J.A.OLD_RUN,run_attempt=1,head_sha=J.A.OLD_CONTROL,status="completed",conclusion="success",repository=dict(id=J.REPOSITORY_ID))
            if url==self.current_run:return current()[0]
            if url==self.current_jobs:return current()[1]
            return publication(next(p for p in pins.values() if J.artifact_endpoint(p)==url))
        @contextmanager
        def response(self,url,*,zip_input=False):
            requests.append(url)
            key=next(key for key,pin in pins.items() if J.artifact_endpoint(pin)+"/zip"==url)
            with Response(archives[key],headers={"Content-Length":str(len(archives[key]))}) as response:yield response
    monkeypatch.setattr(J,"OfficialClient",FixtureClient)
    return tmp_path/"job",resources,requests


def test_complete_synthetic_job_streams_both_cohorts_and_preserves_same_audit_budget(synthetic_job,monkeypatch):
    root,resources,requests=synthetic_job;seen=[];prepare=J.A.prepare_baseline_plan;audit=J.A.audit_baseline
    def planned(*args,**kwargs):
        result=prepare(*args,**kwargs);seen.append(result._budget);return result
    def audited(*args,**kwargs):
        assert args[0]._budget is kwargs["budget"] is seen[0]
        return audit(*args,**kwargs)
    monkeypatch.setattr(J.A,"prepare_baseline_plan",planned);monkeypatch.setattr(J.A,"audit_baseline",audited)
    result=J.run_job(root,token="fake-only",control_sha="1"*40,run_id=7,attempt=1)
    assert result["status"]=="audit_complete_pending_job" and result["candidate_worlds_enabled"] is False
    receipt=json.loads((root/"publication/baseline-audit.json").read_text())
    summary=json.loads((root/"publication/controller.json").read_text())
    sources=json.loads((root/"publication/sources.json").read_text())
    assert set(receipt["archives"])=={"template","procedural"}
    assert all(r["historical_role"].endswith("-candidate") and r["prospective_role"]=="baseline" for r in receipt["roles"].values())
    assert receipt["producer"]==dict(control_sha="1"*40,run_id=7,job_id=8)
    assert summary["receipt_sha256"]==result["receipt_sha256"]
    assert sources["before"]==sources["after"] and sources["identical"] is True and len(sources["before"])==4
    assert result["final_observation"]["source_snapshots_match"] is True
    assert result["final_observation"]["source_snapshot_sha256"]==hashlib.sha256(J.A.json_bytes(sources["before"])).hexdigest()
    assert len([url for url in requests if url.endswith("/zip")])==5
    assert len(list((root/"archives").iterdir()))==5
    assert True in resources and False in resources
    assert (root/"publication/final-charge.json").exists()
    with pytest.raises(J.A.AdmissionError,match="completed"):
        J.A.validate_completed_job(receipt,dict(id=8,run_id=7,head_sha="1"*40,status="in_progress",conclusion=None),
            receipt_sha256=result["receipt_sha256"],expected_receipt_sha256=result["receipt_sha256"],control_sha="1"*40)


def test_invalid_second_archive_cannot_publish_a_success_receipt(synthetic_job,monkeypatch):
    root,resources,requests=synthetic_job
    original=J.A.audit_archive;seen=[]
    def reject_second(path,*args,**kwargs):
        seen.append(Path(path).name)
        if Path(path).name=="procedural-raw.zip":raise J.A.AdmissionError("synthetic payload corruption")
        return original(path,*args,**kwargs)
    monkeypatch.setattr(J.A,"audit_archive",reject_second)
    with pytest.raises(J.A.AdmissionError,match="corruption"):J.run_job(root,token="fake-only",control_sha="1"*40,run_id=7,attempt=1)
    assert seen==["template-raw.zip","procedural-raw.zip"]
    assert not (root/"publication/baseline-audit.json").exists()
    assert not (root/"publication/controller.json").exists()


def test_publication_change_after_download_refuses_before_plan(synthetic_job,monkeypatch):
    root,resources,requests=synthetic_job
    original=J.OfficialClient.metadata;seen={}
    def changed(client,url):
        row=original(client,url)
        if "/actions/artifacts/" in url:
            seen[url]=seen.get(url,0)+1
            if seen[url]>1:row["expired"]=True
        return row
    monkeypatch.setattr(J.OfficialClient,"metadata",changed)
    monkeypatch.setattr(J.A,"prepare_baseline_plan",lambda *a,**k:pytest.fail("changed publication reached audit plan"))
    with pytest.raises(J.A.AdmissionError,match="publication"):J.run_job(root,token="fake-only",control_sha="1"*40,run_id=7,attempt=1)
    assert not (root/"publication/baseline-audit.json").exists()


def test_http_refusal_retains_only_fixed_stage_code_and_zero_body_count():
    state=J.Progress();state.select("input-metadata","template-raw")
    body=SimpleNamespace(close=lambda:None,read=lambda *a:pytest.fail("no denied body"))
    def factory(handler):
        def opened(request,timeout):raise urllib.error.HTTPError(request.full_url,403,"secret-body",{},body)
        return SimpleNamespace(open=opened)
    c=J.OfficialClient("secret-token",run_id=7,attempt=1,budget=Clock().budget(),progress=state,opener_factory=factory)
    with pytest.raises(J.JobRefused) as error:c.metadata(J.artifact_endpoint(J.INPUTS["template-raw"]))
    row=state.refusal(error.value)
    assert row["stage"]=="input-metadata" and row["artifact_id"]==12865287568
    assert row["http_status"]==403 and row["response_bytes_received"]==0 and row["reason"]=="http_refused"
    raw=J.A.json_bytes(row)
    assert len(raw)<=1024 and b"secret" not in raw and b"https:" not in raw


def test_short_download_refusal_retains_exact_received_byte_count(tmp_path,monkeypatch):
    pin=J.InputPin(3,"fixture",10,hashlib.sha256(b"1234567890").hexdigest(),"2026-11-28T01:00:00Z")
    monkeypatch.setattr(J,"INPUTS",{"fixture":pin})
    response=Response(b"short",url="https://unit.blob.core.windows.net/path?sig=secret")
    c,_=client(response);c.progress.select("download","fixture")
    with pytest.raises(J.A.AdmissionError) as error:J.download(c,"fixture",tmp_path/"partial.zip")
    row=c.progress.refusal(error.value)
    assert row["http_status"]==200 and row["response_bytes_received"]==5
    assert row["artifact_id"]==3 and row["reason"]=="digest_refused"


def test_budget_crossing_after_read_still_retains_received_count():
    t=Clock();response=Response(b"received",url=J.API+"/actions/runs/7/attempts/1",step=lambda:setattr(t,"cpu",301))
    c,_=client(response,budget=t.budget());c.progress.select("producer")
    with pytest.raises(J.A.AdmissionError) as error:c.metadata(c.current_run)
    row=c.progress.refusal(error.value)
    assert row["http_status"]==200 and row["response_bytes_received"]==8 and row["reason"]=="budget_exceeded"


@pytest.mark.parametrize("changed_snapshot",[2,3])
def test_source_drift_during_audit_or_finalization_refuses(synthetic_job,monkeypatch,changed_snapshot):
    root,resources,requests=synthetic_job;original=J.source_pins;calls=[]
    def drift(budget):
        result=original(budget);calls.append(True)
        if len(calls)==changed_snapshot:
            result["scripts/wealth_floor_baseline_audit_job.py"]={"bytes":1,"sha256":"0"*64}
        return result
    monkeypatch.setattr(J,"source_pins",drift)
    with pytest.raises(J.A.AdmissionError,match="script bytes changed"):
        J.run_job(root,token="fake-only",control_sha="1"*40,run_id=7,attempt=1)
    assert len(calls)==changed_snapshot
    # Even an existing informational receipt cannot qualify a failed producer.
    assert (root/"publication/baseline-audit.json").exists()
    if changed_snapshot==2:assert not (root/"publication/controller.json").exists()


def test_final_observation_follows_last_heavy_verification(synthetic_job,monkeypatch):
    root,resources,requests=synthetic_job;events=[];source=J.source_pins;inventory=J.publication_inventory
    def sources(budget):events.append("source");return source(budget)
    def inventoried(*a,**k):events.append("inventory");return inventory(*a,**k)
    monkeypatch.setattr(J,"source_pins",sources);monkeypatch.setattr(J,"publication_inventory",inventoried)
    result=J.run_job(root,token="fake-only",control_sha="1"*40,run_id=7,attempt=1)
    assert events==["source","source","inventory","inventory","source"]
    snapshot=json.loads((root/"publication/final-charge.json").read_text())
    assert "before final full publication rehash" in snapshot["snapshot_scope"]
    assert "After final publication rehash" in result["final_observation"]["scope"]
    assert all(result["final_observation"]["audit"][field]>=snapshot["audit_after_controller_fsync"][field]
               for field in ("cpu_seconds","wall_seconds"))


def test_unsupported_deployment_refuses_before_resources_source_or_transport(synthetic_job,monkeypatch):
    root,resources,requests=synthetic_job
    def unsupported():raise J.D.DeploymentRefused("fixture namespace mismatch")
    def forbidden(*a,**k):pytest.fail("unsupported deployment reached resource/source/network IO")
    monkeypatch.setattr(J.D,"hosted_vm_precondition",unsupported)
    monkeypatch.setattr(J.A,"_resources",forbidden);monkeypatch.setattr(J,"source_pins",forbidden)
    monkeypatch.setattr(J,"OfficialClient",forbidden)
    with pytest.raises(J.D.DeploymentRefused) as error:
        J.run_job(root,token="fake-only",control_sha="1"*40,run_id=7,attempt=1)
    assert J.Progress().refusal(error.value)["reason"]=="deployment_refused"
    assert requests==[] and not root.exists()
