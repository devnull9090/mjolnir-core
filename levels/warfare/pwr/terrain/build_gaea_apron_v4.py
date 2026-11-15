"""Author a genuinely 8km native Gaea backdrop; never edits playable terrain.

Independent seeded Alpine ranges occupy a ring outside the central2km valley.
Export in the licensed Gaea UI after the game foreground writer is released.
No repeated image tile, source stretching, reflected edge or synthetic collar
ridge supplies the drainage. The exact gameplay seam is joined downstream.
"""
from pathlib import Path
import json
from build_gaea_v5 import ROOT,HERE,node,obj

def main():
    output=ROOT/'out/pwr/gaea-apron-v4'
    doc=json.loads((HERE/'pwr_world_refined.terrain').read_text())
    asset=doc['Assets']['$values'][0];terrain=asset['Terrain'];nodes={'$id':'5'}
    # Primary peaks are1.6–2.6km from the origin; irregular parallel spurs
    # produce actual connected watersheds, rather than a continuous wall.
    masses=[
      (301,'Northwest inner ridge',.285,.285,.205,2.45,60217),
      (302,'Northwest distant shoulder',.15,.17,.27,2.9,31843),
      (303,'North saddle west',.42,.21,.17,1.9,11447),
      (304,'North saddle east',.61,.205,.20,2.2,55031),
      (305,'Northeast inner ridge',.725,.285,.225,2.7,28661),
      (306,'Northeast distant shoulder',.84,.13,.26,2.8,46003),
      (307,'West inner range',.255,.49,.20,2.4,15877),
      (308,'Western outer range',.085,.57,.255,2.8,30643),
      (309,'Southwest inner ridge',.285,.72,.215,2.4,31991),
      (310,'Southwest distant range',.13,.84,.25,2.9,22699),
      (311,'Eastern inner ridge',.745,.49,.19,2.1,39371),
      (312,'Eastern distant range',.92,.58,.235,2.75,60493),
      (313,'Southeast lake shoulder',.745,.72,.20,1.8,50021),
      (314,'Southeast distant range',.86,.88,.26,2.7,17467),
      (315,'Southern valley west',.43,.81,.22,1.55,41959),
      (316,'Southern valley east',.62,.86,.24,1.7,26417),
    ]
    for index,(ident,name,x,y,scale,height,seed) in enumerate(masses):
        nodes[str(ident)]=node('Mountain',ident,name,26000,25000+index*150,
          Scale=scale,Height=height,Style='Alpine',Seed=seed,X=x,Y=y)
    groups=[]
    for group in range(4):
        ident=330+group;members=masses[group*4:group*4+4]
        ports=[('In' if i==0 else f'Input{i+1}',member[0],'Out') for i,member in enumerate(members)]
        nodes[str(ident)]=node('Combine',ident,'Independent range group',26500,25300+group*400,
          ports,PortCount=4,Ratio=1.,Mode='Max');groups.append(ident)
    nodes['340']=node('Combine',340,'Full8km mountain ring',26900,26000,
       [('In' if i==0 else f'Input{i+1}',source,'Out') for i,source in enumerate(groups)],PortCount=4,Ratio=1.,Mode='Max')
    nodes['350']=node('Erosion2',350,'Range scale drainage',27300,26000,[('In',340,'Out')],
       Duration=30.,Downcutting=.3,ErosionScale=380.,Seed=20604,
       SuspendedLoadDischargeAmount=.3,CoarseSedimentsDischargeAmount=.35,
       Shape=.18,ShapeSharpness=.3,ShapeDetailScale=.06,Version=2)
    nodes['351']=node('Erosion2',351,'Secondary gullies and talus',27700,26000,[('In',350,'Out')],
       Duration=14.,Downcutting=.1,ErosionScale=100.,Seed=36739,
       CoarseSedimentsDischargeAmount=.65,CoarseSedimentsDischargeAngle=29.,Shape=.03,Version=2)
    for i,port in enumerate(('Out','Flow','Wear','Deposits')):
        ident=370+i;name='apron_height' if port=='Out' else 'apron_'+port.lower()
        value=node('Export',ident,name,28100,25800+i*200,[('In',351,port)],Format='FloatRaw32')
        value['SaveDefinition']=obj(Node=ident,Filename=name,Format='FloatRaw32',IsEnabled=True,DisabledInProfiles=obj(**{'$values':[]}))
        nodes[str(ident)]=value
    terrain['Nodes']=nodes;terrain.update(Width=8000.,Height=1100.,Ratio=1100/8000)
    tab=terrain['GraphTabs']['$values'][0];tab.update(ZoomFactor=.35);tab['ViewportLocation'].update(X=25400,Y=24700)
    asset['BuildDefinition'].update(Destination=str(output),Resolution=1024,BakeResolution=1024)
    asset['State'].update(SelectedNode=370,PreviewResolution=512)
    doc['Metadata'].update(Name='PWR independent Alpine backdrop v4',Description=__doc__.strip())
    target=HERE/'pwr_apron_native_v4.terrain';target.write_text(json.dumps(doc,indent=2)+'\n')
    output.mkdir(parents=True,exist_ok=True)
    print(target)

if __name__=='__main__':main()
