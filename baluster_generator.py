"""Baluster (Spindle) Generator for Geometry Studio.
Places vertical supports between treads and handrails based on nosing paths.
"""
from build123d import *
import math
from handrail_generator import get_true_walkline

def build_balusters(config, handrail_height=900.0, diameter=20.0, max_spacing=100.0):
    """
    Generates a list of vertical spindle Parts with code-compliant spacing.
    Automatically calculates spindles per step to ensure gap is < max_spacing.
    """
    width = config["width"]
    going = config["going"]
    offset = width / 2.0
    # Walkline for outer balusters (shifted inwards from width boundary)
    nodes = get_true_walkline(config, offset_from_inner=offset - 25.0, z_offset=0.0)
    
    going = config["going"]
    balusters = []
    
    # 1. Calculate cumulative 2D distance along the entire continuous walkline
    distances = [0.0]
    total_2D_dist = 0.0
    for i in range(len(nodes) - 1):
        p1 = nodes[i]
        p2 = nodes[i+1]
        dist_2d = math.sqrt((p2.X - p1.X)**2 + (p2.Y - p1.Y)**2)
        total_2D_dist += dist_2d
        distances.append(total_2D_dist)
        
    # 2. Determine exact number of balusters required for the whole flight
    # (Must be strictly less than max_spacing, so we round up)
    count = math.ceil(total_2D_dist / max_spacing)
    if count == 0:
        return []
        
    actual_spacing = total_2D_dist / count
    
    # 3. Distribute balusters continuously along the spline
    # We skip the very first (0.0) and very last (1.0) points usually occupied by newel posts
    for j in range(1, count):
        target_dist = j * actual_spacing
        
        # Find which segment this distance falls into
        for i in range(len(distances) - 1):
            if distances[i] <= target_dist <= distances[i+1]:
                # Interpolate percentage exactly within this specific segment
                segment_dist = distances[i+1] - distances[i]
                if segment_dist == 0:
                    t = 0
                else:
                    t = (target_dist - distances[i]) / segment_dist
                    
                p1 = nodes[i]
                p2 = nodes[i+1]
                
                # Full 3D Interpolation (X, Y, and importantly Z slope)
                curr_pos = p1 + (p2 - p1) * t
                
                # Architecural alignment: Push the baluster center backwards along the flight vector
                # so it sits firmly on the wood step, not hovering off the geometric nosing edge
                flight_dir = (p2 - p1).normalized()
                offset_pos = curr_pos - (flight_dir * (diameter / 2 + 5))
                
                with BuildPart() as b:
                    with BuildSketch(Plane.XY.offset(offset_pos.Z)):
                        with Locations((offset_pos.X, offset_pos.Y)):
                            Circle(diameter / 2)
                    extrude(amount=handrail_height)
                balusters.append(b.part)
                break
                
    return balusters

