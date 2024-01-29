from pathlib import Path
from functools import partial
import pandas as pd
import json
from io import BytesIO
from pdfrw import PdfReader, PdfDict
from pdfrw.buildxobj import pagexobj
from pdfrw.toreportlab import makerl

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle, _baseFontNameB
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.graphics.shapes import Drawing
from reportlab.platypus import SimpleDocTemplate, BaseDocTemplate, Flowable, Paragraph, \
    Table, TableStyle, PageTemplate, Frame, PageBreak, NextPageTemplate, \
    Image, FrameBreak
from svglib.svglib import svg2rlg

from ladybug.analysisperiod import AnalysisPeriod
from ladybug.datacollection import HourlyContinuousCollection

from results import load_from_folder
from plot import figure_grids, figure_aperture_group_schedule, figure_ase


folder, vtjks_file, summary, summary_grid, states_schedule, \
    states_schedule_err = load_from_folder(Path('./app/sample'))


def header(canvas, doc, content):
    canvas.saveState()
    w, h = content.wrap(doc.width, doc.topMargin)
    content.drawOn(canvas, doc.leftMargin, doc.height + doc.bottomMargin + h)
    canvas.restoreState()

def footer(canvas, doc, content):
    canvas.saveState()
    w, h = content.wrap(doc.width, doc.bottomMargin)
    content.drawOn(canvas, doc.leftMargin, h)
    canvas.restoreState()

