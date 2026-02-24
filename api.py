"""FastAPI backend for Parametric Staircase Studio.
Runs build123d server-side and serves self-contained GLB files to the Three.js frontend.
Supports both Volumetric and Structural model modes with per-category materials.
"""
import os
import json
import struct
import base64
import tempfile
import io
import zipfile
import ezdxf
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from build123d import export_gltf, export_step, Compound, Color, Axis, Plane
from staircase_parametric import build_staircase, DEFAULT_CONFIG as PARAM_DEFAULTS
from staircase_structural import (
    build_structural_staircase,
    DEFAULT_CONFIG as STRUCT_DEFAULTS,
    C_TREAD, C_RISER, C_STRINGER, C_CARRIAGE, C_RIB, C_PLASTER, C_HANDRAIL,
)
from cnc_nesting import extract_2d_profile, nest_parts_optimized, split_with_scarf_joint

app = FastAPI()

# Category rendering info (matches display_structural in staircase_structural.py)
CATEGORY_ORDER = ["treads", "risers", "plaster", "stringers", "carriages", "ribs", "handrail"]
CATEGORY_STYLE = {
    "treads":    {"color": list(C_TREAD),    "opacity": 0.5},
    "risers":    {"color": list(C_RISER),    "opacity": 0.5},
    "plaster":   {"color": list(C_PLASTER),  "opacity": 0.5},
    "stringers": {"color": list(C_STRINGER), "opacity": 1.0},
    "carriages": {"color": list(C_CARRIAGE), "opacity": 1.0},
    "ribs":      {"color": list(C_RIB),      "opacity": 1.0},
    "handrail":  {"color": list(C_HANDRAIL), "opacity": 1.0},
}


class StaircaseConfig(BaseModel):
    model_type: str = "volumetric"
    width: float
    rise: float
    going: float
    waist: float
    inner_r: float
    s_bottom_steps: int
    winder_steps: int
    s_top_steps: int
    extend_top_flight: float
    unified_soffit: bool
    tread_thickness: Optional[float] = None
    riser_thickness: Optional[float] = None
    stringer_width: Optional[float] = None
    stringer_depth: Optional[float] = None
    carriage_width: Optional[float] = None
    carriage_depth: Optional[float] = None
    rib_spacing: Optional[float] = None
    rib_width: Optional[float] = None
    rib_depth: Optional[float] = None
    plaster_thickness: Optional[float] = None

class CncNestRequest(BaseModel):
    config: StaircaseConfig
    categories: list[str]
    sheet_width: float = 2440.0
    sheet_height: float = 1220.0

