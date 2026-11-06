import struct,sys
def load(fn):
    b=open(fn,'rb').read()
    at=0;secs={}
    while at+8<=len(b):
        m=b[at:at+4];s=struct.unpack_from("<I",b,at+4)[0];secs[m]=(at+8,s);at+=8+s
    o,s=secs[b'HIRC'];n=struct.unpack_from("<I",b,o)[0];at=o+4
    objs={}
    for i in range(n):
        t=b[at];sz=struct.unpack_from("<I",b,at+1)[0];oid=struct.unpack_from("<I",b,at+5)[0]
        objs[oid]=(t,b[at+9:at+5+sz],at);at+=5+sz
    return b,secs,objs
if __name__=='__main__':
    b,secs,objs=load(sys.argv[1])
    print({k.decode():v for k,v in secs.items()})
    ids=[int(x) for x in sys.argv[2:]]
    seen=set()
    def show(i,d=0):
        if i in seen: return
        seen.add(i)
        if i not in objs: print(' '*d,i,'not in bank');return
        t,body,at=objs[i]
        print(' '*d,'type',t,'id',i,'at',at,'size',len(body)+4,'\n',' '*d,body.hex(' '))
        if t==4:
            n=body[0]
            for k in range(n): show(struct.unpack_from('<I',body,1+4*k)[0],d+2)
        if t==3:
            show(struct.unpack_from('<I',body,2)[0],d+2)
    for i in ids: show(i)
