"""Baluster (Spindle) Generator for Geometry Studio.
Places vertical supports between treads and handrails based on nosing paths.
"""
from build123d import *
import math
from handrail_generator import get_stair_nosing_points

def build_balusters(config, handrail_height=900.0, diameter=20.0, max_spacing=100.0):
    """
    Generates a list of vertical spindle Parts with code-compliant spacing.
    Automatically calculates spindles per step to ensure gap is < max_spacing.
    """
    nodes = get_stair_nosing_points(config)
    going = config["going"]
    nosing = config.get("nosing", 0)
    balusters = []
    
    # Calculate required spindles per step to satisfy building code
    # (Gap between spindles must be less than max_spacing)
    spindles_per_step = math.ceil(going / max_spacing)
    
    # We iterate through the segments between nosing points
    for i in range(len(nodes) - 1):
        p1 = nodes[i]
        p2 = nodes[i+1]
        
        # Determine if this is a straight or winder step based on node distance
        dist = (p2 - p1).length
        count = math.ceil(dist / max_spacing) if dist > going else spindles_per_step
        
        for j in range(count):
            # Interpolate position along the segment
            t = (j + 0.5) / count # Center the spindles in their sub-slots
            curr_pos = p1 + (p2 - p1) * t
            
            # Architectural Offset: 
            # Set the baluster back from the nosing so it's centered on the tread/riser line
            # We move it 'nosing' distance back along the flight direction
            flight_dir = (p2 - p1).normalized()
            # Move back by half the 'going' to center it on the tread surface
            offset_pos = curr_pos - (flight_dir * (going / 2))
            
            with BuildPart() as b:
                # Place spindle starting from tread surface
                with BuildSketch(Plane.XY.offset(offset_pos.Z)):
                    with Locations((offset_pos.X, offset_pos.Y)):
                        Circle(diameter / 2)
                # Extrude to reach the handrail
                extrude(amount=handrail_height)
            balusters.append(b.part)
            
    return balusters