@app.post("/cnc/nest")
async def get_nested_layout(req: CncNestRequest):
    """Calculates an optimized nested layout with structural scarf joints.
    Automatically excludes non-flat architectural parts like handrails.
    """
    try:
        config_dict = req.config.dict()
        elements = build_structural_staircase(config_dict)
        
        # Define categories that can actually be nested on a flat sheet
        NESTABLE_CATEGORIES = ["treads", "risers", "stringers", "carriages", "ribs", "plaster"]
        
        final_part_data = []
        global_idx = 0
        
        for cat in req.categories:
            if cat not in NESTABLE_CATEGORIES:
                print(f"[API] Skipping non-nestable category: {cat}")
                continue
                
            parts = elements.get(cat, [])
            for i, p in enumerate(parts):
                # 1. Apply 3D Scarf Split for oversized parts
                segments = split_with_scarf_joint(p, req.sheet_width)
                
                for seg_idx, segment in enumerate(segments):
                    suffix = f"_{chr(65+seg_idx)}" if len(segments) > 1 else ""
                    prof = extract_2d_profile(segment)
                    
                    if prof and prof["width"] > 1 and prof["height"] > 1:
                        final_part_data.append({
                            "id": global_idx,
                            "name": f"{cat}_{i+1}{suffix}",
                            "width": prof["width"],
                            "height": prof["height"],
                            "points": prof["points"]
                        })
                        global_idx += 1
        
        if not final_part_data:
            return JSONResponse({"error": "No nestable parts selected"}, status_code=400)
            
        result = nest_parts_optimized(final_part_data, req.sheet_width, req.sheet_height)
        return JSONResponse(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cnc/export-dxf")
async def export_cnc_dxf(req: CncNestRequest):
    """Generates a multi-sheet DXF from the 3D-scarfed nesting layout."""
    try:
        config_dict = req.config.dict()
        elements = build_structural_staircase(config_dict)
        
        # Only nest flat parts
        NESTABLE_CATEGORIES = ["treads", "risers", "stringers", "carriages", "ribs", "plaster"]
        
        final_part_data = []
        global_idx = 0
        for cat in req.categories:
            if cat not in NESTABLE_CATEGORIES:
                continue
                
            parts = elements.get(cat, [])
            for i, p in enumerate(parts):
                # Use same 3D split logic as the preview
                segments = split_with_scarf_joint(p, req.sheet_width)
                for seg_idx, segment in enumerate(segments):
                    suffix = f"_{chr(65+seg_idx)}" if len(segments) > 1 else ""
                    prof = extract_2d_profile(segment)
                    if prof and prof["width"] > 1:
                        final_part_data.append({
                            "id": global_idx, 
                            "name": f"{cat}_{i+1}{suffix}", 
                            "width": prof["width"], 
                            "height": prof["height"], 
                            "points": prof["points"]
                        })
                        global_idx += 1
        
        if not final_part_data:
            return JSONResponse({"error": "No parts to nest"}, status_code=400)

        result = nest_parts_optimized(final_part_data, req.sheet_width, req.sheet_height)
        
        doc = ezdxf.new()
        doc.layers.add("NESTED_CUTS", color=7)
        doc.layers.add("LABELS", color=1)
        doc.layers.add("SHEET_BORDER", color=8)
        msp = doc.modelspace()
        
        for bin_idx, parts in result["sheets"].items():
            y_offset = int(bin_idx) * (req.sheet_height + 100)
            
            # Sheet Border
            msp.add_lwpolyline([
                (0, y_offset), (req.sheet_width, y_offset), 
                (req.sheet_width, y_offset + req.sheet_height), 
                (0, y_offset + req.sheet_height), (0, y_offset)
            ], dxfattribs={'layer': 'SHEET_BORDER'})
            
            for p in parts:
                pts = p["points"]
                final_pts = []
                for px, py in pts:
                    if p["is_rotated"]:
                        final_pts.append((p["x"] + py, y_offset + p["y"] + px))
                    else:
                        final_pts.append((p["x"] + px, y_offset + p["y"] + py))
                
                if final_pts:
                    final_pts.append(final_pts[0])
                    msp.add_lwpolyline(final_pts, dxfattribs={'layer': 'NESTED_CUTS'})
                    msp.add_text(p["name"], dxfattribs={'layer': 'LABELS', 'height': 20}).set_placement((p["x"]+5, y_offset + p["y"]+5))
            
        dxf_buffer = io.StringIO()
        doc.write(dxf_buffer)
        return Response(content=dxf_buffer.getvalue(), media_type="application/dxf", headers={"Content-Disposition": "attachment; filename=staircase_nested_structural.dxf"})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))