def header_and_footer(canvas, doc, header_content, footer_content):
    header(canvas, doc, header_content)
    footer(canvas, doc, footer_content)


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

    def __init__(self, filename_or_object, width=None, height=None, kind='direct'):
        # If using StringIO buffer, set pointer to begining
        if hasattr(filename_or_object, 'read'):
            filename_or_object.seek(0)
            #print("read")
        self.page = PdfReader(filename_or_object, decompress=False).pages[0]
        self.xobj = pagexobj(self.page)

        self.imageWidth = width
        self.imageHeight = height
        x1, y1, x2, y2 = self.xobj.BBox

        self._w, self._h = x2 - x1, y2 - y1
        if not self.imageWidth:
            self.imageWidth = self._w
        if not self.imageHeight:
            self.imageHeight = self._h
        self.__ratio = float(self.imageWidth)/self.imageHeight
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
        bottomMargin=bottom_margin, showBoundary=True
    )

    title_frame = Frame(doc.leftMargin, doc.bottomMargin + doc.height - 4 * cm, doc.width, 4 * cm, showBoundary=1, id='title-frame')
    extra_frame = Frame(doc.leftMargin, doc.bottomMargin + doc.height - 9 * cm, doc.width, 4 * cm, showBoundary=1, id='extra-frame')
    table_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, 12 * cm, showBoundary=1, id='table-frame')

    grid_page_template = PageTemplate(id='grid-page', frames=[title_frame, extra_frame, table_frame], pagesize=pagesize)
    doc.addPageTemplates(grid_page_template)

    # Set up styles
    styles = getSampleStyleSheet()

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

    title_style = styles['Title']

    story = []
    story.append(Paragraph("LEED Daylight Option I", title_style))

    summary_story = []
    if summary['credits'] > 0:
        summary_story.append(
            Paragraph(f'LEED Credits: {summary["credits"]}', style=styles['Normal'].clone(name='Normal_GREEN', textColor='green'))
        )
    else:
        summary_story.append(
            Paragraph(f'LEED Credits: {summary["credits"]}', style=styles['Normal'])
        )
    
    summary_story.append(
        Paragraph(f'Spatial Daylight Autonomy: {summary["sda"]}%', style=styles['Normal'])
    )

    summary_story.append(
        Paragraph(f'Annual Sunlight Exposure: {summary["ase"]}%', style=styles['Normal'])
    )
    story.extend(summary_story)

    story.append(FrameBreak())

    # Create content
    title = "Sample Report"
    story.extend([
        Paragraph("Table Section", style=styles['h1'])
        ]
    )

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

    header = list(df.columns)
    data = df.values.tolist()

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

    df = df.astype(str)
    table_data =  [tuple(df)] + list(df.itertuples(index=False, name=None))

    # base table style
    table_style = TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
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

    table = Table(formatted_table_data, colWidths='*', repeatRows=1, rowSplitRange=0, spaceBefore=5, spaceAfter=5)
    table.setStyle(table_style)
    story.append(table)

    story.append(NextPageTemplate('grid-page'))

    story.append(PageBreak())
    # footer_content = Paragraph("This is a footer. It goes on every page.  ", styles['Normal'])
    # frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    # template = PageTemplate(id='test', frames=frame, onPage=partial(header_and_footer, header_content=header_content, footer_content=footer_content))
    # doc.addPageTemplates([
    #     PageTemplate(id='no_border', onPage=partial(header_and_footer, header_content=header_content, footer_content=footer_content), frames=[summary_frame, summary_frame_2])
    #     ]
    # )

    with open(folder.joinpath('grids_info.json')) as json_file:
        grids_info = json.load(json_file)


    def scale(drawing: Drawing, scaling_factor: float = None, width: float = None, height: float = None):
        if all(v is None for v in [scaling_factor, width, height]):
            raise ValueError
        
        if scaling_factor:
            scaling_x = scaling_factor
            scaling_y = scaling_factor
            
            drawing.width = drawing.minWidth() * scaling_x
            drawing.height = drawing.height * scaling_y
            drawing.scale(scaling_x, scaling_y)
            return drawing
        if width:
            scaling_factor = width / drawing.width
            drawing.width = width
            drawing.height = drawing.height * scaling_factor
            drawing.scale(scaling_factor, scaling_factor)
            return drawing
        if height:
            scaling_factor = height / drawing.height
            drawing.height = height
            drawing.width = drawing.width * scaling_factor
            drawing.scale(scaling_factor, scaling_factor)
            return drawing

    for grid_id, values in summary_grid.items():
        story.append(Paragraph(grid_id, style=styles['h1']))

        # add sDA
        story.append(Paragraph(f'Spatial Daylight Autonomy: {values["sda"]}%', style=styles['Normal']))

        # add ASE
        story.append(Paragraph(f'Annual Sunlight Exposure: {values["ase"]}%', style=styles['Normal']))

        story.append(table)

        ase_note = values.get('ase_note')
        if ase_note:
            pass
            story.append(Paragraph(ase_note, style=styles['Normal']))

        #drawing = svg2rlg('Flag of Cuba.svg')
        #drawing = scale(drawing, scaling_factor=None, width=None, height=200)
        #story.append(drawing)

        for grid_info in grids_info:
            if grid_id == grid_info['full_id']:
                break

        light_paths = [lp[0] for lp in grid_info['light_path']]
        ap = AnalysisPeriod(st_hour=8, end_hour=17)
        for aperture_group in light_paths:
            datacollection = \
                HourlyContinuousCollection.from_dict(states_schedule[aperture_group])
            
            # filter by occupancy period
            filtered_datacollection = \
                datacollection.filter_by_analysis_period(analysis_period=ap)
            # get the percentage of occupied hours with shading on
            average = filtered_datacollection.average * 100

            # get figure
            figure = figure_aperture_group_schedule(aperture_group, datacollection)
            #svg_path = figure.write_image(f'assets/images/figures/{aperture_group}.pdf', width=700, height=350)
            img = BytesIO()
            fig_svg = figure.to_image(format='pdf', width=700, height=350, scale=3)
            img.write(fig_svg)
            img.seek(0)
            pdf_image =  PdfImage(img, width=200, height=100)
            story.append(pdf_image)
            #drawing = svg2rlg(img)
            #drawing = svg2rlg(svg_path)
            #assert False, drawing
            #drawing = scale(drawing, scaling_factor=None, width=400, height=None)
            #story.append(drawing)

        story.append(PageBreak())

    # Build and save the PDF
    doc.build(
        story
    )


if __name__ == "__main__":
    output_file = "sample.pdf"
    create_pdf(output_file)
    print(f"PDF generated successfully: {output_file}")
