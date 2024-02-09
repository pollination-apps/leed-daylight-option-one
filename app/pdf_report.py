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
from reportlab.lib.utils import simpleSplit
from reportlab.lib.units import mm, cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle, _baseFontNameB
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.graphics.shapes import Drawing
from reportlab.platypus import SimpleDocTemplate, BaseDocTemplate, Flowable, Paragraph, \
    Table, TableStyle, PageTemplate, Frame, PageBreak, NextPageTemplate, \
    Image, FrameBreak, Spacer, HRFlowable, CondPageBreak, KeepTogether
from svglib.svglib import svg2rlg

from ladybug.analysisperiod import AnalysisPeriod
from ladybug.datacollection import HourlyContinuousCollection

from results import load_from_folder
from plot import figure_grids, figure_aperture_group_schedule, figure_ase


folder, vtjks_file, summary, summary_grid, states_schedule, \
    states_schedule_err = load_from_folder(Path('./app/sample'))


class NumberedPageCanvas(canvas.Canvas):
    """
    http://code.activestate.com/recipes/546511-page-x-of-y-with-reportlab/
    http://code.activestate.com/recipes/576832/
    http://www.blog.pythonlibrary.org/2013/08/12/reportlab-how-to-add-page-numbers/
    https://stackoverflow.com/a/59882495/
    """

    def __init__(self, *args, **kwargs):
        """Constructor"""
        super().__init__(*args, **kwargs)
        self.pages = []

    def showPage(self):
        """
        On a page break, add information to the list
        """
        self.pages.append(dict(self.__dict__))
        self._doc.pageCounter += 1
        self._startPage()

    def save(self):
        """
        Add the page number to each page (page x of y)
        """
        page_count = len(self.pages)

        for page in self.pages:
            self.__dict__.update(page)
            self.draw_page_number(page_count)
            super().showPage()

        super().save()

    def draw_page_number(self, page_count):
        """
        Add the page number
        """
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
    document_title = Paragraph("LEED Daylight Option I", title_style)
    story.append(document_title)

    summary_story = []
    if summary['credits'] > 0:
        summary_story.append(
            Paragraph(f'LEED Credits: {summary["credits"]}', style=styles['h1'].clone(name='h1_GREEN', textColor='green'))
        )
    else:
        summary_story.append(
            Paragraph(f'LEED Credits: {summary["credits"]}', style=styles['h1'])
        )
    
    summary_story.append(
        Paragraph(f'Spatial Daylight Autonomy: {summary["sda"]}%', style=styles['Normal'])
    )

    summary_story.append(
        Paragraph(f'Annual Sunlight Exposure: {summary["ase"]}%', style=styles['Normal'])
    )
    story.extend(summary_story)

    story.append(Spacer(width=0*cm, height=0.5*cm))

    # Create content
    story.extend([
        Paragraph("Space Overview", style=styles['h2'])
        ]
    )

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

    def table_from_summary_grid(summary_grid, grid_filter: list = None):
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

        data = df.values.tolist()

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

        story.append(Spacer(width=0*cm, height=0.5*cm))

        _sda_table = Table(data=[['Spatial Daylight Autonomy'], [Paragraph(f'{values["sda"]}%', style=styles['h2_CENTER'])]], rowHeights=[None, 16*mm])
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('ROUNDEDCORNERS', [10, 10, 10, 10]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ])
        table_style.add('BACKGROUND', (0, 0), (0, 0), colors.Color(220 / 255, 220 / 255, 220 / 255, 0.3))
        table_style.add('BACKGROUND', (0, 1), (0, 1), get_sda_cell_color(values["sda"]))
        _sda_table.setStyle(table_style)
        # _ase_table = Table(data=[['Annual Sunlight Exposure'], [Paragraph(f'{values["ase"]}%', style=styles['h2_CENTER'])]], rowHeights=[None, 16*mm])
        # table_style = TableStyle([
        #     ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        #     ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        #     ('ROUNDEDCORNERS', [10, 10, 10, 10]),
        #     ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        # ])
        # table_style.add('BACKGROUND', (0, 0), (0, 0), colors.Color(220 / 255, 220 / 255, 220 / 255, 0.3))
        # table_style.add('BACKGROUND', (0, 1), (0, 1), get_ase_cell_color(values["ase"]))
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

        table, ase_notes = table_from_summary_grid(summary_grid, [grid_id])
        
        story.append(Spacer(width=0*cm, height=0.5*cm))
        story.append(table)
        story.append(Spacer(width=0*cm, height=0.5*cm))

        ase_note = values.get('ase_note')
        if ase_note:
            pass
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
            pdf_image =  PdfImage(BytesIO(fig_pdf), width=doc.width*(2/3), height=None, keep_ratio=True)
            pdf_table = Table([[pdf_image]])
            table = Table([[shading_table, pdf_table]], colWidths=[doc.width*(1/3), doc.width*(2/3)])
            table.setStyle(
                TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP')
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

    pollination_image = 'assets/images/pollination.png'
    # Build and save the PDF
    doc.build(
        story,
        onFirstPage=partial(_header_and_footer, header_content=header_content, footer_content=footer_content, logo=pollination_image),
        onLaterPages=partial(_header_and_footer, header_content=header_content, footer_content=footer_content, logo=pollination_image),
        canvasmaker=NumberedPageCanvas
    )


if __name__ == "__main__":
    output_file = "sample.pdf"
    create_pdf(output_file)
    print(f"PDF generated successfully: {output_file}")
