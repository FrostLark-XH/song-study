"""Portable scene graph for lyric PPTs: shared objects, deterministic states.

progress is text-relative 0..1, never an inferred audio time. All drawing is
specified in data.json; no song names, stock scenes or automatic decorations.
The exported painting is raster; native lyric text remains editable above it.
"""
from io import BytesIO
import math
import random
import re

from PIL import Image, ImageDraw

TRANSFORMS = {'x', 'y', 'scale', 'rotation', 'opacity'}
KINDS = {'polygon', 'line', 'ellipse', 'rect', 'wash'}
MODES = {'continue', 'match', 'cut', 'return'}


def number(value, label, lo=-10000, hi=10000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f'{label}: finite number in {lo}..{hi} required')
    return value


def color(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9A-Fa-f]{6}', value):
        raise ValueError('Scene color must be six hex digits')
    return tuple(int(value[i:i+2],16) for i in (0,2,4))


def rectangle(value, label):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f'{label}: [x,y,width,height] required')
    x,y,w,h = [number(v,label,0,1) for v in value]
    if w <= 0 or h <= 0 or x+w > 1.000001 or y+h > 1.000001:
        raise ValueError(f'{label}: rectangle must fit canvas')
    return x,y,w,h


def layer_state(layer, progress, override=None):
    state = {'x':0,'y':0,'scale':1,'rotation':0,'opacity':1}
    state.update({k:layer[k] for k in TRANSFORMS if k in layer})
    frames = layer.get('frames', [])
    for key in TRANSFORMS:
        track = [(f['at'],f[key]) for f in frames if key in f]
        if not track:continue
        if progress <= track[0][0]:state[key]=track[0][1];continue
        if progress >= track[-1][0]:state[key]=track[-1][1];continue
        for (a,va),(b,vb) in zip(track,track[1:]):
            if a <= progress <= b:
                u=(progress-a)/(b-a)
                state[key]=va+(vb-va)*u
                break
    state.update(override or {})
    return state


def snapshot(assets, spec):
    scene = assets['scene_library'][spec['id']]
    overrides = spec.get('state', {})
    return [{'id':l['id'],'object':l['object'],
             **layer_state(l,spec['progress'],overrides.get(l['id']))}
            for l in scene['layers']]


def smooth_polygon(points):
    """Closed Catmull-Rom contour; keep authored corners when smooth is absent."""
    result=[];n=len(points)
    for i in range(n):
        p0,p1,p2,p3=[points[j%n] for j in (i-1,i,i+1,i+2)]
        for k in range(10):
            t=k/10
            result.append(tuple(.5*((2*p1[a])+(-p0[a]+p2[a])*t+(2*p0[a]-5*p1[a]+4*p2[a]-p3[a])*t*t+(-p0[a]+3*p1[a]-3*p2[a]+p3[a])*t*t*t) for a in (0,1)))
    return result


