import errno
import json
import logging
import math
import os
import shutil
import uuid
from random import randint
from random import seed

import networkx as nx
import pandas as pd
import plotly.graph_objs as go
from matplotlib import pyplot as plt
from plotly.offline import plot

from installed_clients.DataFileUtilClient import DataFileUtil
from GenericsAPI.Utils.CorrelationUtil import CorrelationUtil
from GenericsAPI.Utils.DataUtil import DataUtil
from installed_clients.KBaseReportClient import KBaseReport


class NetworkUtil:

    SIGMA_PATH = '/kb/module/sigma_js'

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

    def _Matrix2D_to_df(self, Matrix2D):
        """
        _Matrix2D_to_df: transform a FloatMatrix2D to data frame
        """

        index = Matrix2D.get('row_ids')
        columns = Matrix2D.get('col_ids')
        values = Matrix2D.get('values')

        df = pd.DataFrame(values, index=index, columns=columns)

        return df

    def _trans_df(self, df):
        """
        _trans_df: transform DF in a links data frame (3 columns only)
        """

        links = df.stack().reset_index()
        links.columns = ['source', 'target', 'value']

        return links

    def _generate_visualization_content(self, graph):
        """
        _generate_visualization_content: generate visualization html content
        """
        
        graph_nodes_content = str(graph.nodes()).replace('u', '')
        graph_edges_content = str([list(edge) for edge in graph.edges()]).replace('u', '')

        return graph_nodes_content, graph_edges_content

    def _generate_network_html_report(self, graph):
        """
        _generate_network_html_report: generate html summary report
        """

        logging.info('Start generating html report')
        html_report = list()

        output_directory = os.path.join(self.scratch, str(uuid.uuid4()))
        self._mkdir_p(output_directory)
        result_file_path = os.path.join(output_directory, 'network_report.html')

        shutil.copytree(self.SIGMA_PATH, os.path.join(output_directory, 'sigma_js'))

        graph_nodes_content, graph_edges_content = self._generate_visualization_content(graph)

        with open(result_file_path, 'w') as result_file:
            with open(os.path.join(os.path.dirname(__file__), 'templates', 'network_template.html'),
                      'r') as report_template_file:
                report_template = report_template_file.read()
                report_template = report_template.replace('//GRAPH_NODES',
                                                          graph_nodes_content)
                report_template = report_template.replace('//GRAPH_EDGES',
                                                          graph_edges_content)
                result_file.write(report_template)

        report_shock_id = self.dfu.file_to_shock({'file_path': output_directory,
                                                  'pack': 'zip'})['shock_id']

        html_report.append({'shock_id': report_shock_id,
                            'name': os.path.basename(result_file_path),
                            'label': os.path.basename(result_file_path),
                            'description': 'HTML summary report for Build Network App'
                            })
        
        return html_report

    def _generate_plotly_network(self, graph):
        """
        _generate_ploty_network: generate html summary report
        """

        logging.info('Start generating html report')
        html_report = list()

        output_directory = os.path.join(self.scratch, str(uuid.uuid4()))
        self._mkdir_p(output_directory)
        result_file_path = os.path.join(output_directory, 'network_report.html')

        self._plotly_network(graph, result_file_path)

        report_shock_id = self.dfu.file_to_shock({'file_path': output_directory,
                                                  'pack': 'zip'})['shock_id']

        html_report.append({'shock_id': report_shock_id,
                            'name': os.path.basename(result_file_path),
                            'label': os.path.basename(result_file_path),
                            'description': 'HTML summary report for Build Network App'
                            })
     
        return html_report

    def _plotly_network(self, graph, result_file_path):
        logging.info('start ploting network using plotly')

        # create node position
        seed(1)
        nodes = dict()
        for edge in list(graph.edges(data=True)):
            node1 = edge[0]
            node2 = edge[1]
            weight = (1 - abs(edge[2]['weight'])) * 100

            if node1 in nodes and node2 not in nodes:
                x1, y1 = nodes[node1]['pos']

                radians = randint(0, 10)
                x2 = x1 + int(math.cos(radians) * weight)
                y2 = y1 + int(math.sin(radians) * weight)

                nodes.update({node2: {'pos': (x2, y2)}})
            elif node2 in nodes and node1 not in nodes:
                x2, y2 = nodes[node2]['pos']

                radians = randint(0, 10)
                x1 = x2 + int(math.cos(radians) * weight)
                y1 = y2 + int(math.sin(radians) * weight)

                nodes.update({node1: {'pos': (x1, y1)}})
            else:
                x1 = randint(0, 100)
                y1 = randint(0, 100)
                nodes.update({node1: {'pos': (x1, y1)}})

                radians = randint(0, 10)
                x2 = x1 + int(math.cos(radians) * weight)
                y2 = y1 + int(math.sin(radians) * weight)

                nodes.update({node2: {'pos': (x2, y2)}})

        # create edges
        edge_trace_pos = go.Scatter(x=[], y=[], line=dict(width=0.6, color='#888'),
                                    hoverinfo='text', mode='lines', name='positive correlation')
        edge_trace_neg = go.Scatter(x=[], y=[], line=dict(width=0.6, color='#888'),
                                    hoverinfo='text', mode='lines', name='negative correlation')

        for edge in graph.edges(data=True):
            x0, y0 = nodes[edge[0]]['pos']
            x1, y1 = nodes[edge[1]]['pos']
            if edge[2]['weight'] >= 0:
                edge_trace_pos['x'] += tuple([x0, x1, None])
                edge_trace_pos['y'] += tuple([y0, y1, None])
            else:
                edge_trace_neg['x'] += tuple([x0, x1, None])
                edge_trace_neg['y'] += tuple([y0, y1, None])

        # create nodes
        node_trace = go.Scatter(x=[], y=[], text=[], mode='markers', hoverinfo='text',
                                marker=dict(showscale=True, colorscale='YlGnBu',
                                            reversescale=True, color=[], size=10,
                                            colorbar=dict(thickness=15, title='Node Connections',
                                                          xanchor='left', titleside='right'),
                                            line=dict(width=2)))

        for node in nodes:
            x, y = nodes[node]['pos']
            node_trace['x'] += tuple([x])
            node_trace['y'] += tuple([y])

        # color and text Node points
        for node, adjacencies in enumerate(graph.adjacency()):
            node_trace['marker']['color'] += tuple([len(adjacencies[1])])
            node_info = adjacencies[0]
            connections = list(adjacencies[1].keys())
            node_info += ', {} connections'.format(len(connections))
            node_trace['text'] += tuple([node_info])

        # create network graph
        fig = go.Figure(data=[edge_trace_pos, edge_trace_neg, node_trace],
                        layout=go.Layout(title='<br>Correlation Network', titlefont=dict(size=16),
                                         showlegend=False, hovermode='closest',
                                         margin=dict(b=20, l=5, r=5, t=40),
                                         xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                                         yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)))

        plot(fig, filename=result_file_path)

    def _generate_network_report(self, graph, network_obj_ref, workspace_name):
        """
        _generate_report: generate summary report
        """
        logging.info('Start creating report')

        output_html_files = self._generate_plotly_network(graph)

        report_params = {'message': '',
                         'objects_created': [{'ref': network_obj_ref,
                                              'description': 'Network'}],
                         'workspace_name': workspace_name,
                         'html_links': output_html_files,
                         'direct_html_link_index': 0,
                         'html_window_height': 333,
                         'report_object_name': 'build_network_' + str(uuid.uuid4())}

        kbase_report_client = KBaseReport(self.callback_url, token=self.token)
        output = kbase_report_client.create_extended_report(report_params)

        report_output = {'report_name': output['name'], 'report_ref': output['ref']}

        return report_output

    def _filter_links_threshold(self, links, threshold):
        """
        _filter_links_threshold: filetre links df over a threshold and remove self correlation (cor(A,A)=1)
        """

        links_filtered = links.loc[(links['value'] >= threshold) & (links['source'] != links['target'])]

        return links_filtered

    def _filter_neg_links_threshold(self, links, threshold):
        """
        _filter_links_threshold: filetre links df below a negative threshold and remove self correlation (cor(A,A)=1)
        """

        links_filtered = links.loc[(links['value'] <= threshold) & (links['source'] != links['target'])]

        return links_filtered

    def _build_network_object(self, graph, workspace_name, network_obj_name, corr_matrix_ref):
        """
        _build_network_object: tansform graph to KBbase network object
        """

        if not isinstance(workspace_name, int):
            ws_name_id = self.dfu.ws_name_to_id(workspace_name)
        else:
            ws_name_id = workspace_name

        network_data = {'description': 'Correlation Network'}
        network_data.update({'corr_matrix_ref': corr_matrix_ref})

        corr_data = self.dfu.get_objects({'object_refs': [corr_matrix_ref]})['data'][0]['data']
        original_matrix_ref = corr_data.get('original_matrix_ref')

        if original_matrix_ref:
            network_data.update({'original_matrix_ref': original_matrix_ref})

        nodes_list = list(graph.nodes())
        nodes = dict()
        for node in nodes_list:
            nodes.update({node: {'label': node}})
        network_data.update({'nodes': nodes})

        edges = list()
        for edge in list(graph.edges(data=True)):
            edges.append({'node_1_id': edge[0],
                          'node_2_id': edge[1],
                          'weight': edge[2]['weight']})
        network_data.update({'edges': edges})

        obj_type = 'KBaseExperiments.Network'
        info = self.dfu.save_objects({
            "id": ws_name_id,
            "objects": [{
                "type": obj_type,
                "data": network_data,
                "name": network_obj_name
            }]
        })[0]

        return "%s/%s/%s" % (info[6], info[0], info[4])

    def _process_build_nx_params(self, params):

        logging.info('start validating build_network params')

        params = params.copy()

        # check for required parameters
        for p in ['corr_matrix_ref', 'workspace_name', 'network_obj_name']:
            if p not in params:
                raise ValueError('"{}" parameter is required, but missing'.format(p))

        if not params['filter_on_threshold']:
            raise ValueError('Must choose either filter_on_threshold or ...')
        # params['filter_on_threshold'] = True

        return params

    def _merge_links(self, corr_links_filtered_pos, corr_links_filtered_neg,
                     sig_links_filtered):

        corr_filtered_df = pd.concat([corr_links_filtered_pos, corr_links_filtered_neg])

        if sig_links_filtered is not None:
            keep_ids = set(corr_filtered_df.index).intersection(set(sig_links_filtered.index))
            corr_filtered_df = corr_filtered_df.loc[list(keep_ids)]

        return corr_filtered_df

    def __init__(self, config):
        self.ws_url = config["workspace-url"]
        self.callback_url = config['SDK_CALLBACK_URL']
        self.token = config['KB_AUTH_TOKEN']
        self.scratch = config['scratch']

        self.data_util = DataUtil(config)
        self.corr_util = CorrelationUtil(config)
        self.dfu = DataFileUtil(self.callback_url)

        plt.switch_backend('agg')

    @staticmethod
    def draw_graph(graph, path, graph_layout='shell', node_size=400, node_color='blue',
                   edge_color='green', font_color='black', alpha=0.3, font_size=15, linewidths=1):

        plt.clf()

        # network layouts
        if graph_layout == 'spring':
            graph_pos = nx.spring_layout(graph)
        elif graph_layout == 'spectral':
            graph_pos = nx.spectral_layout(graph)
        elif graph_layout == 'random':
            graph_pos = nx.random_layout(graph)
        else:
            graph_pos = nx.shell_layout(graph)

        nx.draw(graph, pos=graph_pos, with_labels=True, node_color=node_color, node_size=node_size,
                edge_color=edge_color, alpha=alpha, font_color=font_color, linewidths=linewidths,
                font_size=font_size)

        plt.savefig(path)

    def df_to_graph(self, graph_df, source, target):
        """
        _df_to_graph: a graph from Pandas DataFrame containing an edge list
        """
        graph_df.rename(columns={'value': 'weight'}, inplace=True)

        graph = nx.from_pandas_edgelist(graph_df, source=source, target=target,
                                        edge_attr=['weight'])

        return graph

    def build_network(self, params):
        """
        build_network: filter correlation matrix and build network on filtered correlation matrix
        """

        logging.info('--->\nrunning NetworkUtil.build_network\n' +
            'params:\n{}'.format(json.dumps(params, indent=1)))

        params = self._process_build_nx_params(params)

        corr_matrix_ref = params.get('corr_matrix_ref')
        workspace_name = params.get('workspace_name')
        network_obj_name = params.get('network_obj_name')
        corr_data = self.dfu.get_objects({'object_refs': [corr_matrix_ref]})['data'][0]['data']

        coefficient_data = corr_data.get('coefficient_data')
        significance_data = corr_data.get('significance_data')

        if params.get('filter_on_threshold'):
            coefficient_threshold = params.get('filter_on_threshold').get('coefficient_threshold')
            significance_threshold = params.get('filter_on_threshold').get('significance_threshold')
            corr_df = self._Matrix2D_to_df(coefficient_data)
            corr_links = self._trans_df(corr_df)
            corr_links_filtered_pos = self._filter_links_threshold(corr_links,
                                                                   coefficient_threshold)
            corr_links_filtered_neg = self._filter_neg_links_threshold(corr_links,
                                                                       -coefficient_threshold)

            sig_links_filtered = None
            if significance_data:
                sig_df = self._Matrix2D_to_df(significance_data)
                sig_links = self._trans_df(sig_df)
                sig_links_filtered = self._filter_links_threshold(sig_links, significance_threshold)

            links_filtered = self._merge_links(corr_links_filtered_pos,
                                               corr_links_filtered_neg,
                                               sig_links_filtered)

            graph = self.df_to_graph(links_filtered, source='source', target='target')

        network_obj_ref = self._build_network_object(graph, workspace_name, network_obj_name, corr_matrix_ref)

        returnVal = {'network_obj_ref': network_obj_ref}
        report_output = self._generate_network_report(graph, network_obj_ref, workspace_name)

        returnVal.update(report_output)
        return returnVal
