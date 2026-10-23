import subprocess,json,pathlib,shlex,concurrent.futures
ROOT=pathlib.Path(__file__).resolve().parent
NODES=json.loads((ROOT/'resources.json').read_text())['nodes']
KEY=str(ROOT.parents[1]/'ssh/vectormatch-cloud')
KNOWN=str(ROOT.parents[1]/'ssh/known_hosts')
def sshargs(i):
 n=NODES[i]
 return ['ssh','-i',KEY,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile="'+KNOWN+'"','-p',str(n['ssh_port']),'root@'+n['ssh_host']]
def run(i,command,input=None,timeout=120):
 return subprocess.run(sshargs(i)+[command],input=input,capture_output=True,text=True,timeout=timeout)
def upload(i,local,remote):
 data=pathlib.Path(local).read_bytes()
 # Binary data stays in SSH stdin and is never interpolated into shell code.
 return subprocess.run(sshargs(i)+['umask 077; cat > '+shlex.quote(remote)],input=data,capture_output=True,timeout=120)
