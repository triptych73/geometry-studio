
import sys
import os
import json
from build123d import *

# Add current dir to path
sys.path.append(os.getcwd())
from staircase_structural import build_structural_staircase, DEFAULT_CONFIG
from cnc_nesting import extract_2d_profile, nest_parts

def generate_nesting_svg():
    print("Building structural geometry...")
    elements = build_structural_staircase(DEFAULT_CONFIG)
    
    part_data = []
    idx = 0
    # We'll nest Treads and Stringers for this demo
    categories = ["treads", "stringers"]
    
    for cat in categories:
        parts = elements.get(cat, [])
        for i, p in enumerate(parts):
            prof = extract_2d_profile(p)
            if prof and prof["width"] > 1 and prof["height"] > 1:
                part_data.append({
                    "id": idx,
                    "name": f"{cat}_{i+1}",
                    "width": prof["width"],
                    "height": prof["height"],
                    "points": prof["points"]
                })
                idx += 1
            else:
                print(f"Skipping invalid profile: {cat}_{i+1} (Size: {prof['width'] if prof else 'None'} x {prof['height'] if prof else 'None'})")

    print(f"Nesting {len(part_data)} parts...")
    sheet_w, sheet_h = 2440, 1220
    result = nest_parts(part_data, sheet_w, sheet_h)
    
    # Generate SVG manually for the nesting layout
    # Scale for preview (approx 1:10)
    scale = 0.2
    svg_w = sheet_w * scale
    svg_h = sheet_h * scale
    
    svg_lines = [
        f'<svg width="{svg_w}" height="{svg_h}" viewBox="0 0 {sheet_w} {sheet_h}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect x="0" y="0" width="{sheet_w}" height="{sheet_h}" fill="none" stroke="black" stroke-width="5" />'
    ]
    
    for p in result["parts"]:
        # points are relative to part 0,0. part is at x,y
        pts = p["points"]
        final_pts = []
        for px, py in pts:
            if p["is_rotated"]:
                # Swap x/y for rotation
                final_pts.append(f"{p['x'] + py},{p['y'] + px}")
            else:
                final_pts.append(f"{p['x'] + px},{p['y'] + py}")
        
        poly = " ".join(final_pts)
        svg_lines.append(f'<polygon points="{poly}" fill="rgba(100,150,255,0.5)" stroke="blue" stroke-width="2" />')
        # Add label
        svg_lines.append(f'<text x="{p["x"]+10}" y="{p["y"]+30}" font-size="25" fill="black">{p["name"]}</text>')

    svg_lines.append('</svg>')
    
    with open("cnc_nesting_preview.svg", "w") as f:
        f.write("\n".join(svg_lines))
    print("Saved nesting preview to cnc_nesting_preview.svg")

if __name__ == "__main__":
    try:
        generate_nesting_svg()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
