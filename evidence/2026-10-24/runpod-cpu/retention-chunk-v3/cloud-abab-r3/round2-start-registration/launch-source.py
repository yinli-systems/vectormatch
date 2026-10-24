"""Start exactly one pre-registered finite round on the existing CPU; never retries a launch."""
import argparse,hashlib,importlib.util,json,pathlib,shlex
BASE=pathlib.Path(__file__).resolve().parent
PREP='/opt/vectormatch-cpu/preparation/chunk-cloud-abab-r3'
CONTROLLER_SHA='8be694cfb8e7077fc2035667352b490ca704de21da4bc10f8dc2cca738c423bd'

def main():
 parser=argparse.ArgumentParser(allow_abbrev=False)
 parser.add_argument('--round',type=int,choices=[1,2],required=True)
 parser.add_argument('--staging',type=pathlib.Path,required=True)
 parser.add_argument('--output',type=pathlib.Path,required=True)
 parser.add_argument('--prior-collection-sha256')
 options=parser.parse_args();out=options.output.resolve();out.mkdir(mode=0o700,exist_ok=False)
 receipt=json.loads((options.staging/'SUCCESS.json').read_text());assert receipt['passed'] is True and receipt['readOnlyPreflightPassed'] is True
 release_sha=receipt['releaseSha256'];assert hashlib.sha256((options.staging/'release.json').read_bytes()).hexdigest()==release_sha
 assert options.round==2 or options.prior_collection_sha256 is None
 if options.round==2:assert options.prior_collection_sha256 is not None and len(options.prior_collection_sha256)==64 and all(c in '0123456789abcdef' for c in options.prior_collection_sha256)
 args=['/usr/bin/python3','-B',PREP+'/chunk_cloud_abab.py','--round',str(options.round),'--release-sha256',release_sha,'--start-new']
 if options.round==2:args+=['--prior-collection-sha256',options.prior_collection_sha256]
 program='prep_name='+repr(PREP)+'\nrelease_sha='+repr(release_sha)+'\ncontroller_sha='+repr(CONTROLLER_SHA)+'\nround_number='+repr(options.round)+'\nargs='+repr(args)+'\n'+r'''
import hashlib,json,os,pathlib,subprocess,time
source=pathlib.Path(prep_name)
assert hashlib.sha256((source/'chunk_cloud_abab.py').read_bytes()).hexdigest()==controller_sha
assert hashlib.sha256((source/'release/release.json').read_bytes()).hexdigest()==release_sha
prefix='round-'+str(round_number)+'-execution'
with (source/(prefix+'-register.json')).open('x') as register:
 with (source/(prefix+'.stdout')).open('xb') as output,(source/(prefix+'.stderr')).open('xb') as error:
  child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=output,stderr=error,cwd=str(source),start_new_session=True,close_fds=True)
 proc=pathlib.Path('/proc')/str(child.pid);raw=(proc/'cmdline').read_bytes();fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
 expected=b''.join(arg.encode()+b'\x00' for arg in args)
 row={'pid':child.pid,'startTicks':int(fields[19]),'observedCommandSha256':hashlib.sha256(raw).hexdigest(),'expectedArguments':args,'startUnixNs':time.time_ns(),'round':round_number,'frozenReleaseSha256':release_sha,'noResubmission':True,'observedExecArgvMatches':raw==expected}
 json.dump(row,register,indent=2);register.write('\n');register.flush();os.fsync(register.fileno())
print(json.dumps(row),flush=True)
'''
 spec=importlib.util.spec_from_file_location('cpu_remote',BASE/'remote.py');remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
 r=remote.run('python3 -c '+shlex.quote(program),timeout=45)
 (out/'launch.stdout.json').write_text(r.stdout);(out/'launch.stderr').write_text(r.stderr)
 assert r.returncode==0,r.stderr
 print(r.stdout)

if __name__=='__main__':main()
