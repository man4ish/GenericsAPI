import errno
import itertools
import json
import logging
import os
import shutil
import sys
import uuid

import pandas as pd
import plotly.graph_objs as go
from matplotlib import pyplot as plt
from plotly.offline import plot
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from installed_clients.DataFileUtilClient import DataFileUtil
from GenericsAPI.Utils.DataUtil import DataUtil
from installed_clients.KBaseReportClient import KBaseReport


class PCAUtil:

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

    def _validate_run_pca_params(self, params):
        """
        _validate_run_pca_params:
            validates params passed to run_pca method
        """

        logging.info('start validating run_pca params')

        # check for required parameters
        for p in ['input_obj_ref', 'workspace_name', 'pca_matrix_name']:
            if p not in params:
                raise ValueError('"{}" parameter is required, but missing'.format(p))

    def _df_to_list(self, df):
        """
        _df_to_list: convert Dataframe to FloatMatrix2D matrix data
        """

        df.index = df.index.astype('str')
        df.columns = df.columns.astype('str')
        df.fillna(0, inplace=True)
        matrix_data = {'row_ids': df.index.tolist(),
                       'col_ids': df.columns.tolist(),
                       'values': df.values.tolist()}

        return matrix_data

    def _pca_df_to_excel(self, pca_df, components_df, result_dir, pca_matrix_ref):
        """
        write PCA matrix df into excel
        """
        logging.info('writting pca data frame to excel file')
        pca_matrix_obj = self.dfu.get_objects({'object_refs': [pca_matrix_ref]})['data'][0]
        pca_matrix_info = pca_matrix_obj['info']
        pca_matrix_name = pca_matrix_info[1]

        file_path = os.path.join(result_dir, pca_matrix_name + ".xlsx")

        writer = pd.ExcelWriter(file_path)

        pca_df.to_excel(writer, "principal_component_matrix", index=True)
        if components_df is not None:
            components_df.to_excel(writer, "component_variance_matrix", index=True)

        writer.close()

    def _Matrix2D_to_df(self, Matrix2D):
        """
        _Matrix2D_to_df: transform a FloatMatrix2D to data frame
        """

        index = Matrix2D.get('row_ids')
        columns = Matrix2D.get('col_ids')
        values = Matrix2D.get('values')

        df = pd.DataFrame(values, index=index, columns=columns)

        return df

    def _pca_to_df(self, pca_matrix_ref):
        """
        retrieve pca matrix ws object to pca_df
        """
        logging.info('converting pca matrix to data frame')
        pca_data = self.dfu.get_objects({'object_refs': [pca_matrix_ref]})['data'][0]['data']
       
        rotation_matrix_data = pca_data.get('rotation_matrix')
        # exit(rotation_matrix_data)   {'col_ids': ['principal_component_1', 'principal_component_2'], 'row_ids': ['WRI_RS00010_CDS_1', 'WRI_RS00015_CDS_1', 'WRI_RS00025_CDS_1'], 'values': [[-0.45, 1.06], [-0.69, -0.92], [1.14, -0.13]]}
        components_matrix_data = pca_data.get('components_matrix')
        
        explained_variance = pca_data.get('explained_variance')
        #exit(explained_variance) [0.628769688409428, 0.371230311590572]
        explained_variance_ratio = pca_data.get('explained_variance_ratio')
        #exit(explained_variance_ratio) [0.628769688409428, 0.371230311590572] 
        singular_values = pca_data.get('singular_values')
        #exit(singular_values)
        dimension = pca_data.get('pca_parameters').get('dimension') 
        
        original_matrix_ref = pca_data.get('original_matrix_ref')

        pca_df = self._Matrix2D_to_df(rotation_matrix_data)
        components_df = None
        if components_matrix_data:
            components_df = self._Matrix2D_to_df(components_matrix_data)
            components_df.loc['explained_variance'] = explained_variance
            components_df.loc['explained_variance_ratio'] = explained_variance_ratio
            components_df.loc['singular_values'] = singular_values

        if original_matrix_ref:
            logging.info('appending instance group information to pca data frame')
            obj_data = self.dfu.get_objects({'object_refs': [original_matrix_ref]})['data'][0]['data']

            attributemapping_ref = obj_data.get('{}_attributemapping_ref'.format(dimension))

            am_data = self.dfu.get_objects({'object_refs': [attributemapping_ref]})['data'][0]['data']

            attributes = am_data.get('attributes')
            instances = am_data.get('instances')
            am_df = pd.DataFrame(data=list(instances.values()),
                                 columns=list(map(lambda x: x.get('attribute'), attributes)),
                                 index=instances.keys())

            pca_df = pca_df.merge(am_df, left_index=True, right_index=True, how='left',
                                  validate='one_to_one')

        return pca_df, components_df

    def _save_pca_matrix(self, workspace_name, input_obj_ref, pca_matrix_name, rotation_matrix_df,
                         components_df, explained_variance, explained_variance_ratio,
                         singular_values, n_components, dimension):

        logging.info('saving PCAMatrix')

        if not isinstance(workspace_name, int):
            ws_name_id = self.dfu.ws_name_to_id(workspace_name)
        else:
            ws_name_id = workspace_name

        pca_data = {}

        pca_data.update({'rotation_matrix': self._df_to_list(rotation_matrix_df)})
        pca_data.update({'components_matrix': self._df_to_list(components_df)})
        pca_data.update({'explained_variance': explained_variance})
        pca_data.update({'explained_variance_ratio': explained_variance_ratio})
        pca_data.update({'singular_values': singular_values})
        pca_data.update({'pca_parameters': {'n_components': str(n_components),
                                            'dimension': str(dimension)}})
        pca_data.update({'original_matrix_ref': input_obj_ref})
        

        obj_type = 'KBaseExperiments.PCAMatrix'
        info = self.dfu.save_objects({
            "id": ws_name_id,
            "objects": [{
                "type": obj_type,
                "data": pca_data,
                "name": pca_matrix_name
            }]
        })[0]
        
        return "%s/%s/%s" % (info[6], info[0], info[4])

    def _pca_for_matrix(self, input_obj_ref, n_components, dimension):
        """
        _pca_for_matrix: perform PCA analysis for matrix object
        """

        data_matrix = self.data_util.fetch_data({'obj_ref': input_obj_ref}).get('data_matrix')

        data_df = pd.read_json(data_matrix)
        data_df.fillna(0, inplace=True)

        if dimension == 'col':
            data_df = data_df.T
        elif dimension != 'row':
            err_msg = 'Input dimension [{}] is not available.\n'.format(dimension)
            err_msg += 'Please choose either "col" or "row"'
            raise ValueError(err_msg)

        if n_components > min(data_df.index.size, data_df.columns.size):
            raise ValueError('Number of components should be less than min(n_samples, n_features)')

        # normalize sample
        # logging.info("Standardizing the matrix")
        # s_values = StandardScaler().fit_transform(data_df.values)
        # skip normalizing sample
        s_values = data_df.values

        # Projection to ND
        pca = PCA(n_components=n_components, whiten=True)
        principalComponents = pca.fit_transform(s_values)
        explained_variance = list(pca.explained_variance_)
        explained_variance_ratio = list(pca.explained_variance_ratio_)

        components = pca.components_
        singular_values = list(pca.singular_values_)
        

        col = list()
        for i in range(n_components):
            col.append('principal_component_{}'.format(i+1))

        rotation_matrix_df = pd.DataFrame(data=principalComponents,
                                          columns=col,
                                          index=data_df.index)

        components_df = pd.DataFrame(data=components,
                                     columns=data_df.columns,
                                     index=col).transpose()

        rotation_matrix_df.fillna(0, inplace=True)

        return (rotation_matrix_df, components_df, explained_variance, explained_variance_ratio,
                singular_values)

    def _generate_pca_html_report(self, pca_plots, n_components):

        logging.info('start generating html report')
        html_report = list()

        output_directory = os.path.join(self.scratch, str(uuid.uuid4()))
        self._mkdir_p(output_directory)
        result_file_path = os.path.join(output_directory, 'pca_report.html')

        visualization_content = ''

        for pca_plot in pca_plots:
            shutil.copy2(pca_plot,
                         os.path.join(output_directory, os.path.basename(pca_plot)))
            visualization_content += '<iframe height="900px" width="100%" '
            visualization_content += 'src="{}" '.format(os.path.basename(pca_plot))
            visualization_content += 'style="border:none;"></iframe>\n<p></p>\n'

        with open(result_file_path, 'w') as result_file:
            with open(os.path.join(os.path.dirname(__file__), 'templates', 'pca_template.html'),
                      'r') as report_template_file:
                report_template = report_template_file.read()
                report_template = report_template.replace('<p>Visualization_Content</p>',
                                                          visualization_content)
                report_template = report_template.replace('n_components',
                                                          '{} Components'.format(n_components))
                result_file.write(report_template)

        report_shock_id = self.dfu.file_to_shock({'file_path': output_directory,
                                                  'pack': 'zip'})['shock_id']

        html_report.append({'shock_id': report_shock_id,
                            'name': os.path.basename(result_file_path),
                            'label': os.path.basename(result_file_path),
                            'description': 'HTML summary report for ExpressionMatrix Cluster App'
                            })
        return html_report

    def _generate_pca_report(self, pca_ref, pca_plots, workspace_name, n_components):
        logging.info('creating report')

        output_html_files = self._generate_pca_html_report(pca_plots, n_components)

        objects_created = list()
        objects_created.append({'ref': pca_ref,
                                'description': 'PCA Matrix'})

        report_params = {'message': '',
                         'workspace_name': workspace_name,
                         'objects_created': objects_created,
                         'html_links': output_html_files,
                         'direct_html_link_index': 0,
                         'html_window_height': 666,
                         'report_object_name': 'kb_pca_report_' + str(uuid.uuid4())}

        kbase_report_client = KBaseReport(self.callback_url)
        output = kbase_report_client.create_extended_report(report_params)

        report_output = {'report_name': output['name'], 'report_ref': output['ref']}

        return report_output

    def _append_instance_group(self, plot_pca_matrix, obj_data, dimension):
        plot_pca_matrix = plot_pca_matrix.copy()
        #exit(obj_data)  {'attributes': {'Instrument': 'Old Faithful', 'Scientist': 'Marie Currie'}, 'col_attributemapping_ref': '44071/7/79', 'col_mapping': {'instance_1': 'test_col_instance_1', 'instance_2': 'test_col_instance_2', 'instance_3': 'test_col_instance_3', 'instance_4': 'test_col_instance_4'}, 'col_normalization': 'test_col_normalization', 'data': {'col_ids': ['instance_1', 'instance_2', 'instance_3', 'instance_4'], 'row_ids': ['WRI_RS00010_CDS_1', 'WRI_RS00015_CDS_1', 'WRI_RS00025_CDS_1'], 'values': [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8], [None, None, 1.1, 1.2]]}, 'description': 'test_desc', 'row_attributemapping_ref': '44071/8/71', 'row_mapping': {'WRI_RS00010_CDS_1': 'test_row_instance_1', 'WRI_RS00015_CDS_1': 'test_row_instance_2', 'WRI_RS00025_CDS_1': 'test_row_instance_3'}, 'row_normalization': 'test_row_normalization', 'scale': 'log2', 'search_attributes': ['Scientist | Marie Currie', 'Instrument | Old Faithful']}
        if dimension == 'row':
            attribute_mapping = obj_data.get('row_mapping')
        elif dimension == 'col':
            attribute_mapping = obj_data.get('col_mapping')
        else:
            raise ValueError('Unexpected dimension')

        if not attribute_mapping:
            logging.warning('Matrix object does not have {}_mapping attribute'.format(dimension))
            # build matrix with unify color and shape
            return plot_pca_matrix
        else:
            # append instance col mapping from row/col_mapping
            plot_pca_matrix['instance'] = plot_pca_matrix.index.map(attribute_mapping)
            #exit(plot_pca_matrix)  
            ''' principal_component_1         ...                      instance
            WRI_RS00010_CDS_1              -0.853094         ...           test_row_instance_1
            WRI_RS00015_CDS_1              -0.247377         ...           test_row_instance_2
            WRI_RS00025_CDS_1               1.100471         ...           test_row_instance_3'''


        return plot_pca_matrix

    def _build_size_pca_matrix(self, plot_pca_matrix, obj_data, dimension, attribute_name):
        """
        _build_size_pca_matrix: append attribute value to rotation_matrix
        """
        logging.info('appending attribute value for sizing to rotation matrix')

        plot_pca_matrix = plot_pca_matrix.copy()

        if dimension == 'row':
            attribute_mapping = obj_data.get('row_mapping')
            attribute_mapping_ref = obj_data.get('row_attributemapping_ref')
        elif dimension == 'col':
            attribute_mapping = obj_data.get('col_mapping')
            attribute_mapping_ref = obj_data.get('col_attributemapping_ref')
        else:
            raise ValueError('Unexpected dimension')

        if not attribute_mapping:
            logging.warning('Matrix object does not have {}_mapping attribute'.format(dimension))
            # build matrix with unify color and shape
            return plot_pca_matrix
        else:
            # append instance col mapping from row/col_mapping
            # exit(plot_pca_matrix.index.map(attribute_mapping))  Index(['test_row_instance_1', 'test_row_instance_2', 'test_row_instance_3'], dtype='object')
            plot_pca_matrix['instance'] = plot_pca_matrix.index.map(attribute_mapping)

        res = self.dfu.get_objects({'object_refs': [attribute_mapping_ref]})['data'][0]
        attri_data = res['data']
        attri_name = res['info'][1]

        attributes = attri_data.get('attributes')
        #exit(attributes)  [{'attribute': 'test_attribute_1', 'attribute_ont_id': 'OBI_0500020', 'source': 'upload', 'unit': 'Hour', 'unit_ont_id': 'UO:0000032', 'unit_ont_ref': '6308/15/6'}, {'attribute': 'test_attribute_2', 'attribute_ont_id': 'CHEBI:9168', 'attribute_ont_ref': '6308/19/1', 'source': 'upload', 'unit': 'nanogram per milliliter', 'unit_ont_id': 'UO:0000275', 'unit_ont_ref': '6308/15/6'}, {'attribute': 'test_attribute_3', 'attribute_ont_id': 'CHEBI:9168', 'attribute_ont_ref': '6308/19/1', 'source': 'upload', 'unit': 'nanogram per milliliter', 'unit_ont_id': 'UO:0000275', 'unit_ont_ref': '6308/15/6'}]


        attr_pos = None
        for idx, attribute in enumerate(attributes):
            if attribute.get('attribute') == attribute_name:
                attr_pos = idx
                break

        if attr_pos is None:
            raise ValueError('Cannot find attribute [{}] in [{}]'.format(attribute_name,
                                                                         attri_name))

        instances = attri_data.get('instances')
        #exit(instances) {'test_row_instance_1': ['1', '4', '7'], 'test_row_instance_2': ['3', '4', '8'], 'test_row_instance_3': ['3', '6', '7']}

        plot_pca_matrix['attribute_value_size'] = None
        for instance_name, attri_values in instances.items():
            plot_pca_matrix.loc[plot_pca_matrix.instance == instance_name,
                                ['attribute_value_size']] = attri_values[attr_pos]
        #exit(plot_pca_matrix)
        '''
        principal_component_1          ...           attribute_value_size
        WRI_RS00010_CDS_1              -0.853094          ...                              1
        WRI_RS00015_CDS_1              -0.247377          ...                              3
        WRI_RS00025_CDS_1               1.100471          ...                              3

        '''
        return plot_pca_matrix

    def _build_color_pca_matrix(self, plot_pca_matrix, obj_data, dimension, attribute_name):
        """
        _build_color_pca_matrix: append attribute value to rotation_matrix
        """
        logging.info('appending attribute value for grouping color to rotation matrix')

        plot_pca_matrix = plot_pca_matrix.copy()

        if dimension == 'row':
            attribute_mapping = obj_data.get('row_mapping')
            attribute_mapping_ref = obj_data.get('row_attributemapping_ref')
        elif dimension == 'col':
            attribute_mapping = obj_data.get('col_mapping')
            attribute_mapping_ref = obj_data.get('col_attributemapping_ref')
        else:
            raise ValueError('Unexpected dimension')

        if not attribute_mapping:
            logging.warning('Matrix object does not have {}_mapping attribute'.format(dimension))
            # build matrix with unify color and shape
            return plot_pca_matrix
        else:
            # append instance col mapping from row/col_mapping
            plot_pca_matrix['instance'] = plot_pca_matrix.index.map(attribute_mapping)

        res = self.dfu.get_objects({'object_refs': [attribute_mapping_ref]})['data'][0]
        attri_data = res['data']
        attri_name = res['info'][1]

        attributes = attri_data.get('attributes')

        attr_pos = None
        for idx, attribute in enumerate(attributes):
            if attribute.get('attribute') == attribute_name:
                attr_pos = idx
                break

        if attr_pos is None:
            raise ValueError('Cannot find attribute [{}] in [{}]'.format(attribute_name,
                                                                         attri_name))

        instances = attri_data.get('instances')
        #exit(instances) {'test_row_instance_1': ['1', '4', '7'], 'test_row_instance_2': ['3', '4', '8'], 'test_row_instance_3': ['3', '6', '7']}
        plot_pca_matrix['attribute_value_color'] = None
        for instance_name, attri_values in instances.items():
            #exit(attri_values) ['1', '4', '7']
            plot_pca_matrix.loc[plot_pca_matrix.instance == instance_name,
                                ['attribute_value_color']] = attri_values[attr_pos]

        return plot_pca_matrix

    def _build_2_comp_trace(self, plot_pca_matrix, components_x, components_y):
        #exit(plot_pca_matrix)
        '''
        principal_component_1          ...           attribute_value_size
        WRI_RS00010_CDS_1              -0.853094          ...                              1
        WRI_RS00015_CDS_1              -0.247377          ...                              3
        WRI_RS00025_CDS_1               1.100471          ...                              3

        '''
        #exit(components_x)  principal_component_1
        #exit(components_y)  principal_component_2
        traces = []

        if 'attribute_value_color' in plot_pca_matrix.columns and 'attribute_value_size' in plot_pca_matrix.columns:

            maximum_marker_size = 10
            sizeref = 2.*float(max(plot_pca_matrix['attribute_value_size']))/(maximum_marker_size**2)

            for name in set(plot_pca_matrix.attribute_value_color):
                attribute_value_size = plot_pca_matrix.loc[plot_pca_matrix['attribute_value_color'].eq(name)].attribute_value_size
                size_list = list(map(abs, list(map(float, attribute_value_size))))
                for idx, val in enumerate(size_list):
                    if val == 0:
                        size_list[idx] = sys.float_info.min
                trace = go.Scatter(
                    x=list(plot_pca_matrix.loc[plot_pca_matrix['attribute_value_color'].eq(name)][components_x]),
                    y=list(plot_pca_matrix.loc[plot_pca_matrix['attribute_value_color'].eq(name)][components_y]),
                    mode='markers',
                    name=name,
                    text=list(plot_pca_matrix.loc[plot_pca_matrix['attribute_value_color'].eq(name)].index),
                    textposition='bottom center',
                    marker=go.Marker(symbol='circle', sizemode='area', sizeref=sizeref,
                                     size=size_list, sizemin=2,
                                     line=go.Line(color='rgba(217, 217, 217, 0.14)', width=0.5),
                                     opacity=0.8))
                traces.append(trace)
        elif 'attribute_value_color' in plot_pca_matrix.columns:
            for name in set(plot_pca_matrix.attribute_value_color):
                trace = go.Scatter(
                    x=list(plot_pca_matrix.loc[plot_pca_matrix['attribute_value_color'].eq(name)][components_x]),
                    y=list(plot_pca_matrix.loc[plot_pca_matrix['attribute_value_color'].eq(name)][components_y]),
                    mode='markers',
                    name=name,
                    text=list(plot_pca_matrix.loc[plot_pca_matrix['attribute_value_color'].eq(name)].index),
                    textposition='bottom center',
                    marker=go.Marker(size=10, opacity=0.8, line=go.Line(color='rgba(217, 217, 217, 0.14)',
                                                                        width=0.5)))
                traces.append(trace)
        elif 'attribute_value_size' in plot_pca_matrix.columns:

            maximum_marker_size = 10
            sizeref = 2.*float(max(plot_pca_matrix['attribute_value_size']))/(maximum_marker_size**2)

            for name in set(plot_pca_matrix.instance):
                attribute_value_size = plot_pca_matrix.loc[plot_pca_matrix['instance'].eq(name)].attribute_value_size
                size_list = list(map(abs, list(map(float, attribute_value_size))))
                for idx, val in enumerate(size_list):
                    if val == 0:
                        size_list[idx] = sys.float_info.min
                trace = go.Scatter(
                    x=list(plot_pca_matrix.loc[plot_pca_matrix['instance'].eq(name)][components_x]),
                    y=list(plot_pca_matrix.loc[plot_pca_matrix['instance'].eq(name)][components_y]),
                    mode='markers',
                    name=name,
                    text=list(plot_pca_matrix.loc[plot_pca_matrix['instance'].eq(name)].index),
                    textposition='bottom center',
                    marker=go.Marker(symbol='circle', sizemode='area', sizeref=sizeref,
                                     size=size_list, sizemin=2,
                                     line=go.Line(color='rgba(217, 217, 217, 0.14)', width=0.5),
                                     opacity=0.8))
                traces.append(trace)
        else:
            trace = go.Scatter(
                x=list(plot_pca_matrix[components_x]),
                y=list(plot_pca_matrix[components_y]),
                mode='markers',
                text=list(plot_pca_matrix.index),
                textposition='bottom center',
                marker=go.Marker(size=10, opacity=0.8,
                                 line=go.Line(color='rgba(217, 217, 217, 0.14)', width=0.5)))
            traces.append(trace)

        return traces

    def _plot_pca_matrix(self, plot_pca_matrix, n_components):

        output_directory = os.path.join(self.scratch, str(uuid.uuid4()))
        self._mkdir_p(output_directory)
        result_file_paths = []

        all_pairs = list(itertools.combinations(range(1, n_components+1), 2))

        for pair in all_pairs:
            first_component = pair[0]
            second_component = pair[1]
            result_file_path = os.path.join(output_directory, 'pca_plot_{}_{}.html'.format(
                                                                                first_component,
                                                                                second_component))

            traces = self._build_2_comp_trace(plot_pca_matrix,
                                              'principal_component_{}'.format(first_component),
                                              'principal_component_{}'.format(second_component))

            data = go.Data(traces)
            layout = go.Layout(xaxis=go.XAxis(title='PC{}'.format(first_component), showline=False),
                               yaxis=go.YAxis(title='PC{}'.format(second_component), showline=False))
            fig = go.Figure(data=data, layout=layout)

            plot(fig, filename=result_file_path)

            result_file_paths.append(result_file_path)

        return result_file_paths

    def _validate_pca_matrix(self, obj_data, dimension,
                             color_marker_by, scale_size_by):

        if dimension == 'row':
            attribute_mapping = obj_data.get('row_mapping')
        elif dimension == 'col':
            attribute_mapping = obj_data.get('col_mapping')
        else:
            raise ValueError('Unexpected dimension')

        if not attribute_mapping:
            if (color_marker_by and color_marker_by.get('attribute_color')[0]) or \
               (scale_size_by and scale_size_by.get('attribute_size')[0]):
                raise ValueError('Matrix object is not associated with any {} attribute mapping'.format(dimension))

    def __init__(self, config):
        self.ws_url = config["workspace-url"]
        self.callback_url = config['SDK_CALLBACK_URL']
        self.token = config['KB_AUTH_TOKEN']
        self.scratch = config['scratch']

        self.data_util = DataUtil(config)
        self.dfu = DataFileUtil(self.callback_url)

        plt.switch_backend('agg')

    def run_pca(self, params):
        """
        perform PCA analysis on matrix

        input_obj_ref: object reference of a matrix
        workspace_name: the name of the workspace
        pca_matrix_name: name of PCA (KBaseExperiments.PCAMatrix) object

        n_components - number of components (default 2)
        dimension: compute correlation on column or row, one of ['col', 'row']
        """

        logging.info('--->\nrunning NetworkUtil.build_network\n' +
            'params:\n{}'.format(json.dumps(params, indent=1)))

        self._validate_run_pca_params(params)

        input_obj_ref = params.get('input_obj_ref')
        workspace_name = params.get('workspace_name')
        pca_matrix_name = params.get('pca_matrix_name')

        n_components = int(params.get('n_components', 2))
        dimension = params.get('dimension', 'row')

        res = self.dfu.get_objects({'object_refs': [input_obj_ref]})['data'][0]
        obj_data = res['data']
        obj_type = res['info'][2]

        self._validate_pca_matrix(obj_data, dimension,
                                  params.get('color_marker_by'), params.get('scale_size_by'))

        if "KBaseMatrices" in obj_type:

            (rotation_matrix_df, components_df, explained_variance,
             explained_variance_ratio, singular_values) = self._pca_for_matrix(input_obj_ref,
                                                                               n_components,
                                                                               dimension)
        else:
            err_msg = 'Ooops! [{}] is not supported.\n'.format(obj_type)
            err_msg += 'Please supply KBaseMatrices object'
            raise ValueError("err_msg")

        
        pca_ref = self._save_pca_matrix(workspace_name, input_obj_ref, pca_matrix_name,
                                        rotation_matrix_df, components_df, explained_variance,
                                        explained_variance_ratio, singular_values,
                                        n_components, dimension)

        plot_pca_matrix = self._append_instance_group(rotation_matrix_df.copy(), obj_data,
                                                      dimension)

        if params.get('color_marker_by'):
            plot_pca_matrix = self._build_color_pca_matrix(
                                            plot_pca_matrix, obj_data, dimension,
                                            params.get('color_marker_by').get('attribute_color')[0])
        #exit(plot_pca_matrix)  
        '''
        principal_component_1          ...            attribute_value_color
        WRI_RS00010_CDS_1              -0.853094          ...                                4
        WRI_RS00015_CDS_1              -0.247377          ...                                4
        WRI_RS00025_CDS_1               1.100471          ...                                6
        ''' 
        if params.get('scale_size_by'):
            plot_pca_matrix = self._build_size_pca_matrix(
                                            plot_pca_matrix, obj_data, dimension,
                                            params.get('scale_size_by').get('attribute_size')[0])

        returnVal = {'pca_ref': pca_ref}

        report_output = self._generate_pca_report(pca_ref,
                                                  self._plot_pca_matrix(plot_pca_matrix,
                                                                        n_components),
                                                  workspace_name,
                                                  n_components)

        returnVal.update(report_output)
        return returnVal

    def export_pca_matrix_excel(self, params):
        """
        export PCAMatrix as Excel
        """
        logging.info('start exporting pca matrix')
        pca_matrix_ref = params.get('input_ref')  #44071/62/8
        pca_df, components_df = self._pca_to_df(pca_matrix_ref)
        
        #exit(pca_df)
        '''
        principal_component_1  principal_component_2
        WRI_RS00010_CDS_1                  -0.45                   1.06
        WRI_RS00015_CDS_1                  -0.69                  -0.92
        WRI_RS00025_CDS_1                   1.14                  -0.13
        '''
        result_dir = os.path.join(self.scratch, str(uuid.uuid4()))
        self._mkdir_p(result_dir)
        #exit(result_dir)                       #/kb/module/work/tmp/54e9610e-9b51-4296-a971-333f9f154a1f

        self._pca_df_to_excel(pca_df, components_df, result_dir, pca_matrix_ref)

        package_details = self.dfu.package_for_download({
            'file_path': result_dir,
            'ws_refs': [pca_matrix_ref]
        })

        return {'shock_id': package_details['shock_id']}