def validate_scene_plan(data):
    assets=data.get('visual_assets') or {}
    objects=assets.get('objects')
    scenes=assets.get('scene_library')
    if not isinstance(objects,dict) or not objects or not isinstance(scenes,dict) or not scenes:
        raise ValueError('v4 requires shared objects and scene_library')
    for oid,obj in objects.items():
        if not isinstance(oid,str) or not oid or not isinstance(obj,dict) or not obj.get('meaning'):
            raise ValueError('Scene object requires an ID and meaning')
        primitives=obj.get('primitives')
        if not isinstance(primitives,list) or not primitives or len(primitives)>300:
            raise ValueError(f'{oid}: 1..300 primitives required')
        for p in primitives:
            if not isinstance(p,dict) or p.get('kind') not in KINDS:
                raise ValueError(f'{oid}: unknown drawing primitive')
            if p['kind'] in ('rect','ellipse'):
                box=p.get('box')
                if not isinstance(box,list) or len(box)!=4:raise ValueError(f'{oid}: box required')
                for v in box:number(v,'box')
                if box[2]<=box[0] or box[3]<=box[1]:raise ValueError(f'{oid}: empty box')
            else:
                pts=p.get('points')
                minimum=2 if p['kind']=='line' else 3
                if not isinstance(pts,list) or len(pts)<minimum or len(pts)>2000:
                    raise ValueError(f'{oid}: insufficient points')
                for point in pts:
                    if not isinstance(point,list) or len(point)!=2:raise ValueError(f'{oid}: point must be [x,y]')
                    for v in point:number(v,'point')
            if not p.get('fill') and not p.get('stroke'):raise ValueError(f'{oid}: invisible primitive')
            for key in ('fill','stroke'):
                if p.get(key):color(p[key])
            if p['kind']=='line' and not p.get('stroke'):raise ValueError(f'{oid}: line needs stroke')
            number(p.get('width',2),'stroke width',.1,60)
            number(p.get('opacity',1),'primitive opacity',0,1)
            if 'smooth' in p and not isinstance(p['smooth'],bool):raise ValueError('smooth must be boolean')
            if 'seed' in p and not isinstance(p['seed'],int):raise ValueError('wash seed must be integer')
    for sid,scene in scenes.items():
        if not isinstance(sid,str) or not sid or not isinstance(scene,dict) or not scene.get('meaning'):
            raise ValueError('Scene requires an ID and meaning')
        layers=scene.get('layers')
        if not isinstance(layers,list) or not layers or len(layers)>100:raise ValueError(f'{sid}: layers required')
        ids=set()
        for layer in layers:
            if not isinstance(layer,dict) or not isinstance(layer.get('id'),str) or not layer['id'] or layer['id'] in ids:
                raise ValueError(f'{sid}: unique layer IDs required')
            ids.add(layer['id'])
            if layer.get('object') not in objects:raise ValueError(f'{sid}: unknown object')
            frames=layer.get('frames',[])
            if not isinstance(frames,list):raise ValueError('frames must be a list')
            last=-1
            for frame in frames:
                if not isinstance(frame,dict):raise ValueError('frame must be an object')
                at=number(frame.get('at'),'frame.at',0,1)
                if at<=last:raise ValueError('frame positions must increase')
                last=at
                if set(frame)-TRANSFORMS-{'at'}:raise ValueError('Unsupported frame property')
            for block in [layer,*frames]:
                for key in TRANSFORMS:
                    if key not in block:continue
                    lo,hi=(0,1) if key=='opacity' else (.01,8) if key=='scale' else (-10000,10000)
                    number(block[key],key,lo,hi)
    pages=assets.get('pages',[])
    cover=data.get('visual_profile',{}).get('cover',{})
    previous={'cover':cover}
    for page in [cover,*pages]:
        name=page.get('id','cover')
        spec=page.get('scene')
        if not isinstance(spec,dict) or spec.get('id') not in scenes:raise ValueError(f'{name}: known scene required')
        number(spec.get('progress'),'scene.progress',0,1)
        rectangle(spec.get('viewport'),'scene.viewport')
        rectangle(page.get('text_zone'),'text_zone')
        camera=spec.get('camera',[500,500,1])
        if not isinstance(camera,list) or len(camera)!=3:raise ValueError('camera requires [x,y,zoom]')
        number(camera[0],'camera.x');number(camera[1],'camera.y');number(camera[2],'camera.zoom',.2,4)
        overrides=spec.get('state',{})
        if not isinstance(overrides,dict):raise ValueError('scene.state must be an object')
        valid={l['id'] for l in scenes[spec['id']]['layers']}
        for lid,state in overrides.items():
            if lid not in valid or not isinstance(state,dict) or set(state)-TRANSFORMS:raise ValueError('Unknown layer/state property')
            for k,v in state.items():number(v,k,0 if k=='opacity' else .01 if k=='scale' else -10000,1 if k=='opacity' else 8 if k=='scale' else 10000)
        if page.get('surface') is not None:color(page['surface'])
        # When painting and reading regions overlap, an explicit opaque surface
        # protects the lyric area. It is included in the generated background.
        a,b=rectangle(spec['viewport'],'scene.viewport'),rectangle(page['text_zone'],'text_zone')
        overlap=min(a[0]+a[2],b[0]+b[2])>max(a[0],b[0]) and min(a[1]+a[3],b[1]+b[3])>max(a[1],b[1])
        if overlap and page.get('surface')!=page['background']:
            raise ValueError(f'{name}: overlapping art needs surface equal to background')
        if page is not cover:
            for field in ('visual_event','lyric_basis'):
                if not isinstance(page.get(field),str) or not page[field].strip():raise ValueError(f'{name}: {field} required')
            link=page.get('visual_link')
            if not isinstance(link,dict) or link.get('mode') not in MODES or link.get('from') not in previous:
                raise ValueError(f'{name}: visual_link must reference an earlier page or cover')
            if not isinstance(link.get('change'),str) or not link['change'].strip():raise ValueError('visual_link.change required')
            if link['mode']!='cut':
                anchor=link.get('anchor')
                if not isinstance(anchor,str):raise ValueError('shared anchor object required')
                for p in (page,previous[link['from']]):
                    if not any(s['object']==anchor and s['opacity']>.01 for s in snapshot(assets,p['scene'])):
                        raise ValueError(f'{name}: anchor must be present and visible in both scene states')
            previous[name]=page
    return True


