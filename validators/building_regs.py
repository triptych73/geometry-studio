class PartKValidator:
    """Validator for UK Building Regulations Part K (Stairs)."""
    
    @staticmethod
    def check_staircase(rise: float, going: float) -> list[str]:
        """
        Validate a flight of stairs.
        
        Args:
            rise: Individual riser height (mm)
            going: Individual going depth (mm)
        """
        issues = []
        
        # Part K limits for private dwellings
        # Rise: 150mm to 220mm
        # Going: 220mm to 300mm
        # Pitch: Max 42 degrees
        # 2R + G: 550mm to 700mm
        
        import math
        pitch = math.degrees(math.atan2(rise, going))
        trg = 2 * rise + going
        
        if not (150 <= rise <= 220):
            issues.append(f"Riser height {rise:.1f}mm is outside compliant range [150, 220]")
        
        if not (220 <= going <= 300):
            issues.append(f"Stair going {going:.1f}mm is outside compliant range [220, 300]")
            
        if pitch > 42.1: # Allow a tiny margin for rounding
            issues.append(f"Pitch {pitch:.1f}° exceeds maximum 42°")
            
        if not (550 <= trg <= 700):
            issues.append(f"2R + G calculation ({trg:.1f}) is outside compliant range [550, 700]")
            
        return issues
