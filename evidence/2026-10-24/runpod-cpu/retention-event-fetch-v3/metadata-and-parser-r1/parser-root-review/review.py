"""Closed parser source/guard ZIP byte review; no raw benchmark input or code execution."""
from pathlib import Path
import ast, hashlib, json, re, zipfile
OUT=Path(__file__).resolve().parent
P=OUT.parent/'event-fetch-long-parser-preparation-r1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
closed=load(P/'CLOSED.json');frozen=load(P/'SOURCE_FROZEN.json')
assert sha(P/'CLOSED.json')=='ee93d9695da617b931083d0d342597e79ca276e010448e820e42801949d19c35'
assert sha(P/'SOURCE_FROZEN.json')=='468db7bdb5b2fcf29dd2fab975cef9b3dbe7ce8f9ed73d326d65a5cd74488d8b'
for name,row in closed['files'].items():assert (P/name).stat().st_size==row['bytes'] and sha(P/name)==row['sha256'],name
assert {x.relative_to(P).as_posix() for x in P.rglob('*') if x.is_file()}==set(closed['files'])|{'CLOSED.json'}
provenance=load(P/'BASELINE_PROVENANCE.json');old=Path(provenance['oldParserFreeze']['path']).parent
for name,row in provenance['oldNine'].items():
    for p in [P/'baseline'/name,old/name]:assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],str(p)
attempts=[]
for name,count in [('guards-r1',41),('guards-r2',42)]:
    reg=load(P/name/'REGISTRATION.json');done=load(P/name/'COMPLETION.json')
    assert done['exitCode']==0 and done['allInputsUnchanged'] and not done['actualRawRead']
    with zipfile.ZipFile(P/name/'source.zip') as z:
        assert set(z.namelist())==set(reg['sourceFiles']) and len(z.namelist())==len(set(z.namelist()))
        for member,row in reg['sourceFiles'].items():
            raw=z.read(member);assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
            if name=='guards-r2':assert sha(P/member)==row['sha256']
    text=(P/name/'stderr').read_text();cases=re.findall(r'^(test_\S+ \([^\n]+\)) \.\.\. ok$',text,re.M)
    assert len(cases)==len(set(cases))==count and re.search(r'Ran '+str(count)+r' tests in ',text) and text.rstrip().endswith('OK')
    attempts.append(dict(attempt=name,tests=count,sourceZipSha256=sha(P/name/'source.zip'),capturedFiles=len(reg['sourceFiles'])))
raw_ast=ast.parse((P/'source/audit_raw.py').read_text())
entry=next(x for x in raw_ast.body if isinstance(x,ast.FunctionDef) and x.name=='audit_arm')
assert any(x.arg=='event_fetch_count' and default is None for x,default in zip(entry.args.kwonlyargs,entry.args.kw_defaults))
assert any(x.arg=='local_functional_only' and isinstance(default,ast.Constant) and default.value is False for x,default in zip(entry.args.kwonlyargs,entry.args.kw_defaults))
result=dict(passed=True,reviewSourceSha256=sha(Path(__file__)),parserClosedSha256=sha(P/'CLOSED.json'),parserFrozenSha256=sha(P/'SOURCE_FROZEN.json'),allClosedFilesVerified=len(closed['files']),oldNineOriginalsAndBaselineCopiesExact=True,allCapturedGuardZipMembersVerified=True,guardAttempts=attempts,requiredSelectedPageHasNoDefault=True,strictSchedulerDefaultPreserved=True,manualReview=['Full selected-page contract and read phase source; all changed production functions and new binary/selection tests','General wire maximum32; each successful event RPC/callback exact selected request count/range/prefix; each cycle forces min(selected,remaining)','13 CSV fields, earliest callback, four offers, eight credit, ACK ordering, full prefixes and UNKNOWN gates retained','Legacy telemetry helper exposure derives LONG; original41 and corrected42 guard captures preserved'],limitations=['Pure synthetic codec fixtures are not JVM-captured benchmark wires','Imported common.load_config is legacy provenance; new collector must supply a separately reviewed new event identity gate','No actual raw, native UDP, owner/driver consumption, performance, latency or capacity proof was executed by this review'])
with (OUT/'ROOT_REVIEW.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(dict(passed=True,files=len(closed['files']),finalGuards=42)))
