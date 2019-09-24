import collections
import errno
import logging
import os
import re
import shutil
import uuid
import time

import pandas as pd
from openpyxl import load_workbook  #load workbook function for reading xls
from xlrd.biffh import XLRDError
from sklearn import preprocessing

from installed_clients.DataFileUtilClient import DataFileUtil
from GenericsAPI.Utils.AttributeUtils import AttributesUtil
from GenericsAPI.Utils.DataUtil import DataUtil
from installed_clients.KBaseReportClient import KBaseReport

TYPE_ATTRIBUTES = {'description', 'scale', 'row_normalization', 'col_normalization'}
SCALE_TYPES = {'raw', 'ln', 'log2', 'log10'}


class MatrixUtil:

    def _validate_import_matrix_from_excel_params(self, params):
        """
        _validate_import_matrix_from_excel_params:
            validates params passed to import_matrix_from_excel method
        """
        logging.info('start validating import_matrix_from_excel params')

        # check for required parameters
        for p in ['obj_type', 'matrix_name', 'workspace_name', 'scale']:
            if p not in params:
                raise ValueError('"{}" parameter is required, but missing'.format(p))

        obj_type = params.get('obj_type')
        if obj_type not in self.matrix_types:
            raise ValueError('Unknown matrix object type: {}'.format(obj_type))

        scale = params.get('scale')
        if scale not in SCALE_TYPES:
            raise ValueError('Unknown scale type: {}'.format(scale))

        if params.get('input_file_path'):
            file_path = params.get('input_file_path')
        elif params.get('input_shock_id'):
            file_path = self.dfu.shock_to_file(
                {'shock_id': params['input_shock_id'],
                 'file_path': self.scratch}).get('file_path')
        elif params.get('input_staging_file_path'):
            file_path = self.dfu.download_staging_file(
                        {'staging_file_subdir_path': params.get('input_staging_file_path')}
                        ).get('copy_file_path')
        else:
            error_msg = "Must supply either a input_shock_id or input_file_path "
            error_msg += "or input_staging_file_path"
            raise ValueError(error_msg)

        refs = {k: v for k, v in params.items() if "_ref" in k}

        return (obj_type, file_path, params.get('workspace_name'),
                params.get('matrix_name'), refs, scale)

    def _upload_to_shock(self, file_path):
        """
        _upload_to_shock: upload target file to shock using DataFileUtil
        """
        logging.info('Start uploading file to shock: {}'.format(file_path))

        file_to_shock_params = {
            'file_path': file_path,
            'pack': 'zip'
        }
        shock_id = self.dfu.file_to_shock(file_to_shock_params).get('shock_id')

        return shock_id

    @staticmethod
    def _mkdir_p(path):
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

    @staticmethod
    def _find_between(s, start, end):
        """
        _find_between: find string in between start and end
        """

        return re.search('{}(.*){}'.format(start, end), s).group(1)

    @staticmethod
    def _write_mapping_sheet(file_path, sheet_name, mapping, index):
        """
        _write_mapping_sheet: write mapping to sheet
        """
        df_dict = collections.OrderedDict()

        df_dict[index[0]] = []
        df_dict[index[1]] = []

        for key, value in mapping.items():
            df_dict.get(index[0]).append(key)
            df_dict.get(index[1]).append(value)

        df = pd.DataFrame.from_dict(df_dict)

        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            writer.book = load_workbook(file_path)
            df.to_excel(writer, sheet_name=sheet_name)

    def _generate_report(self, matrix_obj_ref, workspace_name):
        """
        _generate_report: generate summary report
        """

        report_params = {'message': '',
                         'objects_created': [{'ref': matrix_obj_ref,
                                              'description': 'Imported Matrix'}],
                         'workspace_name': workspace_name,
                         'report_object_name': 'import_matrix_from_excel_' + str(uuid.uuid4())}

        kbase_report_client = KBaseReport(self.callback_url, token=self.token)
        output = kbase_report_client.create_extended_report(report_params)

        report_output = {'report_name': output['name'], 'report_ref': output['ref']}

        return report_output

    @staticmethod
    def _process_mapping_sheet(file_path, sheet_name):
        """
        _process_mapping: process mapping sheet
        """

        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, dtype='str')
        except XLRDError:
            return dict()
        else:
            mapping = {value[0]: value[1] for value in df.values.tolist()}

        return mapping

    def _process_attribute_mapping_sheet(self, file_path, sheet_name, matrix_name, workspace_id):
        """
        _process_attribute_mapping_sheet: process attribute_mapping sheet
        """

        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
        except XLRDError:
            return ''
        else:
            obj_name = f'{matrix_name}_{sheet_name}'
            result_directory = os.path.join(self.scratch, str(uuid.uuid4()))
            self._mkdir_p(result_directory)
            file_path = os.path.join(result_directory, '{}.xlsx'.format(obj_name))
            df.to_excel(file_path)
            import_attribute_mapping_params = {
                'output_obj_name': obj_name,
                'output_ws_id': workspace_id,
                'input_file_path': file_path
            }

            ref = self.attr_util.file_to_attribute_mapping(import_attribute_mapping_params)

            return ref.get('attribute_mapping_ref')

    @staticmethod
    def _file_to_df(file_path):
        logging.info('start parsing file content to data frame')

        try:
            df = pd.read_excel(file_path, sheet_name='data', index_col=0)

        except XLRDError:
            try:
                df = pd.read_excel(file_path, index_col=0)
                logging.warning('WARNING: A sheet named "data" was not found in the attached file,'
                                ' proceeding with the first sheet as the data sheet.')

            except XLRDError:

                try:
                    reader = pd.read_csv(file_path, sep=None, iterator=True)
                    inferred_sep = reader._engine.data.dialect.delimiter
                    df = pd.read_csv(file_path, sep=inferred_sep, index_col=0)
                except Exception:
                    raise ValueError('Cannot parse file. Please provide valide tsv, excel or csv file')

        df.index = df.index.astype('str')
        df.columns = df.columns.astype('str')
        # fill NA with "None" so that they are properly represented as nulls in the KBase Object
        df = df.where((pd.notnull(df)), None)

        return df

    def _file_to_data(self, file_path, refs, matrix_name, workspace_id):
        logging.info('Start reading and converting excel file data')
        data = refs

        df = self._file_to_df(file_path)

        matrix_data = {'row_ids': df.index.tolist(),
                       'col_ids': df.columns.tolist(),
                       'values': df.values.tolist()}

        data.update({'data': matrix_data})
        data.update(self._get_axis_attributes('col', matrix_data, refs, file_path, matrix_name,
                                              workspace_id))
        data.update(self._get_axis_attributes('row', matrix_data, refs, file_path, matrix_name,
                                              workspace_id))

        # processing metadata
        metadata = self._process_mapping_sheet(file_path, 'metadata')
        data['attributes'] = {}
        data['search_attributes'] = []
        for k, v in metadata.items():
            k = k.strip()
            v = v.strip()
            if k in TYPE_ATTRIBUTES:
                data[k] = v
            else:
                data['attributes'][k] = v
                data['search_attributes'].append(" | ".join((k, v)))

        return data

    def _get_axis_attributes(self, axis, matrix_data, refs, file_path, matrix_name, workspace_id):
        """Get the row/col_attributemapping and mapping of ids, validating as needed"""
        # Parameter specified mappings should take precedence over tabs in excel so only process
        # if attributemapping_ref is missing:
        attr_data = {}

        if refs.get(f'{axis}_attributemapping_ref'):
            attributemapping_ref = refs[f'{axis}_attributemapping_ref']
        else:
            attributemapping_ref = self._process_attribute_mapping_sheet(
                file_path, f'{axis}_attribute_mapping', matrix_name, workspace_id)

        if attributemapping_ref:
            attr_data[f'{axis}_attributemapping_ref'] = attributemapping_ref

        # col/row_mappings may not be supplied
        id_mapping = self._process_mapping_sheet(file_path, f'{axis}_mapping')
        if id_mapping:
            attr_data[f'{axis}_mapping'] = id_mapping
        # if no mapping, axis ids must match the attribute mapping
        elif attributemapping_ref:
            am_data = self.dfu.get_objects(
                {'object_refs': [attributemapping_ref]}
            )['data'][0]['data']
            axis_ids = matrix_data[f'{axis}_ids']
            unmatched_ids = set(axis_ids) - set(am_data['instances'].keys())
            if unmatched_ids:
                name = "Column" if axis == 'col' else "Row"
                raise ValueError(f"The following {name} IDs from the uploaded matrix do not match "
                                 f"the supplied {name} attribute mapping: {', '.join(unmatched_ids)}"
                                 f"\nPlease verify the input data or upload an excel file with a"
                                 f"{name} mapping tab.")
            else:
                # just gen the IDs in this matrix
                attr_data[f'{axis}_mapping'] = {x: x for x in axis_ids}

        return attr_data

    @staticmethod
    def _build_header_str(attribute_names):

        header_str = ''
        width = 100.0/len(attribute_names)

        header_str += '<tr class="header">'
        header_str += '<th style="width:{0:.2f}%;">Feature ID</th>'.format(width)

        for attribute_name in attribute_names:
            header_str += '<th style="width:{0:.2f}%;"'.format(width)
            header_str += '>{}</th>'.format(attribute_name)
        header_str += '</tr>'

        return header_str

    def _build_html_str(self, row_mapping, attributemapping_data, row_ids):

        logging.info('Start building html replacement')

        attribute_names = [attributes.get('attribute') for attributes in attributemapping_data.get('attributes')]

        header_str = self._build_header_str(attribute_names)

        table_str = ''

        instances = attributemapping_data.get('instances')

        for feature_id, attribute_id in row_mapping.items():
            if feature_id in row_ids:
                feature_instances = instances.get(attribute_id)

                table_str += '<tr>'
                table_str += '<td>{}</td>'.format(feature_id)

                for feature_instance in feature_instances:
                    table_str += '<td>{}</td>'.format(feature_instance)
                table_str += '</tr>'

        return header_str, table_str

    def _generate_search_html_report(self, header_str, table_str):   #generate search html report

        html_report = list()

        output_directory = os.path.join(self.scratch, str(uuid.uuid4()))
        self._mkdir_p(output_directory)
        result_file_path = os.path.join(output_directory, 'search.html')

        shutil.copy2(os.path.join(os.path.dirname(__file__), 'templates', 'kbase_icon.png'),
                     output_directory)
        shutil.copy2(os.path.join(os.path.dirname(__file__), 'templates', 'search_icon.png'),
                     output_directory)

        with open(result_file_path, 'w') as result_file:
            with open(os.path.join(os.path.dirname(__file__), 'templates', 'search_template.html'),
                      'r') as report_template_file:
                report_template = report_template_file.read()
                report_template = report_template.replace('//HEADER_STR', header_str)
                report_template = report_template.replace('//TABLE_STR', table_str)
                result_file.write(report_template)

        report_shock_id = self.dfu.file_to_shock({'file_path': output_directory,
                                                  'pack': 'zip'})['shock_id']

        html_report.append({'shock_id': report_shock_id,
                            'name': os.path.basename(result_file_path),
                            'label': os.path.basename(result_file_path),
                            'description': 'HTML summary report for Search Matrix App'})

        return html_report

    def _generate_search_report(self, header_str, table_str, workspace_name):
        logging.info('Start creating report')

        output_html_files = self._generate_search_html_report(header_str, table_str)

        report_params = {'message': '',
                         'workspace_name': workspace_name,
                         'html_links': output_html_files,
                         'direct_html_link_index': 0,
                         'html_window_height': 366,
                         'report_object_name': 'kb_matrix_filter_report_' + str(uuid.uuid4())}

        kbase_report_client = KBaseReport(self.callback_url, token=self.token)
        output = kbase_report_client.create_extended_report(report_params)

        report_output = {'report_name': output['name'], 'report_ref': output['ref']}

        return report_output

    @staticmethod
    def _filter_value_data(value_data, remove_ids, dimension):
        """Filters a value matrix based on column or row ids"""
        def _norm_id(_id):
            return _id.replace(" ", "_")

        val_df = pd.DataFrame(value_data['values'], index=value_data['row_ids'],
                              columns=value_data['col_ids'], dtype='object')

        if dimension == 'row':
            filtered_df = val_df.drop(remove_ids, axis=0, errors='ignore')
            filtered_df = filtered_df.drop([_norm_id(x) for x in remove_ids], axis=0, errors='ignore')
        elif dimension == 'col':
            filtered_df = val_df.drop(remove_ids, axis=1, errors='ignore')
            filtered_df = filtered_df.drop([_norm_id(x) for x in remove_ids], axis=1, errors='ignore')
        else:
            raise ValueError('Unexpected dimension: {}'.format(dimension))

        filtered_value_data = {
            "values": filtered_df.values.tolist(),
            "col_ids": list(filtered_df.columns),
            "row_ids": list(filtered_df.index),
        }

        return filtered_value_data

    def _standardize_df(self, df, with_mean=True, with_std=True):    

        logging.info("Standardizing matrix data")

        df.fillna(0, inplace=True)

        x_train = df.values

        scaler = preprocessing.StandardScaler(with_mean=with_mean, with_std=with_std).fit(x_train)

        standardized_values = scaler.transform(x_train)

        standardize_df = pd.DataFrame(index=df.index, columns=df.columns, data=standardized_values)

        return standardize_df

    def __init__(self, config):
        self.callback_url = config['SDK_CALLBACK_URL']
        self.scratch = config['scratch']
        self.token = config['KB_AUTH_TOKEN']
        self.dfu = DataFileUtil(self.callback_url)
        self.data_util = DataUtil(config)
        self.attr_util = AttributesUtil(config)
        self.matrix_types = [x.split(".")[1].split('-')[0]
                             for x in self.data_util.list_generic_types()]

    def standardize_matrix(self, params):
        """
        standardize a matrix
        """

        input_matrix_ref = params.get('input_matrix_ref')
        workspace_name = params.get('workspace_name')
        new_matrix_name = params.get('new_matrix_name')
        with_mean = params.get('with_mean', 1)
        with_std = params.get('with_std', 1)

        if not isinstance(workspace_name, int):
            workspace_id = self.dfu.ws_name_to_id(workspace_name)
        else:
            workspace_id = workspace_name

        input_matrix_obj = self.dfu.get_objects({'object_refs': [input_matrix_ref]})['data'][0]
        input_matrix_info = input_matrix_obj['info']
        input_matrix_name = input_matrix_info[1]
        input_matrix_data = input_matrix_obj['data']

        if not new_matrix_name:
            current_time = time.localtime()
            new_matrix_name = input_matrix_name + time.strftime('_%H_%M_%S_%Y_%m_%d', current_time)

        data_matrix = self.data_util.fetch_data({'obj_ref': input_matrix_ref}).get('data_matrix')
        df = pd.read_json(data_matrix)

        standardize_df = self._standardize_df(df, with_mean, with_std)

        new_matrix_data = {'row_ids': df.index.tolist(),
                           'col_ids': df.columns.tolist(),
                           'values': standardize_df.values.tolist()}

        input_matrix_data['data'] = new_matrix_data

        logging.info("Saving new standardized matrix object")
        info = self.dfu.save_objects({
            "id": workspace_id,
            "objects": [{
                "type": input_matrix_info[2],
                "data": input_matrix_data,
                "name": new_matrix_name
            }]
        })[0]

        new_matrix_obj_ref = "%s/%s/%s" % (info[6], info[0], info[4])

        objects_created = [{'ref': new_matrix_obj_ref, 'description': 'Standardized Matrix'}]

        report_params = {'message': '',
                         'objects_created': objects_created,
                         'workspace_name': workspace_name,
                         'report_object_name': 'import_matrix_from_biom_' + str(uuid.uuid4())}

        kbase_report_client = KBaseReport(self.callback_url, token=self.token)
        output = kbase_report_client.create_extended_report(report_params)

        return {'new_matrix_obj_ref': new_matrix_obj_ref,
                'report_name': output['name'], 'report_ref': output['ref']}

    def filter_matrix(self, params):
        """
        filter_matrix: create sub-matrix based on input feature_ids

        arguments:
        matrix_obj_ref: object reference of a matrix
        workspace_name: workspace name
        feature_ids: string of feature ids that result matrix contains
        filtered_matrix_name: name of newly created filtered matrix object
        """

        matrix_obj_ref = params.get('matrix_obj_ref')
        workspace_name = params.get('workspace_name')
        remove_ids = params.get('remove_ids')
        dimension = params.get('dimension')
        filtered_matrix_name = params.get('filtered_matrix_name')

        matrix_source = self.dfu.get_objects(
            {"object_refs": [matrix_obj_ref]})['data'][0]
        matrix_info = matrix_source.get('info')
        matrix_data = matrix_source.get('data')

        matrix_type = self._find_between(matrix_info[2], '\.', '\-')

        value_data = matrix_data.get('data')
        remove_ids = [x.strip() for x in remove_ids.split(',')]
        filtered_value_data = self._filter_value_data(value_data, remove_ids, dimension)

        # if the matrix has changed shape, update the mappings
        if len(filtered_value_data['row_ids']) < len(matrix_data['data']['row_ids']):
            if matrix_data.get('row_mapping'):
                matrix_data['row_mapping'] = {k: matrix_data['row_mapping'][k]
                                              for k in filtered_value_data['row_ids']}
            if matrix_data.get('feature_mapping'):
                matrix_data['feature_mapping'] = {k: matrix_data['feature_mapping'][k]
                                                  for k in filtered_value_data['row_ids']}

        if len(filtered_value_data['col_ids']) < len(matrix_data['data']['col_ids']):
            if matrix_data.get('col_mapping'):
                matrix_data['col_mapping'] = {k: matrix_data['col_mapping'][k]
                                              for k in filtered_value_data['col_ids']}
        matrix_data['data'] = filtered_value_data

        if not isinstance(workspace_name, int):
            workspace_id = self.dfu.ws_name_to_id(workspace_name)
        else:
            workspace_id = workspace_name

        filtered_matrix_obj_ref = self.data_util.save_object({
                                                'obj_type': 'KBaseMatrices.{}'.format(matrix_type),
                                                'obj_name': filtered_matrix_name,
                                                'data': matrix_data,
                                                'workspace_name': workspace_id})['obj_ref']

        returnVal = {'matrix_obj_refs': [filtered_matrix_obj_ref]}

        report_output = self._generate_report(filtered_matrix_obj_ref, workspace_name)

        returnVal.update(report_output)

        return returnVal

    def search_matrix(self, params):
        """
        search_matrix: generate a HTML report that allows users to select feature ids

        arguments:
        matrix_obj_ref: object reference of a matrix
        workspace_name: workspace name
        """

        matrix_obj_ref = params.get('matrix_obj_ref')
        workspace_name = params.get('workspace_name')

        matrix_source = self.dfu.get_objects(
            {"object_refs": [matrix_obj_ref]})['data'][0]
        matrix_data = matrix_source.get('data')

        row_mapping = matrix_data.get('row_mapping')
        row_attributemapping_ref = matrix_data.get('row_attributemapping_ref')

        row_ids = matrix_data['data']['row_ids']

        if not (row_mapping and row_attributemapping_ref):
            raise ValueError('Matrix obejct is missing either row_mapping or row_attributemapping_ref')

        attributemapping_data = self.dfu.get_objects(
                                    {"object_refs": [row_attributemapping_ref]})['data'][0]['data']

        header_str, table_str = self._build_html_str(row_mapping, attributemapping_data, row_ids)

        returnVal = self._generate_search_report(header_str, table_str, workspace_name)

        return returnVal

    def import_matrix_from_excel(self, params):
        """
        import_matrix_from_excel: import matrix object from excel

        arguments:
        obj_type: one of ExpressionMatrix, FitnessMatrix, DifferentialExpressionMatrix
        matrix_name: matrix object name
        workspace_name: workspace name matrix object to be saved to
        input_shock_id: file shock id
        or
        input_file_path: absolute file path
        or
        input_staging_file_path: staging area file path

        optional arguments:
        col_attributemapping_ref: column AttributeMapping reference
        row_attributemapping_ref: row AttributeMapping reference
        genome_ref: genome reference
        matrix_obj_ref: Matrix reference
        """

        (obj_type, file_path, workspace_name,
         matrix_name, refs, scale) = self._validate_import_matrix_from_excel_params(params)

        if not isinstance(workspace_name, int):
            workspace_id = self.dfu.ws_name_to_id(workspace_name)
        else:
            workspace_id = workspace_name

        data = self._file_to_data(file_path, refs, matrix_name, workspace_id)
        data['scale'] = scale
        if params.get('description'):
            data['description'] = params['description']

        matrix_obj_ref = self.data_util.save_object({
                                                'obj_type': 'KBaseMatrices.{}'.format(obj_type),
                                                'obj_name': matrix_name,
                                                'data': data,
                                                'workspace_name': workspace_id})['obj_ref']

        returnVal = {'matrix_obj_ref': matrix_obj_ref}

        report_output = self._generate_report(matrix_obj_ref, workspace_name)

        returnVal.update(report_output)

        return returnVal

    def export_matrix(self, params):
        """
        export_matrix: univeral downloader for matrix data object

        arguments:
        obj_ref: generics object reference

        optional arguments:
        generics_module: select the generics data to be retrieved from
                        e.g. for an given data type like below:
                        typedef structure {
                          FloatMatrix2D data;
                          condition_set_ref condition_set_ref;
                        } SomeGenericsMatrix;
                        and only data is needed
                        generics_module should be
                        {'data': 'FloatMatrix2D'}
        """
        logging.info('Start exporting matrix')

        if 'input_ref' in params:
            params['obj_ref'] = params.pop('input_ref')

        obj_source = self.dfu.get_objects(
            {"object_refs": [params.get('obj_ref')]})['data'][0]
        obj_data = obj_source.get('data')

        result_directory = os.path.join(self.scratch, str(uuid.uuid4()))
        self._mkdir_p(result_directory)
        file_path = os.path.join(result_directory, '{}.xlsx'.format(obj_source.get('info')[1]))

        data_matrix = self.data_util.fetch_data(params).get('data_matrix')
        df = pd.read_json(data_matrix)

        df.to_excel(file_path, sheet_name='data')

        if obj_data.get('col_mapping'):
            self._write_mapping_sheet(file_path, 'col_mapping',
                                      obj_data.get('col_mapping'), ['col_name', 'instance_name'])
            obj_data.pop('col_mapping')

        if obj_data.get('row_mapping'):
            self._write_mapping_sheet(file_path, 'row_mapping',
                                      obj_data.get('row_mapping'), ['row_name', 'instance_name'])
            obj_data.pop('row_mapping')

        try:
            obj_data.pop('data')
        except KeyError:
            logging.warning('Missing key [data]')

        obj_data.update(obj_data.get('attributes', {}))  # flatten for printing
        self._write_mapping_sheet(file_path, 'metadata', obj_data, ['name', 'value'])

        shock_id = self._upload_to_shock(file_path)

        return {'shock_id': shock_id}
