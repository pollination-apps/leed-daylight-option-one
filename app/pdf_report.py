from pathlib import Path
from functools import partial
import pandas as pd
import json
import numpy as np
from io import BytesIO
import datetime
from collections import OrderedDict
from pdfrw import PdfReader, PdfDict
from pdfrw.buildxobj import pagexobj
from pdfrw.toreportlab import makerl

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
from svglib.svglib import svg2rlg

from ladybug.analysisperiod import AnalysisPeriod
from ladybug.datacollection import HourlyContinuousCollection
from ladybug.color import Colorset, ColorRange
from ladybug.legend import Legend, LegendParameters
from honeybee.model import Model, Room

from results import load_from_folder
from plot import figure_grids, figure_aperture_group_schedule, figure_ase


folder, vtjks_file, summary, summary_grid, states_schedule, \
    states_schedule_err, hb_model = load_from_folder(Path('./app/sample'))


class NumberedPageCanvas(canvas.Canvas):
    """
    http://code.activestate.com/recipes/546511-page-x-of-y-with-reportlab/
    http://code.activestate.com/recipes/576832/
    http://www.blog.pythonlibrary.org/2013/08/12/reportlab-how-to-add-page-numbers/
    https://stackoverflow.com/a/59882495/
    """

    def __init__(self, *args, **kwargs):
        """Constructor."""
        self.skip_pages = kwargs.pop('skip_pages', 0)
        self.start_on_skip_pages = kwargs.pop('start_on_skip_pages', None)
        super().__init__(*args, **kwargs)
        self.pages = []

    def showPage(self):
        """On a page break, add information to the list."""
        self.pages.append(dict(self.__dict__))
        self._doc.pageCounter += 1
        self._startPage()

    def save(self):
        """Add the page number to each page (page x of y)."""
        page_count = len(self.pages)

        for page in self.pages:
            self.__dict__.update(page)
            self.draw_page_number(page_count)
            super().showPage()

        super().save()

    def draw_page_number(self, page_count):
        """Add the page number."""
        if self._pageNumber > self.skip_pages:
            if self.start_on_skip_pages:
                page = "Page %s of %s" % (self._pageNumber - self.skip_pages, page_count - self.skip_pages)
                self.setFont("Helvetica", 9)
                self.drawRightString(195 * mm, 15 * mm, page)
            else:
                page = "Page %s of %s" % (self._pageNumber, page_count)
                self.setFont("Helvetica", 9)
                self.drawRightString(195 * mm, 15 * mm, page)


def _header(canvas, doc, content, logo):
    canvas.saveState()
    w, h = content.wrap(doc.width, doc.topMargin)
    content_width = \
        stringWidth(content.text, fontName=content.style.fontName, fontSize=content.style.fontSize)
    content.drawOn(
        canvas,
        doc.leftMargin+doc.width-content_width,
        doc.bottomMargin+doc.height+doc.topMargin-15*mm+1*mm
    )
    canvas.drawImage(
        logo, x=doc.leftMargin,
        y=doc.bottomMargin+doc.height+doc.topMargin-15*mm+1*mm,
        height=5*mm,
        preserveAspectRatio=True,
        anchor='w',
        mask='auto'
    )
    canvas.setLineWidth(0.2)
    canvas.line(
        doc.leftMargin,
        doc.bottomMargin + doc.height + doc.topMargin - 15 * mm,
        doc.leftMargin + doc.width,
        doc.bottomMargin + doc.height + doc.topMargin - 15 * mm)
    canvas.restoreState()

def _footer(canvas, doc, content):
    canvas.saveState()
    w, h = content.wrap(doc.width, doc.bottomMargin)
    content.drawOn(canvas, doc.leftMargin, 15 * mm)
    canvas.restoreState()

def _header_and_footer(canvas, doc, header_content, footer_content, logo):
    _header(canvas, doc, header_content, logo)
    _footer(canvas, doc, footer_content)


