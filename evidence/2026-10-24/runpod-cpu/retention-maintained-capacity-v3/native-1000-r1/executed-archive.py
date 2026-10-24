from pathlib import Path
import json,hashlib,stat,shutil,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=R/'evidence/2026-10-24/runpod-cpu/retention-maintained-capacity-v3/native-1000-r1';assert not O.exists()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def tree(p):
 files={};dirs={}
 for q in[p,*sorted(p.rglob('*'))]:
  assert not q.is_symlink();s=q.stat();n=q.relative_to(p).as_posix();r=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
  if q.is_dir():dirs[n]=r
  else:files[n]=dict(r,bytes=s.st_size,sha256=sha(q))
 return dict(files=files,directories=dirs)
names=['current-maintained-capacity-first-private-proof-r1','current-maintained-capacity-rate-1000-controller-preparation-r1','current-maintained-capacity-rate-1000-controller-preparation-r2','current-maintained-capacity-rate-1000-source-review-r1','current-maintained-capacity-rate-1000-stage-r1','current-maintained-capacity-rate-1000-preflight-r1','current-maintained-capacity-rate-1000-launch-r1','current-maintained-capacity-rate-1000-probe-r1','current-maintained-capacity-rate-1000-collection-r1','current-maintained-capacity-rate-1000-root-review-preparation-r1','current-maintained-capacity-rate-1000-root-review-r1','current-maintained-capacity-streaming-decoder-preparation-r1','current-maintained-capacity-streaming-decoder-validation-r1','current-maintained-capacity-bottleneck-analysis-r1'];root=B/'current-maintained-capacity-rate-1000-root-review-r1';assert json.loads((root/'ROOT_REVIEW.json').read_text())['passed']and json.loads((root/'RAW_AUDIT_R2.json').read_text())['passed'];before={n:tree(B/n)for n in names};O.mkdir()
for n in names:shutil.copytree(B/n,O/n);assert tree(B/n)==tree(O/n)==before[n]
(O/'SOURCE_MIRRORS.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n');shutil.copy2(Path(__file__),O/'executed-archive.py');refs={}
for n in ['local-validation-r1','first-native-500-r1']:
 p=O.parent/n;refs[n]={k:dict(bytes=(p/k).stat().st_size,sha256=sha(p/k))for k in['INVENTORY.json','CLOSED.json']}
(O/'SHARED_EVIDENCE_REFERENCES.json').write_text(json.dumps(refs,indent=2,sort_keys=True)+'\n')
(O/'README.md').write_text('''# First1000/s maintained-load observation: significant backlog

Same b97ef13e application artifact/code2d6267a6 as the500/s pilot;20000 planned orders over20seconds, fixed leader0/sync2/page32/read32/batch4/chunk6144/owner1ms/driver100us/W128Q64/session1. Same CPU host, three JVMs over loopback UDP. All20000 orders eventually accepted, zero UNKNOWN/rejection/notSent/scheduler lateness>20ms. Only13321 confirmations arrived inside the window: goodput666.05/s,66.605% of offered rate. Scheduled-arrival p50=4960.984286ms, p99=11047.394780ms, sampled backlog high-water6903. Last known reply drained10.767631664seconds after the window; source including final maintenance drained12.026292145seconds afterward. This is an overloaded observation, not1000/s stable capacity.

Independent full outer and inner archive byte/metadata/empty-directory streams,20000-row CSV p99 recomputation, streamed full candidate-codec decode/encode, original command/identity/hash/result matching, frame offsets/lengths/hashes and offer associations passed.9999 actual positive publications/replies,69 negative offers. One correlation can carry up to4 original orders; frame count is not order count. Native Java candidate-reference reconciliation and three matching checkpoint logs do not constitute an independent matching oracle or binary snapshot/cold restore proof. Full actual original native/control/source/raw files and available drafts remain retained.

Maintenance took15.134628574seconds across7 cycles versus1.061315932seconds across4 cycles at500/s. Disjoint phase spans show6.299984432seconds archive reads and4.737553177seconds event reads at1000/s, plus2.699358507seconds in verify/writer gaps. Overlapping RPC elapsed totals are not summed as wall time. Slowest1% predispatch share99.41%; whole-host I/O-wait tick share3.88% versus0.28% in the earlier500/s run. Per-process sampled average CPU remains below one core over spans including setup/finalisation. These two finite observations do not isolate storage, scheduling, server or transport causality. Live Aeron CNC counters are absent after driver cleanup, so no zero-transport-retransmit claim is made. Higher offered-rate presets are deferred while this loss of stability is investigated.

The original1000 controller source draft was not staged; source review added explicit nonnegative integer outcome bounds and retained both complete drafts.28 pure fixture mutation guards passed. The bounded streaming decoder was compared row-for-row with the prior complete decoder and rejects negative-length/truncated fixtures. Raw recording and production bytes were unchanged by offline reporting changes. All prior private first-pilot push/readback proof is retained; private branch contains the full native archives, not only summaries.
''');i=tree(O);(O/'INVENTORY.json').write_text(json.dumps(i,indent=2,sort_keys=True)+'\n');(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventorySha256=sha(O/'INVENTORY.json'),payloadFiles=len(i['files']),allCopiedSourceScopesCompleteAndEqual=True,allOriginalNativeRawAndDraftsRetained=True,noNewBenchmarkByArchive=True),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,payloadFiles=len(i['files']),inventorySha256=sha(O/'INVENTORY.json'))))
