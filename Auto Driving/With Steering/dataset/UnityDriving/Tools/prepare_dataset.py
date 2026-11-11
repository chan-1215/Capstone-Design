"""Split complete seeded scenarios across runs, never adjacent frames."""
import argparse,csv,json,random,hashlib
from pathlib import Path
from collections import Counter,defaultdict

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,default=Path(__file__).resolve().parents[1]/'Dataset')
    p.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'DatasetSplits')
    p.add_argument('--seed',type=int,default=20261110)
    p.add_argument('--label-source',choices=['teacher','applied','command'],default='teacher')
    args=p.parse_args();groups=defaultdict(list);rejected=Counter();seen=set()
    column={'teacher':'target_wheel_deg','applied':'applied_wheel_deg','command':'command_wheel_deg'}[args.label_source]
    for manifest in sorted(args.input.glob('*/labels.csv')):
        with manifest.open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                if row['valid']!='1':rejected['invalid_road_margin']+=1;continue
                image=(manifest.parent/row['image']).resolve()
                if not image.is_relative_to(manifest.parent.resolve()) or not image.is_file():
                    rejected['missing_or_external_image']+=1;continue
                if abs(float(row['speed_m_s']))<.015:rejected['stationary']+=1;continue
                digest=hashlib.sha256(image.read_bytes()).hexdigest()
                if digest in seen:rejected['identical_image']+=1;continue
                seen.add(digest)
                row['image']=str(image);row['label_wheel_deg']=row[column]
                row['run']=manifest.parent.name;groups[(row['seed'],row['lane'])].append(row)
    keys=list(groups);random.Random(args.seed).shuffle(keys)
    if len(keys)<3:raise SystemExit('Need at least 3 recorded episodes before splitting. No frame-level fallback is used.')
    nv=max(1,round(len(keys)*.1));nt=max(1,round(len(keys)*.1))
    partitions={'train':keys[nv+nt:],'validation':keys[:nv],'test':keys[nv:nv+nt]}
    args.output.mkdir(parents=True,exist_ok=True);report={'label_source':column,'split_unit':'seed+lane grouped across all runs','seed':args.seed,'rejected':dict(rejected),'partitions':{}}
    for name,part in partitions.items():
        rows=[row for key in part for row in groups[key]]
        with (args.output/(name+'.csv')).open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        turns=Counter('left' if float(r['label_wheel_deg'])<-3 else 'right' if float(r['label_wheel_deg'])>3 else 'straight' for r in rows)
        report['partitions'][name]={'episodes':len(part),'images':len(rows),'turns':dict(turns),'groups':part}
    (args.output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