class PdfImage(Flowable):
    """
    PdfImage wraps the first page from a PDF file as a Flowable
    which can be included into a ReportLab Platypus document.
    Based on the vectorpdf extension in rst2pdf (http://code.google.com/p/rst2pdf/)

    This can be used from the place where you want to return your matplotlib image
    as a Flowable:

        img = BytesIO()

        fig, ax = plt.subplots(figsize=(canvaswidth,canvaswidth))

        ax.plot([1,2,3],[6,5,4],antialiased=True,linewidth=2,color='red',label='a curve')

        fig.savefig(img,format='PDF')

        return(PdfImage(img))

    """

    def __init__(self, filename_or_object, width=None, height=None, kind='direct', keep_ratio=True):
        # If using StringIO buffer, set pointer to beginning
        if hasattr(filename_or_object, 'read'):
            filename_or_object.seek(0)
        self.page = PdfReader(filename_or_object, decompress=False).pages[0]
        self.xobj = pagexobj(self.page)
        self.imageWidth = width
        self.imageHeight = height
        x1, y1, x2, y2 = self.xobj.BBox

        self._w, self._h = x2 - x1, y2 - y1
        if keep_ratio:
            ratio = self._w / self._h
            if not self.imageWidth:
                self.imageWidth = height * ratio
            elif not self.imageHeight:
                self.imageHeight = width / ratio
            else:
                raise ValueError('Either width or height must be specified.')
        else:
            if not self.imageWidth:
                self.imageWidth = self._w
            if not self.imageHeight:
                self.imageHeight = self._h
        self._ratio = float(self.imageWidth) / self.imageHeight
        if kind in ['direct','absolute'] or width==None or height==None:
            self.drawWidth = width or self.imageWidth
            self.drawHeight = height or self.imageHeight
        elif kind in ['bound','proportional']:
            factor = min(float(width)/self._w,float(height)/self._h)
            self.drawWidth = self._w*factor
            self.drawHeight = self._h*factor

    def wrap(self, availableWidth, availableHeight):
        """
        returns draw- width and height

        convenience function to adapt your image 
        to the available Space that is available
        """
        return self.drawWidth, self.drawHeight

    def drawOn(self, canv, x, y, _sW=0):
        """
        translates Bounding Box and scales the given canvas
        """
        x = 0 # override to avoid margins of frame
        y = 0 # override to avoid margins of frame
        if _sW > 0 and hasattr(self, 'hAlign'):
            a = self.hAlign
            if a in ('CENTER', 'CENTRE', TA_CENTER):
                x += 0.5*_sW
            elif a in ('RIGHT', TA_RIGHT):
                x += _sW
            elif a not in ('LEFT', TA_LEFT):
                raise ValueError("Bad hAlign value " + str(a))

        #xobj_name = makerl(canv._doc, self.xobj)
        xobj_name = makerl(canv, self.xobj)

        xscale = self.drawWidth/self._w
        yscale = self.drawHeight/self._h

        x -= self.xobj.BBox[0] * xscale
        y -= self.xobj.BBox[1] * yscale

        canv.saveState()
        canv.translate(x, y)
        canv.scale(xscale, yscale)
        canv.doForm(xobj_name)
        canv.restoreState()


def scale_drawing(drawing: Drawing, sx: float, sy: float):
    new_drawing = drawing.copy()
    new_drawing.scale(sx, sy)
    new_drawing.width = new_drawing.width * sx
    new_drawing.height = new_drawing.height * sy
    return new_drawing


def scale_drawing_to_width(drawing: Drawing, width: float):
    new_drawing = drawing.copy()
    x1, y1, x2, y2 = new_drawing.getBounds()
    contents_width = x2 - x1
    contents_height = y2 - y1
    scale_factor = width / contents_width
    new_height = contents_height * scale_factor
    new_drawing.scale(sx=scale_factor, sy=scale_factor)
    new_drawing.width = width
    new_drawing.height = new_height
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


