"""Import the independently eroded 8 km Gaea backdrop without playable edits."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,default=ROOT/'out/pwr/gaea-apron-v4')
    parser.add_argument('--graph',type=Path,default=HERE/'pwr_apron_native_v4.terrain')
    parser.add_argument('--out',type=Path,default=HERE/'gaea-apron-v4')
    parser.add_argument('--datum',type=float,default=60.)
    args=parser.parse_args()
    report=json.loads((args.build/'report.json').read_text())
    if report.get('Result')!='Success' or report.get('Resolution')!=1024:
        raise ValueError('A successful actual Gaea 1024 build is required')
    graph=json.loads(args.graph.read_text())
    terrain=graph['Assets']['$values'][0]['Terrain']
    width,height=float(terrain['Width']),float(terrain['Height'])
    if width!=8000. or height!=1100. or not np.isfinite(args.datum):
        raise ValueError('Unexpected independent backdrop domain or calibration')
    args.out.mkdir(parents=True,exist_ok=True)
    masks={}
    for name in ('height','flow','wear','deposits'):
        path=args.build/f'apron_{name}.r32'
        raw=np.fromfile(path,dtype='<f4')
        if raw.size!=1024**2 or not np.isfinite(raw).all() or raw.min()<0 or raw.max()>1:
            raise ValueError('Invalid native Gaea normalized export: '+name)
        values=np.flipud(raw.reshape(1024,1024)).copy()
        if name=='height':values=(args.datum+values*height).astype(np.float32)
        filename='source.heights.npy' if name=='height' else name+'.npy'
        np.save(args.out/filename,values)
        shutil.copy2(path,args.out/f'{name}.r32')
        spec={'path':filename,'encoding':'float32_npy','sha256':digest(args.out/filename)}
        if name=='height':height_spec=dict(spec,offset_m=0,scale_m=1)
        else:masks[name]=spec
    shutil.copy2(args.build/'report.json',args.out/'build-report.json')
    manifest={'schema':'pwr-heightfield-v1','coordinates':'authoring_metres_z_up',
        'source_tool':'Gaea 2.3.1.0 Community','source_build_report':'build-report.json',
        'source_graph':str(args.graph.resolve()),'source_graph_sha256':digest(args.graph),
        'source_r32_sha256':digest(args.out/'height.r32'),
        'normalization':'Native north-first R32 flipped to +Y rows; explicit datum plus graph height',
        'calibration':{'datum_m':args.datum,'height_range_m':height},
        'status':'Independent native eroded backdrop; render only, outside frozen playable terrain',
        'origin_m':[-width/2,-width/2],'spacing_m':[width/1023]*2,'dimensions':[1024]*2,
        'row_order':'+y','height':height_spec,'masks':masks}
    (args.out/'source.json').write_text(json.dumps(manifest,indent=2)+'\n')
    elevations=np.load(args.out/'source.heights.npy')
    print(json.dumps({'manifest':str((args.out/'source.json').resolve()),
        'sha256':digest(args.out/'source.json'),'height_percentiles_m':
        dict(zip(['min','p10','p50','p90','p99','max'],np.quantile(elevations,[0,.1,.5,.9,.99,1]).tolist()))}))


if __name__=='__main__':main()
