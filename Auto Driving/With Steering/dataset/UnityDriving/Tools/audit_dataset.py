"""Verify recorded Unity images, timing, labels and scenario split separation."""
from pathlib import Path
import csv,json,math,hashlib
from PIL import Image,ImageStat

ROOT=Path(__file__).resolve().parents[1]
report={'runs':[],'splits':{}}
for labels in sorted((ROOT/'Dataset').glob('*/labels.csv')):
    cfg=json.loads((labels.parent/'config.json').read_text(encoding='utf-8-sig'))
    rows=list(csv.DictReader(labels.open(encoding='utf-8-sig',newline='')))
    previous={};episode_ids=set()
    for row in rows:
        p=labels.parent/row['image'];assert p.is_file(),p
        with Image.open(p) as image:
            image.load();assert image.size==(cfg['imageWidth'],cfg['imageHeight']);assert image.mode=='RGB'
            assert max(ImageStat.Stat(image).stddev)>1,'Blank image: '+str(p)
        for field in ['speed_m_s','applied_wheel_deg','target_wheel_deg','cte_m','road_margin_m','sim_time_s']:
            assert math.isfinite(float(row[field])),field
        episode=row['episode'];t=float(row['sim_time_s']);assert t>previous.get(episode,-1);previous[episode]=t
        assert (float(row['road_margin_m'])>0)==(row['valid']=='1')
        assert -cfg['leftWheelLimit']-.001<=float(row['target_wheel_deg'])<=cfg['rightWheelLimit']+.001
        episode_ids.add(episode)
    assert len(list((labels.parent/'images').glob('*.png')))==len(rows)
    report['runs'].append({'run':labels.parent.name,'images':len(rows),'episodes':len(episode_ids)})
groups_seen=set();hashes_seen=set()
for name in ['train','validation','test']:
    path=ROOT/'DatasetSplits'/(name+'.csv')
    if not path.exists():continue
    rows=list(csv.DictReader(path.open(encoding='utf-8-sig',newline='')))
    groups={(r['seed'],r['lane']) for r in rows};assert not groups&groups_seen
    groups_seen.update(groups)
    hashes={hashlib.sha256(Path(r['image']).read_bytes()).hexdigest() for r in rows};assert not hashes&hashes_seen
    hashes_seen.update(hashes);report['splits'][name]={'images':len(rows),'scenario_groups':len(groups)}
report['status']='passed'
(ROOT/'Diagnostics/dataset_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
