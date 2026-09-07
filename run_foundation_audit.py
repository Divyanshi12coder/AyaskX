from pathlib import Path
import zipfile, json, shutil
from data.ingestion.csv_adapter import CSVAdapter
from data.snapshots.manifest import build_manifest
from data.validation.leakage import detect_name_risks

ROOT=Path(__file__).resolve().parent
ZIP=ROOT.parent/'datasets.zip'
WORK=ROOT/'source_friend_v1'
if WORK.exists(): shutil.rmtree(WORK)
with zipfile.ZipFile(ZIP) as z: z.extractall(WORK)
base=WORK/'SIH26009_DATA'
rows=[]
for p in sorted(base.rglob('*.csv')):
    try:
        df=CSVAdapter().read(p)
        findings=detect_name_risks(list(df.columns))
        rows.append({"file":str(p.relative_to(base)),"rows":len(df),"columns":len(df.columns),"leakage_name_risks":len(findings),"schema_hash":build_manifest(p)["schema_hash"]})
    except Exception as e:
        rows.append({"file":str(p.relative_to(base)),"error":str(e)})
(ROOT/'audit_manifest.json').write_text(json.dumps(rows,indent=2))
print(f"Audited {len(rows)} CSV files")
