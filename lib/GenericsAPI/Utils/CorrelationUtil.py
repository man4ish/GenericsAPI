import errno
import json
import logging
import os
import shutil
import traceback
import uuid

import pandas as pd
import plotly.graph_objs as go
from matplotlib import pyplot as plt
from plotly.offline import plot
from scipy import stats
from natsort import natsorted

from installed_clients.DataFileUtilClient import DataFileUtil
from GenericsAPI.Utils.DataUtil import DataUtil
from installed_clients.KBaseReportClient import KBaseReport

CORR_METHOD = ['pearson', 'kendall', 'spearman']  # correlation method
HIDDEN_SEARCH_THRESHOLD = 1500


class CorrelationUtil:

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

    def _validate_compute_corr_matrix_params(self, params):
        """
        _validate_compute_corr_matrix_params:
            validates params passed to compute_correlation_matrix method
        """

        logging.info('start validating compute_corrrelation_matrix params')

        # check for required parameters
        for p in ['input_obj_ref', 'workspace_name', 'corr_matrix_name']:
            if p not in params:
                raise ValueError('"{}" parameter is required, but missing'.format(p))

    def _validate_compute_correlation_across_matrices_params(self, params):
        """
        _validate_compute_correlation_across_matrices_params:
            validates params passed to compute_correlation_across_matrices method
        """

        logging.info('start validating compute_correlation_across_matrices params')

        # check for required parameters
        for p in ['workspace_name', 'corr_matrix_name', 'matrix_ref_1', 'matrix_ref_2']:
            if p not in params:
                raise ValueError('"{}" parameter is required, but missing'.format(p))

    def _fetch_taxon(self, amplicon_set_ref, amplicon_ids):
        logging.info('start fetching taxon info from AmpliconSet')
        taxons = dict()
        taxons_level = dict()
        
        amplicon_set_data = self.dfu.get_objects(
                                            {'object_refs': [amplicon_set_ref]})['data'][0]['data']

        amplicons = amplicon_set_data.get('amplicons')
        #exit(amplicons)
        '''
        {'GG_OTU_1': {'consensus_sequence': 'ACTGACTAGCTAGCTAACTG', 'taxonomy': {'lineage': ['k__Bacteria', 'p__Proteobacteria', 'c__Gammaproteobacteria', 'o__Enterobacteriales', 'f__Enterobacteriaceae', 'g__Escherichia', 's__'], 'scientific_name': 'Escherichia', 'taxon_id': '561_taxon', 'taxon_level': 'Genus', 'taxon_ref': '1779/125680/3'}}, 'GG_OTU_2': {'consensus_sequence': 'GCATCGTAGCTAGCTACGAT', 'taxonomy': {'lineage': ['k__Bacteria', 'p__Cyanobacteria', 'c__Nostocophycideae', 'o__Nostocales', 'f__Nostocaceae', 'g__Dolichospermum', 's__'], 'scientific_name': 'Dolichospermum', 'taxon_id': '748770_taxon', 'taxon_level': 'Genus', 'taxon_ref': '1779/100716/3'}}, 'GG_OTU_3': {'consensus_sequence': 'CATCGATCGTACGTACGTAG', 'taxonomy': {'lineage': ['k__Archaea', 'p__Euryarchaeota', 'c__Methanomicrobia', 'o__Methanosarcinales', 'f__Methanosarcinaceae', 'g__Methanosarcina', 's__'], 'scientific_name': 'Methanosarcina', 'taxon_id': '2207_taxon', 'taxon_level': 'Genus', 'taxon_ref': '1779/147440/3'}}, 'GG_OTU_4': {'consensus_sequence': 'ATCGATCGATCGTACGATCG', 'taxonomy': {'lineage': ['k__Bacteria', 'p__Firmicutes', 'c__Clostridia', 'o__Halanaerobiales', 'f__Halanaerobiaceae', 'g__Halanaerobium', 's__Halanaerobiumsaccharolyticum'], 'scientific_name': 'Halanaerobium', 'taxon_id': '2330_taxon', 'taxon_level': 'Genus', 'taxon_ref': '1779/149756/3'}}, 'GG_OTU_5': {'consensus_sequence': 'ATCGATCGATCGTACGATCG', 'taxonomy': {'lineage': ['k__Bacteria', 'p__Proteobacteria', 'c__Gammaproteobacteria', 'o__Enterobacteriales', 'f__Enterobacteriaceae', 'g__Escherichia', 's__'], 'scientific_name': 'Escherichia', 'taxon_id': '561_taxon', 'taxon_level': 'Genus', 'taxon_ref': '1779/125680/3'}}}idx_5  57.019677  43.860151  98.837384  10.204481  20.887676  16.130952  65.310833  25.329160  46.631077  24.442559
        '''       
        #exit(amplicon_ids)  ['GG_OTU_1', 'GG_OTU_2', 'GG_OTU_3', 'GG_OTU_4', 'GG_OTU_5']
        for amplicon_id in amplicon_ids:
            scientific_name = 'None'
            level = 'Unknown'
            try:
                scientific_name = amplicons.get(amplicon_id).get('taxonomy').get('scientific_name')
            except Exception:
                pass

            try:
                level = amplicons.get(amplicon_id).get('taxonomy').get('taxon_level')
            except Exception:
                pass

            taxons.update({amplicon_id: scientific_name})
            taxons_level.update({amplicon_id: level})

        # default empty taxons and taxons_level
        if set(taxons.values()) == {'None'}:
            taxons = None

        if set(taxons_level.values()) == {'Unknown'}:
            taxons_level = None
        #exit(taxons_level)   {'GG_OTU_1': 'Genus', 'GG_OTU_2': 'Genus', 'GG_OTU_3': 'Genus', 'GG_OTU_4': 'Genus', 'GG_OTU_5': 'Genus'}
        
        return taxons, taxons_level

    def _build_table_content(self, matrix_2D, output_directory, original_matrix_ref=[],
                             type='corr'):
        """
        _build_table_content: generate HTML table content for FloatMatrix2D object
        """
        #exit(matrix_2D)  {'col_ids': ['gene_1', 'gene_2', 'gene_3'], 'row_ids': ['WRI_RS00010_CDS_1', 'WRI_RS00015_CDS_1', 'WRI_RS00025_CDS_1'], 'values': [[1.0, -0.5447, 0.9668], [1.0, -0.5447, 0.9668], [0.9668, -0.3124, 1.0]]}
        page_content = """\n"""

        table_file_name = '{}_table.html'.format(type)
        data_file_name = '{}_data.json'.format(type)

        page_content += """<iframe height="900px" width="100%" """
        page_content += """src="{}" """.format(table_file_name)
        page_content += """style="border:none;"></iframe>\n"""

        row_ids = matrix_2D.get('row_ids')
        col_ids = matrix_2D.get('col_ids')
        values = matrix_2D.get('values')

        df = pd.DataFrame(values, index=row_ids, columns=col_ids)
        df = df.T
        links = df.stack().reset_index()

        columns = list()
        taxons = None
        taxons_level = None
        if len(original_matrix_ref) == 1:
            res = self.dfu.get_objects({'object_refs': [original_matrix_ref[0]]})['data'][0]
            obj_type = res['info'][2]
            matrix_type = obj_type.split('Matrix')[0].split('.')[-1]
            if matrix_type == 'Amplicon':
                amplicon_set_ref = res['data'].get('amplicon_set_ref')
                if amplicon_set_ref:
                    taxons, taxons_level = self._fetch_taxon(amplicon_set_ref, col_ids)
            columns.extend(['{} 1'.format(matrix_type), '{} 2'.format(matrix_type)])
        elif len(original_matrix_ref) == 2:
            for matrix_ref in original_matrix_ref[::-1]:
                res = self.dfu.get_objects({'object_refs': [matrix_ref]})['data'][0]
                obj_type = res['info'][2]
                matrix_type = obj_type.split('Matrix')[0].split('.')[-1]
                if matrix_type == 'Amplicon':
                    amplicon_set_ref = res['data'].get('amplicon_set_ref')
                    if amplicon_set_ref:
                        taxons, taxons_level = self._fetch_taxon(amplicon_set_ref, col_ids)
                columns.append(matrix_type)
        else:
            links.columns = ['Variable 1', 'Variable 2']
        #exit(links)
        '''
    level_0   level_1       0
0   GG_OTU_1  GG_OTU_1  1.0000
1   GG_OTU_1  GG_OTU_2 -0.5477
2   GG_OTU_1  GG_OTU_3 -0.0510
3   GG_OTU_1  GG_OTU_4  0.1085
4   GG_OTU_1  GG_OTU_5  0.6325
5   GG_OTU_2  GG_OTU_1 -0.5477
6   GG_OTU_2  GG_OTU_2  1.0000
7   GG_OTU_2  GG_OTU_3  0.0000
8   GG_OTU_2  GG_OTU_4  0.2970
9   GG_OTU_2  GG_OTU_5 -0.6495
10  GG_OTU_3  GG_OTU_1 -0.0510
11  GG_OTU_3  GG_OTU_2  0.0000
12  GG_OTU_3  GG_OTU_3  1.0000
13  GG_OTU_3  GG_OTU_4 -0.8015
14  GG_OTU_3  GG_OTU_5 -0.3223
15  GG_OTU_4  GG_OTU_1  0.1085
16  GG_OTU_4  GG_OTU_2  0.2970
17  GG_OTU_4  GG_OTU_3 -0.8015
18  GG_OTU_4  GG_OTU_4  1.0000
19  GG_OTU_4  GG_OTU_5  0.1715
20  GG_OTU_5  GG_OTU_1  0.6325
21  GG_OTU_5  GG_OTU_2 -0.6495
22  GG_OTU_5  GG_OTU_3 -0.3223
23  GG_OTU_5  GG_OTU_4  0.1715
24  GG_OTU_5  GG_OTU_5  1.0000

        '''
        # remove self-comparison
        links = links[links.iloc[:, 0] != links.iloc[:, 1]]
        #exit(links)
        '''
   level_0            level_1       0
0  gene_1  WRI_RS00010_CDS_1  1.0000
1  gene_1  WRI_RS00015_CDS_1  1.0000
2  gene_1  WRI_RS00025_CDS_1  0.9668
3  gene_2  WRI_RS00010_CDS_1 -0.5447
4  gene_2  WRI_RS00015_CDS_1 -0.5447
5  gene_2  WRI_RS00025_CDS_1 -0.3124
6  gene_3  WRI_RS00010_CDS_1  0.9668
7  gene_3  WRI_RS00015_CDS_1  0.9668
8  gene_3  WRI_RS00025_CDS_1  1.0000
        '''

        if type == 'corr':
            columns.append('Correlation')
        elif type == 'sig':
            columns.append('Significance')
        else:
            columns.append('Value')

        links.columns = columns
        

        if taxons:
            links['Taxon'] = links.iloc[:, 0].map(taxons)

        if taxons_level:
            links['Taxon Level'] = links.iloc[:, 0].map(taxons_level)
       
        table_headers = links.columns.tolist()
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
        data_array = links.values.tolist()

        total_rec = len(data_array)
        json_dict = {'draw': 1,
                     'recordsTotal': total_rec,
                     'recordsFiltered': total_rec,
                     'data': data_array}

        with open(os.path.join(output_directory, data_file_name), 'w') as fp:
            json.dump(json_dict, fp)

        logging.info('start generating table html')
        with open(os.path.join(output_directory, table_file_name), 'w') as result_file:
            with open(os.path.join(os.path.dirname(__file__), 'templates', 'table_template.html'),
                      'r') as report_template_file:
                report_template = report_template_file.read()
                report_template = report_template.replace('<p>table_header</p>',
                                                          table_content)
                report_template = report_template.replace('ajax_file_path',
                                                          data_file_name)
                report_template = report_template.replace('deferLoading_size',
                                                          str(total_rec))
                result_file.write(report_template)
        
        return page_content

    def _generate_visualization_content(self, output_directory, corr_matrix_obj_ref,
                                        corr_matrix_plot_path, scatter_plot_path):

        """
        <div class="tab">
            <button class="tablinks" onclick="openTab(event, 'CorrelationMatrix')" id="defaultOpen">Correlation Matrix</button>
        </div>

        <div id="CorrelationMatrix" class="tabcontent">
            <p>CorrelationMatrix_Content</p>
        </div>"""

        tab_def_content = ''
        tab_content = ''

        corr_data = self.dfu.get_objects({'object_refs': [corr_matrix_obj_ref]})['data'][0]['data']
        coefficient_data = corr_data.get('coefficient_data')
        significance_data = corr_data.get('significance_data')
        
        original_matrix_ref = corr_data.get('original_matrix_ref')
        
        tab_def_content += """
        <div class="tab">
            <button class="tablinks" onclick="openTab(event, 'CorrelationMatrix')" id="defaultOpen">Correlation Matrix</button>
        """

        corr_table_content = self._build_table_content(coefficient_data, output_directory,
                                                       original_matrix_ref=original_matrix_ref,
                                                       type='corr')
        tab_content += """
        <div id="CorrelationMatrix" class="tabcontent">{}</div>""".format(corr_table_content)

        if significance_data:
            tab_def_content += """
            <button class="tablinks" onclick="openTab(event, 'SignificanceMatrix')">Significance Matrix</button>
            """
            sig_table_content = self._build_table_content(significance_data, output_directory,
                                                          original_matrix_ref=original_matrix_ref,
                                                          type='sig')
            tab_content += """
            <div id="SignificanceMatrix" class="tabcontent">{}</div>""".format(sig_table_content)

        if corr_matrix_plot_path:
            tab_def_content += """
            <button class="tablinks" onclick="openTab(event, 'CorrelationMatrixPlot')">Correlation Matrix Heatmap</button>
            """

            tab_content += """
            <div id="CorrelationMatrixPlot" class="tabcontent">
            """
            if corr_matrix_plot_path.endswith('.png'):
                corr_matrix_plot_name = 'CorrelationMatrixPlot.png'
                corr_matrix_plot_display_name = 'Correlation Matrix Plot'

                shutil.copy2(corr_matrix_plot_path,
                             os.path.join(output_directory, corr_matrix_plot_name))

                tab_content += '<div class="gallery">'
                tab_content += '<a target="_blank" href="{}">'.format(corr_matrix_plot_name)
                tab_content += '<img src="{}" '.format(corr_matrix_plot_name)
                tab_content += 'alt="{}" width="600" height="400">'.format(
                                                                    corr_matrix_plot_display_name)
                tab_content += '</a><div class="desc">{}</div></div>'.format(
                                                                corr_matrix_plot_display_name)
            elif corr_matrix_plot_path.endswith('.html'):
                corr_matrix_plot_name = 'CorrelationMatrixPlot.html'

                shutil.copy2(corr_matrix_plot_path,
                             os.path.join(output_directory, corr_matrix_plot_name))

                tab_content += '<iframe height="900px" width="100%" '
                tab_content += 'src="{}" '.format(corr_matrix_plot_name)
                tab_content += 'style="border:none;"></iframe>\n<p></p>\n'
            else:
                raise ValueError('unexpected correlation matrix plot format:\n{}'.format(
                                                                            corr_matrix_plot_path))

            tab_content += """</div>"""

        if scatter_plot_path:

            tab_def_content += """
            <button class="tablinks" onclick="openTab(event, 'ScatterMatrixPlot')">Scatter Matrix Plot</button>
            """

            tab_content += """
            <div id="ScatterMatrixPlot" class="tabcontent">
            """

            scatter_plot_name = 'ScatterMatrixPlot.png'
            scatter_plot_display_name = 'Scatter Matrix Plot'

            shutil.copy2(scatter_plot_path,
                         os.path.join(output_directory, scatter_plot_name))

            tab_content += '<div class="gallery">'
            tab_content += '<a target="_blank" href="{}">'.format(scatter_plot_name)
            tab_content += '<img src="{}" '.format(scatter_plot_name)
            tab_content += 'alt="{}" width="600" height="400">'.format(
                                                                scatter_plot_display_name)
            tab_content += '</a><div class="desc">{}</div></div>'.format(
                                                                scatter_plot_display_name)

            tab_content += """</div>"""

        tab_def_content += """</div>"""
        
        return tab_def_content + tab_content

    def _generate_corr_html_report(self, corr_matrix_obj_ref, corr_matrix_plot_path,
                                   scatter_plot_path):

        """
        _generate_corr_html_report: generate html summary report for correlation
        """

        logging.info('Start generating html report')
        html_report = list()

        output_directory = os.path.join(self.scratch, str(uuid.uuid4()))
        self._mkdir_p(output_directory)
        result_file_path = os.path.join(output_directory, 'corr_report.html')

        visualization_content = self._generate_visualization_content(
                                                                     output_directory,
                                                                     corr_matrix_obj_ref,
                                                                     corr_matrix_plot_path,
                                                                     scatter_plot_path)

        with open(result_file_path, 'w') as result_file:
            with open(os.path.join(os.path.dirname(__file__), 'templates', 'corr_template.html'),
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

    def _generate_corr_report(self, corr_matrix_obj_ref, workspace_name, corr_matrix_plot_path,
                              scatter_plot_path=None):
        """
        _generate_report: generate summary report
        """
        logging.info('Start creating report')

        output_html_files = self._generate_corr_html_report(corr_matrix_obj_ref,
                                                            corr_matrix_plot_path,
                                                            scatter_plot_path)

        report_params = {'message': '',
                         'objects_created': [{'ref': corr_matrix_obj_ref,
                                              'description': 'Correlation Matrix'}],
                         'workspace_name': workspace_name,
                         'html_links': output_html_files,
                         'direct_html_link_index': 0,
                         'html_window_height': 666,
                         'report_object_name': 'compute_correlation_matrix_' + str(uuid.uuid4())}

        kbase_report_client = KBaseReport(self.callback_url, token=self.token)
        output = kbase_report_client.create_extended_report(report_params)

        report_output = {'report_name': output['name'], 'report_ref': output['ref']}
        
        return report_output

    def _corr_for_matrix(self, input_obj_ref, method, dimension):
        """
        _corr_for_matrix: compute correlation matrix df for KBaseMatrices object
        """
        data_matrix = self.data_util.fetch_data({'obj_ref': input_obj_ref}).get('data_matrix')
        data_df = pd.read_json(data_matrix)
        data_df = data_df.reindex(index=natsorted(data_df.index))
        data_df = data_df.reindex(columns=natsorted(data_df.columns))

        corr_df = self.df_to_corr(data_df, method=method, dimension=dimension)

        return corr_df, data_df

    def _compute_significance(self, data_df, dimension):
        """
        _compute_significance: compute pairwsie significance dataframe
                               two-sided p-value for a hypothesis test
        """

        logging.info('Start computing significance matrix')
        if dimension == 'row':
            data_df = data_df.T

        data_df = data_df.dropna()._get_numeric_data()
        dfcols = pd.DataFrame(columns=data_df.columns)
        sig_df = dfcols.transpose().join(dfcols, how='outer')

        for r in data_df.columns:
            for c in data_df.columns:
                pvalue = stats.linregress(data_df[r], data_df[c])[3]
                sig_df[r][c] = round(pvalue, 4)

        return sig_df

    def _df_to_list(self, df, threshold=None):
        """
        _df_to_list: convert Dataframe to FloatMatrix2D matrix data
        """

        df.fillna(0, inplace=True)

        if threshold:
            drop_cols = list()
            for col in df.columns:
                if all(df[col] < threshold) and all(df[col] > -threshold):
                    drop_cols.append(col)
            df.drop(columns=drop_cols, inplace=True, errors='ignore')

            drop_idx = list()
            for idx in df.index:
                if all(df.loc[idx] < threshold) and all(df.loc[idx] > -threshold):
                    drop_idx.append(idx)
            df.drop(index=drop_idx, inplace=True, errors='ignore')

        matrix_data = {'row_ids': df.index.tolist(),
                       'col_ids': df.columns.tolist(),
                       'values': df.values.tolist()}

        return matrix_data

    def _save_corr_matrix(self, workspace_name, corr_matrix_name, corr_df, sig_df, method,
                          matrix_ref=None, corr_threshold=None):
        """
        _save_corr_matrix: save KBaseExperiments.CorrelationMatrix object
        """
        logging.info('Start saving CorrelationMatrix')

        if not isinstance(workspace_name, int):
            ws_name_id = self.dfu.ws_name_to_id(workspace_name)
        else:
            ws_name_id = workspace_name

        corr_data = {}

        corr_data.update({'coefficient_data': self._df_to_list(corr_df,
                                                               threshold=corr_threshold)})
        corr_data.update({'correlation_parameters': {'method': method}})
        if matrix_ref:
            corr_data.update({'original_matrix_ref': matrix_ref})

        if sig_df is not None:
            corr_data.update({'significance_data': self._df_to_list(sig_df)})

        obj_type = 'KBaseExperiments.CorrelationMatrix'
        info = self.dfu.save_objects({
            "id": ws_name_id,
            "objects": [{
                "type": obj_type,
                "data": corr_data,
                "name": corr_matrix_name
            }]
        })[0]

        return "%s/%s/%s" % (info[6], info[0], info[4])

    def _Matrix2D_to_df(self, Matrix2D):
        """
        _Matrix2D_to_df: transform a FloatMatrix2D to data frame
        """

        index = Matrix2D.get('row_ids')
        columns = Matrix2D.get('col_ids')
        values = Matrix2D.get('values')

        df = pd.DataFrame(values, index=index, columns=columns)

        return df

    def _corr_to_df(self, corr_matrix_ref):
        """
        retrieve correlation matrix ws object to coefficient_df and significance_df
        """

        corr_data = self.dfu.get_objects({'object_refs': [corr_matrix_ref]})['data'][0]['data']

        coefficient_data = corr_data.get('coefficient_data')
        significance_data = corr_data.get('significance_data')

        coefficient_df = self._Matrix2D_to_df(coefficient_data)

        significance_df = None
        if significance_data:
            significance_df = self._Matrix2D_to_df(significance_data)
        
        return coefficient_df, significance_df

    def _corr_df_to_excel(self, coefficient_df, significance_df, result_dir, corr_matrix_ref):
        """
        write correlation matrix dfs into excel
        """

        corr_info = self.dfu.get_objects({'object_refs': [corr_matrix_ref]})['data'][0]['info']
        corr_name = corr_info[1]

        file_path = os.path.join(result_dir, corr_name + ".xlsx")

        writer = pd.ExcelWriter(file_path)

        coefficient_df.to_excel(writer, "coefficient_data", index=True)

        if significance_df is not None:
            significance_df.to_excel(writer, "significance_data", index=True)

        writer.close()

    def _update_taxonomy_index(self, data_df, amplicon_set_ref):

        logging.info('start updating index with taxonomy info from AmpliconSet')

        amplicon_set_data = self.dfu.get_objects(
                                            {'object_refs': [amplicon_set_ref]})['data'][0]['data']

        amplicons = amplicon_set_data.get('amplicons')

        index = data_df.index.values

        replace_index = list()

        for idx in index:
            scientific_name = None
            try:
                scientific_name = amplicons.get(idx).get('taxonomy').get('scientific_name')
            except Exception:
                pass

            if scientific_name:
                replace_index.append(scientific_name + '_' + idx)
            else:
                replace_index.append(idx)

        for idx, val in enumerate(replace_index):
            index[idx] = val

        return data_df

    def _fetch_matrix_data(self, matrix_ref):

        logging.info('start fectching matrix data')

        res = self.dfu.get_objects({'object_refs': [matrix_ref]})['data'][0]
        obj_type = res['info'][2]

        if "KBaseMatrices" in obj_type:
            data_matrix = self.data_util.fetch_data({'obj_ref': matrix_ref}).get('data_matrix')
            data_df = pd.read_json(data_matrix)
            data_df = data_df.reindex(index=natsorted(data_df.index))
            data_df = data_df.reindex(columns=natsorted(data_df.columns))

            return data_df
        else:
            err_msg = 'Ooops! [{}] is not supported.\n'.format(obj_type)
            err_msg += 'Please supply KBaseMatrices object'
            raise ValueError("err_msg")

    def _compute_metrices_corr(self, df1, df2, method, compute_significance):

        df1.fillna(0, inplace=True)
        df2.fillna(0, inplace=True)

        col_1 = df1.columns
        col_2 = df2.columns
        idx_1 = df1.index
        idx_2 = df2.index

        common_col = col_1.intersection(col_2)
        logging.info('matrices share [{}] common columns'.format(common_col.size))

        if common_col.empty:
            raise ValueError('Matrices share no common columns')

        logging.info('start trimming original matrix')
        df1 = df1.loc[:][common_col]
        df2 = df2.loc[:][common_col]

        corr_df = pd.DataFrame(index=idx_1, columns=idx_2)
        sig_df = pd.DataFrame(index=idx_1, columns=idx_2)

        logging.info('start calculating correlation matrix')
        logging.info('sizing {} x {}'.format(idx_1.size, idx_2.size))
        counter = 0
        for idx_value in idx_1:
            for col_value in idx_2:

                if counter % 100000 == 0:
                    logging.info('computed {} corr/sig values'.format(counter))

                value_array_1 = df1.loc[idx_value].tolist()
                value_array_2 = df2.loc[col_value].tolist()

                if method == 'pearson':
                    corr_value, p_value = stats.pearsonr(value_array_1, value_array_2)
                elif method == 'spearman':
                    corr_value, p_value = stats.spearmanr(value_array_1, value_array_2)
                elif method == 'kendall':
                    corr_value, p_value = stats.kendalltau(value_array_1, value_array_2)
                else:
                    err_msg = 'Input correlation method [{}] is not available.\n'.format(method)
                    err_msg += 'Please choose one of {}'.format(CORR_METHOD)
                    raise ValueError(err_msg)

                corr_df.at[idx_value, col_value] = round(corr_value, 4)
                if compute_significance:
                    sig_df.at[idx_value, col_value] = round(p_value, 4)

                counter += 1

        if not compute_significance:
            sig_df = None

        return corr_df, sig_df

    def __init__(self, config):
        self.ws_url = config["workspace-url"]
        self.callback_url = config['SDK_CALLBACK_URL']
        self.token = config['KB_AUTH_TOKEN']
        self.scratch = config['scratch']

        self.data_util = DataUtil(config)
        self.dfu = DataFileUtil(self.callback_url)

        plt.switch_backend('agg')

    def df_to_corr(self, df, method='pearson', dimension='col'):
        """
        Compute pairwise correlation of dimension (col or row)

        method: one of ['pearson', 'kendall', 'spearman']
        """

        logging.info('Computing correlation matrix')

        if method not in CORR_METHOD:
            err_msg = 'Input correlation method [{}] is not available.\n'.format(method)
            err_msg += 'Please choose one of {}'.format(CORR_METHOD)
            raise ValueError(err_msg)

        if dimension == 'row':
            df = df.T
        elif dimension != 'col':
            err_msg = 'Input dimension [{}] is not available.\n'.format(dimension)
            err_msg += 'Please choose either "col" or "row"'
            raise ValueError(err_msg)

        corr_df = df.corr(method=method).round(4)

        return corr_df

    def plotly_corr_matrix(self, corr_df):
        logging.info('Plotting matrix of correlation')

        result_dir = os.path.join(self.scratch, str(uuid.uuid4()) + '_corr_matrix_plots')
        self._mkdir_p(result_dir)

        try:
            trace = go.Heatmap(z=corr_df.values,
                               x=corr_df.columns,
                               y=corr_df.index)
            data = [trace]
        except Exception:
            err_msg = 'Running plotly_corr_matrix returned an error:\n{}\n'.format(
                                                                    traceback.format_exc())
            raise ValueError(err_msg)
        else:
            corr_matrix_plot_path = os.path.join(result_dir, 'corr_matrix_plots.html')
            logging.info('Saving plot to:\n{}'.format(corr_matrix_plot_path))
            plot(data, filename=corr_matrix_plot_path)

        return corr_matrix_plot_path

    def plot_corr_matrix(self, corr_df):
        """
        plot_corr_matrix: genreate correlation matrix plot
        """
        logging.info('Plotting matrix of correlation')

        result_dir = os.path.join(self.scratch, str(uuid.uuid4()) + '_corr_matrix_plots')
        self._mkdir_p(result_dir)

        try:
            plt.clf()
            matrix_size = corr_df.index.size
            figsize = 10 if matrix_size / 5 < 10 else matrix_size / 5
            fig, ax = plt.subplots(figsize=(figsize, figsize))
            cax = ax.matshow(corr_df)
            plt.xticks(list(range(len(corr_df.columns))), corr_df.columns, rotation='vertical',
                       fontstyle='italic')
            plt.yticks(list(range(len(corr_df.columns))), corr_df.columns, fontstyle='italic')
            plt.colorbar(cax)
        except Exception:
            err_msg = 'Running plot_corr_matrix returned an error:\n{}\n'.format(
                                                                    traceback.format_exc())
            raise ValueError(err_msg)
        else:
            corr_matrix_plot_path = os.path.join(result_dir, 'corr_matrix_plots.png')
            logging.info('Saving plot to:\n{}'.format(corr_matrix_plot_path))
            plt.savefig(corr_matrix_plot_path)

        return corr_matrix_plot_path

    def plot_scatter_matrix(self, df, dimension='col', alpha=0.2, diagonal='kde', figsize=(10, 10)):
        """
        plot_scatter_matrix: generate scatter plot for dimension (col or row)
                             ref: https://pandas.pydata.org/pandas-docs/stable/generated/pandas.plotting.scatter_matrix.html
        """
        logging.info('Plotting matrix of scatter')

        result_dir = os.path.join(self.scratch, str(uuid.uuid4()) + '_scatter_plots')
        self._mkdir_p(result_dir)

        if dimension == 'row':
            df = df.T
        elif dimension != 'col':
            err_msg = 'Input dimension [{}] is not available.\n'.format(dimension)
            err_msg += 'Please choose either "col" or "row"'
            raise ValueError(err_msg)

        try:
            plt.clf()
            sm = pd.plotting.scatter_matrix(df, alpha=alpha, diagonal=diagonal, figsize=figsize)

            # Change label rotation
            [s.xaxis.label.set_rotation(45) for s in sm.reshape(-1)]
            [s.yaxis.label.set_rotation(45) for s in sm.reshape(-1)]

            # # May need to offset label when rotating to prevent overlap of figure
            [s.get_yaxis().set_label_coords(-1.5, 0.5) for s in sm.reshape(-1)]

            # Hide all ticks
            [s.set_xticks(()) for s in sm.reshape(-1)]
            [s.set_yticks(()) for s in sm.reshape(-1)]
        except Exception:
            err_msg = 'Running scatter_matrix returned an error:\n{}\n'.format(
                                                                    traceback.format_exc())
            raise ValueError(err_msg)
        else:
            scatter_plot_path = os.path.join(result_dir, 'scatter_plots.png')
            logging.info('Saving plot to:\n{}'.format(scatter_plot_path))
            plt.savefig(scatter_plot_path)

        return scatter_plot_path

    def compute_correlation_across_matrices(self, params):
        """
        matrix_ref_1: object reference of a matrix
        matrix_ref_2: object reference of a matrix
        workspace_name: workspace name objects to be saved to
        corr_matrix_name: correlation matrix object name
        method: correlation method, one of ['pearson', 'kendall', 'spearman']
        plot_corr_matrix: plot correlation matrix in report, default False
        compute_significance: also compute Significance in addition to correlation matrix
        """

        logging.info('--->\nrunning CorrelationUtil.compute_correlation_across_matrices\n' +
                     'params:\n{}'.format(json.dumps(params, indent=1)))

        self._validate_compute_correlation_across_matrices_params(params)

        matrix_ref_1 = params.get('matrix_ref_1')
        matrix_ref_2 = params.get('matrix_ref_2')
        workspace_name = params.get('workspace_name')
        corr_matrix_name = params.get('corr_matrix_name')
        corr_threshold = params.get('corr_threshold')

        method = params.get('method', 'pearson')
        if method not in CORR_METHOD:
            err_msg = 'Input correlation method [{}] is not available.\n'.format(method)
            err_msg += 'Please choose one of {}'.format(CORR_METHOD)
            raise ValueError(err_msg)
        plot_corr_matrix = params.get('plot_corr_matrix', False)
        compute_significance = params.get('compute_significance', False)

        matrix_1_type = self.dfu.get_objects({'object_refs': [matrix_ref_1]})['data'][0]['info'][2]

        # making sure otu_ids are on the column of table
        if "AmpliconMatrix" in matrix_1_type:
            matrix_ref_1, matrix_ref_2 = matrix_ref_2, matrix_ref_1

        df1 = self._fetch_matrix_data(matrix_ref_1)
        df2 = self._fetch_matrix_data(matrix_ref_2)

        corr_df, sig_df = self._compute_metrices_corr(df1, df2, method, compute_significance)

        if plot_corr_matrix:
            corr_matrix_plot_path = self.plotly_corr_matrix(corr_df)
        else:
            corr_matrix_plot_path = None

        corr_matrix_obj_ref = self._save_corr_matrix(workspace_name, corr_matrix_name, corr_df,
                                                     sig_df, method,
                                                     matrix_ref=[matrix_ref_1, matrix_ref_2],
                                                     corr_threshold=corr_threshold)

        returnVal = {'corr_matrix_obj_ref': corr_matrix_obj_ref}

        report_output = self._generate_corr_report(corr_matrix_obj_ref, workspace_name,
                                                   corr_matrix_plot_path)

        returnVal.update(report_output)

        return returnVal

    def compute_correlation_matrix(self, params):
        """
        input_obj_ref: object reference of a matrix
        workspace_name: workspace name objects to be saved to
        dimension: compute correlation on column or row, one of ['col', 'row']
        corr_matrix_name: correlation matrix object name
        method: correlation method, one of ['pearson', 'kendall', 'spearman']
        compute_significance: compute pairwise significance value, default False
        plot_corr_matrix: plot correlation matrix in repor, default False
        plot_scatter_matrix: plot scatter matrix in report, default False
        """

        logging.info('--->\nrunning CorrelationUtil.compute_correlation_matrix\n' +
                     'params:\n{}'.format(json.dumps(params, indent=1)))

        self._validate_compute_corr_matrix_params(params)

        input_obj_ref = params.get('input_obj_ref')
        workspace_name = params.get('workspace_name')
        corr_matrix_name = params.get('corr_matrix_name')

        method = params.get('method', 'pearson')
        dimension = params.get('dimension', 'row')
        plot_corr_matrix = params.get('plot_corr_matrix', False)
        plot_scatter_matrix = params.get('plot_scatter_matrix', False)
        compute_significance = params.get('compute_significance', False)

        res = self.dfu.get_objects({'object_refs': [input_obj_ref]})['data'][0]
        obj_type = res['info'][2]

        if "KBaseMatrices" in obj_type:
            corr_df, data_df = self._corr_for_matrix(input_obj_ref, method, dimension)
            sig_df = None
            if compute_significance:
                sig_df = self._compute_significance(data_df, dimension)
        else:
            err_msg = 'Ooops! [{}] is not supported.\n'.format(obj_type)
            err_msg += 'Please supply KBaseMatrices object'
            raise ValueError("err_msg")

        if plot_corr_matrix:
            corr_matrix_plot_path = self.plotly_corr_matrix(corr_df)
        else:
            corr_matrix_plot_path = None

        if plot_scatter_matrix:
            scatter_plot_path = self.plot_scatter_matrix(data_df, dimension=dimension)
        else:
            scatter_plot_path = None

        corr_matrix_obj_ref = self._save_corr_matrix(workspace_name, corr_matrix_name, corr_df,
                                                     sig_df, method, matrix_ref=[input_obj_ref])

        returnVal = {'corr_matrix_obj_ref': corr_matrix_obj_ref}

        report_output = self._generate_corr_report(corr_matrix_obj_ref, workspace_name,
                                                   corr_matrix_plot_path, scatter_plot_path)

        returnVal.update(report_output)

        return returnVal

    def export_corr_matrix_excel(self, params):
        """
        export CorrelationMatrix as Excel
        """

        corr_matrix_ref = params.get('input_ref')

        coefficient_df, significance_df = self._corr_to_df(corr_matrix_ref)
        #exit(coefficient_df)
        '''
        SystemExit:                    WRI_RS00010_CDS_1        ...          WRI_RS00025_CDS_1
        WRI_RS00010_CDS_1               1.00        ...                       0.91*** starting test: test_init_ok **
        WRI_RS00015_CDS_1               0.99        ...                       0.91
        WRI_RS00025_CDS_1               0.91        ...                       1.00*** starting test: test_plot_corr_matrix_ok **
        '''

        result_dir = os.path.join(self.scratch, str(uuid.uuid4()))
        self._mkdir_p(result_dir)

        self._corr_df_to_excel(coefficient_df, significance_df, result_dir, corr_matrix_ref)

        package_details = self.dfu.package_for_download({
            'file_path': result_dir,
            'ws_refs': [corr_matrix_ref]
        })

        return {'shock_id': package_details['shock_id']}
