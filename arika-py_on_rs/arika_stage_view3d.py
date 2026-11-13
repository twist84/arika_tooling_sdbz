"""Dependency-free orthographic stage geometry preparation for the Tk viewport."""
import math
from arika_models import identity, quaternion
from arika_backend import matrix_local, matrix_multiply


def project(point,yaw,pitch):
    x,y,z=point;cx=math.cos(yaw);sx=math.sin(yaw);cp=math.cos(pitch);sp=math.sin(pitch)
    right=x*cx+z*sx;depth=-x*sx+z*cx
    return right,y*cp-depth*sp,y*sp+depth*cp


def prepare(scene,model,hit=None,include_templates=False,limit=None):
    allowed=set();todo=scene['roots'][:] if include_templates else [scene['stage_root']]
    while todo:
        i=todo.pop();allowed.add(i);todo.extend(scene['nodes'][i]['children'])
    meshes={m['name']:m for m in model['meshes']} if model else {};objects={o['name']:o for o in hit['objects']} if hit else {}
    matrices=[];points=[];triangles=[];lines=[];candidates=[];total=0
    def transform(matrix,p):return tuple(sum(matrix[a][j]*p[j] for j in range(3))+matrix[a][3] for a in range(3))
    for node in scene['nodes']:
        local=identity() if 'translation'not in node else matrix_local(node['translation'],quaternion([math.degrees(v) for v in node['rotation_radians']]),node['scale'])
        matrix=local if node['parent']<0 else matrix_multiply(matrices[node['parent']],local);matrices.append(matrix)
        if node['index']not in allowed:continue
        points.append((node['index'],transform(matrix,(0,0,0)),node['kind']))
        mesh=meshes.get(node['name']) if node['kind']==2 else None
        if mesh:
            faces=[face for part in mesh['primitives'] for face in part['triangles']]
            candidates.append((node['index'],matrix,mesh,faces));total+=len(faces)
        for ref in node['references']:
            obj=objects.get(ref['name'])
            if not obj:continue
            for poly in hit['polygons'][obj['first_polygon']:obj['first_polygon']+obj['polygon_count']]:
                if len(lines)>=5000:break
                first=poly['first_vertex'];vertices=hit['vertices'][first:first+poly['vertex_count']]
                line=[transform(matrix,v[:3]) for v in vertices];lines.append(line+[line[0]])
    stride=max(1,math.ceil(total/limit)) if limit else 1;counter=0
    for index,matrix,mesh,faces in candidates:
        transformed={}
        def vertex(v):
            if v not in transformed:transformed[v]=transform(matrix,mesh['vertices'][v]['position'])
            return transformed[v]
        for face in faces:
            keep=counter%stride==0;counter+=1
            if keep:triangles.append((index,[vertex(v) for v in face]))
    return dict(points=points,triangles=triangles,lines=lines,total_triangles=total,sampled=stride>1)


def render_image(data,width,height,yaw,pitch,scale,offset,selected=None,collision=False):
    from PIL import Image,ImageDraw
    image=Image.new('RGB',(max(1,width),max(1,height)),(17,28,38));draw=ImageDraw.Draw(image)
    cache={};faces=[]
    def projected(p):
        if p not in cache:
            x,y,z=project(p,yaw,pitch);cache[p]=(x*scale+offset[0],-y*scale+offset[1],z)
        return cache[p]
    if '_colors'not in data:
        colors=[]
        for index,triangle in data['triangles']:
            a,b,c=triangle;u=[b[j]-a[j] for j in range(3)];v=[c[j]-a[j] for j in range(3)]
            n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
            length=math.sqrt(sum(x*x for x in n));shade=.35+.6*abs((n[0]*.3+n[1]*.8+n[2]*.4)/max(length,1e-12))
            colors.append(tuple(min(255,int(channel*shade)) for channel in (95,155,195)))
        data['_colors']=colors
    for (index,triangle),color in zip(data['triangles'],data['_colors']):
        view=[projected(p) for p in triangle]
        if max(p[0] for p in view)<0 or min(p[0] for p in view)>=width or max(p[1] for p in view)<0 or min(p[1] for p in view)>=height:continue
        faces.append((sum(p[2] for p in view),[(p[0],p[1]) for p in view],(255,202,102) if index==selected else color))
    faces.sort(key=lambda f:f[0])
    for depth,points,color in faces:draw.polygon(points,fill=color)
    if collision:
        for line in data['lines']:draw.line([projected(p)[:2] for p in line],fill=(75,175,128),width=1)
    return image