def create_pdf(
        output_file, pagesize: tuple = A4, left_margin: float = 1.5*cm,
        right_margin: float = 1.5*cm, top_margin: float = 2*cm,
        bottom_margin: float = 2*cm,
    ):

    pdf_canvas = canvas.Canvas(output_file, pagesize=pagesize)
    # Create a PDF document
    doc = SimpleDocTemplate(
        output_file, pagesize=pagesize, leftMargin=left_margin,
        rightMargin=right_margin, topMargin=top_margin,
        bottomMargin=bottom_margin, showBoundary=False
    )

    # Set up styles
    styles = getSampleStyleSheet()

    # modify styles
    styles['BodyText'].leading = 18

    styles.add(ParagraphStyle(name='Normal_BOLD',
                              parent=styles['Normal'],
                              fontSize=10,
                              leading=12,
                              fontName=_baseFontNameB)
    )

    styles.add(ParagraphStyle(name='Normal_CENTER',
                              parent=styles['Normal'],
                              alignment=TA_CENTER,
                              fontSize=10,
                              leading=12)
    )
    styles.add(ParagraphStyle(name='Normal_RIGHT',
                              parent=styles['Normal'],
                              alignment=TA_RIGHT,
                              fontSize=10,
                              leading=12)
    )
    new_style = styles['h2'].clone('h2_CENTER')
    new_style.alignment = TA_CENTER
    styles.add(new_style)

    title_frame = Frame(doc.leftMargin, doc.bottomMargin + doc.height - 4 * cm, doc.width, 4 * cm, showBoundary=1, id='title-frame')
    extra_frame = Frame(doc.leftMargin, doc.bottomMargin + doc.height - 9 * cm, doc.width, 4 * cm, showBoundary=1, id='extra-frame')
    table_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, 12 * cm, showBoundary=1, id='table-frame')

    header_content = Paragraph("This is a header. testing testing testing!", styles['Normal'])
    footer_content = Paragraph("LEED Daylight Option I", styles['Normal'])
    title_page_template = PageTemplate(id='title-page', onPage=partial(_header, content=header_content), frames=[title_frame], pagesize=pagesize)
    #doc.addPageTemplates(title_page_template)
    #grid_page_template = PageTemplate(id='grid-page', onPage=partial(_header, content=header_content), pagesize=pagesize)
    #doc.addPageTemplates(grid_page_template)

    title_style = styles['Title']

    story = []
    #story.append(NextPageTemplate('title-page'))
    front_page_table = Table(data=
        [
            [Paragraph("LEED Daylight Option I Report", styles['h2'])],
            [Paragraph('Project: My Project')],
            [Paragraph('Prepared by: Mikkel Pedersen')],
            [Paragraph(f'Date created: {datetime.datetime.today().strftime("%B %d, %Y")}')]
        ]
    )
    story.append(front_page_table)
    story.append(PageBreak())
    document_title = Paragraph("LEED Daylight Option I", title_style)
    story.append(document_title)

    if summary['credits'] > 0:
        story.append(
            Paragraph(f'LEED Credits: {summary["credits"]}', style=styles['h1'].clone(name='h1_GREEN', textColor='green'))
        )
    else:
        story.append(
            Paragraph(f'LEED Credits: {summary["credits"]}', style=styles['h1'])
        )
    story.append(Spacer(width=0*cm, height=0.5*cm))

    def get_sda_cell_color(val: float):
        val = float(val)
        if val >= 75:
            return colors.Color(0, 255 / 255, 0, 0.3)
        elif val >= 55:
            return colors.Color(85 / 255, 255 / 255, 0, 0.3)
        elif val >= 40:
            return colors.Color(170 / 255, 255 / 255, 0, 0.3)
        else:
            return colors.Color(255 / 255, 170 / 255, 0, 0.3)

    def get_ase_cell_color(val: float):
        val = float(val)
        if val > 10:
            return colors.Color(255 / 255, 170 / 255, 0, 0.3)
        else:
            return colors.Color(0, 255 / 255, 0, 0.3)

    _sda_table = Table(data=[[Paragraph(f'sDA: {summary["sda"]}%', style=styles['h2_CENTER'])]], rowHeights=[16*mm])
    table_style = TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('ROUNDEDCORNERS', [10, 10, 10, 10]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ])
    table_style.add('BACKGROUND', (0, 0), (0, 0), get_sda_cell_color(summary["sda"]))
    _sda_table.setStyle(table_style)

    _ase_table = Table(data=[[Paragraph(f'ASE: {summary["ase"]}%', style=styles['h2_CENTER'])]], rowHeights=[16*mm])
    table_style = TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('ROUNDEDCORNERS', [10, 10, 10, 10]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ])
    table_style.add('BACKGROUND', (0, 0), (0, 0), get_ase_cell_color(summary["ase"]))
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

    # Create content
    story.extend([
        Paragraph("Space Overview", style=styles['h2'])
        ]
    )

    def table_from_summary_grid(summary_grid, grid_filter: list = None, add_total: bool = True):
        if grid_filter:
            summary_grid = {k: summary_grid[k] for k in grid_filter if k in summary_grid}
        df = pd.DataFrame.from_dict(summary_grid).transpose()
        try:
            df = df[
                ['ase', 'sda', 'floor_area_passing_ase', 'floor_area_passing_sda',
                'total_floor_area']
                ]
            # rename columns
            df.rename(
                columns={
                    'ase': 'ASE [%]',
                    'sda': 'sDA [%]',
                    'floor_area_passing_ase': 'Floor area passing ASE',
                    'floor_area_passing_sda': 'Floor area passing sDA',
                    'total_floor_area': 'Total floor area'
                    }, inplace=True)
        except Exception:
            df = df[
                ['ase', 'sda', 'sensor_count_passing_ase',
                'sensor_count_passing_sda', 'total_sensor_count']
                ]
            # rename columns
            df.rename(
                columns={
                    'ase': 'ASE [%]',
                    'sda': 'sDA [%]',
                    'sensor_count_passing_ase': 'Sensor count passing ASE',
                    'sensor_count_passing_sda': 'Sensor count passing sDA',
                    'total_sensor_count': 'Total sensor count'
                }
            )
        df = df.rename_axis('Space Name').reset_index()

        ase_notes = []
        for data in summary_grid.values():
            if 'ase_note' in data:
                ase_notes.append('1)')
            else:
                ase_notes.append('')
        if not all(n=='' for n in ase_notes):
            df['ASE Note'] = ase_notes

        #data = df.values.tolist()
        if add_total:
            total_row = [
                Paragraph('Total'),
                Paragraph(''),
                Paragraph(''),
                Paragraph(str(round(df['Floor area passing ASE'].sum(), 2))),
                Paragraph(str(round(df['Floor area passing sDA'].sum(), 2))),
                Paragraph(str(round(df['Total floor area'].sum(), 2))),
                Paragraph('')
            ]
        df = df.astype(str)
        table_data =  [tuple(df)] + list(df.itertuples(index=False, name=None))

        # base table style
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ])

        formatted_table_data = []
        # add additional commands to table style
        for idx_row, row in enumerate(table_data):
            formatted_row = []
            for idx_cell, cell_value in enumerate(row):
                if idx_cell == 1 and idx_row != 0:
                    cell_color = get_ase_cell_color(cell_value)
                    table_style.add('BACKGROUND', (idx_cell, idx_row), (idx_cell, idx_row), cell_color)
                if idx_cell == 2 and idx_row != 0:
                    cell_color = get_sda_cell_color(cell_value)
                    table_style.add('BACKGROUND', (idx_cell, idx_row), (idx_cell, idx_row), cell_color)
                if idx_row == 0:
                    formatted_row.append(Paragraph(cell_value, style=styles['Normal_BOLD']))
                else:
                    formatted_row.append(Paragraph(cell_value))
            formatted_table_data.append(formatted_row)

        if add_total:
            formatted_table_data.append(total_row)

        table = Table(formatted_table_data, colWidths='*', repeatRows=1, rowSplitRange=0, spaceBefore=5, spaceAfter=5)
        table.setStyle(table_style)

        return table, ase_notes

    table, ase_notes = table_from_summary_grid(summary_grid)
    story.append(table)

    if not all(n=='' for n in ase_notes):
        ase_note = Paragraph('1) The Annual Sunlight Exposure is greater than '
                             '10% for this space. Identify in writing how the '
                             'space is designed to address glare.')
        story.append(Spacer(width=0*cm, height=0.5*cm))
        story.append(ase_note)

    story.append(PageBreak())

    with open(folder.joinpath('grids_info.json')) as json_file:
        grids_info = json.load(json_file)

    sensor_grids = hb_model.properties.radiance.sensor_grids
    sensor_grids = {sg.full_identifier: sg for sg in sensor_grids}

    rooms_by_story = {story_id: [] for story_id in sorted(hb_model.stories)}
    for room in hb_model.rooms:
        if room.story in rooms_by_story:
            rooms_by_story[room.story].append(room)
    for story_id, rooms in rooms_by_story.items():
        story.append(Paragraph(story_id, style=styles['h1']))
        story.append(Spacer(width=0*cm, height=0.5*cm))

        horiz_bounds = [room.horizontal_boundary() for room in rooms]
        rooms_min = Room._calculate_min(horiz_bounds)
        rooms_max = Room._calculate_max(horiz_bounds)

        _width = rooms_max.x - rooms_min.x
        _height = rooms_max.y - rooms_min.y
        _ratio = _width / _height
        drawing_scale = 500
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
                    floor_area += summary_grid[room.display_name]['total_floor_area']
                    floor_area_passing_sda += summary_grid[room.display_name]['floor_area_passing_sda']
                    floor_area_passing_ase += summary_grid[room.display_name]['floor_area_passing_ase']
                    floor_sensor_grids.append(sensor_grid.full_identifier)

                    mesh = sensor_grid.mesh
                    faces = mesh.faces
                    faces_centroids = mesh.face_centroids

                    da = np.loadtxt(Path(f'app/sample/leed-summary/results/da/{sensor_grid.full_identifier}.da'))
                    da_color_range = ColorRange(colors=Colorset.annual_comfort(), domain=[0, 100])
                    hrs_above = np.loadtxt(Path(f'app/sample/leed-summary/results/ase_hours_above/{sensor_grid.full_identifier}.res'))
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
        floor_ase = floor_area_passing_ase / floor_area * 100

        _sda_table = Table(data=[[Paragraph(f'sDA: {round(floor_sda, 2)}%', style=styles['h2_CENTER'])]], rowHeights=[16*mm])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('ROUNDEDCORNERS', [10, 10, 10, 10]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ])
        table_style.add('BACKGROUND', (0, 0), (0, 0), get_sda_cell_color(floor_sda))
        _sda_table.setStyle(table_style)

        _ase_table = Table(data=[[Paragraph(f'ASE: {round(floor_ase, 2)}%', style=styles['h2_CENTER'])]], rowHeights=[16*mm])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('ROUNDEDCORNERS', [10, 10, 10, 10]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ])
        table_style.add('BACKGROUND', (0, 0), (0, 0), get_ase_cell_color(floor_ase))
        _ase_table.setStyle(table_style)
        table_style = TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        ])
        column_widths = [doc.width*0.45, doc.width*0.10, doc.width*0.45]
        colWidths = [col_width-12/len(column_widths) for col_width in column_widths]
        _metric_table = Table(data=[[_sda_table, '',_ase_table]], colWidths=colWidths)
        _metric_table.setStyle(table_style)
        story.append(_metric_table)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        table, ase_notes = table_from_summary_grid(summary_grid, grid_filter=floor_sensor_grids)
        story.append(table)

        if not all(n=='' for n in ase_notes):
            ase_note = Paragraph('1) The Annual Sunlight Exposure is greater than '
                                '10% for this space. Identify in writing how the '
                                'space is designed to address glare.')
            story.append(Spacer(width=0*cm, height=0.5*cm))
            story.append(ase_note)

        north_arrow_drawing = draw_north_arrow(north=0, radius=10)
        section_header = Paragraph('Daylight Autonomy', style=styles['h2'])

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

        ddd = Drawing(0, 0)
        gggg = Group()
        segment_min, segment_max = legend.segment_mesh.min, legend.segment_mesh.max
        for segment_number, face, segment_color, segment_text_location in zip(legend.segment_numbers, legend.segment_mesh_scene_2d.face_vertices, legend.segment_colors, legend.segment_text_location):
            points = []
            stl_x, stl_y, stl_z = segment_text_location.o.to_array()
            fillColor = colors.Color(segment_color.r / 255, segment_color.g / 255, segment_color.b / 255)
            for vertex in face:
                points.extend([vertex.x, vertex.y])
            polygon = Polygon(points=points, fillColor=fillColor, strokeWidth=0, strokeColor=fillColor)
            gggg.add(polygon)
            ddd.add(polygon)
            string = String(x=stl_x, y=-5*1.1, text=str(int(segment_number)), textAnchor='start', fontName='Helvetica', fontSize=5)
            gggg.add(string)
            ddd.add(string)
        string = String(x=segment_min.x-5, y=0, text='Daylight Autonomy (300 lux) [%]',textAnchor='end', fontName='Helvetica', fontSize=5)
        gggg.add(string)
        ddd.add(string)
        ddd_bounds = ddd.getBounds()
        dx = abs(0 - ddd_bounds[0])
        dy = abs(0 - ddd_bounds[1])
        ddd.translate(dx, dy)
        drawing_dimensions_from_bounds(ddd)

        translate_group_relative(gggg, north_arrow_group, anchor='e', padding=5)
        legend_north_drawing.add(gggg)
        drawing_dimensions_from_bounds(legend_north_drawing)
        da_drawing = scale_drawing_to_width(da_drawing, doc.width-12)
        da_group = KeepTogether(flowables=[section_header, da_drawing, Spacer(width=0*cm, height=0.5*cm), legend_north_drawing])
        story.append(da_group)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        section_header = Paragraph('Daylight Autonomy | Pass / Fail', style=styles['h2'])

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
        da_drawing_pf = scale_drawing_to_width(da_drawing_pf, doc.width-12)
        da_pf_group = KeepTogether(flowables=[section_header, da_drawing_pf, Spacer(width=0*cm, height=0.5*cm), legend_north_drawing])
        story.append(da_pf_group)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        section_header = Paragraph('Direct Sunlight', style=styles['h2'])

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
        ddd = Drawing(0, 0)
        gggg = Group()
        segment_min, segment_max = legend.segment_mesh.min, legend.segment_mesh.max
        for segment_number, face, segment_color, segment_text_location in zip(legend.segment_numbers, legend.segment_mesh_scene_2d.face_vertices, legend.segment_colors, legend.segment_text_location):
            points = []
            stl_x, stl_y, stl_z = segment_text_location.o.to_array()
            fillColor = colors.Color(segment_color.r / 255, segment_color.g / 255, segment_color.b / 255)
            for vertex in face:
                points.extend([vertex.x, vertex.y])
            polygon = Polygon(points=points, fillColor=fillColor, strokeWidth=0, strokeColor=fillColor)
            gggg.add(polygon)
            ddd.add(polygon)
            string = String(x=stl_x, y=-5*1.1, text=str(int(segment_number)), textAnchor='start', fontName='Helvetica', fontSize=5)
            gggg.add(string)
            ddd.add(string)
        string = String(x=segment_min.x-5, y=0, text='Direct Sunlight (1000 lux) [hrs]',textAnchor='end', fontName='Helvetica', fontSize=5)
        gggg.add(string)
        ddd.add(string)
        ddd_bounds = ddd.getBounds()
        dx = abs(0 - ddd_bounds[0])
        dy = abs(0 - ddd_bounds[1])
        ddd.translate(dx, dy)
        drawing_dimensions_from_bounds(ddd)

        translate_group_relative(gggg, north_arrow_group, 'e', 5)
        legend_north_drawing.add(gggg)
        drawing_dimensions_from_bounds(legend_north_drawing)
        hrs_above_drawing = scale_drawing_to_width(hrs_above_drawing, doc.width-12)
        hrs_above_group = KeepTogether(flowables=[section_header, hrs_above_drawing, Spacer(width=0*cm, height=0.5*cm), legend_north_drawing])
        story.append(hrs_above_group)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        section_header = Paragraph('Direct Sunlight | Pass / Fail', style=styles['h2'])
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
        hrs_above_drawing_pf = scale_drawing_to_width(hrs_above_drawing_pf, doc.width-12)
        hrs_above_pf_group = KeepTogether(flowables=[section_header, hrs_above_drawing_pf, Spacer(width=0*cm, height=0.5*cm), legend_north_drawing])
        story.append(hrs_above_pf_group)
        story.append(PageBreak())

    # SUMMARY OF EACH GRID
    for grid_id, values in summary_grid.items():
        story.append(Paragraph(grid_id, style=styles['h1']))
        story.append(Spacer(width=0*cm, height=0.5*cm))

        _sda_table = Table(data=[[Paragraph(f'sDA: {values["sda"]}%', style=styles['h2_CENTER'])]], rowHeights=[16*mm])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('ROUNDEDCORNERS', [10, 10, 10, 10]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ])
        table_style.add('BACKGROUND', (0, 0), (0, 0), get_sda_cell_color(values["sda"]))
        _sda_table.setStyle(table_style)

        _ase_table = Table(data=[[Paragraph(f'ASE: {values["ase"]}%', style=styles['h2_CENTER'])]], rowHeights=[16*mm])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('ROUNDEDCORNERS', [10, 10, 10, 10]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ])
        table_style.add('BACKGROUND', (0, 0), (0, 0), get_ase_cell_color(values["ase"]))
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
        sensor_grid = sensor_grids[grid_id]
        room: Room = hb_model.rooms_by_identifier([sensor_grid.room_identifier])[0]
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
        da = np.loadtxt(Path(f'app/sample/leed-summary/results/da/{grid_id}.da'))
        hrs_above_drawing = Drawing(drawing_width, drawing_height)
        hrs_above = np.loadtxt(Path(f'app/sample/leed-summary/results/ase_hours_above/{grid_id}.res'))
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

        _da_heatmap_table = Table(data=[[da_drawing]])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ])
        _da_heatmap_table.setStyle(table_style)

        _hrs_above_heatmap_table = Table(data=[[hrs_above_drawing]])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ])
        _hrs_above_heatmap_table.setStyle(table_style)

        table_style = TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        ])
        _heatmap_table = Table(data=[[_da_heatmap_table, '', _hrs_above_heatmap_table]], colWidths=[doc.width*0.45, None, doc.width*0.45])
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

        ddd = Drawing(0, 0)
        gggg = Group()
        segment_min, segment_max = legend.segment_mesh.min, legend.segment_mesh.max
        for segment_number, face, segment_color, segment_text_location in zip(legend.segment_numbers, legend.segment_mesh_scene_2d.face_vertices, legend.segment_colors, legend.segment_text_location):
            points = []
            stl_x, stl_y, stl_z = segment_text_location.o.to_array()
            fillColor = colors.Color(segment_color.r / 255, segment_color.g / 255, segment_color.b / 255)
            for vertex in face:
                points.extend([vertex.x, vertex.y])
            polygon = Polygon(points=points, fillColor=fillColor, strokeWidth=0, strokeColor=fillColor)
            gggg.add(polygon)
            ddd.add(polygon)
            string = String(x=stl_x, y=-5*1.1, text=str(int(segment_number)), textAnchor='start', fontName='Helvetica', fontSize=5)
            gggg.add(string)
            ddd.add(string)
        string = String(x=segment_min.x-5, y=0, text='Daylight Autonomy (300 lux) [%]',textAnchor='end', fontName='Helvetica', fontSize=5)
        gggg.add(string)
        ddd.add(string)
        ddd_bounds = ddd.getBounds()
        dx = abs(0 - ddd_bounds[0])
        dy = abs(0 - ddd_bounds[1])
        ddd.translate(dx, dy)
        drawing_dimensions_from_bounds(ddd)

        translate_group_relative(gggg, north_arrow_group, anchor='e', padding=5)
        legend_da.add(gggg)
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
        ddd = Drawing(0, 0)
        gggg = Group()
        segment_min, segment_max = legend.segment_mesh.min, legend.segment_mesh.max
        for segment_number, face, segment_color, segment_text_location in zip(legend.segment_numbers, legend.segment_mesh_scene_2d.face_vertices, legend.segment_colors, legend.segment_text_location):
            points = []
            stl_x, stl_y, stl_z = segment_text_location.o.to_array()
            fillColor = colors.Color(segment_color.r / 255, segment_color.g / 255, segment_color.b / 255)
            for vertex in face:
                points.extend([vertex.x, vertex.y])
            polygon = Polygon(points=points, fillColor=fillColor, strokeWidth=0, strokeColor=fillColor)
            gggg.add(polygon)
            ddd.add(polygon)
            string = String(x=stl_x, y=-5*1.1, text=str(int(segment_number)), textAnchor='start', fontName='Helvetica', fontSize=5)
            gggg.add(string)
            ddd.add(string)
        string = String(x=segment_min.x-5, y=0, text='Direct Sunlight (1000 lux) [hrs]',textAnchor='end', fontName='Helvetica', fontSize=5)
        gggg.add(string)
        ddd.add(string)
        ddd_bounds = ddd.getBounds()
        dx = abs(0 - ddd_bounds[0])
        dy = abs(0 - ddd_bounds[1])
        ddd.translate(dx, dy)
        drawing_dimensions_from_bounds(ddd)

        translate_group_relative(gggg, north_arrow_group, 'e', 5)
        legend_hrs_above.add(gggg)
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

        # if grid_id == 'Room_2':
        #     table_style = TableStyle([
        #         ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        #         ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        #         ('LEFTPADDING', (0, 0), (-1, -1), 0),
        #         ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        #         ('TOPPADDING', (0, 0), (-1, -1), 0),
        #         ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
        #     ])
        #     _scale_table = Table(
        #         data=[
        #             [
        #                 da_drawing,
        #                 scale_drawing(da_drawing, 200 / 300, 200 / 300),
        #                 scale_drawing(da_drawing, 200 / 400, 200 / 400),
        #                 scale_drawing(da_drawing, 200 / 500, 200 / 500),
        #                 scale_drawing(da_drawing, 200 / 1000, 200 / 1000),
        #                 scale_drawing(da_drawing, 200 / 2000, 200 / 2000)
        #             ],
        #             [
        #                 '1:200',
        #                 '1:300',
        #                 '1:400',
        #                 '1:500',
        #                 '1:1000',
        #                 '1:2000'
        #             ]
        #             ],
        #         colWidths='*')
        #     _scale_table.setStyle(table_style)
        #     story.append(_scale_table)
        #     story.append(Spacer(width=0*cm, height=0.5*cm))

        table, ase_notes = table_from_summary_grid(summary_grid, [grid_id], add_total=False)
        
        story.append(table)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        ase_note = values.get('ase_note')
        if ase_note:
            story.append(Paragraph(ase_note, style=styles['Normal']))


        for grid_info in grids_info:
            if grid_id == grid_info['full_id']:
                break

        light_paths = [lp[0] for lp in grid_info['light_path']]
        ap = AnalysisPeriod(st_hour=8, end_hour=17)
        story.append(Paragraph('Aperture Groups', style=styles['h2']))
        body_text = (
            f'This section present the Aperture Groups for the space <b>{grid_id}</b>. '
            'The shading schedule of each Aperture Group is visualized in an '
            'annual heat map. The shading schedule has two states: <i>Shading On</i> '
            'and <i>Shading Off</i>. The percentage of occupied hours for both '
            'states is presented in a table.'
        )
        story.append(Paragraph(body_text, style=styles['BodyText']))
        for aperture_group in light_paths:
            aperture_group_header = Paragraph(aperture_group, style=styles['h3'])
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
                ['', 'Occupied Hours'],
                ['Shading On', f'{shading_on_pct}%'],
                ['Shading Off', f'{shading_off_pct}%']
            ]
            shading_table = Table(data=shading_data_table)

            # get figure
            figure = figure_aperture_group_schedule(aperture_group, datacollection)
            fig_pdf = figure.to_image(format='pdf', width=700, height=350, scale=3)
            column_widths = [doc.width*(1/3), doc.width*(2/3)]
            pdf_image =  PdfImage(BytesIO(fig_pdf), width=doc.width*(2/3)-12/len(column_widths), height=None, keep_ratio=True)
            pdf_table = Table([[pdf_image]])
            pdf_table.setStyle(
                TableStyle([
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
                ])
            )
            colWidths = [col_width-12/len(column_widths) for col_width in column_widths]
            table = Table([[shading_table, pdf_table]], colWidths=colWidths)
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
            story.append(KeepTogether(flowables=[aperture_group_header, table]))
            #story.append(ggg)
            #story.append(Spacer(width=0*cm, height=0.5*cm))
            #drawing = svg2rlg(img)
            #drawing = svg2rlg(svg_path)
            #assert False, drawing
            #drawing = scale(drawing, scaling_factor=None, width=400, height=None)
            #story.append(drawing)

        #story.append(NextPageTemplate('grid-page'))
        story.append(PageBreak())
        # story.append(CondPageBreak())
        break

    pollination_image = 'assets/images/pollination.png'
    # Build and save the PDF
    doc.build(
        story,
        #onFirstPage=partial(_header_and_footer, header_content=header_content, footer_content=footer_content, logo=pollination_image),
        onLaterPages=partial(_header_and_footer, header_content=header_content, footer_content=footer_content, logo=pollination_image),
        canvasmaker=partial(NumberedPageCanvas, skip_pages=1, start_on_skip_pages=True)
    )


if __name__ == "__main__":
    output_file = "sample.pdf"
    create_pdf(output_file)
    print(f"PDF generated successfully: {output_file}")
