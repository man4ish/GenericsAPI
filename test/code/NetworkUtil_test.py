# -*- coding: utf-8 -*-
import inspect
import os  # noqa: F401
import unittest
import time
import pandas as pd
from configparser import ConfigParser

from GenericsAPI.Utils.NetworkUtil import NetworkUtil
from GenericsAPI.GenericsAPIImpl import GenericsAPI
from GenericsAPI.GenericsAPIServer import MethodContext
from GenericsAPI.authclient import KBaseAuth as _KBaseAuth
from installed_clients.DataFileUtilClient import DataFileUtil
from installed_clients.WorkspaceClient import Workspace as workspaceService


class NetworkUtilTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        token = os.environ.get('KB_AUTH_TOKEN', None)
        config_file = os.environ.get('KB_DEPLOYMENT_CONFIG', None)
        cls.cfg = {}
        config = ConfigParser()
        config.read(config_file)
        for nameval in config.items('GenericsAPI'):
            cls.cfg[nameval[0]] = nameval[1]
        # Getting username from Auth profile for token
        authServiceUrl = cls.cfg['auth-service-url']
        auth_client = _KBaseAuth(authServiceUrl)
        user_id = auth_client.get_user(token)
        # WARNING: don't call any logging methods on the context object,
        # it'll result in a NoneType error
        cls.ctx = MethodContext(None)
        cls.ctx.update({'token': token,
                        'user_id': user_id,
                        'provenance': [
                            {'service': 'GenericsAPI',
                             'method': 'please_never_use_it_in_production',
                             'method_params': []
                             }],
                        'authenticated': 1})
        cls.wsURL = cls.cfg['workspace-url']
        cls.wsClient = workspaceService(cls.wsURL)
        cls.serviceImpl = GenericsAPI(cls.cfg)
        cls.scratch = cls.cfg['scratch']
        cls.callback_url = os.environ['SDK_CALLBACK_URL']
        cls.dfu = DataFileUtil(cls.callback_url)
        cls.network_util = NetworkUtil(cls.cfg)

        suffix = int(time.time() * 1000)
        cls.wsName = "man4ish_gupta:narrative_1568644342277"
        cls.wsId = 44071

        #cls.wsName = "test_network_util_" + str(suffix)
        #ret = cls.wsClient.create_workspace({'workspace': cls.wsName})
        #cls.wsId = ret[0]

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'wsName'):
            #cls.wsClient.delete_workspace({'workspace': cls.wsName})
            print('Test workspace was deleted')

    def getWsClient(self):
        return self.__class__.wsClient

    def getWsName(self):
        return self.__class__.wsName

    def getImpl(self):
        return self.__class__.serviceImpl

    def getContext(self):
        return self.__class__.ctx

    def getNetworkUtil(self):
        return self.__class__.network_util

    def loadCorrData(self):
        if hasattr(self.__class__, 'corr_data'):
            return self.__class__.corr_data

        corr_data = {'row_ids': ['WRI_RS00010_CDS_1',
                                 'WRI_RS00015_CDS_1',
                                 'WRI_RS00025_CDS_1'],
                     'values': [[1.0, 0.99, 0.91],
                                [0.99, 1.0, 0.91],
                                [0.91, 0.91, 1.0]],
                     'col_ids': ['WRI_RS00010_CDS_1',
                                 'WRI_RS00015_CDS_1',
                                 'WRI_RS00025_CDS_1']}

        self.__class__.corr_data = corr_data
        print('Loaded Correlation Data:\n{}\n'.format(corr_data))
        return corr_data

    def loadGraphDF(self):                             #loading graph data frame

        if hasattr(self.__class__, 'graph_df'):
            return self.__class__.graph_df

        d = {'source': ['A', 'E', 'F', 'F', 'F', 'F', 'G', 'G', 'G', 'H',
                        'I', 'I', 'I', 'J', 'J', 'J'],
             'target': ['E', 'A', 'G', 'H', 'I', 'J', 'F', 'I', 'J', 'F',
                        'F', 'G', 'J', 'F', 'G', 'I'],
             'value': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 1, 2, 3, 4, 5, 6]}
        graph_df = pd.DataFrame(data=d)

        self.__class__.graph_df = graph_df
        print('Loaded Graph Data:\n{}\n'.format(graph_df))
        
        return graph_df

    def loadCorrMatrix(self):                      #loading correlation matrix

        if hasattr(self.__class__, 'corr_matrix_ref'):
            return self.__class__.corr_matrix_ref

        object_type = 'KBaseExperiments.CorrelationMatrix'
        corr_matrix_object_name = 'test_corr_matrix'
        corr_matrix_data = {'correlation_parameters': {'method': 'pearson'},
                            'coefficient_data': self.loadCorrData(),
                            'significance_data': {'row_ids': ['WRI_RS00010_CDS_1',
                                                              'WRI_RS00015_CDS_1',
                                                              'WRI_RS00025_CDS_1'],
                                                  'values': [[0.0, 0.0, 0.0879],
                                                             [0.0, 0.0, 0.0879],
                                                             [0.0879, 0.0879, 0.0]],
                                                  'col_ids': ['WRI_RS00010_CDS_1',
                                                              'WRI_RS00015_CDS_1',
                                                              'WRI_RS00025_CDS_1']}}

        save_object_params = {
            'id': self.wsId,
            'objects': [{'type': object_type,
                         'data': corr_matrix_data,
                         'name': corr_matrix_object_name}]
        }

        dfu_oi = self.dfu.save_objects(save_object_params)[0]
        corr_matrix_ref = str(dfu_oi[6]) + '/' + str(dfu_oi[0]) + '/' + str(dfu_oi[4])

        self.__class__.corr_matrix_ref = corr_matrix_ref
        print('Loaded Correlation Matrix: ' + corr_matrix_ref)
        
        return corr_matrix_ref

    def fail_build_network(self, params, error, exception=ValueError, contains=False):
        with self.assertRaises(exception) as context:
            self.getImpl().build_network(self.ctx, params)
        if contains:
            self.assertIn(error, str(context.exception.args))
        else:
            self.assertEqual(error, str(context.exception.args[0]))

    def start_test(self):
        testname = inspect.stack()[1][3]
        print('\n*** starting test: ' + testname + ' **')

    def test_build_network_fail(self):
        self.start_test()

        invalidate_params = {'missing_corr_matrix_ref': 'corr_matrix_ref',
                             'workspace_name': 'workspace_name'}
        error_msg = '"corr_matrix_ref" parameter is required, but missing'
        self.fail_build_network(invalidate_params, error_msg)

        invalidate_params = {'corr_matrix_ref': 'corr_matrix_ref',
                             'missing_workspace_name': 'workspace_name'}
        error_msg = '"workspace_name" parameter is required, but missing'
        self.fail_build_network(invalidate_params, error_msg)

    def test_build_network_ok(self):                   #build network
        self.start_test()

        corr_matrix_ref = self.loadCorrMatrix()

        params = {'corr_matrix_ref': corr_matrix_ref,
                  'workspace_name': self.wsName,
                  'network_obj_name': 'test_network_obj',
                  'filter_on_threshold': {'coefficient_threshold': 0.8}}

        ret = self.getImpl().build_network(self.ctx, params)[0]

    def test_init_ok(self):
        self.start_test()
        class_attri = ['scratch', 'token', 'callback_url', 'ws_url']

        network_util = self.getNetworkUtil()
        self.assertTrue(set(class_attri) <= set(network_util.__dict__.keys()))
        self.assertEqual(network_util.scratch, self.cfg.get('scratch'))

    def test__Matrix2D_to_df(self):

        corr_data = self.loadCorrData()

        df = self.getNetworkUtil()._Matrix2D_to_df(corr_data)

        self.assertCountEqual(df.index.tolist(), corr_data.get('row_ids'))
        self.assertCountEqual(df.columns.tolist(), corr_data.get('col_ids'))
        self.assertCountEqual(df.values.tolist(), corr_data.get('values'))

    def test__trans_df_ok(self):
        corr_data = self.loadCorrData()

        df = self.getNetworkUtil()._Matrix2D_to_df(corr_data)

        links = self.getNetworkUtil()._trans_df(df)

        self.assertEqual(links.index.size, len(corr_data.get('row_ids'))**2)
        self.assertEqual(links.columns.size, 3)

    def test_df_to_graph_ok(self):

        graph_df = self.loadGraphDF()

        graph = self.getNetworkUtil().df_to_graph(graph_df, 'source', 'target')

        expected_nodes = ['A', 'E', 'G', 'F', 'I', 'H', 'J']
        self.assertCountEqual(list(graph.nodes()), expected_nodes)

    def test_draw_graph_ok(self):

        graph_df = self.loadGraphDF()
        graph = self.getNetworkUtil().df_to_graph(graph_df, 'source', 'target')

        graph_path = os.path.join(self.scratch, 'graph.png')

        self.getNetworkUtil().draw_graph(graph, graph_path)
        self.assertGreater(os.path.getsize(graph_path), 1024)  # file size greate than 1KB

        self.getNetworkUtil().draw_graph(graph, graph_path, graph_layout='spectral')
        self.assertGreater(os.path.getsize(graph_path), 1024)  # file size greate than 1KB
