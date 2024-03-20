import streamlit as st
from pathlib import Path
from functools import partial
import pandas as pd
import json
import numpy as np
from io import BytesIO
import datetime
from pdfrw import PdfReader
from pdfrw.buildxobj import pagexobj
from pdfrw.toreportlab import makerl

from pollination_io.interactors import Run

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import simpleSplit
from reportlab.lib.units import mm, cm, inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle, _baseFontNameB
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.graphics.shapes import Drawing, Circle, Rect, Polygon, Line, PolyLine, Group, String
from reportlab.graphics.widgets.adjustableArrow import AdjustableArrow
from reportlab.platypus import SimpleDocTemplate, BaseDocTemplate, Flowable, Paragraph, \
    Table, TableStyle, PageTemplate, Frame, PageBreak, NextPageTemplate, \
    Image, FrameBreak, Spacer, HRFlowable, CondPageBreak, KeepTogether
from reportlab.platypus.tableofcontents import TableOfContents

from ladybug.analysisperiod import AnalysisPeriod
from ladybug.datacollection import HourlyContinuousCollection
from ladybug.color import Colorset, ColorRange
from ladybug.legend import Legend, LegendParameters
from honeybee.model import Model, Room
from honeybee_radiance.modifier.material.glass import Glass

from results import load_from_folder
from plot import figure_grids, figure_aperture_group_schedule, figure_ase
from pdf.helper import scale_drawing, scale_drawing_to_width, scale_drawing_to_height, \
    create_north_arrow, draw_north_arrow, translate_group_relative, \
    drawing_dimensions_from_bounds, UNITS_AREA, ROWBACKGROUNDS
from pdf.flowables import PdfImage
from pdf.template import MyDocTemplate, NumberedPageCanvas, _header_and_footer
from pdf.styles import STYLES
from pdf.tables import table_from_summary_grid, create_metric_table
from pdf.colors import get_ase_cell_color, get_sda_cell_color
from pdf.drawings import draw_room_isometric, ViewOrientation


