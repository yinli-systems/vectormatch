from pathlib import Path
P=Path(__file__).resolve().parent
parts=[P/'storage_primitives.py',P/'remote_actions.py']
(P/'remote_retire.py').write_text('\n\n'.join(p.read_text()for p in parts))
