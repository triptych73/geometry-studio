
import sys
import os
from build123d import *

# Add current dir to path to find the helpers
sys.path.append(os.getcwd())
from staircase_parametric import build_staircase, DEFAULT_CONFIG

def generate_2d_image():
    print("Building staircase geometry...")
    stair = build_staircase(DEFAULT_CONFIG)
    
    print("Projecting to 2D...")
    # Create a nice isometric-style projection
    # We rotate the model slightly for a better view
    view_stair = stair.rotate(Axis.X, 45).rotate(Axis.Z, 45)
    
    # Export as SVG
    # Note: build123d's export_svg is the most reliable way to get a 2D visual in this env
    exporter = ExportSVG(scale=0.1)
    exporter.add_shape(view_stair)
    exporter.write("staircase_preview.svg")
    print("Saved preview to staircase_preview.svg")

if __name__ == "__main__":
    try:
        generate_2d_image()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
