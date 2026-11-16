"""Room orientation: transform and inverse transforms of room shapes.

Transformations are applied to the outline and wall openings. The room's dimensions (length, width, height)
are updated to reflect the new orientation.
"""

import copy
import math

from subtune import shape


OPS = ("cw", "ccw", "180", "mirror")


def inverse(op: str) -> str:
    """Return the inverse of an operation."""
    if op == "cw":
        return "ccw"
    elif op == "ccw":
        return "cw"
    elif op in ("180", "mirror"):
        return op
    else:
        raise ValueError(f"Unknown operation: {op}")


def transform_room(room: dict, op: str) -> dict:
    """Apply an orientation operation to a room.

    Returns a NEW deep copy (use copy.deepcopy), never changes `room`.
    Point maps (z never changes):
      cw:     (x, y) -> (L - y, x)      and the room's width_m and length_m swap
      ccw:    (x, y) -> (y, W - x)      and width_m and length_m swap
      180:    (x, y) -> (W - x, L - y)
      mirror: (x, y) -> (W - x, y)      and the outline point order is reversed

    Apply the point map to: every outline point (room["room"]["outline"], if not None),
    every seat (x_m, y_m), every sub in room["subs"].values() (x_m, y_m),
    every speaker in room["speakers"].values() (x_m, y_m).
    If x_m or y_m is None, leave it None. Round every result to 4 decimals.
    """
    if op not in OPS:
        raise ValueError(f"Unknown operation: {op}")

    # Create a deep copy of the room
    new_room = copy.deepcopy(room)

    # Get room dimensions - need to access nested room structure
    rm = new_room["room"]

    # Determine width and length (use outline extent if available, otherwise from room properties)
    outline_pts = shape.outline(rm)
    if outline_pts:
        W, L = shape.extent(outline_pts)
    else:
        # Handle case where no outline exists but width_m/length_m are specified
        W = rm.get("width_m", 0.0)
        L = rm.get("length_m", 0.0)

    # Apply the transformation to all relevant points
    def transform_point(x, y):
        if x is None or y is None:
            return x, y

        if op == "cw":
            # (x, y) -> (L - y, x)
            new_x = round(L - y, 4)
            new_y = round(x, 4)
        elif op == "ccw":
            # (x, y) -> (y, W - x)
            new_x = round(y, 4)
            new_y = round(W - x, 4)
        elif op == "180":
            # (x, y) -> (W - x, L - y)
            new_x = round(W - x, 4)
            new_y = round(L - y, 4)
        elif op == "mirror":
            # (x, y) -> (W - x, y)
            new_x = round(W - x, 4)
            new_y = round(y, 4)

        return new_x, new_y

    # Transform outline points
    if "outline" in rm and rm["outline"] is not None:
        rm["outline"] = [list(transform_point(p[0], p[1])) for p in rm["outline"]]

    # Transform seats (seats is a list, not dict)
    if "seats" in new_room:
        for seat in new_room["seats"]:
            seat["x_m"], seat["y_m"] = transform_point(seat.get("x_m"), seat.get("y_m"))

    # Transform subs (subs is a dict keyed by id)
    if "subs" in new_room:
        for sub in new_room["subs"].values():
            sub["x_m"], sub["y_m"] = transform_point(sub.get("x_m"), sub.get("y_m"))

    # Transform speakers (speakers is a dict keyed by id)
    if "speakers" in new_room:
        for speaker in new_room["speakers"].values():
            speaker["x_m"], speaker["y_m"] = transform_point(speaker.get("x_m"), speaker.get("y_m"))

    # Update dimensions after transformation (for cw and ccw operations)
    if op in ("cw", "ccw"):
        # Swap width and length
        rm["width_m"], rm["length_m"] = rm["length_m"], rm["width_m"]

    # Handle ceiling turn if present
    if isinstance(rm.get("ceiling"), dict):
        ceiling = rm["ceiling"]
        if "low_side" in ceiling:
            low_side = ceiling["low_side"]
            if op == "cw":
                mapping = {"front": "right", "right": "back", "back": "left", "left": "front"}
                ceiling["low_side"] = mapping[low_side]
            elif op == "ccw":
                mapping = {"front": "left", "left": "back", "back": "right", "right": "front"}
                ceiling["low_side"] = mapping[low_side]
            elif op == "180":
                mapping = {"front": "back", "back": "front", "left": "right", "right": "left"}
                ceiling["low_side"] = mapping[low_side]
            elif op == "mirror":
                ceiling["low_side"] = low_side  # mirror doesn't change low_side direction

        # Handle ridge turn for vault ceilings
        if "ridge" in ceiling:
            ridge = ceiling["ridge"]
            if op in ("cw", "ccw") and ridge == "length":
                ceiling["ridge"] = "width"
            elif op in ("cw", "ccw") and ridge == "width":
                ceiling["ridge"] = "length"
            elif op == "180":  # 180 doesn't change ridge
                pass
            # mirror also doesn't change ridge for vault ceilings

    # Handle openings turn if present
    if "wall_openings" in rm and rm["wall_openings"] is not None:
        openings = rm["wall_openings"]

        # Determine which case we're in: use stored outline (not shape.outline)
        stored_outline = rm.get("outline")

        new_openings = []
        for opening in openings:
            wall = opening.get("wall")
            if wall is not None:
                # Apply transformation based on operation
                if stored_outline is not None:
                    # Case A: outline present
                    if op == "mirror":
                        n = len(stored_outline)
                        new_wall = (n - 2 - wall) % n
                        # Adjust from_m for mirror operation using old edge length
                        if "from_m" in opening and "width_m" in opening:
                            # Calculate the OLD edge length before transformation
                            old_edge_length = math.dist(stored_outline[wall], stored_outline[(wall + 1) % len(stored_outline)])
                            opening["from_m"] = old_edge_length - opening["from_m"] - opening["width_m"]
                    else:
                        # For cw, ccw, 180: no changes to wall or from_m (outline points keep their order)
                        new_wall = wall
                else:
                    # Case B: outline None (plain rectangle)
                    if op == "cw":
                        new_wall = (wall + 1) % 4
                    elif op == "ccw":
                        new_wall = (wall + 3) % 4
                    elif op == "180":
                        new_wall = (wall + 2) % 4
                    elif op == "mirror":
                        # For mirror: map 0->0, 1->3, 2->2, 3->1
                        mapping = {0: 0, 1: 3, 2: 2, 3: 1}
                        new_wall = mapping[wall]
                        # Adjust from_m for mirror operation using old dimensions
                        if "from_m" in opening and "width_m" in opening:
                            # Get the OLD room dimensions (before any transformation)
                            old_width = room["room"].get("width_m", 0.0)
                            old_length = room["room"].get("length_m", 0.0)
                            # Determine edge length based on wall index
                            old_edge_length = old_length if wall in (1, 3) else old_width
                            opening["from_m"] = old_edge_length - opening["from_m"] - opening["width_m"]

                opening["wall"] = new_wall
                new_openings.append(opening)
            else:
                # Keep openings without wall index unchanged
                new_openings.append(opening)

        rm["wall_openings"] = new_openings

    # Reverse outline point order for mirror operation
    if op == "mirror" and "outline" in rm and rm["outline"] is not None:
        rm["outline"].reverse()

    return new_room