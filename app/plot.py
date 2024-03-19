"""Functions to support plots."""
import json
from pathlib import Path
import streamlit as st
import numpy as np
import plotly.graph_objects as go

from ladybug.datacollection import HourlyContinuousCollection
from ladybug.datatype.base import DataTypeBase
from ladybug.header import Header
from ladybug.color import Colorset
from ladybug.analysisperiod import AnalysisPeriod
from ladybug_charts._to_dataframe import dataframe
from ladybug_charts._helper import rgb_to_hex
from ladybug_pandas.series import Series


def get_figure_config(title: str) -> dict:
    """Set figure config so that a figure can be downloaded as SVG."""
    return {
        'toImageButtonOptions': {
            'format': 'svg',  # one of png, svg, jpeg, webp
            'filename': title,
            'height': 350,
            'width': 700,
            'scale': 1  # Multiply title/legend/axis/canvas sizes by this factor
        }
    }

def figure_grids(grid_id: str, states_schedule_err: dict):
    data_type = DataTypeBase(grid_id)
    hoys = states_schedule_err[grid_id]
    analysis_period = AnalysisPeriod()
    values = [0] * 8760
    for hoy in hoys:
        values[hoy] = 1
    header = Header(data_type=data_type, unit=None, analysis_period=analysis_period)
    hourly_data = HourlyContinuousCollection(header=header, values=values)

    df = dataframe()
    series = Series(hourly_data)
    df["value"] = series.values

    category = ["Pass", "Fail"]
    df["pass/fail"] = [category[int(value)] for value in df["value"]]

    fig = go.Figure(
        data=go.Heatmap(
            y=df["hour"],
            x=df["UTC_time"].dt.date,
            z=df["value"],
            zmin=0,
            zmax=1,
            colorscale=[[0, "rgb(90,255,90)"], [0.5, "rgb(90,255,90)"], [0.5, "rgb(255,90,90)"], [1, "rgb(255,90,90)"]],
            customdata=np.stack((df["month_names"], df["day"], df["pass/fail"]), axis=-1),
            hovertemplate=(
                "<b>"
                + grid_id
                + ": %{customdata[2]}"
                + "</b><br>Month: %{customdata[0]}<br>Day: %{customdata[1]}<br>"
                + "Hour: %{y}:00<br>"
            ),
            name="",
            colorbar=dict(
                tickvals=[0.25, 0.75],
                ticktext=category,
                thickness=20
            )
        )
    )

    # add horizontal lines marking the occupancy schedule
    fig.add_hline(y=7.5, line_dash='dash', line_width=1, line_color='black')
    fig.add_hline(y=17.5, line_dash='dash', line_width=1, line_color='black')
    fig.update_xaxes(dtick="M1", tickformat="%b", ticklabelmode="period")
    fig.update_yaxes(title_text="Hours of the day")

    fig_title = {
        'text': grid_id,
        'y': 0.95,
        'x': 0.5,
        'xanchor': 'center',
        'yanchor': 'top'
    }

    fig.update_layout(
        template='plotly_white',
        margin=dict(
            l=20, r=20, t=50, b=20),
        yaxis_nticks=13,
        title=fig_title
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor="black", mirror=True)
    fig.update_yaxes(showline=True, linewidth=1, linecolor="black", mirror=True)

    return fig


