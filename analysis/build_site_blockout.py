#!/usr/bin/env python3
"""Build an indicative Kinmen Jinning site massing model with Blender.

Input geometries are existing project GeoJSON layers marked indicative. The
result is a conceptual context model for visualization, not an as-built survey.
Run with: blender --background --python analysis/build_site_blockout.py -- ...
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


ORIGIN = (118.3420, 24.4313)
LAT0 = math.radians(ORIGIN[1])
METERS_LON = 111320.0 * math.cos(LAT0)
METERS_LAT = 110540.0


def local(lonlat):
    return ((lonlat[0] - ORIGIN[0]) * METERS_LON,
            (lonlat[1] - ORIGIN[1]) * METERS_LAT)


def mat(name, color, roughness=0.78, metallic=0.0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1.0)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return m


def use_material(obj, material):
    obj.data.materials.append(material)
    return obj


def extruded_polygon(name, ring, height, material, collection, base_z=0.0):
    pts = [local(p) for p in ring[:-1] if len(p) >= 2]
    if len(pts) < 3:
        return None
    n = len(pts)
    verts = [(x, y, base_z) for x, y in pts] + [(x, y, base_z + height) for x, y in pts]
    faces = [tuple(range(n)), tuple(range(n, 2*n))]
    faces.extend((i, (i+1) % n, (i+1) % n + n, i+n) for i in range(n))
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj["geometry_status"] = "indicative footprint; not survey controlled"
    return obj


def cylinder(name, x, y, radius, depth, z, material, collection, vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                        location=(x, y, z + depth/2))
    obj = bpy.context.object
    obj.name = name
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    collection.objects.link(obj)
    use_material(obj, material)
    return obj


def bottle(name, x, y, height, material, collection):
    profile = [(0.0,0.0),(0.44,0.0),(0.50,0.08),(0.50,0.40),(0.43,0.55),
               (0.30,0.62),(0.22,0.74),(0.17,0.92),(0.15,0.97),
               (0.19,1.0),(0.19,1.08),(0.0,1.08)]
    verts, faces = [], []
    segments = 24
    for r, zf in profile:
        for i in range(segments):
            a = 2*math.pi*i/segments
            verts.append((x+r*math.cos(a), y+r*math.sin(a), zf*height))
    for j in range(len(profile)-1):
        for i in range(segments):
            a=j*segments+i; b=j*segments+(i+1)%segments
            faces.append((a,b,b+segments,a+segments))
    faces.append(tuple(range((len(profile)-1)*segments,len(profile)*segments)))
    mesh=bpy.data.meshes.new(name+"_mesh"); mesh.from_pydata(verts,[],faces); mesh.materials.append(material); mesh.update()
    obj=bpy.data.objects.new(name,mesh); collection.objects.link(obj)
    obj["geometry_status"]="stylized landmark massing"
    return obj


def curve_line(name, coords, bevel, z, material, collection, cyclic=False):
    data=bpy.data.curves.new(name+"_curve","CURVE"); data.dimensions="3D"; data.resolution_u=16; data.bevel_depth=bevel; data.bevel_resolution=3
    spline=data.splines.new("POLY"); spline.points.add(len(coords)-1)
    for p,xy in zip(spline.points,coords): p.co=(xy[0],xy[1],z,1)
    spline.use_cyclic_u=cyclic
    obj=bpy.data.objects.new(name,data); collection.objects.link(obj); obj.data.materials.append(material)
    return obj


def line_geometry(geometry):
    kind=geometry.get("type"); coords=geometry.get("coordinates",[])
    if kind=="LineString": return [coords]
    if kind=="MultiLineString": return coords
    if kind=="GeometryCollection":
        return [line for g in geometry.get("geometries",[]) for line in line_geometry(g)]
    return []


def main():
    argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--visitor",required=True,type=Path)
    ap.add_argument("--buildings",required=True,type=Path)
    ap.add_argument("--roads",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--preview",type=Path)
    a=ap.parse_args(argv)

    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
    for c in list(bpy.data.collections):
        if c.name!="Collection": bpy.data.collections.remove(c)
    scene=bpy.context.scene
    root=scene.collection
    collections={}
    for name in ("00_Ground","01_Roads","02_Production_Buildings","03_Visitor_Buildings","04_Landscape_Water","05_Landmarks"):
        col=bpy.data.collections.new(name); root.children.link(col); collections[name]=col

    materials={
        "ground":mat("Ground | neutral",(0.46,0.50,0.45)),
        "road":mat("Road | asphalt",(0.20,0.22,0.23)),
        "production":mat("Production buildings | warm gray",(0.66,0.63,0.57)),
        "visitor":mat("Visitor buildings | pale brick",(0.68,0.46,0.35)),
        "museum":mat("History building | brick",(0.58,0.32,0.25)),
        "grass":mat("Landscape | green",(0.27,0.43,0.24)),
        "water":mat("Water | blue",(0.12,0.46,0.62),0.22,0.12),
        "stone":mat("Fountain stone | light gray",(0.62,0.63,0.60)),
        "bottle":mat("Bottle landmark | ceramic white",(0.90,0.88,0.78),0.32),
        "cap":mat("Bottle cap | gold",(0.77,0.52,0.12),0.3,0.3),
    }

    visitor=json.loads(a.visitor.read_text(encoding="utf-8"))
    buildings=json.loads(a.buildings.read_text(encoding="utf-8"))
    roads=json.loads(a.roads.read_text(encoding="utf-8"))
    allpts=[]
    focuspts=[]

    for f in buildings.get("features",[]):
        g=f["geometry"]; props=f.get("properties",{}); name=props.get("name","Building")
        if g["type"]!="Polygon": continue
        ring=g["coordinates"][0]
        pts=[local(p) for p in ring]; allpts.extend(pts); focuspts.extend(pts)
        h=float(props.get("height_m_estimate",10))
        extruded_polygon("Production | "+name,ring,h,materials["production"],collections["02_Production_Buildings"])

    for f in visitor.get("features",[]):
        g=f["geometry"]; props=f.get("properties",{}); name=props.get("name","Facility")
        if g["type"]=="Polygon":
            ring=g["coordinates"][0]; pts=[local(p) for p in ring]; allpts.extend(pts); focuspts.extend(pts)
            category=props.get("category","")
            m=materials["museum"] if category in ("museum","history") or name=="廠史館" else materials["visitor"]
            extruded_polygon("Visitor | "+name,ring,float(props.get("height_m_estimate",8)),m,collections["03_Visitor_Buildings"])
        elif g["type"]=="Point":
            x,y=local(g["coordinates"]); allpts.append((x,y)); focuspts.append((x,y))
            category=props.get("category","")
            w=float(props.get("width_m_estimate",20)); d=float(props.get("depth_m_estimate",w))
            if category=="fountain":
                cylinder(name+" | stone rim",x,y,w/2,1.0,0.0,materials["stone"],collections["04_Landscape_Water"])
                cylinder(name+" | water",x,y,w/2-1.4,0.12,0.72,materials["water"],collections["04_Landscape_Water"])
            elif category=="spring":
                cylinder(name+" | basin",x,y,w/2,0.8,0.0,materials["stone"],collections["04_Landscape_Water"])
                cylinder(name+" | water",x,y,w/2-1.2,0.1,0.62,materials["water"],collections["04_Landscape_Water"])
            elif category=="bottle_park":
                bpy.ops.mesh.primitive_uv_sphere_add(segments=40,ring_count=16,radius=1,location=(x,y,0.7))
                obj=bpy.context.object; obj.name="Landscape mound | 酒瓶公園"; obj.scale=(w/2,d/2,1.4)
                for c in list(obj.users_collection):c.objects.unlink(obj)
                collections["04_Landscape_Water"].objects.link(obj); use_material(obj,materials["grass"])
                bottle("Park bottle sculpture",x,y,8.0,materials["bottle"],collections["05_Landmarks"])
            elif category=="bottle_landmark":
                bottle("Bottle landmark A",x-5,y,15.0,materials["bottle"],collections["05_Landmarks"])
                bottle("Bottle landmark B",x+5,y,15.0,materials["bottle"],collections["05_Landmarks"])
                cylinder("Entry sign plinth",x,y,9,1.2,0,materials["stone"],collections["05_Landmarks"])

    # The S-shaped circulation is a conceptual connector between the two water features.
    pts={f.get("properties",{}).get("name"):local(f["geometry"]["coordinates"])
         for f in visitor.get("features",[]) if f["geometry"]["type"]=="Point"}
    if "迎賓水池" in pts and "寶月新泉" in pts:
        start=pts["迎賓水池"]; end=pts["寶月新泉"]
        midx=(start[0]+end[0])/2; midy=(start[1]+end[1])/2
        path=[start,(start[0]-7,start[1]+12),(midx+7,midy+10),(end[0]+7,end[1]-10),end]
        curve_line("Curved pedestrian path | 曲水流觴 (concept)",path,2.0,0.18,materials["stone"],collections["04_Landscape_Water"])

    for f in roads.get("features",[]):
        props=f.get("properties",{}); highway=props.get("highway","")
        width={"secondary":8.0,"tertiary":6.0,"service":4.0,"residential":5.0,"track":3.0}.get(highway,3.5)
        for coords in line_geometry(f["geometry"]):
            xy=[local(p) for p in coords]
            if len(xy)<2: continue
            allpts.extend(xy)
            curve_line("Road | "+props.get("name",highway or "OSM"),xy,width/2,0.06,materials["road"],collections["01_Roads"])

    if not allpts: raise RuntimeError("No geometries were loaded")
    xmin=min(p[0] for p in allpts); xmax=max(p[0] for p in allpts)
    ymin=min(p[1] for p in allpts); ymax=max(p[1] for p in allpts)
    cx=(xmin+xmax)/2; cy=(ymin+ymax)/2
    fxmin=min(p[0] for p in focuspts); fxmax=max(p[0] for p in focuspts)
    fymin=min(p[1] for p in focuspts); fymax=max(p[1] for p in focuspts)
    fcx=(fxmin+fxmax)/2; fcy=(fymin+fymax)/2
    # Local tangent-plane frame: origin is retained in GLB metadata sidecar.
    ground=mesh=None
    bpy.ops.mesh.primitive_plane_add(size=1,location=(fcx,fcy,-0.35))
    ground=bpy.context.object; ground.name="Site ground | flat context"
    ground.scale=((fxmax-fxmin)+300,(fymax-fymin)+300,1)
    for c in list(ground.users_collection):c.objects.unlink(ground)
    collections["00_Ground"].objects.link(ground); use_material(ground,materials["ground"])

    # Studio light and camera are for the preview render; GLB stores only model geometry.
    bpy.ops.object.light_add(type="AREA",location=(fcx-180,fcy-220,330)); light=bpy.context.object;light.name="Preview key light";light.data.energy=180000;light.data.shape="DISK";light.data.size=320
    light.rotation_euler=(math.radians(18),0,math.radians(-35))
    bpy.ops.object.light_add(type="SUN",location=(fcx+100,fcy-100,350)); sun=bpy.context.object;sun.name="Preview fill light";sun.data.energy=2.2
    sun.rotation_euler=(math.radians(20),math.radians(-25),math.radians(-25))
    bpy.ops.object.camera_add(location=(fcx-180,fcy-220,250)); camera=bpy.context.object;camera.name="Preview camera";camera.data.type="ORTHO";camera.data.ortho_scale=max(fxmax-fxmin,fymax-fymin)*1.35
    direction=Vector((fcx,fcy,0))-camera.location;camera.rotation_euler=direction.to_track_quat("-Z","Y").to_euler()
    scene.camera=camera
    scene.render.engine="BLENDER_EEVEE_NEXT";scene.render.resolution_x=1280;scene.render.resolution_y=900;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG";scene.render.film_transparent=False
    scene.world.color=(0.72,0.76,0.8)
    scene.view_settings.view_transform="Standard";scene.view_settings.look="Medium High Contrast";scene.view_settings.exposure=0.7
    if a.preview:
        a.preview.parent.mkdir(parents=True,exist_ok=True);scene.render.filepath=str(a.preview);bpy.ops.render.render(write_still=True)
    # Camera/lights are excluded from the interoperable model.
    bpy.ops.object.select_all(action="DESELECT")
    for obj in scene.objects:
        if obj.type in {"MESH","CURVE"}:obj.select_set(True)
    bpy.context.view_layer.objects.active=next((o for o in scene.objects if o.type=="MESH"),None)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(a.out),export_format="GLB",use_selection=True,export_apply=True)
    sidecar={"title":"金門酒廠金寧廠 3D 概念方塊模型","status":"visualization blockout; indicative-only, not as-built or survey controlled",
             "local_coordinate_frame":{"origin_wgs84":list(ORIGIN),"x":"east metres","y":"north metres","z":"estimated metres"},
             "sources":["data/visitor-zone.geojson","data/existing-buildings.geojson","data/roads-osm.geojson"],
             "limitations":["Flat ground; no terrain survey.","Building footprints, heights, and visitor amenity positions are indicative.","Water features, bottle sculptures, and 曲水流觴 path are simplified massing.","Historical EIA plan is not proof that all modeled facilities are currently built."]}
    Path(str(a.out)+".json").write_text(json.dumps(sidecar,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"glb":str(a.out),"preview":str(a.preview) if a.preview else None,"buildings":len(buildings.get('features',[])),"visitor_features":len(visitor.get('features',[])),"road_features":len(roads.get('features',[])),"bounds_m":[xmin,ymin,xmax,ymax]},ensure_ascii=False))


if __name__=="__main__":main()
