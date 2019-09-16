# -*- coding: utf-8 -*-
import inspect
import os
import shutil
import time
import unittest
from configparser import ConfigParser  # py2
from os import environ

from installed_clients.DataFileUtilClient import DataFileUtil
from GenericsAPI.GenericsAPIImpl import GenericsAPI
from GenericsAPI.GenericsAPIServer import MethodContext
from GenericsAPI.authclient import KBaseAuth as _KBaseAuth
from installed_clients.GenomeFileUtilClient import GenomeFileUtil
from installed_clients.WorkspaceClient import Workspace as workspaceService


class GenericsAPITest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        token = environ.get('KB_AUTH_TOKEN', None)
        config_file = environ.get('KB_DEPLOYMENT_CONFIG', None)
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

        cls.gfu = GenomeFileUtil(cls.callback_url)
        cls.dfu = DataFileUtil(cls.callback_url)

        suffix = int(time.time() * 1000)
        cls.wsName = "test_GenericsAPI_" + str(suffix)
        cls.wsClient.create_workspace({'workspace': cls.wsName})
        cls.prepare_data()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'wsName'):
            cls.wsClient.delete_workspace({'workspace': cls.wsName})
            print('Test workspace was deleted')

    @classmethod
    def prepare_data(cls):

        # upload genome object
        genbank_file_name = 'minimal.gbff'
        genbank_file_path = os.path.join(cls.scratch, genbank_file_name)
        shutil.copy(os.path.join('data', genbank_file_name), genbank_file_path)

        genome_object_name = 'test_Genome'
        cls.genome_ref = cls.gfu.genbank_to_genome({'file': {'path': genbank_file_path},
                                                    'workspace_name': cls.wsName,
                                                    'genome_name': genome_object_name,
                                                    'generate_ids_if_needed': 1
                                                    })['genome_ref']

        # upload AttributeMapping object
        workspace_id = cls.dfu.ws_name_to_id(cls.wsName)
        object_type = 'KBaseExperiments.AttributeMapping'
        attribute_mapping_object_name = 'test_attribute_mapping'
        attribute_mapping_data = {'instances': {'test_instance_1': ['1-1', '1-2', '1-3'],
                                                'test_instance_2': ['2-1', '2-2', '2-3'],
                                                'test_instance_3': ['3-1', '3-2', '3-3']},
                                  'attributes': [{'attribute': 'test_attribute_1',
                                                  'source': 'upload'},
                                                 {'attribute': 'test_attribute_2',
                                                  'source': 'upload'},
                                                 {'attribute': 'test_attribute_3',
                                                  'source': 'upload'}],
                                  'ontology_mapping_method': 'user curation'}
        save_object_params = {
            'id': workspace_id,
            'objects': [{'type': object_type,
                         'data': attribute_mapping_data,
                         'name': attribute_mapping_object_name}]
        }

        dfu_oi = cls.dfu.save_objects(save_object_params)[0]
        cls.attribute_mapping_ref = str(dfu_oi[6]) + '/' + str(dfu_oi[0]) + '/' + str(dfu_oi[4])

        cls.col_ids = ['instance_1', 'instance_2', 'instance_3', 'instance_4']
        cls.row_ids = ['WRI_RS00050_CDS_1', 'WRI_RS00065_CDS_1', 'WRI_RS00070_CDS_1']
        cls.values = [[0.1, 0.2, 0.3, 0.4],
                      [0.3, 0.4, 0.5, 0.6],
                      [None, None, None, None]]
        cls.row_mapping = {'WRI_RS00050_CDS_1': 'test_instance_1',
                           'WRI_RS00065_CDS_1': 'test_instance_2',
                           'WRI_RS00070_CDS_1': 'test_instance_3'}
        cls.col_mapping = {'instance_1': 'test_instance_1',
                           'instance_2': 'test_instance_2',
                           'instance_3': 'test_instance_3',
                           'instance_4': 'test_instance_3'}
        cls.feature_mapping = {'WRI_RS00050_CDS_1': 'WRI_RS00050_CDS_1',
                               'WRI_RS00065_CDS_1': 'WRI_RS00065_CDS_1',
                               'WRI_RS00070_CDS_1': 'WRI_RS00070_CDS_1'}

    def start_test(self):
        testname = inspect.stack()[1][3]
        print('\n*** starting test: ' + testname + ' **')

    def test_import_matrix_from_excel(self):
        self.start_test()

        obj_type = 'ExpressionMatrix'
        params = {'obj_type': obj_type,
                  'matrix_name': 'test_ExpressionMatrix',
                  'workspace_name': self.wsName,
                  'input_file_path': os.path.join('data', 'test_import.xlsx'),
                  'genome_ref': self.genome_ref,
                  'scale': 'log2',
                  }
        returnVal = self.serviceImpl.import_matrix_from_excel(self.ctx, params)[0]
        self.assertTrue('matrix_obj_ref' in returnVal)
        self.assertTrue('report_name' in returnVal)
        self.assertTrue('report_ref' in returnVal)

        obj = self.dfu.get_objects(
            {'object_refs': [returnVal['matrix_obj_ref']]}
        )['data'][0]['data']
        self.assertCountEqual(obj['search_attributes'],
                              ["Scientist | Marie Currie", "Instrument | Old Faithful"])
        self.assertEqual(obj['description'], 'test_desc')
        self.assertEqual(obj['scale'], 'log2')
        self.assertEqual(obj['col_normalization'], 'test_col_normalization')
        self.assertEqual(obj['row_normalization'], 'test_row_normalization')

    @unittest.skip("skipping for missing attribute mapping")
    def test_import_matrix_from_csv(self):
        self.start_test()

        obj_type = 'ExpressionMatrix'
        params = {'obj_type': obj_type,
                  'matrix_name': 'test_ExpressionMatrix2',
                  'workspace_name': self.wsName,
                  'input_file_path': os.path.join('data', 'generic_data.csv'),
                  'genome_ref': self.genome_ref,
                  'scale': 'log2',
                  'description': "an expression matrix",
                  }
        returnVal = self.serviceImpl.import_matrix_from_excel(self.ctx, params)[0]
        self.assertIn('matrix_obj_ref', returnVal)
        self.assertIn('report_name', returnVal)
        self.assertIn('report_ref', returnVal)
        obj = self.dfu.get_objects(
            {'object_refs': [returnVal['matrix_obj_ref']]}
        )['data'][0]['data']
        self.assertIn('genome_ref', obj)
        self.assertIn('description', obj)
        self.assertEqual(obj['description'], 'an expression matrix')

    def test_import_metabolite_matrix_from_excel(self):
        self.start_test()

        obj_type = 'MetaboliteMatrix'
        params = {'obj_type': obj_type,
                  'matrix_name': 'test_MetaboliteMatrix',
                  'workspace_name': self.wsName,
                  'input_file_path': os.path.join('data', 'metabolite.xlsx'),
                  'scale': 'log2',
                  'biochemistry_ref': 'kbase/default',
                  'description': "a biochem matrix",
                  "row_attributemapping_ref": "",
                  }
        returnVal = self.serviceImpl.import_matrix_from_excel(self.ctx, params)[0]
        self.assertIn('matrix_obj_ref', returnVal)
        self.assertIn('report_name', returnVal)
        self.assertIn('report_ref', returnVal)
        obj = self.dfu.get_objects(
            {'object_refs': [returnVal['matrix_obj_ref']]}
        )['data'][0]['data']
        self.assertIn('biochemistry_ref', obj)
        self.assertIn('description', obj)
        self.assertEqual(obj['description'], 'a biochem matrix')

    def test_bad_import_matrix_params(self):
        self.start_test()

        with self.assertRaisesRegex(ValueError, "parameter is required, but missing"):
            params = {'obj_type': 'ExpressionMatrix',
                      'matrix_name': 'test_ExpressionMatrix',
                      'workspace_name': self.wsName,
                      'input_file_path': os.path.join('data', 'test_import.xlsx'),
                      }
            returnVal = self.serviceImpl.import_matrix_from_excel(self.ctx, params)[0]

        with self.assertRaisesRegex(ValueError, "Unknown matrix object type"):
            params = {'obj_type': 'foo',
                      'matrix_name': 'test_ExpressionMatrix',
                      'workspace_name': self.wsName,
                      'input_file_path': os.path.join('data', 'test_import.xlsx'),
                      'scale': 'log2'
                      }
            returnVal = self.serviceImpl.import_matrix_from_excel(self.ctx, params)[0]

        with self.assertRaisesRegex(ValueError, "Unknown scale type"):
            params = {'obj_type': 'ExpressionMatrix',
                      'matrix_name': 'test_ExpressionMatrix',
                      'workspace_name': self.wsName,
                      'input_file_path': os.path.join('data', 'test_import.xlsx'),
                      'scale': 'foo'
                      }
            returnVal = self.serviceImpl.import_matrix_from_excel(self.ctx, params)[0]

        with self.assertRaisesRegex(ValueError, "input_shock_id or input_file_path"):
            params = {'obj_type': 'ExpressionMatrix',
                      'matrix_name': 'test_ExpressionMatrix',
                      'workspace_name': self.wsName,
                      'scale': 'log2'
                      }
            returnVal = self.serviceImpl.import_matrix_from_excel(self.ctx, params)[0]

        with self.assertRaisesRegex(ValueError, "Row IDs from the uploaded matrix do not match"):
            params = {'obj_type': 'MetaboliteMatrix',
                      'matrix_name': 'test_MetaboliteMatrix',
                      'workspace_name': self.wsName,
                      'input_file_path': os.path.join('data', 'generic_data.csv'),
                      'scale': 'log2',
                      'biochemistry_ref': 'kbase/default',
                      'description': "a biochem matrix",
                      'row_attributemapping_ref': self.attribute_mapping_ref
                      }
            returnVal = self.serviceImpl.import_matrix_from_excel(self.ctx, params)[0]
