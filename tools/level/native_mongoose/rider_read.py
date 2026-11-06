"""Rider joints in the vehicle's own frame, from the sim's node matrices. cm, x forward, y left, z up."""
import os
import ctypes,sys,struct,json,re,subprocess
MJ = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "target", "release", "mjolnir.exe")
HERE=sys.argv[1]
k=ctypes.WinDLL("kernel32",use_last_error=True)
k.OpenProcess.restype=ctypes.c_void_p
k.ReadProcessMemory.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
out=subprocess.run([MJ,"live","objects"],capture_output=True,text=True).stdout
veh=bip=None
for l in out.splitlines():
    c=l.split("\t")
    if len(c)>13:
        if c[4].endswith("nmg\mongoose"): veh=int(c[13],16)
        if ("spartans" in c[4] or "nmg" in c[4]) and c[3]=="bipd": bip=int(c[13],16)
pid=int(subprocess.run('powershell -c "(Get-Process HaloCampaignEvolved* | sort WorkingSet64 -desc | select -first 1).Id"',shell=True,capture_output=True,text=True).stdout)
h=k.OpenProcess(0x10|0x400,0,pid)
def rd(a,n):
    b=ctypes.create_string_buffer(n);r=ctypes.c_size_t();k.ReadProcessMemory(h,a,b,n,ctypes.byref(r));return b.raw[:r.value]
names=list(json.load(open(HERE+"/rider/spartan_poses.json",encoding="utf-8"))["ghost_d:idle"].keys())
def find(a,NN,size=0x12000):
    m=rd(a,size)
    for off in range(0,len(m)-NN*0x34,4):
        ok=True
        for i in range(NN):
            sc=struct.unpack_from('<f',m,off+i*0x34)[0]
            if not 0.2<sc<3: ok=False;break
            f=struct.unpack_from('<3f',m,off+i*0x34+4)
            if abs(f[0]**2+f[1]**2+f[2]**2-1)>0.05: ok=False;break
        if ok: return off,m
    return None,m
print("veh",hex(veh or 0),"biped",hex(bip or 0),"names",len(names),names[:4])
voff,vm=find(veh,15)
V=struct.unpack_from('<13f',vm,voff)
F,L,U,P=V[1:4],V[4:7],V[7:10],V[10:13]
dot=lambda a,b:sum(x*y for x,y in zip(a,b))
NN=int(sys.argv[2]) if len(sys.argv)>2 else 60
off,m=find(bip,NN)
print("biped nodes at",hex(off) if off is not None else None)
if off is None: sys.exit()
cnt=NN
while off+(cnt+1)*0x34<len(m):
    sc=struct.unpack_from('<f',m,off+cnt*0x34)[0]; f=struct.unpack_from('<3f',m,off+cnt*0x34+4)
    if 0.2<sc<3 and abs(dot(f,f)-1)<0.05: cnt+=1
    else: break
print("nodes",cnt)
want=sys.argv[3].split(",") if len(sys.argv)>3 else ["root_m","chest_m","head_m","shoulder_l","shoulder_r","wrist_l","wrist_r","hip_l","hip_r","knee_l","knee_r","ankle_l","ankle_r"]
T={"shoulder_l":None,"wrist_l":(8.8,32.6,158.0),"wrist_r":(7.3,-34.1,157.4),"ankle_l":(-50.5,38.1,87.4),"ankle_r":(-45.0,-36.7,86.3),"root_m":(-61.7,-1.2,129.0),"head_m":(-18.7,-1.3,171.0),"knee_l":(-16.4,36.8,120.6),"knee_r":(-12.3,-28.9,120.1)}
for w in want:
    i=next((j for j,n in enumerate(names) if n and n.lower()==w.lower()),None)
    if i is None or i>=cnt: print(w,"?"); continue
    R=struct.unpack_from('<13f',m,off+i*0x34)
    d=[R[10+j]-P[j] for j in range(3)]
    c=[dot(d,F)*304.8,dot(d,L)*304.8,dot(d,U)*304.8]
    t=T.get(w); e=(sum((a-b)**2 for a,b in zip(c,t))**.5) if t else None
    print(f"{w:12s} {c[0]:8.1f} {c[1]:8.1f} {c[2]:8.1f}"+(f"   CE {t[0]:7.1f} {t[1]:7.1f} {t[2]:7.1f}  miss {e:5.1f}" if t else ""))
