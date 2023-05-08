"""Pollination LEED Daylight Option I App."""
import streamlit as st
from packaging import version
from pathlib import Path

from pollination_streamlit.selectors import get_api_client, run_selector
from pollination_streamlit_io import auth_user
from pollination_streamlit_viewer import viewer

from helper import (download_files, process_summary,
    show_warnings_and_errors, process_space, process_states_schedule,
    process_ase, select_menu, load_from_folder)
from inputs import initialize


st.set_page_config(
    page_title='LEED Daylight Option I', layout='wide',
    page_icon='https://app.pollination.cloud/favicon.ico'
)

def main():
    # title
    st.header('LEED Daylight Option I')

    # initialize session state variables
    initialize()

    # set up tabs
    study_tab, summary_tab, states_schedule_tab, dir_ill_tab, visualization_tab = \
        st.tabs(['Select a study', 'Summary report', 'States schedule',
                 'Direct Illuminance', 'Visualization']
        )

    with study_tab:
        st.radio(
            'Load method', options=st.session_state.options,
            horizontal=True, label_visibility='collapsed', key='load_method',
            index=st.session_state.options.index(
                st.session_state.active_option)
        )

        if st.session_state['load_method'] != 'Try the sample run':
            api_client = get_api_client()
            user = auth_user('auth-user', api_client)
            if st.session_state['load_method'] == 'Load from a project':
                select_menu(api_client, user)
            elif st.session_state['load_method'] == 'Load from a URL':
                run = run_selector(
                    api_client, default=st.session_state['run_url'],
                    help='Paste run URL.'
                )
                st.session_state['run'] = run
        else:
            # get sample files
            sample_folder = st.session_state.target_folder.joinpath('sample')
            folder, vtjks_file, summary, summary_grid, states_schedule, \
                states_schedule_err = load_from_folder(sample_folder)

    if st.session_state['run'] is not None \
            or st.session_state['load_method'] == 'Try the sample run':
        run = st.session_state['run']
        if st.session_state['load_method'] != 'Try the sample run':
            if run.status.status.value != 'Succeeded':
                st.error(
                    'The run status must be \'Succeeded\'. '
                    f'The input run has status \'{run.status.status.value}\'.'
                )
                st.stop()
            if f'{run.recipe.owner}/{run.recipe.name}' != \
                'pollination/leed-daylight-option-one':
                st.error(
                    'This app is designed to work with pollination/leed-daylight-option-one '
                    f'recipe. The input run is using {run.recipe.owner}/{run.recipe.name}.'
                )
                st.stop()
            if version.parse(run.recipe.tag) < version.parse('0.0.19'):
                with study_tab:
                    st.error(
                        'Only versions pollination/leed-daylight-option-one:0.0.19 or higher '
                        f'are valid. Current version of the recipe: {run.recipe.tag}.'
                    )
                st.stop()

            if st.session_state.run_url:
                run_id = st.session_state.run_url.split('/')[-1]
                run_folder = Path(st.session_state['target_folder'].joinpath('data', run_id))
            if run_folder.exists():
                folder, vtjks_file, summary, summary_grid, states_schedule, \
                    states_schedule_err = load_from_folder(run_folder)
            else:
                with st.spinner('Downloading files...'):
                    folder, vtjks_file, summary, summary_grid, states_schedule, \
                        states_schedule_err = download_files(run)

        with summary_tab:
            process_summary(summary)
            show_warnings_and_errors(summary, summary_grid, states_schedule_err)
            process_space(summary_grid)

        with states_schedule_tab:
            process_states_schedule(states_schedule)

        with dir_ill_tab:
            process_ase(folder)

        with visualization_tab:
            viewer(content=vtjks_file.read_bytes(), key='viz')
    else:
        for tab in (summary_tab, states_schedule_tab, dir_ill_tab,
                    visualization_tab):
            with tab:
                st.error('Select a study in the first tab!')

if __name__ == '__main__':
    main()
