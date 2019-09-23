import logging
import uuid
import os
import json
import pandas as pd
import errno
from natsort import natsorted

from installed_clients.DataFileUtilClient import DataFileUtil
from GenericsAPI.Utils.DataUtil import DataUtil
from installed_clients.KBaseReportClient import KBaseReport


class DataTableUtil:

    def _mkdir_p(self, path):
        """
        _mkdir_p: make directory for given path
        """
        if not path:
            return
        try:
            os.makedirs(path)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(path):
                pass
            else:
                raise

    def _build_table_content(self, output_directory, matrix_df):
        """
        _build_table_content: generate HTML table content for FloatMatrix2D object
        """

        logging.info('Start generating table content page')

        page_content = """\n"""

        table_file_name = 'matrix_data_viewer_{}.html'.format(str(uuid.uuid4()))
        data_file_name = 'matrix_data_{}.json'.format(str(uuid.uuid4()))

        page_content += """<iframe height="900px" width="100%" """
        page_content += """src="{}" """.format(table_file_name)
        page_content += """style="border:none;"></iframe>\n"""

        table_headers = matrix_df.columns.tolist()
        table_content = """\n"""
        # build header and footer
        table_content += """\n<thead>\n<tr>\n"""
        for table_header in table_headers:
            table_content += """\n <th>{}</th>\n""".format(table_header)
        table_content += """\n</tr>\n</thead>\n"""

        table_content += """\n<tfoot>\n<tr>\n"""
        for table_header in table_headers:
            table_content += """\n <th>{}</th>\n""".format(table_header)
        table_content += """\n</tr>\n</tfoot>\n"""

        logging.info('start generating table json file')
        data_array = matrix_df.values.tolist()

        total_rec = len(data_array)
        json_dict = {'draw': 1,
                     'recordsTotal': total_rec,
                     'recordsFiltered': total_rec,
                     'data': data_array}

        with open(os.path.join(output_directory, data_file_name), 'w') as fp:
            json.dump(json_dict, fp)

        logging.info('start generating table html')
        with open(os.path.join(output_directory, table_file_name), 'w') as result_file:
            with open(os.path.join(os.path.dirname(__file__), 'templates',
                                   'matrix_table_viewer_template.html'),
                      'r') as report_template_file:
                report_template = report_template_file.read()
                report_template = report_template.replace('<p>table_header</p>',
                                                          table_content)
                report_template = report_template.replace('ajax_file_path',
                                                          data_file_name)
                report_template = report_template.replace('deferLoading_size',
                                                          str(total_rec))
                result_file.write(report_template)
        #exit(page_content)
        '''
        <iframe height="900px" width="100%" src="matrix_data_viewer_f3dac561-d9a3-4b05-a79c-d5ce454a36e8.html" style="border:none;"></iframe>
        '''
        return page_content

    def _generate_visualization_content(self, output_directory, matrix_df):
        #exit(matrix_df)
        '''
        ID                        ...                                                                   taxonomy
        0  GG_OTU_1                        ...                          ['k__Bacteria', 'p__Proteobacteria', 'c__Gamma...
        1  GG_OTU_2                        ...                          ['k__Bacteria', 'p__Cyanobacteria', 'c__Nostoc...
        2  GG_OTU_3                        ...                          ['k__Archaea', 'p__Euryarchaeota', 'c__Methano...
        3  GG_OTU_4                        ...                          ['k__Bacteria', 'p__Firmicutes', 'c__Clostridi...
        4  GG_OTU_5                        ...                          ['k__Bacteria', 'p__Proteobacteria', 'c__Gamma...

        [5 rows x 8 columns]
        '''
        tab_def_content = ''
        tab_content = ''

        tab_def_content += """\n<div class="tab">\n"""
        tab_def_content += """
        <button class="tablinks" onclick="openTab(event, 'MatrixData')" id="defaultOpen">Matrix Data</button>
        """

        corr_table_content = self._build_table_content(output_directory, matrix_df)
        tab_content += """\n<div id="MatrixData" class="tabcontent">{}</div>\n""".format(
                                                                                corr_table_content)

        tab_def_content += """\n</div>\n"""

        #exit(tab_def_content + tab_content)
        '''
        <div class="tab">

        <button class="tablinks" onclick="openTab(event, 'MatrixData')" id="defaultOpen">Matrix Data</button>
        
</div>

<div id="MatrixData" class="tabcontent">
<iframe height="900px" width="100%" src="matrix_data_viewer_273ab8bc-b5bf-4708-87c6-5fe01208be55.html" style="border:none;"></iframe>
</div>

        '''
        return tab_def_content + tab_content

    def _generate_matrix_html_report(self, matrix_df):

        """
        _generate_matrix_html_report: generate html summary report for matrix
        """

        logging.info('Start generating html report')
        html_report = list()

        output_directory = os.path.join(self.scratch, str(uuid.uuid4()))
        self._mkdir_p(output_directory)
        result_file_path = os.path.join(output_directory, 'matrix_report.html')

        visualization_content = self._generate_visualization_content(output_directory, matrix_df)

        with open(result_file_path, 'w') as result_file:
            with open(os.path.join(os.path.dirname(__file__), 'templates', 'matrix_template.html'),
                      'r') as report_template_file:
                report_template = report_template_file.read()
                report_template = report_template.replace('<p>Visualization_Content</p>',
                                                          visualization_content)
                result_file.write(report_template)

        report_shock_id = self.dfu.file_to_shock({'file_path': output_directory,
                                                  'pack': 'zip'})['shock_id']

        html_report.append({'shock_id': report_shock_id,
                            'name': os.path.basename(result_file_path),
                            'label': os.path.basename(result_file_path),
                            'description': 'HTML summary report for Compute Correlation App'
                            })
        return html_report

    def _generate_corr_report(self, workspace_name, matrix_df):
        """
        _generate_report: generate summary report
        """
        logging.info('Start creating report')

        output_html_files = self._generate_matrix_html_report(matrix_df)

        report_params = {'message': '',
                         'workspace_name': workspace_name,
                         'html_links': output_html_files,
                         'direct_html_link_index': 0,
                         'html_window_height': 666,
                         'report_object_name': 'matrix_viewer_report_' + str(uuid.uuid4())}

        kbase_report_client = KBaseReport(self.callback_url, token=self.token)
        output = kbase_report_client.create_extended_report(report_params)

        report_output = {'report_name': output['name'], 'report_ref': output['ref']}

        return report_output

    def _fetch_matrix_df(self, input_matrix_ref, with_attribute_info):
        #exit(input_matrix_ref)    44071/21/229
        logging.info('Start fetch matrix content')

        matrix_obj = self.dfu.get_objects({'object_refs': [input_matrix_ref]})['data'][0]
        matrix_info = matrix_obj['info']
        matrix_data = matrix_obj['data']

        matrix_type = matrix_info[2].split('-')[0].split('.')[-1]
        if matrix_type not in self.matrix_types:
            raise ValueError('Unexpected matrix type: {}'.format(matrix_type))

        data_matrix = self.data_util.fetch_data({'obj_ref': input_matrix_ref}).get('data_matrix')
        matrix_df = pd.read_json(data_matrix)
        matrix_df = matrix_df.reindex(index=natsorted(matrix_df.index))

        row_am_ref = matrix_data.get('row_attributemapping_ref')
        if with_attribute_info and row_am_ref:
            am_data = self.dfu.get_objects({'object_refs': [row_am_ref]})['data'][0]['data']
            instances = am_data['instances']
            columns = [x['attribute'] for x in am_data['attributes']]
            row_am_df = pd.DataFrame(list(instances.values()), index=instances.keys(), columns=columns)

            # row_am = self.data_util.fetch_data({'obj_ref': row_am_ref}).get('data_matrix')g
            # row_am_df = pd.read_json(row_am)

            matrix_df = matrix_df.join(row_am_df)

        matrix_df.index.name = 'ID'
        matrix_df.reset_index(inplace=True)
        matrix_df = matrix_df.astype(str)
        #exit(matrix_df)
        '''
        SystemExit:          ID                        ...                                                                   taxonomy
0  GG_OTU_1                        ...                          ['k__Bacteria', 'p__Proteobacteria', 'c__Gamma...
1  GG_OTU_2                        ...                          ['k__Bacteria', 'p__Cyanobacteria', 'c__Nostoc...
2  GG_OTU_3                        ...                          ['k__Archaea', 'p__Euryarchaeota', 'c__Methano...
3  GG_OTU_4                        ...                          ['k__Bacteria', 'p__Firmicutes', 'c__Clostridi...
4  GG_OTU_5                        ...                          ['k__Bacteria', 'p__Proteobacteria', 'c__Gamma...

        '''
        return matrix_df

    def __init__(self, config):
        self.callback_url = config['SDK_CALLBACK_URL']
        self.scratch = config['scratch']
        self.token = config['KB_AUTH_TOKEN']
        self.dfu = DataFileUtil(self.callback_url)
        self.data_util = DataUtil(config)
        self.matrix_types = [x.split(".")[1].split('-')[0]
                             for x in self.data_util.list_generic_types()]

    def view_matrix_as_table(self, params):
        input_matrix_ref = params.get('input_matrix_ref')
        workspace_name = params.get('workspace_name')
        with_attribute_info = params.get('with_attribute_info', True)

        matrix_df = self._fetch_matrix_df(input_matrix_ref, with_attribute_info)

        returnVal = dict()
        report_output = self._generate_corr_report(workspace_name, matrix_df)

        returnVal.update(report_output)

        return returnVal