def create_pdf(
        output_file: Path, run_folder: Path, run: Run, report_data: dict, create_stories: bool, pagesize: tuple = A4, left_margin: float = 1.5*cm,
        right_margin: float = 1.5*cm, top_margin: float = 2*cm,
        bottom_margin: float = 2*cm,
    ):
    output_file = str(output_file)
    folder, vtjks_file, summary, summary_grid, states_schedule, \
        states_schedule_err, hb_model = load_from_folder(run_folder)
    if create_stories:
        hb_model.assign_stories_by_floor_height(overwrite=True)

    # Create a PDF document
    doc = MyDocTemplate(
        output_file, pagesize=pagesize, leftMargin=left_margin,
        rightMargin=right_margin, topMargin=top_margin,
        bottomMargin=bottom_margin, showBoundary=False, skip_pages=1,
        start_on_skip_pages=True
    )

    title_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, showBoundary=0, id='title-frame')

    header_content = Paragraph('', STYLES['Normal'])
    footer_content = Paragraph('LEED Daylight Option I', STYLES['Normal'])
    pollination_image = st.session_state.target_folder.joinpath('assets', 'images', 'pollination.png')
    title_page_template = PageTemplate(id='title-page', frames=[title_frame], pagesize=pagesize)
    base_template = PageTemplate(
        'base',
        [Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='base-frame',
               leftPadding=0, bottomPadding=0, rightPadding=0, topPadding=0)],
        onPage=partial(_header_and_footer, header_content=header_content, footer_content=footer_content, logo=pollination_image)
    )
    doc.addPageTemplates(title_page_template)
    doc.addPageTemplates(base_template)

    story = []

    ### TITLE PAGE
    front_page_table = Table(
        [
            [Paragraph('LEED Daylight Option I Report', STYLES['h1_c'])],
            [Paragraph(f'Project: {report_data["project"]}', STYLES['h2_c'])],
            [],
            [Paragraph(f'Prepared by: {report_data["prepared_by"]}', STYLES['Normal_CENTER'])],
            [Paragraph(f'Date created: {datetime.datetime.today().strftime("%B %d, %Y")}', STYLES['Normal_CENTER'])]
        ]
    )
    host_table = Table(
        [[front_page_table]], colWidths=[doc.width]
    )
    # add spacer to center the table vertically
    story.append(Spacer(width=0*cm, height=doc.height/2-host_table.wrap(0, 0)[1]))
    story.append(host_table)
    story.append(NextPageTemplate('base'))
    story.append(PageBreak())

    ### TABLE OF CONTENTS
    toc = TableOfContents()
    toc.dotsMinLevel = 0
    story.append(toc)
    story.append(PageBreak())

    ### SUMMARY PAGE
    story.append(Paragraph("Summary", STYLES['h1']))

    if summary['credits'] > 0:
        story.append(
            Paragraph(f'LEED Credits: {summary["credits"]}', style=STYLES['h2'].clone(name='h2_GREEN', textColor='green'))
        )
    else:
        story.append(
            Paragraph(f'LEED Credits: {summary["credits"]}', style=STYLES['h2'].clone(name='h2_BLACK', textColor='black'))
        )
    story.append(Spacer(width=0*cm, height=0.5*cm))

    if 'note' in summary:
        story.append(Paragraph(summary['note'], style=STYLES['BodyText']))
        story.append(Spacer(width=0*cm, height=0.5*cm))

    _metric_table = create_metric_table(doc, summary['sda'], summary['ase'])
    story.append(_metric_table)
    story.append(Spacer(width=0*cm, height=0.5*cm))

    story.append(Paragraph("Space Overview", style=STYLES['h2']))
    table, ase_notes = table_from_summary_grid(hb_model, summary_grid)
    story.append(table)

    if not all(n=='' for n in ase_notes):
        ase_note = Paragraph('1) The Annual Sunlight Exposure is greater than '
                             '10% for this space. Identify in writing how the '
                             'space is designed to address glare.')
        story.append(Spacer(width=0*cm, height=0.5*cm))
        story.append(ase_note)

    story.append(PageBreak())

    ### STORY SUMMARY
    with open(folder.joinpath('grids_info.json')) as json_file:
        grids_info = json.load(json_file)

    sensor_grids = hb_model.properties.radiance.sensor_grids
    sensor_grids = {sg.full_identifier: sg for sg in sensor_grids}

    rooms_by_story = {story_id: [] for story_id in sorted(hb_model.stories)}
    for room in hb_model.rooms:
        if room.story in rooms_by_story:
            rooms_by_story[room.story].append(room)
    for story_id, rooms in rooms_by_story.items():
        story.append(Paragraph(story_id, style=STYLES['h1']))
        story.append(Spacer(width=0*cm, height=0.5*cm))

        horiz_bounds = [room.horizontal_boundary() for room in rooms]
        rooms_min = Room._calculate_min(horiz_bounds)
        rooms_max = Room._calculate_max(horiz_bounds)

        _width = rooms_max.x - rooms_min.x
        _height = rooms_max.y - rooms_min.y
        _ratio = _width / _height
        drawing_scale = 200
        drawing_width = (_width / drawing_scale) * 1000 * mm
        drawing_height = drawing_width / _ratio
        da_drawing = Drawing(drawing_width, drawing_height)
        da_drawing_pf = Drawing(drawing_width, drawing_height)
        hrs_above_drawing = Drawing(drawing_width, drawing_height)
        hrs_above_drawing_pf = Drawing(drawing_width, drawing_height)

        floor_area = 0
        floor_area_passing_sda = 0
        floor_area_passing_ase = 0
        floor_sensor_grids = []
        for room in rooms:
            for sensor_grid in sensor_grids.values():
                if sensor_grid.room_identifier == room.identifier:
                    floor_area += summary_grid[sensor_grid.full_identifier]['total_floor_area']
                    floor_area_passing_sda += summary_grid[sensor_grid.full_identifier]['floor_area_passing_sda']
                    floor_area_passing_ase += summary_grid[sensor_grid.full_identifier]['floor_area_passing_ase']
                    floor_sensor_grids.append(sensor_grid.full_identifier)

                    mesh = sensor_grid.mesh
                    faces = mesh.faces
                    faces_centroids = mesh.face_centroids

                    da = np.loadtxt(run_folder.joinpath('leed-summary', 'results', 'da', f'{sensor_grid.full_identifier}.da'))
                    da_color_range = ColorRange(colors=Colorset.annual_comfort(), domain=[0, 100])
                    hrs_above = np.loadtxt(run_folder.joinpath('leed-summary', 'results', 'ase_hours_above', f'{sensor_grid.full_identifier}.res'))
                    hrs_above_color_range = ColorRange(colors=Colorset.original(), domain=[0, 250])
                    for face, face_centroid, _da, _hrs in zip(faces, faces_centroids, da, hrs_above):
                        vertices = [mesh.vertices[i] for i in face]
                        points = []
                        for vertex in vertices:
                            points.extend(
                                [
                                    np.interp(vertex.x, [rooms_min.x, rooms_max.x], [0, drawing_width]),
                                    np.interp(vertex.y, [rooms_min.y, rooms_max.y], [0, drawing_height])
                                ]
                            )

                        lb_color =  da_color_range.color(_da)
                        fillColor = colors.Color(lb_color.r / 255, lb_color.g / 255, lb_color.b / 255)
                        polygon = Polygon(points=points, fillColor=fillColor, strokeWidth=0, strokeColor=fillColor)
                        da_drawing.add(polygon)

                        if _da >= 50:
                            fillColor = colors.Color(0 / 255, 195 / 255, 0 / 255)
                        else:
                            fillColor = colors.Color(175 / 255, 175 / 255, 175 / 255)
                        circle = Circle(
                            np.interp(face_centroid.x, [rooms_min.x, rooms_max.x], [0, drawing_width]),
                            np.interp(face_centroid.y, [rooms_min.y, rooms_max.y], [0, drawing_height]),
                            ((2 * 250 * mm) / 2 ) * 0.85 / drawing_scale,
                            fillColor=fillColor,
                            strokeWidth=0,
                            strokeOpacity=0
                        )
                        da_drawing_pf.add(circle)

                        lb_color =  hrs_above_color_range.color(_hrs)
                        fillColor = colors.Color(lb_color.r / 255, lb_color.g / 255, lb_color.b / 255)
                        polygon = Polygon(
                            points=points,
                            fillColor=fillColor,
                            strokeWidth=0,
                            strokeColor=fillColor
                        )
                        hrs_above_drawing.add(polygon)

                        if _hrs > 250:
                            fillColor = colors.Color(175 / 255, 175 / 255, 175 / 255)
                        else:
                            fillColor = colors.Color(0 / 255, 195 / 255, 0 / 255)
                        polygon = Circle(
                            np.interp(face_centroid.x, [rooms_min.x, rooms_max.x], [0, drawing_width]),
                            np.interp(face_centroid.y, [rooms_min.y, rooms_max.y], [0, drawing_height]),
                            ((2 * 250 * mm) / 2 ) * 0.85 / drawing_scale,
                            fillColor=fillColor,
                            strokeWidth=0,
                            strokeOpacity=0
                        )
                        hrs_above_drawing_pf.add(polygon)

            horiz_bound = room.horizontal_boundary()
            horiz_bound_vertices = horiz_bound.vertices
            points = []
            horiz_bound_vertices = horiz_bound_vertices + (horiz_bound_vertices[0],)
            for vertex in horiz_bound_vertices:
                points.extend(
                    [
                        np.interp(vertex.x, [rooms_min.x, rooms_max.x], [0, drawing_width]),
                        np.interp(vertex.y, [rooms_min.y, rooms_max.y], [0, drawing_height])
                    ]
                )
            polygon = Polygon(points=points, strokeWidth=0.2, fillOpacity=0)
            da_drawing.add(polygon)
            da_drawing_pf.add(polygon)
            hrs_above_drawing.add(polygon)
            hrs_above_drawing_pf.add(polygon)

            # draw vertical apertures
            for aperture in room.apertures:
                if aperture.normal.z == 0:
                    aperture_min = aperture.geometry.lower_left_corner
                    aperture_max = aperture.geometry.lower_right_corner
                    strokeColor = colors.Color(95 / 255, 195 / 255, 255 / 255)
                    line = Line(np.interp(aperture_min.x, [rooms_min.x, rooms_max.x], [0, drawing_width]),
                                np.interp(aperture_min.y, [rooms_min.y, rooms_max.y], [0, drawing_height]),
                                np.interp(aperture_max.x, [rooms_min.x, rooms_max.x], [0, drawing_width]),
                                np.interp(aperture_max.y, [rooms_min.y, rooms_max.y], [0, drawing_height]),
                                strokeColor=strokeColor,
                                strokeWidth=0.5
                                )
                    da_drawing.add(line)
                    da_drawing_pf.add(line)
                    hrs_above_drawing.add(line)
                    hrs_above_drawing_pf.add(line)

        floor_sda = floor_area_passing_sda / floor_area * 100
        floor_ase = 100 - (floor_area_passing_ase / floor_area * 100)

        _metric_table = create_metric_table(doc, round(floor_sda, 2), round(floor_ase, 2))
        story.append(_metric_table)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        table, ase_notes = table_from_summary_grid(hb_model, summary_grid, grid_filter=floor_sensor_grids)
        story.append(table)

        if not all(n=='' for n in ase_notes):
            ase_note = Paragraph('1) The Annual Sunlight Exposure is greater than '
                                '10% for this space. Identify in writing how the '
                                'space is designed to address glare.')
            story.append(Spacer(width=0*cm, height=0.5*cm))
            story.append(ase_note)

        section_header = Paragraph('Daylight Autonomy', style=STYLES['h2'])

        legend_north_drawing = Drawing(0, 0)
        north_arrow_group = create_north_arrow(0, 10)
        group_bounds = north_arrow_group.getBounds()
        if group_bounds[0] < 0 or group_bounds[1] < 0:
            dx = 0
            dy = 0
            if group_bounds[0] < 0:
                dx = abs(group_bounds[0])
            if group_bounds[1] < 0:
                dy = abs(group_bounds[1])
            north_arrow_group.translate(dx, dy)
        legend_north_drawing.add(north_arrow_group)

        legend_par = LegendParameters(min=0, max=100, segment_count=11, colors=Colorset.annual_comfort())
        legend_par.vertical = False
        legend_par.segment_height = 5
        legend_par.segment_width = 20
        legend_par.decimal_count = 0
        legend = Legend([0, 100], legend_parameters=legend_par)

        drawing = Drawing(0, 0)
        group = Group()
        segment_min, segment_max = legend.segment_mesh.min, legend.segment_mesh.max
        for segment_number, face, segment_color, segment_text_location in zip(legend.segment_numbers, legend.segment_mesh_scene_2d.face_vertices, legend.segment_colors, legend.segment_text_location):
            points = []
            stl_x, stl_y, stl_z = segment_text_location.o.to_array()
            fillColor = colors.Color(segment_color.r / 255, segment_color.g / 255, segment_color.b / 255)
            for vertex in face:
                points.extend([vertex.x, vertex.y])
            polygon = Polygon(points=points, fillColor=fillColor, strokeWidth=0, strokeColor=fillColor)
            group.add(polygon)
            drawing.add(polygon)
            string = String(x=stl_x, y=-5*1.1, text=str(int(segment_number)), textAnchor='start', fontName='Helvetica', fontSize=5)
            group.add(string)
            drawing.add(string)
        string = String(x=segment_min.x-5, y=0, text='Daylight Autonomy (300 lux) [%]',textAnchor='end', fontName='Helvetica', fontSize=5)
        group.add(string)
        drawing.add(string)
        drawing_bounds = drawing.getBounds()
        dx = abs(0 - drawing_bounds[0])
        dy = abs(0 - drawing_bounds[1])
        drawing.translate(dx, dy)
        drawing_dimensions_from_bounds(drawing)

        translate_group_relative(group, north_arrow_group, anchor='e', padding=5)
        legend_north_drawing.add(group)
        drawing_dimensions_from_bounds(legend_north_drawing)
        da_drawing = scale_drawing_to_width(da_drawing, doc.width)
        da_group = KeepTogether(flowables=[section_header, da_drawing, Spacer(width=0*cm, height=0.5*cm), legend_north_drawing])
        story.append(da_group)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        section_header = Paragraph('Daylight Autonomy | Pass / Fail', style=STYLES['h2'])

        legend_north_drawing = Drawing(0, 0)
        north_arrow_group = create_north_arrow(0, 10)
        group_bounds = north_arrow_group.getBounds()
        if group_bounds[0] < 0 or group_bounds[1] < 0:
            dx = 0
            dy = 0
            if group_bounds[0] < 0:
                dx = abs(group_bounds[0])
            if group_bounds[1] < 0:
                dy = abs(group_bounds[1])
            north_arrow_group.translate(dx, dy)
        legend_north_drawing.add(north_arrow_group)

        rectangles = Group(
            Rect(-50, 0, 50, 5, fillColor=colors.Color(175 / 255, 175 / 255, 175 / 255), strokeWidth=0, strokeColor=colors.Color(155 / 255, 155 / 255, 155 / 255)),
            Rect(0, 0, 50, 5, fillColor=colors.Color(0 / 255, 195 / 255, 0 / 255), strokeWidth=0, strokeColor=colors.Color(0 / 255, 195 / 255, 0 / 255)),
            String(x=0, y=-5*1.1, text='50',textAnchor='middle', fontName='Helvetica', fontSize=5),
            String(x=-50, y=-5*1.1, text='0',textAnchor='start', fontName='Helvetica', fontSize=5),
            String(x=50, y=-5*1.1, text='100',textAnchor='end', fontName='Helvetica', fontSize=5),
            String(x=-50-5, y=0, text='Daylight Autonomy (300 lux) [%]',textAnchor='end', fontName='Helvetica', fontSize=5)
        )

        translate_group_relative(rectangles, north_arrow_group, 'e', 5)
        legend_north_drawing.add(rectangles)
        drawing_dimensions_from_bounds(legend_north_drawing)
        da_drawing_pf = scale_drawing_to_width(da_drawing_pf, doc.width)
        da_pf_group = KeepTogether(flowables=[section_header, da_drawing_pf, Spacer(width=0*cm, height=0.5*cm), legend_north_drawing])
        story.append(da_pf_group)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        section_header = Paragraph('Direct Sunlight', style=STYLES['h2'])

        legend_north_drawing = Drawing(0, 0)
        north_arrow_group = create_north_arrow(0, 10)
        group_bounds = north_arrow_group.getBounds()
        if group_bounds[0] < 0 or group_bounds[1] < 0:
            dx = 0
            dy = 0
            if group_bounds[0] < 0:
                dx = abs(group_bounds[0])
            if group_bounds[1] < 0:
                dy = abs(group_bounds[1])
            north_arrow_group.translate(dx, dy)
        legend_north_drawing.add(north_arrow_group)

        legend_par = LegendParameters(min=0, max=250, segment_count=11, colors=Colorset.original())
        legend_par.vertical = False
        legend_par.segment_height = 5
        legend_par.segment_width = 20
        legend_par.decimal_count = 0
        legend = Legend([0, 250], legend_parameters=legend_par)
        drawing = Drawing(0, 0)
        group = Group()
        segment_min, segment_max = legend.segment_mesh.min, legend.segment_mesh.max
        for segment_number, face, segment_color, segment_text_location in zip(legend.segment_numbers, legend.segment_mesh_scene_2d.face_vertices, legend.segment_colors, legend.segment_text_location):
            points = []
            stl_x, stl_y, stl_z = segment_text_location.o.to_array()
            fillColor = colors.Color(segment_color.r / 255, segment_color.g / 255, segment_color.b / 255)
            for vertex in face:
                points.extend([vertex.x, vertex.y])
            polygon = Polygon(points=points, fillColor=fillColor, strokeWidth=0, strokeColor=fillColor)
            group.add(polygon)
            drawing.add(polygon)
            string = String(x=stl_x, y=-5*1.1, text=str(int(segment_number)), textAnchor='start', fontName='Helvetica', fontSize=5)
            group.add(string)
            drawing.add(string)
        string = String(x=segment_min.x-5, y=0, text='Direct Sunlight (1000 lux) [hrs]',textAnchor='end', fontName='Helvetica', fontSize=5)
        group.add(string)
        drawing.add(string)
        drawing_bounds = drawing.getBounds()
        dx = abs(0 - drawing_bounds[0])
        dy = abs(0 - drawing_bounds[1])
        drawing.translate(dx, dy)
        drawing_dimensions_from_bounds(drawing)

        translate_group_relative(group, north_arrow_group, 'e', 5)
        legend_north_drawing.add(group)
        drawing_dimensions_from_bounds(legend_north_drawing)
        hrs_above_drawing = scale_drawing_to_width(hrs_above_drawing, doc.width)
        hrs_above_group = KeepTogether(flowables=[section_header, hrs_above_drawing, Spacer(width=0*cm, height=0.5*cm), legend_north_drawing])
        story.append(hrs_above_group)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        section_header = Paragraph('Direct Sunlight | Pass / Fail', style=STYLES['h2'])
        legend_north_drawing = Drawing(0, 0)
        north_arrow_group = create_north_arrow(0, 10)
        group_bounds = north_arrow_group.getBounds()
        if group_bounds[0] < 0 or group_bounds[1] < 0:
            dx = 0
            dy = 0
            if group_bounds[0] < 0:
                dx = abs(group_bounds[0])
            if group_bounds[1] < 0:
                dy = abs(group_bounds[1])
            north_arrow_group.translate(dx, dy)
        legend_north_drawing.add(north_arrow_group)

        rectangles = Group(
            Rect(-50, 0, 50, 5, fillColor=colors.Color(0 / 255, 195 / 255, 0 / 255), strokeWidth=0, strokeColor=colors.Color(0 / 255, 195 / 255, 0 / 255)),
            Rect(0, 0, 50, 5, fillColor=colors.Color(175 / 255, 175 / 255, 175 / 255), strokeWidth=0, strokeColor=colors.Color(155 / 255, 155 / 255, 155 / 255)),
            String(x=0, y=-5*1.1, text='250',textAnchor='middle', fontName='Helvetica', fontSize=5),
            String(x=-50, y=-5*1.1, text='0',textAnchor='start', fontName='Helvetica', fontSize=5),
            String(x=-50-5, y=0, text='Direct Sunlight (1000 lux) [hrs]',textAnchor='end', fontName='Helvetica', fontSize=5)
        )

        translate_group_relative(rectangles, north_arrow_group, 'e', 5)
        legend_north_drawing.add(rectangles)
        drawing_dimensions_from_bounds(legend_north_drawing)
        hrs_above_drawing_pf = scale_drawing_to_width(hrs_above_drawing_pf, doc.width)
        hrs_above_pf_group = KeepTogether(flowables=[section_header, hrs_above_drawing_pf, Spacer(width=0*cm, height=0.5*cm), legend_north_drawing])
        story.append(hrs_above_pf_group)
        story.append(PageBreak())

    # SUMMARY OF EACH GRID
    for grid_summary in summary_grid.values():
        grid_name = grid_summary['name']
        grid_id = grid_summary['full_id']
        sensor_grid = sensor_grids[grid_id]
        # get room object
        room: Room = hb_model.rooms_by_identifier([sensor_grid.room_identifier])[0]

        story.append(Paragraph(grid_name, style=STYLES['h1']))
        story.append(Spacer(width=0*cm, height=0.5*cm))

        _sda_table = Table(data=[[Paragraph(f'sDA: {grid_summary["sda"]}%', style=STYLES['h2_c'])]], rowHeights=[16*mm])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('ROUNDEDCORNERS', [10, 10, 10, 10]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ])
        table_style.add('BACKGROUND', (0, 0), (0, 0), get_sda_cell_color(grid_summary["sda"]))
        _sda_table.setStyle(table_style)

        _ase_table = Table(data=[[Paragraph(f'ASE: {grid_summary["ase"]}%', style=STYLES['h2_c'])]], rowHeights=[16*mm])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('ROUNDEDCORNERS', [10, 10, 10, 10]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ])
        table_style.add('BACKGROUND', (0, 0), (0, 0), get_ase_cell_color(grid_summary["ase"]))
        _ase_table.setStyle(table_style)
        table_style = TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        ])
        _metric_table = Table(data=[[_sda_table, '',_ase_table]], colWidths=[doc.width*0.45, None, doc.width*0.45])
        _metric_table.setStyle(table_style)
        story.append(_metric_table)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        # heat map
        horiz_bound = room.horizontal_boundary()
        room_min = room.min
        room_max = room.max
        horiz_bound_vertices = horiz_bound.vertices
        mesh = sensor_grid.mesh
        faces = mesh.faces
        faces_centroids = mesh.face_centroids
        _width = room_max.x - room_min.x
        _height = room_max.y - room_min.y
        _ratio = _width / _height
        drawing_scale = 200
        drawing_width = (_width / drawing_scale) * 1000 * mm
        drawing_height = drawing_width / _ratio

        da_drawing = Drawing(drawing_width, drawing_height)
        da = np.loadtxt(run_folder.joinpath('leed-summary', 'results', 'da', f'{grid_id}.da'))
        hrs_above_drawing = Drawing(drawing_width, drawing_height)
        hrs_above = np.loadtxt(run_folder.joinpath('leed-summary', 'results', 'ase_hours_above', f'{grid_id}.res'))
        da_color_range = ColorRange(colors=Colorset.annual_comfort(), domain=[0, 100])
        hrs_above_color_range = ColorRange(colors=Colorset.original(), domain=[0, 250])

        for face, face_centroid, _da, _hrs in zip(faces, faces_centroids, da, hrs_above):
            vertices = [mesh.vertices[i] for i in face]
            points = []
            for vertex in vertices:
                points.extend(
                    [
                        np.interp(vertex.x, [room_min.x, room_max.x], [0, drawing_width]),
                        np.interp(vertex.y, [room_min.y, room_max.y], [0, drawing_height])
                    ]
                )

            lb_color =  da_color_range.color(_da)
            fillColor = colors.Color(lb_color.r / 255, lb_color.g / 255, lb_color.b / 255)
            polygon = Polygon(points=points, fillColor=fillColor, strokeColor=fillColor, strokeWidth=0)
            da_drawing.add(polygon)

            lb_color =  hrs_above_color_range.color(_hrs)
            fillColor = colors.Color(lb_color.r / 255, lb_color.g / 255, lb_color.b / 255)
            polygon = Polygon(points=points, fillColor=fillColor, strokeColor=fillColor, strokeWidth=0)
            hrs_above_drawing.add(polygon)

        points = []
        horiz_bound_vertices = horiz_bound_vertices + (horiz_bound_vertices[0],)
        for vertex in horiz_bound_vertices:
            points.extend(
                [
                    np.interp(vertex.x, [room_min.x, room_max.x], [0, drawing_width]),
                    np.interp(vertex.y, [room_min.y, room_max.y], [0, drawing_height])
                ]
            )
        polygon = Polygon(points=points, strokeWidth=0.2, fillOpacity=0)
        hrs_above_drawing.add(polygon)
        da_drawing.add(polygon)

        room = hb_model.rooms_by_identifier([sensor_grid.room_identifier])[0]
        # draw vertical apertures
        for aperture in room.apertures:
            if aperture.normal.z == 0:
                aperture_min = aperture.geometry.lower_left_corner
                aperture_max = aperture.geometry.lower_right_corner
                strokeColor = colors.Color(95 / 255, 195 / 255, 255 / 255)
                line = Line(np.interp(aperture_min.x, [room_min.x, room_max.x], [0, drawing_width]),
                            np.interp(aperture_min.y, [room_min.y, room_max.y], [0, drawing_height]),
                            np.interp(aperture_max.x, [room_min.x, room_max.x], [0, drawing_width]),
                            np.interp(aperture_max.y, [room_min.y, room_max.y], [0, drawing_height]),
                            strokeColor=strokeColor,
                            strokeWidth=0.5
                            )
                da_drawing.add(line)
                hrs_above_drawing.add(line)

        #scale_drawing_to_width(da_drawing, doc.width*0.45)
        # _da_heatmap_table = Table(data=[[da_drawing]])
        # table_style = TableStyle([
        #     ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        #     ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        # ])
        # _da_heatmap_table.setStyle(table_style)

        # scale_drawing_to_width(hrs_above_drawing, doc.width*0.45)
        # _hrs_above_heatmap_table = Table(data=[[hrs_above_drawing]])
        # table_style = TableStyle([
        #     ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        #     ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        # ])
        # _hrs_above_heatmap_table.setStyle(table_style)

        # table_style = TableStyle([
        #     ('LEFTPADDING', (0, 0), (-1, -1), 0),
        #     ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        #     ('TOPPADDING', (0, 0), (-1, -1), 0),
        #     ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        # ])
        _heatmap_table = Table(data=[[scale_drawing_to_width(da_drawing, doc.width*0.45), '', scale_drawing_to_width(hrs_above_drawing, doc.width*0.45)]], colWidths=[doc.width*0.45, None, doc.width*0.45])
        _heatmap_table.setStyle(table_style)
        story.append(_heatmap_table)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        legend_da = Drawing(0, 0)
        north_arrow_group = create_north_arrow(0, 10)
        group_bounds = north_arrow_group.getBounds()
        if group_bounds[0] < 0 or group_bounds[1] < 0:
            dx = 0
            dy = 0
            if group_bounds[0] < 0:
                dx = abs(group_bounds[0])
            if group_bounds[1] < 0:
                dy = abs(group_bounds[1])
            north_arrow_group.translate(dx, dy)
        legend_da.add(north_arrow_group)

        legend_par = LegendParameters(min=0, max=100, segment_count=11, colors=Colorset.annual_comfort())
        legend_par.vertical = False
        legend_par.segment_height = 5
        legend_par.segment_width = 10
        legend_par.decimal_count = 0
        legend = Legend([0, 100], legend_parameters=legend_par)

        drawing = Drawing(0, 0)
        group = Group()
        segment_min, segment_max = legend.segment_mesh.min, legend.segment_mesh.max
        for segment_number, face, segment_color, segment_text_location in zip(legend.segment_numbers, legend.segment_mesh_scene_2d.face_vertices, legend.segment_colors, legend.segment_text_location):
            points = []
            stl_x, stl_y, stl_z = segment_text_location.o.to_array()
            fillColor = colors.Color(segment_color.r / 255, segment_color.g / 255, segment_color.b / 255)
            for vertex in face:
                points.extend([vertex.x, vertex.y])
            polygon = Polygon(points=points, fillColor=fillColor, strokeWidth=0, strokeColor=fillColor)
            group.add(polygon)
            drawing.add(polygon)
            string = String(x=stl_x, y=-5*1.1, text=str(int(segment_number)), textAnchor='start', fontName='Helvetica', fontSize=5)
            group.add(string)
            drawing.add(string)
        string = String(x=segment_min.x-5, y=0, text='Daylight Autonomy (300 lux) [%]',textAnchor='end', fontName='Helvetica', fontSize=5)
        group.add(string)
        drawing.add(string)
        drawing_bounds = drawing.getBounds()
        dx = abs(0 - drawing_bounds[0])
        dy = abs(0 - drawing_bounds[1])
        drawing.translate(dx, dy)
        drawing_dimensions_from_bounds(drawing)

        translate_group_relative(group, north_arrow_group, anchor='e', padding=5)
        legend_da.add(group)
        drawing_dimensions_from_bounds(legend_da)

        legend_hrs_above = Drawing(0, 0)
        north_arrow_group = create_north_arrow(0, 10)
        group_bounds = north_arrow_group.getBounds()
        if group_bounds[0] < 0 or group_bounds[1] < 0:
            dx = 0
            dy = 0
            if group_bounds[0] < 0:
                dx = abs(group_bounds[0])
            if group_bounds[1] < 0:
                dy = abs(group_bounds[1])
            north_arrow_group.translate(dx, dy)
        legend_hrs_above.add(north_arrow_group)

        legend_par = LegendParameters(min=0, max=250, segment_count=11, colors=Colorset.original())
        legend_par.vertical = False
        legend_par.segment_height = 5
        legend_par.segment_width = 10
        legend_par.decimal_count = 0
        legend = Legend([0, 250], legend_parameters=legend_par)
        drawing = Drawing(0, 0)
        group = Group()
        segment_min, segment_max = legend.segment_mesh.min, legend.segment_mesh.max
        for segment_number, face, segment_color, segment_text_location in zip(legend.segment_numbers, legend.segment_mesh_scene_2d.face_vertices, legend.segment_colors, legend.segment_text_location):
            points = []
            stl_x, stl_y, stl_z = segment_text_location.o.to_array()
            fillColor = colors.Color(segment_color.r / 255, segment_color.g / 255, segment_color.b / 255)
            for vertex in face:
                points.extend([vertex.x, vertex.y])
            polygon = Polygon(points=points, fillColor=fillColor, strokeWidth=0, strokeColor=fillColor)
            group.add(polygon)
            drawing.add(polygon)
            string = String(x=stl_x, y=-5*1.1, text=str(int(segment_number)), textAnchor='start', fontName='Helvetica', fontSize=5)
            group.add(string)
            drawing.add(string)
        string = String(x=segment_min.x-5, y=0, text='Direct Sunlight (1000 lux) [hrs]',textAnchor='end', fontName='Helvetica', fontSize=5)
        group.add(string)
        drawing.add(string)
        drawing_bounds = drawing.getBounds()
        dx = abs(0 - drawing_bounds[0])
        dy = abs(0 - drawing_bounds[1])
        drawing.translate(dx, dy)
        drawing_dimensions_from_bounds(drawing)

        translate_group_relative(group, north_arrow_group, 'e', 5)
        legend_hrs_above.add(group)
        drawing_dimensions_from_bounds(legend_hrs_above)

        legends_table = Table(data=[[scale_drawing_to_width(legend_da, doc.width*0.45), '', scale_drawing_to_width(legend_hrs_above, doc.width*0.45)]], colWidths=[doc.width*0.45, None, doc.width*0.45])
        
        table_style = TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        ])
        legends_table.setStyle(table_style)
        story.append(legends_table)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        if states_schedule_err.get(grid_name, None):
                    story.append(Paragraph('Space did not pass \'2% rule\'', style=STYLES['h2']))
                    body_text = (
                        'There is at least one hour where 2% of the floor area '
                        'receives direct illuminance of 1000 lux or more. These are '
                        'hours where no combination of blinds was able to reduce the '
                        'direct illuminance below the target of 2% of the floor area. '
                        'The hours are visualized in below.'
                    )
                    story.append(Paragraph(body_text, style=STYLES['BodyText']))
                    figure = figure_grids(grid_name, states_schedule_err)
                    fig_pdf = figure.to_image(format='pdf', width=700, height=350, scale=3)
                    pdf_image =  PdfImage(BytesIO(fig_pdf), width=doc.width*0.60, height=None, keep_ratio=True)
                    pdf_table = Table([[pdf_image]])
                    pdf_table.setStyle(
                        TableStyle([
                            ('LEFTPADDING', (0, 0), (-1, -1), 0),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                            ('TOPPADDING', (0, 0), (-1, -1), 0),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
                        ])
                    )
                    two_pct_pf_table = Table([['', pdf_table, '']], colWidths='*')
                    two_pct_pf_table.setStyle(
                        TableStyle([
                            ('LEFTPADDING', (0, 0), (-1, -1), 0),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                            ('TOPPADDING', (0, 0), (-1, -1), 0),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTRE'),
                            ('VALIGN', (0, 0), (-1, -1), 'TOP')
                        ]) 
                    )
                    story.append(two_pct_pf_table)
                    story.append(Spacer(width=0*cm, height=0.5*cm))

        table, ase_notes = table_from_summary_grid(hb_model, summary_grid, [grid_id], add_total=False)

        story.append(table)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        ase_note = grid_summary.get('ase_note')
        if ase_note:
            story.append(Paragraph(ase_note, style=STYLES['Normal']))

        for grid_info in grids_info:
            if grid_id == grid_info['full_id']:
                break

        light_paths = [elem for lp in grid_info['light_path'] for elem in lp]
        ap = AnalysisPeriod(st_hour=8, end_hour=17)
        story.append(Paragraph('Aperture Groups', style=STYLES['h2']))
        body_text = (
            f'This section present the Aperture Groups for the space <b>{grid_id}</b>. '
            'The shading schedule of each Aperture Group is visualized in an '
            'annual heat map. The shading schedule has two states: <i>Shading On</i> '
            'and <i>Shading Off</i>. The percentage of occupied hours for both '
            'states is presented in a table.'
        )
        story.append(Paragraph(body_text, style=STYLES['BodyText']))

        for aperture_group in light_paths:
            if aperture_group == '__static_apertures__':
                break
            aperture_group_header = Paragraph(aperture_group, style=STYLES['h3'])

            aperture_data = []
            aperture_data.append(
                [
                    Paragraph('Name', style=STYLES['Normal_BOLD']),
                    Paragraph(f'Area [{UNITS_AREA[hb_model.units]}2]', style=STYLES['Normal_BOLD']),
                    Paragraph('Transmittance', style=STYLES['Normal_BOLD'])
                ]
            )
            for aperture in room.apertures:
                if aperture.properties.radiance.dynamic_group_identifier == aperture_group:
                    modifier = aperture.properties.radiance.modifier
                    if isinstance(modifier, Glass):
                        average_transmittance = round(modifier.average_transmittance, 2)
                    else:
                        average_transmittance = ''
                    aperture_data.append([
                        aperture.display_name,
                        round(aperture.area, 2),
                        average_transmittance
                    ])
            aperture_table = Table(data=aperture_data)
            aperture_table.setStyle(
                TableStyle([
                    ('LINEBELOW', (0, 0), (-1, 0), 0.2, colors.black),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), ROWBACKGROUNDS)
                ])
            )

            drawing_3d = draw_room_isometric(room, orientation=ViewOrientation.SE, dynamic_group_identifier=aperture_group)

            #colWidths = [doc.width*(1/2), doc.width*(1/2)]
            drawing_table = Table([[scale_drawing_to_height(drawing_3d, 3*cm)]])
            drawing_table.setStyle(
                TableStyle([
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTRE'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP')
                ])
            )

            # table_1 = Table([[aperture_table, drawing_table]], colWidths=colWidths)
            # table_1.setStyle(
            #     TableStyle([
            #         ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            #         ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            #         ('LEFTPADDING', (0, 0), (-1, -1), 0),
            #         ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            #         ('TOPPADDING', (0, 0), (-1, -1), 0),
            #         ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
            #     ])
            # )

            datacollection = \
                HourlyContinuousCollection.from_dict(states_schedule[aperture_group])
            
            # filter by occupancy period
            filtered_datacollection = \
                datacollection.filter_by_analysis_period(analysis_period=ap)
            filtered_datacollection.total

            # get the percentage of occupied hours with shading on
            shading_on_pct = round(filtered_datacollection.values.count(1) \
                / 3650 * 100, 2)
            shading_off_pct = round(filtered_datacollection.values.count(0) \
                / 3650 * 100, 2)

            shading_data_table = [
                ['', Paragraph('Occupied Hours', style=STYLES['Normal_BOLD'])],
                ['Shading On', f'{shading_on_pct}%'],
                ['Shading Off', f'{shading_off_pct}%']
            ]
            shading_table = Table(data=shading_data_table)
            shading_table.setStyle(
                TableStyle([
                    ('LINEBELOW', (0, 0), (-1, 0), 0.2, colors.black),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), ROWBACKGROUNDS)
                ])
            )

            # get figure
            figure = figure_aperture_group_schedule(aperture_group, datacollection)
            fig_pdf = figure.to_image(format='pdf', width=700, height=350, scale=3)
            colWidths = [doc.width*0.35, None, doc.width*0.60]
            pdf_image =  PdfImage(BytesIO(fig_pdf), width=doc.width*0.60, height=None, keep_ratio=True)
            pdf_table = Table([[pdf_image]])
            pdf_table.setStyle(
                TableStyle([
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
                ])
            )

            table = Table([[shading_table, '', pdf_table]], colWidths=colWidths)
            table.setStyle(
                TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
                ])
            )
            story.append(Spacer(width=0*cm, height=0.5*cm))
            story.append(KeepTogether(flowables=[aperture_group_header, Spacer(width=0*cm, height=0.5*cm), drawing_table, aperture_table, Spacer(width=0*cm, height=0.5*cm), table]))

        story.append(PageBreak())
        break

    if run:
        story.append(Paragraph('Study Metadata', style=STYLES['h1']))
        story.append(Spacer(width=0*cm, height=0.5*cm))
        run_url = [
            'https://app.pollination.cloud', run.owner, 'projects',
            run.project, 'studies', run.job_id, 'runs', run.id
        ]
        run_url = '/'.join(run_url)
        study_info_data = []
        study_info_data.append(['Owner', run.owner])
        study_info_data.append(['Project', run.project])
        study_info_data.append(['Started At', run.status.started_at])
        study_info_data.append(['Finished At', run.status.finished_at])
        text = f'<a href="{run_url}"><u>Go to study on Pollination</u></a>'
        study_info_data.append([Paragraph(text, style=STYLES['Normal_URL'])])
        study_info_table = Table(study_info_data)
        story.append(study_info_table)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        recipe_data = []
        recipe_data.append([Paragraph('Recipe', style=STYLES['Normal_BOLD']), Paragraph('Version', style=STYLES['Normal_BOLD'])])
        recipe_data.append([run.recipe.name, run.recipe.tag])
        recipe_table = Table(recipe_data)
        story.append(recipe_table)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        _, input_parameters = next(run.job.runs_dataframe.input_parameters.iterrows())
        recipe_input_data = []
        recipe_input_data.append([Paragraph('Recipe Input', style=STYLES['Normal_BOLD']), Paragraph('Input Value', style=STYLES['Normal_BOLD'])])
        recipe_input_data.extend([[index, value] for index, value in input_parameters.items()])
        recipe_input_table = Table(recipe_input_data)
        story.append(recipe_input_table)

    # build and save the PDF
    doc.multiBuild(
        story,
        canvasmaker=partial(NumberedPageCanvas, skip_pages=doc.skip_pages, start_on_skip_pages=doc.start_on_skip_pages)
    )