def _inject_materials_into_gltf(gltf_json, category_counts, part_face_counts):
    """Create glTF materials from scratch and assign by mesh index.

    OCCT's RWGltf_CafWriter exports a single Compound as one Mesh with many primitives (one per face).
    This function splits that single mesh into one mesh per part based on part_face_counts,
    mapping exactly to the frontend's expected object tree structure.
    """
    if not category_counts or not part_face_counts:
        return

    # 1. Create materials array
    materials = []
    for cat_name, _ in category_counts:
        style = CATEGORY_STYLE[cat_name]
        r, g, b = style["color"]
        a = style["opacity"]
        mat = {
            "name": cat_name,
            "pbrMetallicRoughness": {
                "baseColorFactor": [r, g, b, a],
                "metallicFactor": 0.05,
                "roughnessFactor": 0.65,
            },
        }
        if a < 1.0:
            mat["alphaMode"] = "BLEND"
            mat["doubleSided"] = True
        materials.append(mat)

    gltf_json["materials"] = materials

    # 2. Split monolithic mesh into individual part meshes
    meshes = gltf_json.get("meshes", [])
    if not meshes:
        return

    original_primitives = meshes[0].get("primitives", [])
    new_meshes = []
    new_nodes = []
    
    prim_idx = 0
    mat_idx = 0
    part_idx = 0
    
    for cat_name, count in category_counts:
        for _ in range(count):
            face_count = part_face_counts[part_idx]
            part_prims = original_primitives[prim_idx : prim_idx + face_count]
            
            for prim in part_prims:
                prim["material"] = mat_idx
                
            new_meshes.append({"primitives": part_prims, "name": f"mesh_{part_idx}"})
            new_nodes.append({"mesh": part_idx, "name": f"part_{part_idx}"})
            
            prim_idx += face_count
            part_idx += 1
            
        mat_idx += 1

    gltf_json["meshes"] = new_meshes
    gltf_json["nodes"] = new_nodes
    
    if "scenes" in gltf_json and len(gltf_json["scenes"]) > 0:
        gltf_json["scenes"][0]["nodes"] = list(range(len(new_nodes)))


def pack_glb(gltf_path, category_counts=None, part_face_counts=None):
    """Read .gltf + .bin → self-contained GLB bytes.

    Args:
        gltf_path: path to the .gltf file
        category_counts: optional list of (name, count) for material injection
        part_face_counts: optional list of face counts to map flat primitives back to parts
    """
    with open(gltf_path, "r") as f:
        gltf_json = json.load(f)

    bin_path = gltf_path.rsplit(".", 1)[0] + ".bin"
    bin_data = b""
    if os.path.exists(bin_path):
        with open(bin_path, "rb") as f:
            bin_data = f.read()
        if "buffers" in gltf_json:
            for buf in gltf_json["buffers"]:
                if "uri" in buf:
                    del buf["uri"]
                buf["byteLength"] = len(bin_data)

    # Inject materials from scratch if counts are provided
    if category_counts and part_face_counts:
        _inject_materials_into_gltf(gltf_json, category_counts, part_face_counts)

    json_bytes = json.dumps(gltf_json, separators=(",", ":")).encode("utf-8")
    json_padding = (4 - len(json_bytes) % 4) % 4
    json_bytes += b" " * json_padding

    bin_padding = (4 - len(bin_data) % 4) % 4
    bin_data += b"\x00" * bin_padding

    total_length = 12 + 8 + len(json_bytes) + 8 + len(bin_data)

    glb = bytearray()
    glb += struct.pack("<I", 0x46546C67)
    glb += struct.pack("<I", 2)
    glb += struct.pack("<I", total_length)
    glb += struct.pack("<I", len(json_bytes))
    glb += struct.pack("<I", 0x4E4F534A)
    glb += json_bytes
    glb += struct.pack("<I", len(bin_data))
    glb += struct.pack("<I", 0x004E4942)
    glb += bin_data

    return bytes(glb)


@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(os.path.join("web", "index.html"), "r", encoding="utf-8") as f:
        return f.read()


@app.get("/defaults")
async def get_defaults():
    return {"volumetric": PARAM_DEFAULTS, "structural": STRUCT_DEFAULTS}


