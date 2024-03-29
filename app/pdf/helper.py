from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing, Circle, Polygon, PolyLine, Group


UNITS_ABBREVIATIONS = {
    'Meters': 'm',
    'Millimeters': 'mm',
    'Feet': 'ft',
    'Inches': 'in',
    'Centimeters': 'cm'
}


ROWBACKGROUNDS = [
    colors.Color(248 / 255, 248 / 255, 248 / 255),
    colors.Color(253 / 255, 253 / 255, 253 / 255)
]


def scale_drawing(drawing: Drawing, sx: float, sy: float) -> Drawing:
    new_drawing = drawing.copy()
    new_drawing.scale(sx, sy)
    new_drawing.width = new_drawing.width * sx
    new_drawing.height = new_drawing.height * sy
    return new_drawing


def scale_drawing_to_width(drawing: Drawing, width: float, max_height: float = None) -> Drawing:
    new_drawing = drawing.copy()
    x1, y1, x2, y2 = new_drawing.getBounds()
    contents_width = x2 - x1
    contents_height = y2 - y1
    scale_factor = width / contents_width
    height = contents_height * scale_factor
    if max_height is not None and height > max_height:
        scale_factor = max_height / contents_height
        width = contents_width * scale_factor
        height = max_height
    new_drawing.scale(sx=scale_factor, sy=scale_factor)
    new_drawing.width = width
    new_drawing.height = height
    return new_drawing


def scale_drawing_to_height(drawing: Drawing, height: float, max_width: float = None) -> Drawing:
    new_drawing = drawing.copy()
    x1, y1, x2, y2 = new_drawing.getBounds()
    contents_width = x2 - x1
    contents_height = y2 - y1
    scale_factor = height / contents_height
    width = contents_width * scale_factor
    if max_width is not None and width > max_width:
        scale_factor = max_width / contents_width
        width = max_width
        height = contents_height * scale_factor
    new_drawing.scale(sx=scale_factor, sy=scale_factor)
    new_drawing.width = width
    new_drawing.height = height
    return new_drawing


def create_north_arrow(north: float, radius: float) -> Group:
    north_arrow = Group(
        Polygon(points=[-radius*0.2, 0, radius*0.2, 0, 0, radius], fillColor=colors.black, strokeColor=colors.black, strokeWidth=0),
        Circle(0, 0, radius, strokeWidth=radius*0.025, fillOpacity=0),
        PolyLine([-radius, 0, radius, 0], strokeWidth=radius*0.025/2)
    )
    north_arrow.rotate(north)
    return north_arrow


def draw_north_arrow(north: float, radius: float) -> Drawing:
    north_arrow_drawing = Drawing(width=radius*2, height=radius*2)
    group = create_north_arrow(north, radius)
    for elem in group.contents:
        north_arrow_drawing.add(elem)
    north_arrow_drawing.translate(radius, radius)
    return north_arrow_drawing


def translate_group_relative(group: Group, anchor_group: Group, anchor: str, padding: float):
    anchor_bounds = anchor_group.getBounds()
    group_bounds = group.getBounds()
    if anchor == 'e':
        new_x = anchor_bounds[2]
        new_y = (anchor_bounds[1] + anchor_bounds[3]) / 2
        old_y = (group_bounds[1] + group_bounds[3]) / 2
        dx = new_x - group_bounds[0] + padding
        dy = new_y - old_y
        group.translate(dx, dy)
    else:
        raise NotImplementedError()


def drawing_dimensions_from_bounds(drawing: Drawing):
    """Set the width and height based on the boundaries of the contents."""
    drawing_bounds = drawing.getBounds()
    if drawing_bounds[0] != 0 or drawing_bounds[1] != 0:
        dx = 0 - drawing_bounds[0]
        dy = 0 - drawing_bounds[1]
        drawing.translate(dx, dy)
    drawing_bounds = drawing.getBounds()
    drawing.width = abs(drawing_bounds[2] - drawing_bounds[0])
    drawing.height = abs(drawing_bounds[3] - drawing_bounds[1])


def grid_info_by_full_id(grids_info: list, full_id: str) -> dict:
    """A function to return a grid information dictionary."""
    for grid_info in grids_info:
        if grid_info['full_id'] == full_id:
            return grid_info