def figure_aperture_group_schedule(aperture_group: str,
    states_schedule: HourlyContinuousCollection):

    df = dataframe()
    series = Series(states_schedule)
    df["value"] = series.values

    category = ['Shading off', 'Shading on']

    shd_trans = states_schedule.header.metadata['Shade Transmittance']
    #df['value'] = df['value'].replace(1, 0).replace(shd_trans, 1)
    df['shading'] = [category[int(value)] for value in df['value']]

    fig = go.Figure(
        data=go.Heatmap(
            y=df["hour"],
            x=df["UTC_time"].dt.date,
            z=df["value"],
            zmin=0,
            zmax=1,
            colorscale=[[0, "rgb(90,255,90)"], [0.5, "rgb(90,255,90)"], [0.5, "rgb(255,90,90)"], [1, "rgb(255,90,90)"]],
            customdata=np.stack((df["month_names"], df["day"], df['shading']), axis=-1),
            hovertemplate=(
                "<b>"
                + aperture_group
                + ": %{customdata[2]} - " + "{:.0%}".format(round(shd_trans, 3))
                + "</b><br>Month: %{customdata[0]}<br>Day: %{customdata[1]}<br>"
                + "Hour: %{y}:00<br>"
            ),
            name="",
            colorbar=dict(
                tickvals=[0.25, 0.75],
                ticktext=['Shading off', 'Shading on'],
                thickness=20
            )
        )
    )

    # add horizontal lines marking the standard LEED occupancy schedule
    fig.add_hline(y=7.5, line_dash='dash', line_width=1, line_color='black')
    fig.add_hline(y=17.5, line_dash='dash', line_width=1, line_color='black')
    fig.update_xaxes(dtick="M1", tickformat="%b", ticklabelmode="period")
    fig.update_yaxes(title_text="Hours of the day")

    fig_title = {
        'text': aperture_group + ' - Shading transmittance: ' + '{:.0%}'.format(round(shd_trans, 3)),
        'y': 0.95,
        'x': 0.5,
        'xanchor': 'center',
        'yanchor': 'top'
    }

    fig.update_layout(
        template='plotly_white',
        margin=dict(
            l=20, r=20, t=50, b=20),
        yaxis_nticks=13,
        title=fig_title
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor="black", mirror=True)
    fig.update_yaxes(showline=True, linewidth=1, linecolor="black", mirror=True)

    return fig


def figure_ase(grid_info: dict, results_folder: Path):
    full_id = grid_info['full_id']
    grid_name = grid_info['name']
    with open (results_folder.joinpath(f'{full_id}.json')) as file:
        data_dict = json.load(file)
    hourly_data = HourlyContinuousCollection.from_dict(data_dict)

    df = dataframe()
    series = Series(hourly_data)
    df["value"] = series.values

    colors = Colorset.original()

    fig = go.Figure(
        data=go.Heatmap(
            y=df["hour"],
            x=df["UTC_time"].dt.date,
            z=df["value"],
            zmin=st.session_state['legend_min'],
            zmax=st.session_state['legend_max'],
            colorscale=[rgb_to_hex(color) for color in colors],
            customdata=np.stack((df["month_names"], df["day"]), axis=-1),
            hovertemplate=(
                "<b>"
                + grid_name
                + ": %{z:.2f}%"
                + "</b><br>Month: %{customdata[0]}<br>Day: %{customdata[1]}<br>"
                + "Hour: %{y}:00<br>"
            ),
            name="",
            colorbar=dict(
                title='[%]',
                thickness=20
            )
        )
    )

    # add horizontal lines marking the occupancy schedule
    fig.add_hline(y=7.5, line_dash='dash', line_width=1, line_color='black')
    fig.add_hline(y=17.5, line_dash='dash', line_width=1, line_color='black')
    fig.update_xaxes(dtick="M1", tickformat="%b", ticklabelmode="period")
    fig.update_yaxes(title_text="Hours of the day")

    fig_title = {
        'text': grid_name,
        'y': 1,
        'x': 0.5,
        'xanchor': 'center',
        'yanchor': 'top'
    }

    fig.update_layout(
        template='plotly_white',
        margin=dict(
            l=20, r=20, t=50, b=20),
        yaxis_nticks=13,
        title=fig_title
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor="black", mirror=True)
    fig.update_yaxes(showline=True, linewidth=1, linecolor="black", mirror=True)

    st.plotly_chart(fig, use_container_width=True, config=get_figure_config(grid_name))
