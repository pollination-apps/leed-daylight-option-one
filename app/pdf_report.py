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
from honeybee_radiance.writer import _unique_modifiers
from ladybug.epw import EPW
from ladybug.wea import Wea

from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import simpleSplit
from reportlab.lib.units import mm, cm, inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle, _baseFontNameB
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.graphics.shapes import Drawing, Circle, Rect, Polygon, Line, PolyLine, Group, String
from reportlab.platypus import SimpleDocTemplate, BaseDocTemplate, Flowable, Paragraph, \
    Table, TableStyle, PageTemplate, Frame, PageBreak, NextPageTemplate, \
    Image, FrameBreak, Spacer, HRFlowable, CondPageBreak, KeepTogether, TopPadder, \
    UseUpSpace, AnchorFlowable, KeepInFrame
from reportlab.platypus.tableofcontents import TableOfContents

from ladybug.analysisperiod import AnalysisPeriod
from ladybug.datacollection import HourlyContinuousCollection
from ladybug.color import Colorset, ColorRange
from ladybug.legend import Legend, LegendParameters
from honeybee.model import Model, Room
from honeybee.units import conversion_factor_to_meters, parse_distance_string
from honeybee_radiance.modifier.material import Glass, Plastic

from results import load_from_folder
from plot import figure_grids, figure_aperture_group_schedule, figure_ase
from pdf.helper import scale_drawing, scale_drawing_to_width, scale_drawing_to_height, \
    create_north_arrow, draw_north_arrow, translate_group_relative, \
    drawing_dimensions_from_bounds, UNITS_ABBREVIATIONS, ROWBACKGROUNDS, grid_info_by_full_id
