"""Compile the actual shader helper, catching errors CPU math tests cannot."""
import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]


class AlpineHlslTests(unittest.TestCase):
    def test_full_landscape_body_compiles_with_ecology_and_road_detail(self):
        candidates=sorted(Path('C:/Program Files (x86)/Windows Kits/10/bin').glob('*/x64/dxc.exe'),reverse=True)
        dxc=shutil.which('dxc') or (str(candidates[0]) if candidates else None)
        if not dxc:self.skipTest('DXC unavailable')
        tree=ast.parse((ROOT/'unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py').read_text())
        code=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
                  and any(isinstance(target,ast.Name) and target.id=='LAND_PBR_CODE' for target in node.targets))
        shader='#define Texture2DSample(T,S,U) T.Sample(S,U)\n#define Texture2DSampleGrad(T,S,U,X,Y) T.SampleGrad(S,U,X,Y)\n#define Texture2DSampleLevel(T,S,U,L) T.SampleLevel(S,U,L)\n'
        textures='Base SurfaceData Ecology SandD SandN SandO RipD RipN RipO GrassD GrassN GrassO SandBD SandBN DirtD DirtN DirtO MidD MidN MidO GravD GravN GravO LM FootRT Edge RockD RockN'.split()
        for name in textures:shader+=f'Texture2D {name};SamplerState {name}Sampler;\n'
        vectors='EcologyInfo SurfaceDataInfo LandRect GrassTint Tiles Sea Mix WetLook Inland Dirt DirtTint SandTint Look LMLevels FootRect FootMpc Foot Par Macro RockTint Steep Slope Fill EdgeLook Ice IceColor Alpine'.split()
        shader+='cbuffer C {float4 Inputs[32];float FootFromMpc,MeshUV,Plain;float2 TC0,TC1;};\n'
        shader+='struct Params {float3x3 TangentToWorld;};struct ViewData {float3 ViewForward;};\n'
        shader+='float3 surface(float3 W,float3 Nw,float3 Cam,Params Parameters,out float3 Normal,out float Rough,out float AO,out float PDO,out float Spec,out float3 Emissive)\n{\n'
        shader+='ViewData View;View.ViewForward=float3(0,0,-1);\n'+''.join(f'float4 {name}=Inputs[{i}];\n' for i,name in enumerate(vectors))
        shader+=code+'\n}\n'
        shader+='float4 main(float3 W:TEXCOORD0,float3 Nw:TEXCOORD1):SV_Target {float3 N,E;float R,A,D,S;Params P;P.TangentToWorld=float3x3(1,0,0,0,1,0,0,0,1);return float4(surface(W,Nw,float3(0,0,10000),P,N,R,A,D,S,E)+N*.1+E+R*.1+A*.1+D*.1+S*.1,1);}\n'
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'landscape.hlsl';source.write_text(shader)
            result=subprocess.run([dxc,'-HV','2021','-T','ps_6_6','-E','main','-Fo',str(Path(folder)/'landscape.dxil'),str(source)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_full_apron_body_compiles_including_shared_helpers(self):
        candidates=sorted(Path('C:/Program Files (x86)/Windows Kits/10/bin').glob('*/x64/dxc.exe'),reverse=True)
        dxc=shutil.which('dxc') or (str(candidates[0]) if candidates else None)
        if not dxc:self.skipTest('DXC unavailable')
        tree=ast.parse((ROOT/'unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py').read_text())
        code=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
                  and any(isinstance(target,ast.Name) and target.id=='ALPINE_APRON_CODE' for target in node.targets))
        shader='#define Texture2DSample(T,S,U) T.Sample(S,U)\n#define Texture2DSampleGrad(T,S,U,X,Y) T.SampleGrad(S,U,X,Y)\n#define Texture2DSampleLevel(T,S,U,L) T.SampleLevel(S,U,L)\n'
        for name in ('Geology','Ecology','Field','GrassD','GrassN','SoilD','SoilN','RockD','RockN','SnowD','SnowN'):
            shader+=f'Texture2D {name};SamplerState {name}Sampler;\n'
        vectors='FieldInfo FieldRect EcologyInfo Extent GeologyBlend GeologyRect GeologyMix GrassTint SoilTint RockTint Tiles Steep Alpine FarSnow SnowRetention'.split()
        shader+='cbuffer C {'+''.join('float4 '+name+';' for name in vectors)+'};\n'
        shader+='struct Params {float3x3 TangentToWorld;};\nfloat3 surface(float3 W,float3 Nw,float3 Cam,Params Parameters,out float3 Normal,out float Rough,out float Spec)\n{\n'+code+'\n}\n'
        shader+='float4 main(float3 W:TEXCOORD0,float3 Nw:TEXCOORD1):SV_Target {float3 N;float R,S;Params P;P.TangentToWorld=float3x3(1,0,0,0,1,0,0,0,1);return float4(surface(W,Nw,float3(0,0,10000),P,N,R,S)+N*.1+R*.1+S*.1,1);}\n'
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'apron.hlsl';source.write_text(shader)
            result=subprocess.run([dxc,'-HV','2021','-T','ps_6_6','-E','main','-Fo',str(Path(folder)/'apron.dxil'),str(source)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_paving_layout_and_full_surface_body_compile(self):
        candidates=sorted(Path('C:/Program Files (x86)/Windows Kits/10/bin').glob('*/x64/dxc.exe'),reverse=True)
        dxc=shutil.which('dxc') or (str(candidates[0]) if candidates else None)
        if not dxc:self.skipTest('DXC unavailable')
        tree=ast.parse((ROOT/'unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py').read_text())
        code=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
                  and any(isinstance(target,ast.Name) and target.id=='PWR_PAVING_CODE' for target in node.targets))
        shader='#define Texture2DSample(T,S,U) T.Sample(S,U)\nTexture2D PanelData,PanelNormal; SamplerState PanelDataSampler,PanelNormalSampler;\n'
        shader+='cbuffer C {float4 Paving,Tint,PanelLayout,Pattern;};\n'
        shader+='float3 surface(float3 W,float3 Nw,out float3 Normal,out float Rough,out float AO,out float Metal)\n{\n'+code+'\n}\n'
        shader+='float4 main(float3 W:TEXCOORD0,float3 Nw:TEXCOORD1):SV_Target {float3 N;float R,A,M;return float4(surface(W,Nw,N,R,A,M)+N*.1+R*.1+A*.1+M*.1,1);}\n'
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'paving.hlsl';source.write_text(shader)
            result=subprocess.run([dxc,'-HV','2021','-T','ps_6_6','-E','main','-Fo',str(Path(folder)/'paving.dxil'),str(source)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_actual_nested_helper_compiles_with_dxc(self):
        candidates=sorted(Path('C:/Program Files (x86)/Windows Kits/10/bin').glob('*/x64/dxc.exe'),reverse=True)
        dxc=shutil.which('dxc') or (str(candidates[0]) if candidates else None)
        if not dxc:self.skipTest('DXC unavailable; full Unreal cook remains required')
        tree=ast.parse((ROOT/'unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py').read_text())
        code=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
                  and any(isinstance(target,ast.Name) and target.id=='LAND_PBR_CODE' for target in node.targets))
        helper=code[code.index('struct LPStochastic'):code.index('// The deformation map')]
        # Exact nested-struct context used by an Unreal custom expression.
        shader='#define Texture2DSampleGrad(T,S,U,X,Y) T.SampleGrad(S,U,X,Y)\n#define Texture2DSampleLevel(T,S,U,L) T.SampleLevel(S,U,L)\nTexture2D tex; SamplerState smp;\n'
        shader+='float4 main(float2 uv:TEXCOORD0):SV_Target\n{\n'+helper
        shader+='return LPStochastic::tileBlend(tex,smp,uv,ddx(uv),ddy(uv),true);\n}\n'
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'shader.hlsl';source.write_text(shader)
            result=subprocess.run([dxc,'-HV','2021','-T','ps_6_6','-E','main','-Fo',str(Path(folder)/'shader.dxil'),str(source)],
                                  capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
