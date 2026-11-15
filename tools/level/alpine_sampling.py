"""CPU reference for the Alpine stochastic texture blend and visual QA.

This verifies the sampling construction, not Unreal lighting or performance.
"""
import numpy as np


def turn(p, r):
    p=np.asarray(p);r=np.asarray(r)
    return np.where((r==0)[...,None],p,
           np.where((r==1)[...,None],np.stack((-p[...,1],p[...,0]),-1),
           np.where((r==2)[...,None],-p,np.stack((p[...,1],-p[...,0]),-1))))


def bilinear(image, uv):
    h,w=image.shape[:2];p=(uv%1)*[w,h]-.5
    i=np.floor(p).astype(int);f=p-i
    a=f[...,0,None];b=f[...,1,None]
    return ((1-a)*(1-b)*image[i[...,1]%h,i[...,0]%w]
            +a*(1-b)*image[i[...,1]%h,(i[...,0]+1)%w]
            +(1-a)*b*image[(i[...,1]+1)%h,i[...,0]%w]
            +a*b*image[(i[...,1]+1)%h,(i[...,0]+1)%w])


def stochastic(image, uv, normal=False, footprint=0., stable_normals=True):
    base=np.floor(uv);f=uv-base;upper=f.sum(-1)>1
    vertices=[base+upper[...,None],base+[1,0],base+[0,1]]
    weights=np.where(upper[...,None],np.stack((f.sum(-1)-1,1-f[...,1],1-f[...,0]),-1),
                     np.stack((1-f.sum(-1),f[...,0],f[...,1]),-1))**3
    weights/=weights.sum(-1,keepdims=True)
    result=np.zeros((*uv.shape[:-1],image.shape[-1]))
    mean_normal=image[...,:2].mean((0,1))*2-1 if normal and stable_normals else 0
    detail=np.clip((np.asarray(footprint)-.08)/(.45-.08),0,1)
    detail=1-detail*detail*(3-2*detail) if stable_normals else 1.
    for i,vertex in enumerate(vertices):
        hashed=(np.sin(vertex@np.array([[127.1,269.5],[311.7,183.3]]))*43758.5453)%1
        rotation=np.floor(hashed[...,0]*4).astype(int)
        value=bilinear(image,turn(uv,rotation)+hashed)
        if normal:value[...,:2]=turn(value[...,:2]*2-1-mean_normal,(4-rotation)%4)*np.asarray(detail)[...,None]
        result+=value*weights[...,i,None]
    return result
