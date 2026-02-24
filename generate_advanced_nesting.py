import sys
import os
import json
import importlib
from build123d import *

# Add current dir to path and FORCE REFRESH
sys.path.insert(0, os.getcwd())
import cnc_nesting
importlib.reload(cnc_nesting)
from cnc_nesting import extract_2d_profile, nest_parts_optimized, split_with_scarf_joint

print(f"[DEBUG] Using engine at: {cnc_nesting.__file__}")

from staircase_structural import build_structural_staircase, DEFAULT_CONFIG

def generate_full_manufacturing_report():
    print("Building structural geometry...")
    elements = build_structural_staircase(DEFAULT_CONFIG)
    
    # Define Thickness Groups
    groups = {
        "20mm_Timber": ["treads", "risers"],
        "50mm_Structural": ["stringers", "carriages"],
        "18mm_Plywood": ["ribs"]
    }
    
    sheet_w, sheet_h = 2440.0, 1220.0
    
    for group_name, categories in groups.items():
        print(f"\n--- Processing Group: {group_name} ---", flush=True)
        part_data = []
        global_idx = 0
        
        for cat in categories:
            parts = elements.get(cat, [])
            print(f"  [DEBUG] Iterating through category: '{cat}' ({len(parts)} parts)", flush=True)
            for i, p in enumerate(parts):
                # 1. Apply 3D Scarf Split for oversized parts (Orientation Agnostic)
                segments = split_with_scarf_joint(p, sheet_w)
                
                for seg_idx, segment in enumerate(segments):
                    suffix = f"_{chr(65+seg_idx)}" if len(segments) > 1 else ""
                    print(f"    [DEBUG] Processing {cat}_{i+1}{suffix}: {type(segment)}", flush=True)
                    
                    # 2. Extract 2D Profile using Edge Trace
                    prof = extract_2d_profile(segment)
                    if prof and prof["width"] > 1 and prof["height"] > 1:
                        part_data.append({
                            "id": global_idx,
                            "name": f"{cat}_{i+1}{suffix}",
                            "width": prof["width"],
                            "height": prof["height"],
                            "points": prof.get("points", []),
                            "outer": prof.get("outer", prof.get("points", [])),
                            "inner": prof.get("inner", [])
                        })
                        global_idx += 1
        
        if not part_data:
            print(f"No parts found for {group_name}. Skipping.")
            continue
            
        print(f"Nesting {len(part_data)} parts for {group_name}...")
        result = nest_parts_optimized(part_data, sheet_w, sheet_h)
        
        if not result:
            print(f"Nesting failed for {group_name}")
            continue
        
        print(f"Winner: {result['algo']} | Efficiency: {result['efficiency']}%")
        
        # Generate SVG
        num_sheets = result["sheet_count"]
        scale = 0.2
        svg_w = sheet_w * scale
        svg_h = (sheet_h * num_sheets + (50 * num_sheets)) * scale
        
        # Clean up algorithm name for XML safety
        algo_name = str(result["algo"]).split(".")[-1].replace("'>", "")
        
        svg_lines = [
            f'<svg width="{svg_w}" height="{svg_h}" viewBox="0 0 {sheet_w} {sheet_h * num_sheets + (50 * num_sheets)}" xmlns="http://www.w3.org/2000/svg">',
            f'<rect width="100%" height="100%" fill="white" />'
        ]
        
        for bin_idx, parts in result["sheets"].items():
            y_offset = bin_idx * (sheet_h + 50)
            svg_lines.append(f'<rect x="0" y="{y_offset}" width="{sheet_w}" height="{sheet_h}" fill="none" stroke="black" stroke-width="10" />')
            svg_lines.append(f'<text x="20" y="{y_offset + 60}" font-size="50" font-weight="bold" fill="red">SHEET {bin_idx + 1} ({group_name})</text>')
            svg_lines.append(f'<text x="20" y="{y_offset + 110}" font-size="30" fill="gray">Algo: {algo_name} | Efficiency: {result["efficiency"]}%</text>')
            
            import html
            for p in parts:
                safe_name = html.escape(str(p["name"]))
                
                # Render Outer Perimeter
                outer_pts = p.get("outer", p.get("points", []))
                final_outer = []
                for px, py in outer_pts:
                    if p.get("is_rotated", False):
                        nx = round(float(p["x"] + py), 2)
                        ny = round(float(y_offset + p["y"] + px), 2)
                    else:
                        nx = round(float(p["x"] + px), 2)
                        ny = round(float(y_offset + p["y"] + py), 2)
                    final_outer.append(f"{nx},{ny}")
                
                if final_outer:
                    svg_lines.append(f'<polygon points="{" ".join(final_outer)}" fill="rgba(100,150,255,0.3)" stroke="blue" stroke-width="2" />')
                
                # Render Inner Holes
                for inner_loop in p.get("inner", []):
                    final_inner = []
                    for px, py in inner_loop:
                        if p.get("is_rotated", False):
                            nx = round(float(p["x"] + py), 2)
                            ny = round(float(y_offset + p["y"] + px), 2)
                        else:
                            nx = round(float(p["x"] + px), 2)
                            ny = round(float(y_offset + p["y"] + py), 2)
                        final_inner.append(f"{nx},{ny}")
                    if final_inner:
                        svg_lines.append(f'<polygon points="{" ".join(final_inner)}" fill="white" stroke="red" stroke-width="1.5" stroke-dasharray="4" />')
                        
                svg_lines.append(f'<text x="{p["x"]+10}" y="{y_offset + p["y"]+30}" font-size="20" fill="black">{safe_name}</text>')

        svg_lines.append('</svg>')
        output_file = f"nesting_{group_name.lower()}.svg"
        with open(output_file, "w") as f: f.write("\n".join(svg_lines))
        print(f"Saved optimized layout to {output_file}")


if __name__ == "__main__":
    try:
        generate_full_manufacturing_report()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