def render_scene(assets, page, size=(1920,1080)):
    """Render exactly one state. Seeded washes are independent of export order."""
    width,height=size
    canvas=Image.new('RGBA',size,(*color(page['background']),255))
    spec=page['scene']; vx,vy,vw,vh=spec['viewport']
    box=(round(vx*width),round(vy*height),round((vx+vw)*width),round((vy+vh)*height))
    pw,ph=box[2]-box[0],box[3]-box[1]
    panel=Image.new('RGBA',(pw,ph),(0,0,0,0))
    cx,cy,zoom=spec.get('camera',[500,500,1])
    ratio=min(pw,ph)/1000*zoom
    for state in snapshot(assets,spec):
        obj=assets['objects'][state['object']]
        angle=math.radians(state['rotation']);co,si=math.cos(angle),math.sin(angle)
        scale=state['scale']
        def transform(point):
            x,y=point
            x,y=(x*co-y*si)*scale+state['x'],(x*si+y*co)*scale+state['y']
            return ((x-cx)*ratio+pw/2,(y-cy)*ratio+ph/2)
        for primitive in obj['primitives']:
            layer=Image.new('RGBA',(pw,ph),(0,0,0,0));draw=ImageDraw.Draw(layer)
            kind=primitive['kind'];opacity=primitive.get('opacity',1)*state['opacity']
            if opacity<=0:continue
            rgba=lambda c:(*color(c),round(opacity*255))
            fill=rgba(primitive['fill']) if primitive.get('fill') else None
            stroke=rgba(primitive['stroke']) if primitive.get('stroke') else None
            sw=max(1,round(primitive.get('width',2)*ratio*scale))
            if kind in ('rect','ellipse'):
                x0,y0,x1,y1=primitive['box']
                if kind=='ellipse':
                    pts=[transform(((x0+x1)/2+(x1-x0)/2*math.cos(a*math.tau/80),(y0+y1)/2+(y1-y0)/2*math.sin(a*math.tau/80))) for a in range(80)]
                else:pts=[transform(p) for p in ((x0,y0),(x1,y0),(x1,y1),(x0,y1))]
            else:
                source=primitive['points']
                if primitive.get('smooth') and kind!='line':source=smooth_polygon(source)
                pts=[transform(p) for p in source]
            if kind=='line':draw.line(pts,fill=stroke,width=sw,joint='curve')
            else:
                if fill:draw.polygon(pts,fill=fill)
                if stroke:draw.line(pts+[pts[0]],fill=stroke,width=sw,joint='curve')
            if kind=='wash' and fill:
                # Granulation belongs to this pigment polygon, not the canvas.
                mask=layer.getchannel('A'); rng=random.Random(primitive.get('seed',0))
                flecks=Image.new('RGBA',(pw,ph),(0,0,0,0));fd=ImageDraw.Draw(flecks)
                xs,ys=zip(*pts)
                for _ in range(1100):
                    x=rng.uniform(min(xs),max(xs));y=rng.uniform(min(ys),max(ys));radius=rng.uniform(.25,1.25)*max(1,ratio)
                    fd.ellipse((x-radius,y-radius,x+radius,y+radius),fill=(255,255,255,rng.randint(3,18)))
                flecks.putalpha(Image.composite(flecks.getchannel('A'),Image.new('L',(pw,ph),0),mask))
                layer=Image.alpha_composite(layer,flecks)
            panel=Image.alpha_composite(panel,layer)
    canvas.alpha_composite(panel,(box[0],box[1]))
    if page.get('surface'):
        x,y,w,h=page['text_zone']
        # Preserve clear space around ruby as well as the base text.
        pad=12
        ImageDraw.Draw(canvas).rectangle((x*width-pad,y*height-pad,(x+w)*width+pad,(y+h)*height+pad),fill=(*color(page['surface']),255))
    return canvas.convert('RGB')


def add_scene(slide, assets, page, width_pt, height_pt):
    from pptx.util import Pt
    buf=BytesIO();render_scene(assets,page).save(buf,format='PNG');buf.seek(0)
    slide.shapes.add_picture(buf,0,0,Pt(width_pt),Pt(height_pt)).name='background'