from pdf.flowables import PdfImage, CentrePadder
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
        start_on_skip_pages=True, title='LEED Daylight Option I'
    )

    title_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, showBoundary=0, id='title-frame')

    header_content = Paragraph('', STYLES['Normal'])
    footer_content = Paragraph('LEED Daylight Option I', STYLES['Normal'])
    pollination_image = st.session_state.target_folder.joinpath('assets', 'images', 'pollination.png')
    title_page_template = PageTemplate(id='title-page', frames=[title_frame], pagesize=pagesize)
    base_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                       id='base-frame', leftPadding=0, bottomPadding=0,
                       rightPadding=0, topPadding=0)
    base_template = PageTemplate(
        'base',
        [base_frame],
        onPage=partial(_header_and_footer, header_content=header_content, footer_content=footer_content, logo=pollination_image)
    )
    doc.addPageTemplates(title_page_template)
    doc.addPageTemplates(base_template)

    if run:
        _, input_artifacts = next(run.job.runs_dataframe.input_artifacts.iterrows())
        _bytes = run.job.download_artifact(input_artifacts.wea)
        weather_file = run_folder.joinpath('weather.wea')
        with open(weather_file, 'wb') as f:
            f.write(_bytes.getbuffer())
        with open(weather_file) as inf:
            first_word = inf.read(5)
        is_wea = True if first_word == 'place' else False
        if not is_wea:
            wea = Wea.from_epw_file(weather_file)
        else:
            wea = Wea.from_file(weather_file)

    story = []

    ### TITLE PAGE
    front_page_data = [
            [Paragraph('LEED Daylight Option I Report', STYLES['h1_c'])],
            [Paragraph(f'Project: {report_data["project"]}', STYLES['h2_c'])],
    ]
    if run:
        front_page_data.append([
            Paragraph(f'Location: {wea.location.city}', STYLES['h2_c'])
        ])
    front_page_data.append([])
    front_page_data.extend([
        [Paragraph(f'Prepared by: {report_data["prepared_by"]}', STYLES['Normal_CENTER'])],
        [Paragraph(f'Date created: {datetime.datetime.today().strftime("%B %d, %Y")}', STYLES['Normal_CENTER'])]
    ])
    front_page_table = Table(front_page_data)
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

    story.append(Paragraph('Levels Summary', STYLES['h1']))
    for story_id, rooms in rooms_by_story.items():
        story.append(Paragraph(story_id, style=STYLES['h2']))
        story.append(Spacer(width=0*cm, height=0.5*cm))

        horiz_bounds = [room.horizontal_boundary() for room in rooms]
        rooms_min = Room._calculate_min(horiz_bounds)
        rooms_max = Room._calculate_max(horiz_bounds)

        _width = rooms_max.x - rooms_min.x
        _height = rooms_max.y - rooms_min.y
        _ratio = _width / _height
        drawing_scale = 200
        drawing_width = parse_distance_string(f'{_width / drawing_scale}{UNITS_ABBREVIATIONS[hb_model.units]}', destination_units='Millimeters') * mm
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
                        max_x = float('-inf')
                        min_x = float('inf')
                        max_y = float('-inf')
                        min_y = float('inf')
                        for vertex in vertices:
                            points.extend(
                                [
                                    np.interp(vertex.x, [rooms_min.x, rooms_max.x], [0, drawing_width]),
                                    np.interp(vertex.y, [rooms_min.y, rooms_max.y], [0, drawing_height])
                                ]
                            )
                            if vertex.x > max_x:
                                max_x = vertex.x
                            if vertex.x < min_x:
                                min_x = vertex.x
                            if vertex.y > max_y:
                                max_y = vertex.y
                            if vertex.y < min_y:
                                min_y = vertex.y

                        circle_size = min([max_x - min_x, max_y - min_y])
                        circle_size_mm = parse_distance_string(f'{circle_size}{UNITS_ABBREVIATIONS[hb_model.units]}', destination_units='Millimeters')
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
                            (circle_size_mm * mm / 2) * 0.85  / drawing_scale,
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
                            (circle_size_mm * mm / 2) * 0.85 / drawing_scale,
                            fillColor=fillColor,
                            strokeWidth=0,
                            strokeOpacity=0
                        )
                        hrs_above_drawing_pf.add(polygon)

            # add room boundary Polygon
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

        story.append(PageBreak())
        section_story = []
        section_story.append(Paragraph('Daylight Autonomy', style=STYLES['h3']))
        body_text = (
            'The Daylight Autonomy is the percentage of occupied hours where '
            'the illuminance is 300 lux or higher. The average <b>sDA</b> for this '
            f'level is: <b>{round(floor_sda, 2)}%</b>. It is calculated based '
            'on shading schedules for each Aperture Group. The detailed shading '
            'schedules are visualized under each Room summary.'
        )
        section_story.append(Paragraph(body_text, style=STYLES['BodyText']))
        section_story.append(Spacer(width=0*cm, height=0.5*cm))

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

        legend_north_drawing_table = Table([[legend_north_drawing]])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        ])
        legend_north_drawing_table.setStyle(table_style)

        remaining_height = (base_frame._aH - sum([flowable.wrap(base_frame._aW, base_frame._aH)[1] for flowable in section_story]) - legend_north_drawing_table.wrap(base_frame._aW, base_frame._aH)[1]) * 0.98

        da_drawing_table = Table([[scale_drawing_to_width(da_drawing, doc.width*0.9, max_height=remaining_height)]], rowHeights=[remaining_height])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        ])
        da_drawing_table.setStyle(table_style)
        section_story.append(da_drawing_table)

        section_story.append(legend_north_drawing_table)
        story.append(KeepTogether(flowables=section_story))
        story.append(PageBreak())

        section_story = []
        section_story.append(Paragraph('Daylight Autonomy | Pass / Fail', style=STYLES['h3']))
        body_text = (
            'The Daylight Autonomy is the percentage of occupied hours where '
            'the illuminance is 300 lux or higher. The average <b>sDA</b> for this '
            f'level is: <b>{round(floor_sda, 2)}%</b>. It is calculated based '
            'on shading schedules for each Aperture Group. The detailed shading '
            'schedules are visualized under each Room summary.'
        )
        section_story.append(Paragraph(body_text, style=STYLES['BodyText']))
        section_story.append(Spacer(width=0*cm, height=0.5*cm))

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

        legend_north_drawing_table = Table([[legend_north_drawing]])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        ])
        legend_north_drawing_table.setStyle(table_style)

        remaining_height = (base_frame._aH - sum([flowable.wrap(base_frame._aW, base_frame._aH)[1] for flowable in section_story]) - legend_north_drawing_table.wrap(base_frame._aW, base_frame._aH)[1]) * 0.98

        da_drawing_pf_table = Table([[scale_drawing_to_width(da_drawing_pf, doc.width*0.9, max_height=remaining_height)]], rowHeights=[remaining_height])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        ])
        da_drawing_pf_table.setStyle(table_style)
        section_story.append(da_drawing_pf_table)

        section_story.append(legend_north_drawing_table)
        story.append(KeepTogether(flowables=section_story))
        story.append(PageBreak())

        section_story = []
        section_story.append(Paragraph('Direct Sunlight', style=STYLES['h3']))
        body_text = (
            'The Direct Sunlight is the number of occupied hours where the '
            'direct illuminance is larger than 1000 lux. The average <b>ASE</b> '
            f'for this level is: <b>{round(floor_ase, 2)}%</b>. It is calculated '
            'in a static state without use of shading schedules for each '
            'Aperture Group.'
        )
        section_story.append(Paragraph(body_text, style=STYLES['BodyText']))
        section_story.append(Spacer(width=0*cm, height=0.5*cm))

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

        legend_north_drawing_table = Table([[legend_north_drawing]])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        ])
        legend_north_drawing_table.setStyle(table_style)

        remaining_height = (base_frame._aH - sum([flowable.wrap(base_frame._aW, base_frame._aH)[1] for flowable in section_story]) - legend_north_drawing_table.wrap(base_frame._aW, base_frame._aH)[1]) * 0.98

        hrs_above_drawing_table = Table([[scale_drawing_to_width(hrs_above_drawing, doc.width*0.9, max_height=remaining_height)]], rowHeights=[remaining_height])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        ])
        hrs_above_drawing_table.setStyle(table_style)
        section_story.append(hrs_above_drawing_table)

        section_story.append(legend_north_drawing_table)
        story.append(KeepTogether(flowables=section_story))
        story.append(PageBreak())

        section_story = []
        section_story.append(Paragraph('Direct Sunlight | Pass / Fail', style=STYLES['h3']))
        body_text = (
            'The Direct Sunlight is the number of occupied hours where the '
            'direct illuminance is larger than 1000 lux. The average <b>ASE</b> '
            f'for this level is: <b>{round(floor_ase, 2)}%</b>. It is calculated '
            'in a static state without use of shading schedules for each '
            'Aperture Group.'
        )
        section_story.append(Paragraph(body_text, style=STYLES['BodyText']))
        section_story.append(Spacer(width=0*cm, height=0.5*cm))
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

        legend_north_drawing_table = Table([[legend_north_drawing]])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        ])
        legend_north_drawing_table.setStyle(table_style)

        remaining_height = (base_frame._aH - sum([flowable.wrap(base_frame._aW, base_frame._aH)[1] for flowable in section_story]) - legend_north_drawing_table.wrap(base_frame._aW, base_frame._aH)[1]) * 0.98

        hrs_above_drawing_pf_table = Table([[scale_drawing_to_width(hrs_above_drawing_pf, doc.width*0.9, max_height=remaining_height)]], rowHeights=[remaining_height])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        ])
        hrs_above_drawing_pf_table.setStyle(table_style)
        section_story.append(hrs_above_drawing_pf_table)

        section_story.append(legend_north_drawing_table)
        story.append(KeepTogether(flowables=section_story))
        story.append(PageBreak())

    story.append(Paragraph("Rooms Summary", STYLES['h1']))
    # SUMMARY OF EACH GRID
    for grid_summary in summary_grid.values():
        grid_name = grid_summary['name']
        grid_id = grid_summary['full_id']

        grid_info = grid_info_by_full_id(grids_info, grid_id)

        sensor_grid = sensor_grids[grid_id]
        # get room object
        room: Room = hb_model.rooms_by_identifier([sensor_grid.room_identifier])[0]

        story.append(Paragraph(grid_name, style=STYLES['h2']))
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
        drawing_width = parse_distance_string(f'{_width / drawing_scale}{UNITS_ABBREVIATIONS[hb_model.units]}', destination_units='Millimeters') * mm
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

        _heatmap_table = Table(data=[[scale_drawing_to_width(da_drawing, doc.width*0.45, max_height=60*mm), '', scale_drawing_to_width(hrs_above_drawing, doc.width*0.45, max_height=60*mm)]], colWidths=[doc.width*0.45, None, doc.width*0.45])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        ])
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
            story.append(Paragraph('Space did not pass \'2% rule\'', style=STYLES['h3']))
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
            story.append(Spacer(width=0*cm, height=0.5*cm))

        geometry_objects = room.faces + room.apertures + room.doors + tuple(room.shades)
        modifiers = _unique_modifiers(geometry_objects)
        modifiers_data = []
        modifiers_data.append([
            Paragraph('Modifier', style=STYLES['Normal_BOLD']),
            Paragraph('Reflectance', style=STYLES['Normal_BOLD']),
            Paragraph('Transmittance', style=STYLES['Normal_BOLD'])
        ])
        for modifier in modifiers:
            if isinstance(modifier, Plastic):
                modifiers_data.append([
                    modifier.display_name, round(modifier.average_reflectance, 2), 'N/A'
                ])
            elif isinstance(modifier, Glass):
                modifiers_data.append([
                    modifier.display_name, 'N/A', round(modifier.average_transmittance, 2)
                ])
        modifiers_table = Table(modifiers_data)
        modifiers_table.setStyle(
            TableStyle([
                ('LINEBELOW', (0, 0), (-1, 0), 0.2, colors.black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), ROWBACKGROUNDS)
            ])
        )
        story.append(modifiers_table)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        light_paths = [elem for lp in grid_info['light_path'] for elem in lp]
        ap = AnalysisPeriod(st_hour=8, end_hour=17)
        story.append(Paragraph('Aperture Groups', style=STYLES['h3']))
        body_text = (
            f'This section presents the Aperture Groups for the space <b>{grid_name}</b>. '
            'The shading schedule of each Aperture Group is visualized in an '
            'annual heat map. The shading schedule has two states: <i>Shading On</i> '
            'and <i>Shading Off</i>. The percentage of occupied hours for both '
            'states is presented in a table.'
        )
        story.append(Paragraph(body_text, style=STYLES['BodyText']))

        for aperture_group in light_paths:
            if aperture_group == '__static_apertures__':
                break
            aperture_group_header = Paragraph(aperture_group, style=STYLES['h4'])

            aperture_data = []
            aperture_data.append(
                [
                    Paragraph('Name', style=STYLES['Normal_BOLD']),
                    Paragraph(f'Area [{UNITS_ABBREVIATIONS[hb_model.units]}2]', style=STYLES['Normal_BOLD']),
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
            story.append(KeepTogether(flowables=[aperture_group_header, Spacer(width=0*cm, height=0.5*cm), drawing_table, Spacer(width=0*cm, height=0.5*cm), aperture_table, Spacer(width=0*cm, height=0.5*cm), table]))

        story.append(PageBreak())

    if run:
        story.append(Paragraph('Study Information', style=STYLES['h1']))
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

        weather_data = []
        weather_data.append(
            [
                Paragraph('Location', style=STYLES['Normal_BOLD']),
                Paragraph('Latitude', style=STYLES['Normal_BOLD']),
                Paragraph('Longitude', style=STYLES['Normal_BOLD'])
            ]
        )
        weather_data.append(
            [
                Paragraph(wea.location.city),
                Paragraph(f'{wea.location.latitude:.2f}'),
                Paragraph(f'{wea.location.longitude:.2f}')
            ]
        )
        weather_table = Table(weather_data)
        story.append(weather_table)
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
        story.append(Spacer(width=0*cm, height=0.5*cm))
        story.append(PageBreak())

    story.append(Paragraph('Radiance Modifiers', style=STYLES['h2']))
    geometry_objects = ()
    geometry_objects = hb_model.faces + hb_model.apertures + hb_model.shades + hb_model.doors + list(hb_model.shade_meshes)
    modifiers = _unique_modifiers(geometry_objects)
    for modifier in modifiers:
        story.append(Paragraph(modifier.to_radiance().replace('\n', '<br />\n')))
        story.append(Spacer(width=0*cm, height=0.5*cm))

    # build and save the PDF
    doc.multiBuild(
        story,
        canvasmaker=partial(NumberedPageCanvas, skip_pages=doc.skip_pages, start_on_skip_pages=doc.start_on_skip_pages)
    )
