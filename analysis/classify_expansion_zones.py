#!/usr/bin/env python3
"""Extract private A/B/C expansion-zone candidates from page-8 legend styling.

Color-to-zone mapping is read from the page-8 legend colors. Geometry remains
candidate until a reviewer confirms that each colored source path is the
intended zone boundary. The output is privately source-derived.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import fitz
import ezdxf
from PIL import Image
from shapely.geometry import LineString, Polygon, MultiLineString, mapping

A_GREEN=(0.0,0.7647058964,0.0)
B_GRAY=(0.7254749537,0.7254749537,0.7254749537)
C_RED=(1.0,0.0,0.0)


def rgb_close(color, target, tol=.015):
    return color is not None and max(abs(a-b) for a,b in zip(color,target)) <= tol


def to_display(point, matrix):
    p=fitz.Point(point)*matrix
    return float(p.x),float(p.y)


def cubic(p0,p1,p2,p3,steps=48):
    out=[]
    for i in range(steps+1):
        t=i/steps; u=1-t
        out.append((u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0],
                    u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1]))
    return out


def path_parts(drawing, matrix, tol=.20):
    chains=[];current=[];source_items=[]
    def flush():
        nonlocal current,source_items
        if len(current)>=2:chains.append((current,source_items))
        current=[];source_items=[]
    for ii,item in enumerate(drawing["items"]):
        k=item[0]
        if k=="l":
            seq=[to_display(item[1],matrix),to_display(item[2],matrix)]
        elif k=="c":
            seq=cubic(*[to_display(p,matrix) for p in item[1:5]])
        elif k=="re":
            flush(); r=item[1]
            seq=[to_display(q,matrix) for q in [(r.x0,r.y0),(r.x1,r.y0),(r.x1,r.y1),(r.x0,r.y1),(r.x0,r.y0)]]
            chains.append((seq,[ii]));continue
        elif k=="qu":
            flush();q=item[1]
            seq=[to_display(p,matrix) for p in (q.ul,q.ur,q.lr,q.ll,q.ul)]
            chains.append((seq,[ii]));continue
        else: continue
        if current and math.dist(current[-1],seq[0])>tol:
            flush()
        if not current:current=list(seq);source_items=[ii]
        else:current.extend(seq[1:]);source_items.append(ii)
    flush()
    return chains


def local_registered(p, scale, tx, ty, page7_height):
    # Invert the provisional p7 -> p8 image registration, returning p7 local metres.
    x7=(p[0]-tx)/scale; y7=(p[1]-ty)/scale
    return [x7*scale_data["m_per_pt"],(page7_height-y7)*scale_data["m_per_pt"]]


def run(pdf_path, out, m_per_pt, endpoint_tol=.20):
    global scale_data
    scale_data={"m_per_pt":m_per_pt}
    doc=fitz.open(pdf_path);p7,p8=doc[6],doc[7];matrix=p8.rotation_matrix
    pdf_sha=hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    # Same four-window provisional fit exported by register_pages.py.
    reg_path=out/"registration"/"page-registration.json"
    if not reg_path.exists():reg_path=out.parent/"registration"/"page-registration.json"
    if not reg_path.exists():
        raise FileNotFoundError(f"Run register_pages.py first; missing {reg_path}")
    reg=json.loads(reg_path.read_text(encoding="utf-8"))
    transform=reg["transform_page7_display_to_page8_display"]
    s=transform["scale"];tx,ty=transform["translation_display_pt"]
    features=[];qa=[];svg_groups={"A":[],"B":[],"C":[]}
    doc_dxf=ezdxf.new("R2013");msp=doc_dxf.modelspace()
    for name,color in (("A",A_GREEN),("B",B_GRAY),("C",C_RED)):
        doc_dxf.layers.new(f"EXPANSION_{name}_CANDIDATE")
    drawings=p8.get_drawings()
    for di,d in enumerate(drawings):
        fill=d.get("fill");stroke=d.get("color")
        r=d["rect"]; corners=[to_display(q,matrix) for q in [(r.x0,r.y0),(r.x1,r.y1)]]
        x0=min(q[0] for q in corners);x1=max(q[0] for q in corners);y0=min(q[1] for q in corners);y1=max(q[1] for q in corners)
        area=(x1-x0)*(y1-y0)
        if rgb_close(fill,A_GREEN):zone="A"
        elif rgb_close(fill,B_GRAY) and area>1000:zone="B"
        elif rgb_close(stroke,C_RED) and area>1000:zone="C"
        else:continue
        chains=path_parts(d,matrix,endpoint_tol)
        for part_i,(pts,item_ids) in enumerate(chains):
            closed=len(pts)>=4 and math.dist(pts[0],pts[-1])<=endpoint_tol
            # PDF fill semantics close open subpaths; keep that as a candidate closure.
            area_semantics=fill is not None and len(set(pts[:-1] if closed else pts))>=3
            polygon=Polygon(pts if closed else pts+[pts[0]]) if (closed or area_semantics) else None
            if polygon is not None and polygon.area==0:polygon=None
            if polygon is not None:
                source_polygon=polygon
                geom_kind="Polygon"
                site_coords=[[local_registered(q,s,tx,ty,float(p7.rect.height)) for q in list(polygon.exterior.coords)]]
                site_geom=Polygon(site_coords[0])
                # Candidate fill polygons are reviewed against color legend; keep holes absent unless explicit.
                msp.add_lwpolyline(site_coords[0],close=True,dxfattribs={"layer":f"EXPANSION_{zone}_CANDIDATE"})
                svg_points=pts if closed else pts+[pts[0]]
                d_attr="M "+" L ".join(f"{x:.4f},{y:.4f}" for x,y in svg_points)+" Z"
                fill_attr=f"#{int(color[0]*255):02x}{int(color[1]*255):02x}{int(color[2]*255):02x}" if zone!="C" else "none"
                svg_groups[zone].append(f'<path d="{d_attr}" fill="{fill_attr}" fill-opacity="0.13" stroke="{fill_attr if zone!="C" else "#e33"}" stroke-width="0.9"/>')
            else:
                geom_kind="LineString"
                site_coords=[local_registered(q,s,tx,ty,float(p7.rect.height)) for q in pts]
                site_geom=LineString(site_coords)
                for a,b in zip(site_coords,site_coords[1:]):msp.add_line(a,b,dxfattribs={"layer":f"EXPANSION_{zone}_CANDIDATE"})
                color_svg={"A":"#008000","B":"#b9b9b9","C":"#e33"}[zone]
                d_attr="M "+" L ".join(f"{x:.4f},{y:.4f}" for x,y in pts)
                svg_groups[zone].append(f'<path d="{d_attr}" fill="none" stroke="{color_svg}" stroke-width="0.45"/>')
            ref=f"8:{di}:{part_i}"
            feature={"type":"Feature","id":ref,"geometry":mapping(site_geom),"properties":{
                "source_refs":[f"8:{di}:{ii}" for ii in item_ids],"source_drawing_index":di,"source_item_indices":item_ids,
                "zone_label_candidate":zone,"classification":"candidate","semantic_basis":"page-8 legend color; geometry is not yet human-approved",
                "figure":"4.2.2-2","page8_source_bbox_display_pt":[x0,y0,x1,y1],"endpoint_closed_within_tolerance":closed,
                "polygon_valid":bool(source_polygon.is_valid) if polygon is not None else None,
                "polygon_self_intersection":not bool(source_polygon.is_valid) if polygon is not None else None,
                "coordinate_frame":"page-7 display frame after provisional inverse registration, then page-7 scale to local metres",
                "registration_status":reg["status"],"source_sha256":pdf_sha}}
            features.append(feature)
            qa.append({"feature_id":ref,"zone_candidate":zone,"source_drawing_index":di,"source_item_indices":item_ids,
                       "geometry_type":geom_kind,"source_color_fill":fill,"source_color_stroke":stroke,
                       "source_bbox_display_pt":[x0,y0,x1,y1],"endpoint_closed":closed,
                       "polygon_valid":feature["properties"]["polygon_valid"],"polygon_self_intersection":feature["properties"]["polygon_self_intersection"]})
    doc_dxf.header["$INSUNITS"]=6
    out.mkdir(parents=True,exist_ok=True)
    geo={"type":"FeatureCollection","name":"page-8 expansion zone candidates private","metadata":{
        "source":"C04.PDF page 8 figure 4.2.2-2","source_sha256":pdf_sha,"legend_mapping":{"A":"green fill","B":"gray fill","C":"red boundary/hatch stroke"},
        "registration":reg,"scale_m_per_display_point":m_per_pt,"crs":None,
        "status":"candidate; not accepted engineering geometry; historical EIA proposal only"},"features":features}
    (out/"expansion-zones-ABC.geojson").write_text(json.dumps(geo,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    doc_dxf.saveas(out/"expansion-zones-ABC.dxf")
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="842pt" height="595.22pt" viewBox="0 0 842 595.22"><metadata>PRIVATE; source-derived legend-color candidates only.</metadata>'
    for z in "ABC":svg+=f'<g id="EXPANSION_{z}_CANDIDATE">'+"".join(svg_groups[z])+"</g>"
    svg+="</svg>\n";(out/"expansion-zones-ABC.svg").write_text(svg,encoding="utf-8")
    summary={"schema":"kkl-expansion-zone-candidate-qa-v1","source_sha256":pdf_sha,"registration_status":reg["status"],
             "feature_count_by_zone":{z:sum(f["properties"]["zone_label_candidate"]==z for f in features) for z in "ABC"},
             "closed_polygon_count_by_zone":{z:sum(f["properties"]["zone_label_candidate"]==z and f["geometry"]["type"]=="Polygon" and f["properties"]["endpoint_closed_within_tolerance"] for f in features) for z in "ABC"},
             "invalid_polygon_count":sum(f["properties"]["polygon_valid"] is False for f in features),
             "features":qa,"limitations":["Color mapping follows the printed legend, but each path remains a candidate until human source-image review.",
                "Gray B fill is emitted as multiple candidate pieces; no guessed merger into one perimeter.",
                "Page-7/page-8 transform is an image registration, not survey control.","All areas are historic proposal, not as-built evidence."]}
    (out/"expansion-zones-ABC-qa.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    # Private view of candidate layer overlays on source page 8.
    pix=p8.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False);base=Image.frombytes("RGB",(pix.width,pix.height),pix.samples).convert("RGBA")
    try:
        import cairosvg
        png=cairosvg.svg2png(bytestring=svg.encode(),output_width=pix.width,output_height=pix.height)
        from io import BytesIO
        base.alpha_composite(Image.open(BytesIO(png)).convert("RGBA"))
        base.convert("RGB").save(out/"expansion-zones-ABC-overlay-PRIVATE.png")
    except ImportError:
        pass
    print(json.dumps({"out":str(out),"feature_count_by_zone":summary["feature_count_by_zone"],"closed_polygon_count_by_zone":summary["closed_polygon_count_by_zone"],"invalid_polygon_count":summary["invalid_polygon_count"]},ensure_ascii=False))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--pdf",type=Path,required=True);p.add_argument("--out",type=Path,required=True);p.add_argument("--metres-per-display-point",type=float,required=True);p.add_argument("--endpoint-tolerance-pt",type=float,default=.20)
    a=p.parse_args();run(a.pdf,a.out,a.metres_per_display_point,a.endpoint_tolerance_pt)

if __name__=="__main__":main()
