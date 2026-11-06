"""Wwise bank v150 node parser, for reading only."""
import struct,sys,os
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','bank'))
import hirc
RTPC_SCALE=860323339
def varint(b,o):
    v=0
    while True:
        c=b[o];o+=1;v=(v<<7)|(c&0x7f)
        if not c&0x80: return v,o
def base(b,o):
    """NodeBaseParams at o -> dict and end."""
    r={'at':o}
    r['ofx']=b[o];n=b[o+1];o+=2
    if n: o+=1+n*6
    r['nfx']=n
    r['omd']=b[o];m=b[o+1];o+=2
    if m: o+=1+m*6
    r['bus'],r['parent']=struct.unpack_from('<II',b,o);o+=8
    r['bits']=b[o];o+=1
    r['props_at']=o
    c=b[o];o+=1
    ids=list(b[o:o+c]);o+=c
    r['props']={i:struct.unpack_from('<f',b,o+4*k)[0] if i!=0x54 else struct.unpack_from('<I',b,o+4*k)[0] for k,i in enumerate(ids)};o+=4*c
    c=b[o];o+=1
    ids=list(b[o:o+c]);o+=c
    r['ranged']={i:struct.unpack_from('<ff',b,o+8*k) for k,i in enumerate(ids)};o+=8*c
    # positioning
    r['pos_at']=o
    pb=b[o];o+=1
    if pb&0x02:   # override or has3d: bit1 = positioning 3d
        b3=b[o];o+=1
        r['b3']=b3
        if (b3>>5)&1 or ((b3>>5)&3)!=0 and False: pass
        ty=(b3>>5)&3   # automation
        if b3&0x60:
            o+=1+4+1  # pathmode, transition time... handled below by error
            raise ValueError('3d automation')
    r['posbits']=pb
    r['aux_at']=o
    ab=b[o];o+=1
    if ab&0x08: o+=16
    o+=4 # reflections aux bus
    r['adv_at']=o
    o+=1+1+2+1+1
    # state chunk
    r['state_at']=o
    n,o=varint(b,o)
    r['nstateprops']=n
    for i in range(n):
        p,o=varint(b,o);o+=2
    g,o=varint(b,o)
    r['nstategroups']=g
    for i in range(g):
        o+=4+1
        s,o=varint(b,o)
        for j in range(s):
            o+=4
            c=None
            pc,o=varint(b,o)
            for k in range(pc):
                p,o=varint(b,o);o+=4
    r['rtpc_at']=o
    n=struct.unpack_from('<H',b,o)[0];o+=2
    rt=[]
    for i in range(n):
        rid=struct.unpack_from('<I',b,o)[0];ty=b[o+4];acc=b[o+5];o+=6
        p,o=varint(b,o)
        cid=struct.unpack_from('<I',b,o)[0];sc=b[o+4];size=struct.unpack_from('<H',b,o+5)[0];o+=7
        pts=[struct.unpack_from('<ffI',b,o+12*k) for k in range(size)];o+=12*size
        rt.append(dict(rtpc=rid,type=ty,accum=acc,param=p,curve=cid,scaling=sc,points=pts))
    r['rtpc']=rt
    r['end']=o
    return r
def node(t,body):
    if t==2:
        pl=struct.unpack_from('<I',body,0)[0]
        o=14
        if pl&0xf==2: 
            s=struct.unpack_from('<I',body,o)[0];o+=4+s
        return base(body,o)
    if t in(5,6,7,9):
        return base(body,0)
