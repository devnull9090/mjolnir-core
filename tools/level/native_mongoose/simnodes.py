import ctypes,sys,struct,time,json
k=ctypes.WinDLL("kernel32",use_last_error=True)
k.OpenProcess.restype=ctypes.c_void_p
k.ReadProcessMemory.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
h=k.OpenProcess(0x10|0x400,0,int(sys.argv[1]))
A=int(sys.argv[2],16); NN=int(sys.argv[3]); SIZE=0x8000
def rd():
    b=ctypes.create_string_buffer(SIZE);r=ctypes.c_size_t()
    k.ReadProcessMemory(h,A,b,SIZE,ctypes.byref(r)); return b.raw[:r.value]
def find(m):
    for off in range(0,len(m)-NN*0x34,4):
        ok=True
        for i in range(NN):
            s=struct.unpack_from('<f',m,off+i*0x34)[0]
            if not 0.5<s<2.0: ok=False;break
            f=struct.unpack_from('<3f',m,off+i*0x34+4)
            if abs(f[0]**2+f[1]**2+f[2]**2-1)>0.02: ok=False;break
        if ok: return off
m=rd(); off=find(m); print("nodes at",hex(off) if off is not None else None,"read",len(m))
if off is None: sys.exit()
def rows(m):
    R=[]
    for i in range(NN):
        v=struct.unpack_from('<13f',m,off+i*0x34)
        R.append(v)
    return R
def rel(R,i):
    b=R[0];n=R[i]
    F,L,U,P=b[1:4],b[4:7],b[7:10],b[10:13]
    dp=[n[10+j]-P[j] for j in range(3)]
    dot=lambda a,c:sum(x*y for x,y in zip(a,c))
    loc=[dot(dp,F),dot(dp,L),dot(dp,U)]
    ax=[dot(n[1:4],F),dot(n[1:4],L),dot(n[1:4],U),dot(n[7:10],F),dot(n[7:10],L),dot(n[7:10],U)]
    return loc+ax
first=[rel(rows(m),i) for i in range(NN)]
print("node0 pos",rows(m)[0][10:13])
for i in range(NN): print(i,"rel wu",[round(x,3) for x in first[i][:3]],"ax",[round(x,3) for x in first[i][3:]])
secs=float(sys.argv[4]); end=time.time()+secs; mx=[[0]*2 for _ in range(NN)]
while time.time()<end:
    m=rd(); R=rows(m)
    for i in range(NN):
        c=rel(R,i)
        mx[i][0]=max(mx[i][0],sum((c[j]-first[i][j])**2 for j in range(3))**.5)
        mx[i][1]=max(mx[i][1],max(abs(c[j]-first[i][j]) for j in range(3,9)))
    time.sleep(0.01)
print("max change over run (wu, axis)")
for i in range(NN): print(i,round(mx[i][0],4),round(mx[i][1],4))
