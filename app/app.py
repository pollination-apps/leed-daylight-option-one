"""Pollination LEED Daylight Option I App."""
import streamlit as st

from pollination_streamlit_viewer import viewer

from inputs import initialize
from menu import study_menu
from run import check_run_recipe
from results import load_results, load_from_folder
from process_results import (process_summary, show_errors, process_space,
    process_states_schedule, process_ase)


st.set_page_config(
    page_title='LEED Daylight Option I', layout='wide',
    page_icon='https://app.pollination.cloud/favicon.ico'
)

def main():
    """Main."""
    st.header('LEED Daylight Option I')
    initialize()

    study_tab, summary_tab, states_schedule_tab, dir_ill_tab, visualization_tab = \
        st.tabs(['Select a study', 'Summary report', 'States schedule',
                 'Direct Illuminance', 'Visualization']
        )

    with study_tab:
        study_menu()

    if st.session_state['run'] is not None \
        or st.session_state['load_method'] == 'Try the sample run':
        if st.session_state['load_method'] == 'Try the sample run':
            folder, vtjks_file, summary, summary_grid, states_schedule, \
                states_schedule_err, hb_model = load_from_folder(st.session_state.sample_folder)
        else:
            check_run_recipe(study_tab)
            folder, vtjks_file, summary, summary_grid, states_schedule, \
                states_schedule_err, hb_model = load_results()

        with study_tab:
            st.info('Please go to the next tab to show the results!')

        with summary_tab:
            process_summary(summary, hb_model)
            show_errors(summary, states_schedule_err)
            process_space(summary_grid, states_schedule_err)

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
