from pathlib import Path
from functools import partial
import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle, _baseFontNameB
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, BaseDocTemplate, Paragraph, \
    Table, TableStyle, PageTemplate, Frame, PageBreak, NextPageTemplate, \
    Image


from results import load_from_folder


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


def create_pdf(
        output_file, pagesize: tuple = A4, left_margin: float = 1.5*cm,
        right_margin: float = 1.5*cm, top_margin: float = 2*cm,
        bottom_margin: float = 2*cm,
    ):
    # Create a PDF document
    doc = SimpleDocTemplate(
        output_file, pagesize=pagesize, leftMargin=left_margin,
        rightMargin=right_margin, topMargin=top_margin,
        bottomMargin=bottom_margin, showBoundary=True
    )

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
    normal_style = styles['Normal']

    content = []
    content.append(Paragraph("LEED Daylight Option I", title_style))

    summary_content = []
    if summary['credits'] > 0:
        summary_content.append(
            Paragraph(f'LEED Credits: {summary["credits"]}', style=styles['Normal'].clone(name='Normal_GREEN', textColor='green'))
        )
    else:
        summary_content.append(
            Paragraph(f'LEED Credits: {summary["credits"]}', style=styles['Normal'])
        )
    
    summary_content.append(
        Paragraph(f'Spatial Daylight Autonomy: {summary["sda"]}%', style=styles['Normal'])
    )

    summary_content.append(
        Paragraph(f'Annual Sunlight Exposure: {summary["ase"]}%', style=styles['Normal'])
    )
    content.extend(summary_content)

    # Create content
    title = "Sample Report"
    content.extend([
        Paragraph("Introduction:", normal_style),
        Paragraph("This is the introduction section of the report.", normal_style),
        PageBreak(),
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

    table = Table(formatted_table_data, colWidths='*', repeatRows=1, rowSplitRange=4, spaceBefore=5, spaceAfter=5)
    table.setStyle(table_style)
    content.append(table)
    # footer_content = Paragraph("This is a footer. It goes on every page.  ", styles['Normal'])
    # frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    # template = PageTemplate(id='test', frames=frame, onPage=partial(header_and_footer, header_content=header_content, footer_content=footer_content))
    # doc.addPageTemplates([
    #     PageTemplate(id='no_border', onPage=partial(header_and_footer, header_content=header_content, footer_content=footer_content), frames=[summary_frame, summary_frame_2])
    #     ]
    # )

    # Build and save the PDF
    doc.build(
        content
    )


if __name__ == "__main__":
    output_file = "sample.pdf"
    create_pdf(output_file)
    print(f"PDF generated successfully: {output_file}")
