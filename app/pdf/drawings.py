import numpy as np
from enum import Enum

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Drawing, Polygon

from honeybee.model import Room

from pdf.helper import drawing_dimensions_from_bounds


class ViewOrientation(Enum):
    NE = 'NE'
    SE = 'SE'
    SW = 'SW'
    NW = 'NW'


ISOMETRICPROJECTMATRIX = {
    ViewOrientation.NE: np.array([
        [-np.sqrt(2) / 2, np.sqrt(2) / 2, 0, 0],
        [-1 / np.sqrt(6), -1 / np.sqrt(6), 2 / np.sqrt(6), 0],
        [0, 0, 0, 0],
        [0, 0, 0, 1]
    ]),
    ViewOrientation.SE: np.array([
        [np.sqrt(2) / 2, np.sqrt(2) / 2, 0, 0],
        [-1 / np.sqrt(6), 1 / np.sqrt(6), 2 / np.sqrt(6), 0],
        [0, 0, 0, 0],
        [0, 0, 0, 1]
    ]),
    ViewOrientation.SW: np.array([
        [np.sqrt(2) / 2, -np.sqrt(2) / 2, 0, 0],
        [1 / np.sqrt(6), 1 / np.sqrt(6), 2 / np.sqrt(6), 0],
        [0, 0, 0, 0],
        [0, 0, 0, 1]
    ]),
    ViewOrientation.NW: np.array([
        [-np.sqrt(2) / 2, -np.sqrt(2) / 2, 0, 0],
        [1 / np.sqrt(6), -1 / np.sqrt(6), 2 / np.sqrt(6), 0],
        [0, 0, 0, 0],
        [0, 0, 0, 1]
    ]),
}


def draw_room_isometric(
        room: Room, orientation: ViewOrientation = ViewOrientation.SE,
        dynamic_group_identifier: str = None):
    drawing_3d = Drawing(0, 0)
    points_projected = []
    faces_projected = []
    room.merge_coplanar_faces()
    apertures_projected = {}
    for face in room.faces:
        face_projected = []
        for vertex in face.vertices:
            point_3d = np.array(vertex.to_array())
            point_3d = np.append(point_3d, 1)

            projected_coordinates = np.dot(ISOMETRICPROJECTMATRIX[orientation], point_3d)
            face_projected.append(
                [projected_coordinates[0], projected_coordinates[1]]
            )
        faces_projected.append(face_projected)
        points_projected.extend(face_projected)

        for aperture in face.apertures:
            aperture_projected = []
            for vertex in aperture.vertices:
                point_3d = np.array(vertex.to_array())
                point_3d = np.append(point_3d, 1)
                projected_coordinates = np.dot(ISOMETRICPROJECTMATRIX[orientation], point_3d)
                aperture_projected.append(
                    [projected_coordinates[0], projected_coordinates[1]]
                )
            if not dynamic_group_identifier:
                apertures_projected[aperture.identifier] = {
                    'points': aperture_projected,
                    'fillColor': colors.Color(95 / 255, 195 / 255, 255 / 255),
                    'strokeColor': colors.Color(95 / 255, 195 / 255, 255 / 255)
                }
            elif aperture.properties.radiance.dynamic_group_identifier == dynamic_group_identifier:
                apertures_projected[aperture.identifier] = {
                    'points': aperture_projected,
                    'fillColor': colors.Color(95 / 255, 195 / 255, 255 / 255),
                    'strokeColor': colors.Color(95 / 255, 195 / 255, 255 / 255)
                }
            else:
                apertures_projected[aperture.identifier] = {
                    'points': aperture_projected,
                    'fillColor': colors.Color(220 / 255, 220 / 255, 220 / 255),
                    'strokeColor': colors.Color(220 / 255, 220 / 255, 220 / 255)
                }

            points_projected.extend(aperture_projected)

    min_x, min_y = np.array(points_projected).min(axis=0)
    max_x, max_y = np.array(points_projected).max(axis=0)
    __width = max_x - min_x
    __height = max_y - min_y
    __ratio = __width / __height
    __drawing_scale = 200
    __drawing_width = (__width / __drawing_scale) * 1000 * mm
    __drawing_height = __drawing_width / __ratio
    for aperture_data in apertures_projected.values():
        points = []
        for vertex in aperture_data['points']:
            points.extend(
                [
                    np.interp(vertex[0], [min_x, max_x], [0, __drawing_width]),
                    np.interp(vertex[1], [min_y, max_y], [0, __drawing_height])
                ]
            )
        fillColor = aperture_data['fillColor']
        strokeColor = aperture_data['strokeColor']
        drawing_3d.add(Polygon(points, fillColor=fillColor, strokeColor=strokeColor, strokeWidth=0.1, fillOpacity=0.3, strokeLineJoin=1))
    for face in faces_projected:
        points = []
        for vertex in face:
            points.extend(
                [
                    np.interp(vertex[0], [min_x, max_x], [0, __drawing_width]),
                    np.interp(vertex[1], [min_y, max_y], [0, __drawing_height])
                ]
            )
        drawing_3d.add(Polygon(points, strokeWidth=0.1, fillOpacity=0, strokeLineJoin=1))

    drawing_dimensions_from_bounds(drawing_3d)

    return drawing_3d
