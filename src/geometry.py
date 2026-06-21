import numpy as np

def calculate_line_parameters(width, height, line_pos, line_angle):
    """
    Calculates line parameters A, B, C for the line equation A*x + B*y + C = 0
    and returns pivot point (x0, y0) and drawing endpoints line_pt1, line_pt2.
    """
    is_vertical_ish = 45 <= (line_angle % 180) < 135
    if is_vertical_ish:
        x0 = int(width * line_pos)
        y0 = int(height / 2)
    else:
        x0 = int(width / 2)
        y0 = int(height * line_pos)

    # Line equation parameters: A*x + B*y + C = 0
    theta = np.radians(line_angle)
    A = -np.sin(theta)
    B = np.cos(theta)
    C = np.sin(theta) * x0 - np.cos(theta) * y0
    
    # Calculate boundary intersection points to draw the line
    pts = []
    # Left edge (x = 0)
    if abs(B) > 1e-5:
        y = -C / B
        if 0 <= y <= height:
            pts.append((0, int(y)))
    # Right edge (x = width)
    if abs(B) > 1e-5:
        y = -(A * width + C) / B
        if 0 <= y <= height:
            pts.append((width, int(y)))
    # Top edge (y = 0)
    if abs(A) > 1e-5:
        x = -C / A
        if 0 <= x <= width:
            pts.append((int(x), 0))
    # Bottom edge (y = height)
    if abs(A) > 1e-5:
        x = -(B * height + C) / A
        if 0 <= x <= width:
            pts.append((int(x), height))
            
    # Keep unique points
    unique_pts = []
    for pt in pts:
        if pt not in unique_pts:
            unique_pts.append(pt)
            
    if len(unique_pts) >= 2:
        line_pt1 = unique_pts[0]
        line_pt2 = unique_pts[1]
    else:
        if is_vertical_ish:
            line_pt1 = (x0, 0)
            line_pt2 = (x0, height)
        else:
            line_pt1 = (0, y0)
            line_pt2 = (width, y0)
            
    return A, B, C, x0, y0, line_pt1, line_pt2, is_vertical_ish


def check_crossing(prev_cx, prev_cy, cx, cy, A, B, C, is_vertical_ish, in_dir):
    """
    Checks if a point has crossed the line and in which direction.
    Returns (crossed_in, crossed_out).
    """
    crossed_in = False
    crossed_out = False

    prev_d = A * prev_cx + B * prev_cy + C
    curr_d = A * cx + B * cy + C
    
    if prev_d * curr_d < 0:
        # Crossed the line!
        # Determine if movement is in direction of normal vector
        is_forward = curr_d > prev_d
        
        # Decide IN vs OUT based on line orientation and configured in-dir
        if is_vertical_ish:
            # For vertical-ish: default left-to-right (reverse direction) is IN
            if in_dir in ["right", "forward"]:
                if not is_forward:
                    crossed_in = True
                else:
                    crossed_out = True
            else: # left / reverse
                if is_forward:
                    crossed_in = True
                else:
                    crossed_out = True
        else:
            # For horizontal-ish: default top-to-bottom (forward direction) is IN
            if in_dir in ["down", "forward"]:
                if is_forward:
                    crossed_in = True
                else:
                    crossed_out = True
            else: # up / reverse
                if not is_forward:
                    crossed_in = True
                else:
                    crossed_out = True

    return crossed_in, crossed_out
