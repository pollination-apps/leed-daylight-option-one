import pandas as pd

from reportlab.lib import colors
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.units import mm

from pdf.helper import ROWBACKGROUNDS, UNITS_ABBREVIATIONS
from pdf.styles import STYLES
from pdf.colors import get_ase_cell_color, get_sda_cell_color
from pdf.template import MyDocTemplate

from honeybee.model import Model


def table_from_summary_grid(model: Model, summary_grid: dict, grid_filter: list = None, add_total: bool = True):
    if grid_filter:
        summary_grid = {k: summary_grid[k] for k in grid_filter if k in summary_grid}
    df = pd.DataFrame.from_dict(summary_grid, orient='index')
    try:
        df = df[
            ['name', 'ase', 'sda', 'floor_area_passing_ase', 'floor_area_passing_sda',
            'total_floor_area']
            ]
        # rename columns
        df.rename(
            columns={
                'name': 'Space Name',
                'ase': 'ASE [%]',
                'sda': 'sDA [%]',
                'floor_area_passing_ase': f'Floor area passing ASE [{UNITS_ABBREVIATIONS[model.units]}2]',
                'floor_area_passing_sda': f'Floor area passing sDA [{UNITS_ABBREVIATIONS[model.units]}2]',
                'total_floor_area': f'Total floor area [{UNITS_ABBREVIATIONS[model.units]}2]'
                }, inplace=True)
    except Exception:
        df = df[
            ['name', 'ase', 'sda', 'sensor_count_passing_ase',
            'sensor_count_passing_sda', 'total_sensor_count']
            ]
        # rename columns
        df.rename(
            columns={
                'name': 'Space Name',
                'ase': 'ASE [%]',
                'sda': 'sDA [%]',
                'sensor_count_passing_ase': 'Sensor count passing ASE',
                'sensor_count_passing_sda': 'Sensor count passing sDA',
                'total_sensor_count': 'Total sensor count'
            }
        )

    ase_notes = []
    for data in summary_grid.values():
        if 'ase_note' in data:
            ase_notes.append('1)')
            df.loc[df['Space Name'] == data['name'], 'ASE Note'] = '1)'
        else:
            ase_notes.append('')
            df.loc[df['Space Name'] == data['name'], 'ASE Note'] = ''
    # if not all(n=='' for n in ase_notes):
    #     df['ASE Note'] = ase_notes

    if add_total:
        total_row = [
            Paragraph('Total'),
            Paragraph(''),
            Paragraph(''),
            Paragraph(str(round(df[f'Floor area passing ASE [{UNITS_ABBREVIATIONS[model.units]}2]'].sum(), 2))),
            Paragraph(str(round(df[f'Floor area passing sDA [{UNITS_ABBREVIATIONS[model.units]}2]'].sum(), 2))),
            Paragraph(str(round(df[f'Total floor area [{UNITS_ABBREVIATIONS[model.units]}2]'].sum(), 2))),
            Paragraph('')
        ]
    df = df.astype(str)
    table_data =  [tuple(df)] + list(df.itertuples(index=False, name=None))

    # base table style
    table_style = TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('LINEBELOW', (0, 0), (-1, 0), 0.2, colors.black)
    ])
    if add_total:
        table_style.add('ROWBACKGROUNDS', (0, 1), (-1, -2), ROWBACKGROUNDS)
    else:
        table_style.add('ROWBACKGROUNDS', (0, 1), (-1, -1), ROWBACKGROUNDS)

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
                formatted_row.append(Paragraph(cell_value, style=STYLES['Normal_BOLD']))
            else:
                formatted_row.append(Paragraph(cell_value))
        formatted_table_data.append(formatted_row)

    if add_total:
        formatted_table_data.append(total_row)
        table_style.add('LINEABOVE', (0, -1), (-1, -1), 0.2, colors.black)

    table = Table(formatted_table_data, colWidths='*', repeatRows=1, rowSplitRange=0, spaceBefore=5, spaceAfter=5)
    table.setStyle(table_style)

    return table, ase_notes


def create_metric_table(doc: MyDocTemplate, sda: float, ase: float):
    _sda_table = Table(
        data=[[Paragraph(f'sDA: {sda}%', style=STYLES['h2_c'])]],
        rowHeights=[16*mm]
    )
    table_style = TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('ROUNDEDCORNERS', [10, 10, 10, 10]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ])
    table_style.add('BACKGROUND', (0, 0), (0, 0), get_sda_cell_color(sda))
    _sda_table.setStyle(table_style)

    _ase_table = Table(
        data=[[Paragraph(f'ASE: {ase}%', style=STYLES['h2_c'])]],
        rowHeights=[16*mm]
    )
    table_style = TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('ROUNDEDCORNERS', [10, 10, 10, 10]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ])
    table_style.add('BACKGROUND', (0, 0), (0, 0), get_ase_cell_color(ase))
    _ase_table.setStyle(table_style)
    table_style = TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0)
    ])
    _metric_table = Table(
        data=[[_sda_table, '',_ase_table]],
        colWidths=[doc.width*0.45, None, doc.width*0.45]
    )
    _metric_table.setStyle(table_style)

    return _metric_table
