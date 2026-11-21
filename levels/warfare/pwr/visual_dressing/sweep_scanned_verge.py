"""Pack real gravel faces, dry pine silhouettes and trampled grain at 5 mm/texel."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import binary_closing, find_objects, gaussian_filter, label
from scipy.spatial import ConvexHull

WIDTH, HEIGHT = 224, 1008


def detached_stones(images):
    sprites=[]
    for name in ("stone", "scree"):
        rgb=images[name][...,:3]
        lum=rgb @ [0.2126, 0.7152, 0.0722]
        high=lum-gaussian_filter(lum,13,mode="wrap")
        faces=binary_closing(high > np.percentile(high,84),iterations=2)
        labels,_=label(faces,np.ones((3,3)))
        for j,region in enumerate(find_objects(labels),1):
            piece=labels[region]==j
            h,w=piece.shape
            if min(h,w)<7 or max(h,w)>59 or min(h,w)/max(h,w)<.32 or piece.sum()<62:
                continue
            y,x=np.nonzero(piece)
            hull=ConvexHull(np.c_[x,y])
            outline=Image.new("L",(w,h))
            ImageDraw.Draw(outline).polygon([(int(x[i]),int(y[i])) for i in hull.vertices],fill=255)
            mask=np.asarray(outline.filter(ImageFilter.GaussianBlur(.42))).copy()
            albedo=np.clip((lum[region]-.09)*1.27,.10,.95)
            sprites.append((mask,np.rint(albedo*255).astype(np.uint8)))
    if len(sprites)<25:
        raise ValueError("Too few detached angular faces in the two native gravel scans")
    return sprites


def verge_strip(images):
    rng=np.random.default_rng(20261122)
    h,w=HEIGHT,WIDTH
    tex=np.zeros((h,w,4),np.float32)
    tex[...,3]=.5
    # Actual fine trampled-soil scan, with the large lighting gradients removed.
    soil=images["earth"][...,:3] @ [.2126,.7152,.0722]
    grain=soil-gaussian_filter(soil,4.5,mode="wrap")
    # Keep each physical pixel square and ease both axes into the stock tile
    # wrap at the boundary of this rectangular crop.
    xx=np.clip((np.arange(w)-(w-25))/24,0,1)[None,:]
    yy=np.clip((np.arange(h)-(h-25))/24,0,1)[:,None]
    xx=xx*xx*(3-2*xx); yy=yy*yy*(3-2*yy)
    top=grain[:h,:w]*(1-xx)+grain[:h,-w:]*xx
    bottom=grain[-h:,:w]*(1-xx)+grain[-h:,-w:]*xx
    grit=top*(1-yy)+bottom*yy
    variance=max(.006,float(grit.std()))
    tex[...,2]=np.clip(.50+grit*(.24/variance),.018,.985)
    stone_faces=detached_stones(images)
    def stamp(mask, pigment, p, channel):
        hh,ww=mask.shape
        yy=(int(p[1])-hh//2+np.arange(hh))%h
        xx=(int(p[0])-ww//2+np.arange(ww))%w
        rr=np.ix_(yy,xx)
        area=mask.astype(float)/255
        tex[...,channel][rr]=np.maximum(tex[...,channel][rr],area)
        tex[...,3][rr]=tex[...,3][rr]*(1-area)+pigment*area
    def transform(values, shape, degrees):
        return np.asarray(Image.fromarray(values).resize(shape,Image.Resampling.LANCZOS).rotate(
            degrees,Image.Resampling.BICUBIC,expand=True))
    islands=rng.uniform([0,0],[w,h],(26,2))
    for i in range(205):
        mask,luma=stone_faces[rng.integers(len(stone_faces))]
        longest=rng.uniform(6.0,21.) if i%6 else rng.uniform(19.,37.)
        scale=longest/max(mask.shape)
        shape=(max(3,round(mask.shape[1]*scale)),max(3,round(mask.shape[0]*scale)))
        angle=rng.uniform(0,360)
        p=(islands[i%len(islands)]+rng.normal([0,0],[13.,18.]) if i%4 else rng.uniform([0,0],[w,h]))
        stamp(transform(mask,shape,angle),transform(luma,shape,angle)/255.,p,0)
    needles=[]
    for i in (1,2,3):
        im=Image.fromarray((255*images[f"needle{i}"][...,0]).astype(np.uint8))
        needles.append(im.crop(im.point(lambda v:255 if v>27 else 0).getbbox()))
    fans=rng.uniform([0,0],[w,h],(48,2))
    for f,p in enumerate(fans):
        angle=rng.uniform(0,360)
        for _ in range(5+(f%9)):
            needle=needles[rng.integers(3)]
            size=rng.uniform(19.,45.)
            a=angle+rng.normal(0,21)
            shape=(max(2,round(size*needle.width/needle.height*1.22)),round(size))
            blade=transform(np.asarray(needle),shape,a)
            blade=np.rint(255*np.clip((blade/255.-.03)*1.46,0,1)).astype(np.uint8)
            stamp(blade,rng.uniform(.79,.97),p+rng.normal(0,8,2),1)
    for _ in range(57):
        size=rng.integers(12,39)
        im=Image.new("L",(int(size+6),13))
        draw=ImageDraw.Draw(im)
        draw.polygon([(1,7),(6,5),(size-5,6),(size+2,3),(size,6),(7,8)],fill=235)
        if size>24:
            draw.line([(size//2,7),(size//2+4,2)],fill=185,width=1)
        blade=np.asarray(im.rotate(rng.uniform(0,360),Image.Resampling.BICUBIC,expand=True))
        stamp(blade,rng.uniform(.06,.16),rng.uniform([0,0],[w,h]),1)
    receipt={"scan_panel_content_bbox":[1816,8,2040,1016],"scan_panel_bbox":[1808,0,2048,1024],
             "resized_litter_panel_bbox":[1024,0,1808,1024],"inspected_stock_faces":len(stone_faces),
             "detached_stone_stamps":205,"straw_fans":len(fans),"twig_stamps":57,
             "stone_coverage":float(np.mean(tex[...,0]>.5)),"wood_and_straw_coverage":float(np.mean(tex[...,1]>.4)),
             "texel_width_m":.005,"gutter_texels":8}
    return np.pad(np.rint(255*tex).astype(np.uint8),((8,8),(8,8),(0,0)),mode="wrap"),receipt
