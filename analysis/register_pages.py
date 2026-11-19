#!/usr/bin/env python3
"""Privately register the shared historic facility region on C04 PDF pages 7 and 8."""
import argparse
import json
from pathlib import Path

import fitz
import numpy as np
from PIL import Image
from scipy.ndimage import sobel, zoom
from scipy.signal import fftconvolve

# Four manually selected windows within the common existing-plant map area.
# Coordinates are PDF display-page points (after page.rotation_matrix).
CONTROL_WINDOWS = [
    [225, 255, 300, 325],
    [225, 320, 300, 390],
    [295, 300, 370, 380],
    [350, 250, 430, 330],
]


def edge_map(gray):
    grad = np.hypot(sobel(gray.astype(float), axis=0), sobel(gray.astype(float), axis=1))
    return (grad > 120).astype(float)


def best_match(target, template):
    corr = fftconvolve(target, template[::-1, ::-1], mode="valid")
    iy, ix = np.unravel_index(np.argmax(corr), corr.shape)
    # Parabolic peak interpolation for subpixel offsets in the rendered image.
    def subpixel(a, b, c):
        den = a - 2 * b + c
        return 0.5 * (a - c) / den if den else 0.0
    dy = subpixel(corr[iy - 1, ix], corr[iy, ix], corr[iy + 1, ix]) if 0 < iy < corr.shape[0]-1 else 0
    dx = subpixel(corr[iy, ix - 1], corr[iy, ix], corr[iy, ix + 1]) if 0 < ix < corr.shape[1]-1 else 0
    return (iy + dy, ix + dx), float(corr[iy, ix] / max(template.sum(), 1))


def register(pdf_path: Path, out: Path, dpi=144, metres_per_display_point=None):
    doc = fitz.open(pdf_path)
    p7, p8 = doc[6], doc[7]
    factor = dpi / 72
    pix7 = p7.get_pixmap(matrix=fitz.Matrix(factor, factor), alpha=False)
    im7 = Image.frombytes("RGB", (pix7.width, pix7.height), pix7.samples).convert("L")
    im8pix = p8.get_pixmap(matrix=fitz.Matrix(factor, factor), alpha=False)
    im8 = Image.frombytes("RGB", (im8pix.width, im8pix.height), im8pix.samples).convert("L")
    edges7, edges8 = edge_map(np.array(im7)), edge_map(np.array(im8))
    # Page 8 target extent covers the shared existing plant, excluding most labels/legend.
    tx0, ty0, tx1, ty1 = 220, 250, 570, 470
    px_per_pt = int(round(factor))
    target = edges8[ty0*px_per_pt:ty1*px_per_pt, tx0*px_per_pt:tx1*px_per_pt]
    best = None
    # Discrete scale search; no rotation is assumed because page display axes agree.
    for scale in np.arange(0.805, 0.826, 0.001):
        matches=[]; scores=[]
        for x0,y0,x1,y1 in CONTROL_WINDOWS:
            tpl=edges7[round(y0*factor):round(y1*factor),round(x0*factor):round(x1*factor)]
            resized=zoom(tpl,scale,order=0)
            (iy,ix),score=best_match(target,resized)
            px=tx0+(ix+resized.shape[1]/2)/factor
            py=ty0+(iy+resized.shape[0]/2)/factor
            sx=(x0+x1)/2; sy=(y0+y1)/2
            matches.append((sx,sy,px,py)); scores.append(score)
        # Fit a common translation for each candidate scale and minimize RMS residual.
        offsets=np.array([(px-scale*sx,py-scale*sy) for sx,sy,px,py in matches])
        translation=offsets.mean(axis=0)
        residuals=offsets-translation
        rmse=float(np.sqrt(np.mean(np.sum(residuals**2,axis=1))))
        candidate=(rmse,float(scale),translation,matches,scores,residuals)
        if best is None or candidate[0]<best[0]: best=candidate
    rmse,scale,translation,matches,scores,residuals=best
    points=[]
    for i,((sx,sy,tx,ty),score,res) in enumerate(zip(matches,scores,residuals),1):
        points.append({"id":f"window-{i}","method":"manual overlapping-window selection + edge-template correlation",
                       "page7_window_center_display_pt":[sx,sy],"matched_page8_window_center_display_pt":[tx,ty],
                       "match_score_overlap_fraction":score,"residual_vector_display_pt":[float(res[0]),float(res[1])],
                       "residual_magnitude_display_pt":float(np.linalg.norm(res))})
    report={"schema":"kkl-p7-p8-registration-v1","status":"PROVISIONAL_IMAGE_REGISTRATION_REVIEW_REQUIRED",
            "pages":{"source":7,"target":8},"control_points":points,
            "transform_page7_display_to_page8_display":{"type":"isotropic_scale_plus_translation","matrix_3x3":[[scale,0,float(translation[0])],[0,scale,float(translation[1])],[0,0,1]],
                 "scale":scale,"rotation_degrees":0,"translation_display_pt":[float(translation[0]),float(translation[1])]},
            "residuals":{"control_point_count":len(points),"rms_display_pt":rmse,
                         "rms_target_page8_m_using_page7_scale":rmse*metres_per_display_point if metres_per_display_point else None,
                         "max_display_pt":max(p["residual_magnitude_display_pt"] for p in points)},
            "render":{"dpi":dpi,"edge_threshold":120,"search_scale_range":[0.805,0.825],"search_step":0.001,
                       "page8_search_region_display_pt":[tx0,ty0,tx1,ty1],"control_windows_display_pt":CONTROL_WINDOWS},
            "limitations":["Image-registration controls are manually selected patches, not surveyed monuments or engineering datum.",
                           "Transform aligns shared historical drawing content only; it does not prove as-built status or legal/site coordinates.",
                           "Page 8 expansion boundaries are historical plans; do not treat them as completed facilities."]}
    out.mkdir(parents=True,exist_ok=True)
    (out/"page-registration.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    # Private review overlay: p7 source page resampled onto the p8 page grid.
    pix7=p7.get_pixmap(matrix=fitz.Matrix(factor,factor),alpha=False)
    src=Image.frombytes("RGB",(pix7.width,pix7.height),pix7.samples).convert("L")
    ink=Image.fromarray(np.where(np.array(src)<150,180,0).astype("uint8"))
    overlay=Image.new("RGBA",src.size,(0,145,255,0));overlay.putalpha(ink)
    inv=1/scale; tx,ty=translation
    warped=overlay.transform(im8.size,Image.Transform.AFFINE,(inv,0,-factor*tx/scale,0,inv,-factor*ty/scale),resample=Image.Resampling.BILINEAR)
    base=Image.fromarray(np.array(im8)).convert("RGBA");base.alpha_composite(warped)
    base.convert("RGB").save(out/"p7-registered-over-p8-full-PRIVATE.png")
    # Restrict review view to the shared existing-plant portion; page titles and legends are not controls.
    crop=[240,240,590,470]
    base.crop(tuple(round(v*factor) for v in crop)).convert("RGB").save(out/"p7-registered-over-p8-PRIVATE.png")
    report["overlay_crop_page8_display_pt"]=crop
    (out/"page-registration.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--pdf",type=Path,required=True);p.add_argument("--out",type=Path,required=True);p.add_argument("--dpi",type=int,default=144)
    p.add_argument("--metres-per-display-point",type=float,help="Private measured page-scale value; used only to express residuals in metres")
    a=p.parse_args(); print(json.dumps(register(a.pdf,a.out,a.dpi,a.metres_per_display_point),ensure_ascii=False,indent=2))

if __name__=="__main__":main()
