from pathlib import Path
import json
p=Path('/opt/vectormatch-cpu/preparation/pg-readonly-recovery-r1')
print(json.dumps({'report':json.loads((p/'sql-inspection-r1/inspection.json').read_text()),'inspectorStderr':(p/'sql.stderr').read_text(),'postgresLog':(p/'postgres.log').read_text(),'stop':json.loads((p/'automatic-stop.json').read_text())}))
