"""Room orientation: transform and inverse transforms of room shapes.

Transformations are applied to the outline and wall openings. The room's dimensions (length, width, height)
are updated to reflect the new orientation.
"""

import copy

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

    # Reverse outline point order for mirror operation
    if op == "mirror" and "outline" in rm and rm["outline"] is not None:
        rm["outline"].reverse()

    return new_room