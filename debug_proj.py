
import sys
import os
from build123d import *

# Add current dir to path
sys.path.append(os.getcwd())
from staircase_structural import build_structural_staircase, DEFAULT_CONFIG

def debug_projection():
    print("Building model...")
    elements = build_structural_staircase(DEFAULT_CONFIG)
    tread = elements["treads"][0]
    
    print(f"Testing Tread: {tread}")
    
    for name, plane in {"XY": Plane.XY, "XZ": Plane.XZ, "YZ": Plane.YZ}.items():
        print(f"\n--- Projecting onto {name} ---")
        try:
            projected = tread.project_to_plane(plane)
            print(f"Projected Type: {type(projected)}")
            
            # Check for faces
            faces = projected.faces()
            print(f"Number of faces: {len(faces)}")
            
            # Check for wires
            wires = projected.wires()
            print(f"Number of wires: {len(wires)}")
            
            if wires:
                w = wires[0]
                print(f"Wire Area: {w.area}")
                print(f"Number of edges: {len(w.edges())}")
                
        except Exception as e:
            print(f"Error on {name}: {e}")

if __name__ == "__main__":
    debug_projection()
