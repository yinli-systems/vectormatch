"""Direct SSH to the one user-provided CPU Pod; imports perform no network action."""
import pathlib,subprocess,shlex
BASE=pathlib.Path(__file__).resolve().parent
HOST='185.226.156.243';PORT=13658;POD='4il7v4518ccogj';EXPECTED_HOSTNAME='ed6c0673f5cb'
KEY=pathlib.Path.home()/'.ssh/id_ed25519'
def sshargs():
 return ['ssh','-i',str(KEY),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','StrictHostKeyChecking=yes','-p',str(PORT),'root@'+HOST]
def run(command,input=None,timeout=120):
 return subprocess.run(sshargs()+[command],input=input,capture_output=True,text=True,timeout=timeout)
def upload(local,target):
 return subprocess.run(sshargs()+['umask 077; cat > '+shlex.quote(target)],input=pathlib.Path(local).read_bytes(),capture_output=True,timeout=150)
