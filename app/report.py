import streamlit as st

from pollination_io.api.user import UserApi

from pdf_report import create_pdf


def export_report(user_api: UserApi):
    st.warning('This is a work in progress. Please do not use the report for compliance yet!')

    report_data = {}
    if st.session_state.load_method == 'Try the sample run':
        project_name = st.text_input('Project Name', value='Sample Project')
        prepared_by = st.text_input('Prepared By', value=user_api.get_user()['name'])
        project_folder = st.session_state.sample_folder
        temp_folder = st.session_state.target_folder.joinpath('temp')
        output_file = temp_folder.joinpath(f'report_{user_api.get_user()["username"]}.pdf')
        if not temp_folder.exists():
            temp_folder.mkdir()
        create_stories = st.checkbox('Create Stories', value=False,
            help='Check this box to create stories in the Honeybee Model. '
            'You should ideally create the stories before running the '
            'simulation. This option is temporary and exists only to showcase '
            'the summaries for each story in case they are not modelled prior '
            'to running the recipe.')
    else:
        project_name = st.text_input('Project Name', value=st.session_state.run.project)
        prepared_by = st.text_input('Prepared By', value=user_api.get_user()['name'])
        project_folder = st.session_state.run_folder
        output_file = project_folder.joinpath('report.pdf')
        create_stories = st.checkbox('Create Stories', value=False,
            help='Check this box to create stories in the Honeybee Model. '
            'You should ideally create the stories before running the '
            'simulation. This option is temporary and exists only to showcase '
            'the summaries for each story in case they are not modelled prior '
            'to running the recipe.')
    report_data['prepared_by'] = prepared_by
    report_data['project'] = project_name

    if st.button('Generate Report'):
        with st.spinner('Generating report...'):
            if output_file.exists():
                output_file.unlink()
            create_pdf(output_file, project_folder, st.session_state['run'], report_data, create_stories)

    if output_file.exists():
        with open(output_file, 'rb') as pdf_file:
            pdf_bytes = pdf_file.read()
        st.download_button('Download Report',
                           data=pdf_bytes,
                           file_name='report.pdf',
                           mime='application/octet-stream')