@app.post("/generate")
async def generate_staircase(config: StaircaseConfig):
    try:
        config_dict = config.dict()
        model_type = config_dict.pop("model_type", "volumetric")

        temp_dir = tempfile.gettempdir()
        gltf_path = os.path.join(temp_dir, "staircase_output.glb")

        if model_type == "structural":
            for key, default_val in STRUCT_DEFAULTS.items():
                if config_dict.get(key) is None:
                    config_dict[key] = default_val

            print(f"[API] Building structural model...")
            elements = build_structural_staircase(config_dict)

            # Build list of parts and manifest for glTF material post-processing and UI tree
            all_parts = []
            manifest_categories = []
            mesh_index = 0
            
            for cat_name in CATEGORY_ORDER:
                parts = elements.get(cat_name, [])
                if not parts:
                    continue
                
                cat_manifest = {
                    "name": cat_name,
                    "color": CATEGORY_STYLE[cat_name]["color"],
                    "opacity": CATEGORY_STYLE[cat_name]["opacity"],
                    "parts": []
                }
                
                for i, p in enumerate(parts):
                    all_parts.append(p)
                    bbox = p.bounding_box()
                    cat_manifest["parts"].append({
                        "name": f"{cat_name}_{i+1}",
                        "mesh_index": mesh_index,
                        "volume_mm3": round(p.volume, 2),
                        "bbox": {
                            "min": [round(bbox.min.X, 1), round(bbox.min.Y, 1), round(bbox.min.Z, 1)],
                            "max": [round(bbox.max.X, 1), round(bbox.max.Y, 1), round(bbox.max.Z, 1)],
                            "size": [round(bbox.size.X, 1), round(bbox.size.Y, 1), round(bbox.size.Z, 1)]
                        }
                    })
                    mesh_index += 1
                
                manifest_categories.append(cat_manifest)

            if not all_parts:
                raise HTTPException(status_code=500, detail="No geometry produced")

            export_gltf(Compound(all_parts), gltf_path)

            # For structural, we track category counts and face counts to inject materials and split meshes
            # The order in all_parts matches manifest_categories
            category_counts = [(c["name"], len(c["parts"])) for c in manifest_categories]
            part_face_counts = [len(p.faces()) for p in all_parts]
            glb_bytes = pack_glb(gltf_path, category_counts=category_counts, part_face_counts=part_face_counts)

            return JSONResponse({
                "model_type": "structural",
                "glb": base64.b64encode(glb_bytes).decode("ascii"),
                "manifest": {"categories": manifest_categories},
                "styles": CATEGORY_STYLE,
            })
        else:
            print(f"[API] Building volumetric model...")
            stair = build_staircase(config_dict)
            export_gltf(stair, gltf_path)
            glb_bytes = pack_glb(gltf_path)

            return JSONResponse({
                "model_type": "volumetric",
                "glb": base64.b64encode(glb_bytes).decode("ascii"),
                "manifest": {"categories": []},
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/export/autocad")
async def export_autocad_bundle(config: StaircaseConfig):
    """Generates a ZIP bundle with per-category STEP files and an AutoLISP import script."""
    try:
        config_dict = config.dict()
        elements = build_structural_staircase(config_dict)

        # Create a ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            manifest_parts = []

            # 1. Export STEP files per category
            for cat_name in CATEGORY_ORDER:
                parts = elements.get(cat_name, [])
                if not parts:
                    continue

                cat_compound = Compound(parts)
                with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as tmp:
                    tmp_path = tmp.name

                try:
                    export_step(cat_compound, tmp_path)
                    zip_file.write(tmp_path, f"{cat_name}.step")
                    manifest_parts.append(cat_name)
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

            # 2. Generate Manifest JSON
            manifest = {
                "categories": manifest_parts,
                "config": config_dict
            }
            zip_file.writestr("manifest.json", json.dumps(manifest, indent=2))

            # 3. Generate AutoLISP Script
            ACAD_COLORS = {
                "treads": "32", "risers": "34", "stringers": "42",
                "carriages": "44", "ribs": "52", "plaster": "9"
            }

            lisp_lines = [
                ";; import_staircase.lsp - Auto-generated by Staircase Studio",
                "(defun import-to-layer (filepath layername color / lastent ss)",
                "  (setq lastent (entlast))",
                "  (if (findfile filepath)",
                "    (progn",
                '      (command \"-LAYER\" \"M\" layername \"C\" color layername \"\")',
                '      (command \"-IMPORT\" filepath \"\")',
                "      (setq ss (ssadd))",
                "      (if lastent",
                "        (while (setq lastent (entnext lastent)) (ssadd lastent ss))",
                '        (setq ss (ssget \"X\"))',
                "      )",
                '      (if ss (command \"-CHPROP\" ss \"\" \"LA\" layername \"C\" \"BYLAYER\" \"\"))',
                "    )",
                '    (princ (strcat \"\\nFile not found: \" filepath))',
                "  )",
                ")",
                "",
                "(defun C:IMPORT-STAIRCASE (/ path)",
                '  (setq path (getvar \"DWGPREFIX\"))',
                '  (setvar \"CMDECHO\" 0)',
            ]

            for cat in manifest_parts:
                lisp_lines.append(
                    f'  (import-to-layer (strcat path \"{cat}.step\") \"SS-{cat.upper()}\" \"{ACAD_COLORS.get(cat, "7")}\")'  
                )

            lisp_lines.extend([
                '  (setvar \"CMDECHO\" 1)',
                '  (princ \"\\nStaircase import complete.\")',
                "  (princ)",
                ")",
            ])
            zip_file.writestr("import_staircase.lsp", "\n".join(lisp_lines))

        zip_buffer.seek(0)
        filename = f"staircase_autocad_{config.model_type}.zip"
        return StreamingResponse(
            zip_buffer,
            media_type="application/x-zip-compressed",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        print(f"[API] Export Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/export/dxf")
async def export_dxf_file(config: StaircaseConfig):
    """Generates a DXF file with 2D profiles and labels for all structural parts.
    Uses the robust Edge Trace logic to match manufacturing layouts.
    """
    try:
        config_dict = config.dict()
        elements = build_structural_staircase(config_dict)
        
        doc = ezdxf.new()
        doc.layers.add("PROFILES", color=7)
        doc.layers.add("LABELS", color=1)
        msp = doc.modelspace()
        
        spacing = 1000.0
        row_size = 5
        x_offset = 0.0
        y_offset = 0.0
        count = 0
        
        # Define categories that make sense to export as 2D profiles
        EXPORT_CATEGORIES = ["treads", "risers", "stringers", "carriages", "ribs"]
        
        for cat_name in EXPORT_CATEGORIES:
            parts = elements.get(cat_name, [])
            for i, p in enumerate(parts):
                # Apply 3D Scarf Split for oversized parts in DXF too
                segments = split_with_scarf_joint(p, 2440.0)
                
                for seg_idx, segment in enumerate(segments):
                    suffix = f"_{chr(65+seg_idx)}" if len(segments) > 1 else ""
                    # Use the robust Edge Trace engine
                    prof = extract_2d_profile(segment)
                    
                    if prof and prof["points"]:
                        # Convert points to 2D tuples for ezdxf
                        path_points = [(px + x_offset, py + y_offset) for px, py in prof["points"]]
                        path_points.append(path_points[0]) # Close loop
                        
                        msp.add_lwpolyline(path_points, dxfattribs={'layer': 'PROFILES'})
                        
                        # Add label
                        label_text = f"{cat_name}_{i+1}{suffix}"
                        msp.add_text(label_text, dxfattribs={
                            'layer': 'LABELS',
                            'height': 50,
                        }).set_placement((x_offset, y_offset + 50))
                        
                        # Increment grid
                        count += 1
                        x_offset += spacing
                        if count % row_size == 0:
                            x_offset = 0.0
                            y_offset -= spacing

        dxf_buffer = io.StringIO()
        doc.write(dxf_buffer)
        
        return Response(
            content=dxf_buffer.getvalue(),
            media_type="application/dxf",
            headers={"Content-Disposition": f"attachment; filename=staircase_profiles_{config.model_type}.dxf"}
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        print(f"[API] DXF Export Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
