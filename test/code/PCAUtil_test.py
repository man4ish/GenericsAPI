# -*- coding: utf-8 -*-
import inspect
import os  # noqa: F401
import unittest
import time
import shutil
from configparser import ConfigParser
import uuid
import pandas as pd

from GenericsAPI.Utils.PCAUtil import PCAUtil
from GenericsAPI.GenericsAPIImpl import GenericsAPI
from GenericsAPI.GenericsAPIServer import MethodContext
from GenericsAPI.authclient import KBaseAuth as _KBaseAuth
from installed_clients.DataFileUtilClient import DataFileUtil
from installed_clients.WorkspaceClient import Workspace as workspaceService


class PCAUtilTest(unittest.TestCase):

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
        cls.pca_util = PCAUtil(cls.cfg)

        suffix = int(time.time() * 1000)

        cls.wsName = "man4ish_gupta:narrative_1568644342277"
        cls.wsId = 44071
        #ret = cls.wsClient.create_workspace({'workspace': cls.wsName})
        #cls.wsName = "test_pca_util_" + str(suffix)
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

    def getPCAUtil(self):
        return self.__class__.pca_util

    def loadExpressionMatrix(self):
        if hasattr(self.__class__, 'expr_matrix_ref'):
            return self.__class__.expr_matrix_ref

        matrix_file_name = 'test_import.xlsx'
        matrix_file_path = os.path.join(self.scratch, matrix_file_name)
        shutil.copy(os.path.join('data', matrix_file_name), matrix_file_path)

        obj_type = 'ExpressionMatrix'
        params = {'obj_type': obj_type,
                  'matrix_name': 'test_ExpressionMatrix',
                  'workspace_name': self.wsName,
                  'input_file_path': matrix_file_path,
                  'scale': "log2",
                  }
        expr_matrix_ref = self.serviceImpl.import_matrix_from_excel(
            self.ctx, params)[0].get('matrix_obj_ref')

        self.__class__.expr_matrix_ref = expr_matrix_ref
        print('Loaded ExpressionMatrix: ' + expr_matrix_ref)
        return expr_matrix_ref

    def loadPCAMatrix(self):

        if hasattr(self.__class__, 'pca_matrix_ref'):
            return self.__class__.pca_matrix_ref

        original_matrix_ref = self.loadExpressionMatrix()

        object_type = 'KBaseExperiments.PCAMatrix'
        pca_matrix_object_name = 'test_PCA_matrix'
        pca_matrix_data = {'explained_variance_ratio': [0.628769688409428, 0.371230311590572],
                           'explained_variance': [0.628769688409428, 0.371230311590572],
                           # 'original_matrix_ref': original_matrix_ref,
                           'pca_parameters': {'dimension': 'row', 'n_components': '2'},
                           'rotation_matrix': {'col_ids': ['principal_component_1',
                                                           'principal_component_2'],
                                               'row_ids': ['WRI_RS00010_CDS_1',
                                                           'WRI_RS00015_CDS_1',
                                                           'WRI_RS00025_CDS_1'],
                                               'values': [[-0.45, 1.06],
                                                          [-0.69, -0.92],
                                                          [1.14, -0.13]]}}

        save_object_params = {
            'id': self.wsId,
            'objects': [{'type': object_type,
                         'data': pca_matrix_data,
                         'name': pca_matrix_object_name}]
        }

        dfu_oi = self.dfu.save_objects(save_object_params)[0]
        pca_matrix_ref = str(dfu_oi[6]) + '/' + str(dfu_oi[0]) + '/' + str(dfu_oi[4])

        self.__class__.pca_matrix_ref = pca_matrix_ref
        print('Loaded Correlation Matrix: ' + pca_matrix_ref)
        return pca_matrix_ref

    def fail_run_pca(self, params, error, exception=ValueError, contains=False):
        with self.assertRaises(exception) as context:
            self.getImpl().run_pca(self.ctx, params)
        if contains:
            self.assertIn(error, str(context.exception.args))
        else:
            self.assertEqual(error, str(context.exception.args[0]))

    def start_test(self):
        testname = inspect.stack()[1][3]
        print('\n*** starting test: ' + testname + ' **')

    def test_run_pca_fail(self):
        self.start_test()

        invalidate_params = {'missing_input_obj_ref': 'input_obj_ref',
                             'workspace_name': 'workspace_name'}
        error_msg = '"input_obj_ref" parameter is required, but missing'
        self.fail_run_pca(invalidate_params, error_msg)

        invalidate_params = {'input_obj_ref': 'input_obj_ref',
                             'missing_workspace_name': 'workspace_name'}
        error_msg = '"workspace_name" parameter is required, but missing'
        self.fail_run_pca(invalidate_params, error_msg)

    def test_run_pca_ok(self):
        self.start_test()

        expr_matrix_ref = self.loadExpressionMatrix()

        params = {'input_obj_ref': expr_matrix_ref,
                  'workspace_name': self.wsName,
                  'pca_matrix_name': 'test_pca_matrix_obj',
                  'scale_size_by': {
                        "attribute_size": ["test_attribute_1"]
                    },
                  'color_marker_by': {
                        "attribute_color": ["test_attribute_2"]
                    },
                  'n_components': 3}

        ret = self.getImpl().run_pca(self.ctx, params)[0]

        self.assertTrue('report_name' in ret)
        self.assertTrue('report_ref' in ret)
        self.assertTrue('pca_ref' in ret)

        pca_matrix_ref = ret.get('pca_ref')

        pca_matrix_data = self.dfu.get_objects(
                    {"object_refs": [pca_matrix_ref]})['data'][0]['data']

        self.assertTrue('explained_variance_ratio' in pca_matrix_data)
        self.assertTrue('rotation_matrix' in pca_matrix_data)
        self.assertEqual(len(pca_matrix_data.get('explained_variance_ratio')), 3)

        expected_row_ids = ['WRI_RS00010_CDS_1', 'WRI_RS00015_CDS_1', 'WRI_RS00025_CDS_1']
        expected_col_ids = ['principal_component_1', 'principal_component_2', 'principal_component_3']
        self.assertCountEqual(pca_matrix_data['rotation_matrix']['row_ids'], expected_row_ids)
        self.assertCountEqual(pca_matrix_data['rotation_matrix']['col_ids'], expected_col_ids)

    def test_export_pca_matrix_excel_ok(self):
        self.start_test()

        pca_ref = self.loadPCAMatrix()

        params = {'input_ref': pca_ref}

        ret = self.getImpl().export_pca_matrix_excel(self.ctx, params)[0]

        assert ret and ('shock_id' in ret)

        output_directory = os.path.join(self.scratch, str(uuid.uuid4()))
        os.makedirs(output_directory)

        self.dfu.shock_to_file({'shock_id': ret['shock_id'],
                                'file_path': output_directory,
                                'unpack': 'unpack'})

        xl_files = [file for file in os.listdir(output_directory) if file.endswith('.xlsx')]
        self.assertEqual(len(xl_files), 1)

        xl = pd.ExcelFile(os.path.join(output_directory, xl_files[0]))
        expected_sheet_names = ['principal_component_matrix']
        self.assertCountEqual(xl.sheet_names, expected_sheet_names)

        df = xl.parse("principal_component_matrix")
        expected_index = ['WRI_RS00010_CDS_1', 'WRI_RS00015_CDS_1', 'WRI_RS00025_CDS_1']
        expected_col = ['principal_component_1', 'principal_component_2']
        self.assertCountEqual(df.index.tolist(), expected_index)
        self.assertCountEqual(df.columns.tolist(), expected_col)

    def test_init_ok(self):
        self.start_test()
        class_attri = ['scratch', 'token', 'callback_url', 'ws_url']

        network_util = self.getPCAUtil()
        self.assertTrue(set(class_attri) <= set(network_util.__dict__.keys()))
        self.assertEqual(network_util.scratch, self.cfg.get('scratch'))
