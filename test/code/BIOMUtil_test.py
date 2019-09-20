# -*- coding: utf-8 -*-
import inspect
import json
import os
import time
import unittest
from configparser import ConfigParser
from os import environ
from mock import patch

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
        cls.wsName = "man4ish_gupta:narrative_1568644342277"
        cls.wsId = 44071
        #cls.wsName = "test_GenericsAPI_" + str(suffix)
        #cls.wsClient.create_workspace({'workspace': cls.wsName})
        cls.prepare_data()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'wsName'):
            #cls.wsClient.delete_workspace({'workspace': cls.wsName})
            print('Test workspace was deleted')

    @classmethod
    def prepare_data(cls):
        workspace_id = cls.dfu.ws_name_to_id(cls.wsName)
        object_type = 'KBaseExperiments.AttributeMapping'
        attribute_mapping_object_name = 'test_attribute_mapping'
        attribute_mapping_data = json.load(open('data/biom_am.json'))
        save_object_params = {
            'id': workspace_id,
            'objects': [{'type': object_type,
                         'data': attribute_mapping_data,
                         'name': attribute_mapping_object_name}]
        }

        dfu_oi = cls.dfu.save_objects(save_object_params)[0]
        cls.attribute_mapping_ref = str(dfu_oi[6]) + '/' + str(dfu_oi[0]) + '/' + str(dfu_oi[4])

    def getWsClient(self):
        return self.__class__.wsClient

    def getWsName(self):
        return self.__class__.wsName

    def getImpl(self):
        return self.__class__.serviceImpl

    def getContext(self):
        return self.__class__.ctx

    def start_test(self):
        testname = inspect.stack()[1][3]
        print('\n*** starting test: ' + testname + ' **')

    def mock_download_staging_file(params):
        print('Mocking DataFileUtilClient.download_staging_file')
        print(params)

        file_path = params.get('staging_file_subdir_path')

        return {'copy_file_path': file_path}

    @patch.object(DataFileUtil, "download_staging_file", side_effect=mock_download_staging_file)
    def test_import_matrix_from_biom_1_0_biom_tsv(self, download_staging_file):
        self.start_test()

        params = {'obj_type': 'AmpliconMatrix',
                  'matrix_name': 'test_AmpliconMatrix',
                  'workspace_name': self.wsName,
                  "biom_tsv": {
                        "biom_file_biom_tsv": os.path.join('data', 'phyloseq_test.biom'),
                        "tsv_file_biom_tsv": os.path.join('data', 'amplicon_test.tsv')
                        },
                  'scale': 'raw',
                  'description': "OTU data",
                  'amplicon_set_name': 'test_AmpliconSet'
                  }
        returnVal = self.getImpl().import_matrix_from_biom(self.ctx, params)[0]
        self.assertIn('matrix_obj_ref', returnVal)
        self.assertIn('amplicon_set_obj_ref', returnVal)
        self.assertIn('report_name', returnVal)
        self.assertIn('report_ref', returnVal)
        obj = self.dfu.get_objects(
            {'object_refs': [returnVal['matrix_obj_ref']]}
        )['data'][0]['data']
        self.assertIn('description', obj)
        self.assertEqual(obj['description'], 'OTU data')
        self.assertIn('attributes', obj)
        self.assertEqual(obj['attributes'], {'generated_by': 'QIIME revision XYZ'})
        self.assertIn('row_attributemapping_ref', obj)
        self.assertIn('col_attributemapping_ref', obj)

    @patch.object(DataFileUtil, "download_staging_file", side_effect=mock_download_staging_file)
    def test_import_matrix_from_biom_1_0_biom_fasta(self, download_staging_file):
        self.start_test()

        params = {'obj_type': 'AmpliconMatrix',
                  'matrix_name': 'test_AmpliconMatrix',
                  'workspace_name': self.wsName,
                  "biom_fasta": {
                        "biom_file_biom_fasta": os.path.join('data', 'phyloseq_test.biom'),
                        "fasta_file_biom_fasta": os.path.join('data', 'phyloseq_test.fa')
                        },
                  'scale': 'raw',
                  'description': "OTU data",
                  'amplicon_set_name': 'test_AmpliconSet'
                  }
        returnVal = self.getImpl().import_matrix_from_biom(self.ctx, params)[0]
        self.assertIn('matrix_obj_ref', returnVal)
        self.assertIn('amplicon_set_obj_ref', returnVal)
        self.assertIn('report_name', returnVal)
        self.assertIn('report_ref', returnVal)
        obj = self.dfu.get_objects(
            {'object_refs': [returnVal['matrix_obj_ref']]}
        )['data'][0]['data']
        self.assertIn('description', obj)
        self.assertEqual(obj['description'], 'OTU data')
        self.assertIn('attributes', obj)
        self.assertEqual(obj['attributes'], {'generated_by': 'QIIME revision XYZ'})
        self.assertIn('row_attributemapping_ref', obj)
        self.assertIn('col_attributemapping_ref', obj)

    @patch.object(DataFileUtil, "download_staging_file", side_effect=mock_download_staging_file)
    def test_import_matrix_from_biom_1_0_tsv_fasta(self, download_staging_file):
        self.start_test()

        params = {'obj_type': 'AmpliconMatrix',
                  'matrix_name': 'test_AmpliconMatrix',
                  'workspace_name': self.wsName,
                  "tsv_fasta": {
                        "tsv_file_tsv_fasta": os.path.join('data', 'amplicon_test.tsv'),
                        "fasta_file_tsv_fasta": os.path.join('data', 'phyloseq_test.fa'),
                        'metadata_keys_tsv_fasta': 'taxonomy_id, taxonomy, taxonomy_source, consensus_sequence',
                        },
                  'scale': 'raw',
                  'description': "OTU data",
                  'amplicon_set_name': 'test_AmpliconSet'
                  }
        returnVal = self.getImpl().import_matrix_from_biom(self.ctx, params)[0]
        self.assertIn('matrix_obj_ref', returnVal)
        self.assertIn('amplicon_set_obj_ref', returnVal)
        self.assertIn('report_name', returnVal)
        self.assertIn('report_ref', returnVal)
        obj = self.dfu.get_objects(
            {'object_refs': [returnVal['matrix_obj_ref']]}
        )['data'][0]['data']
        self.assertIn('description', obj)
        self.assertEqual(obj['description'], 'OTU data')
        self.assertIn('row_attributemapping_ref', obj)
        self.assertNotIn('col_attributemapping_ref', obj)

    @patch.object(DataFileUtil, "download_staging_file", side_effect=mock_download_staging_file)
    def test_import_matrix_from_biom_1_0_tsv(self, download_staging_file):
        self.start_test()

        params = {'obj_type': 'AmpliconMatrix',
                  'matrix_name': 'test_AmpliconMatrix',
                  'workspace_name': self.wsName,
                  "tsv": {
                        "tsv_file_tsv": os.path.join('data', 'amplicon_test.tsv'),
                        'metadata_keys_tsv': 'taxonomy_id, taxonomy, taxonomy_source, consensus_sequence'
                        },
                  'scale': 'raw',
                  'description': "OTU data",
                  'amplicon_set_name': 'test_AmpliconSet'
                  }
        returnVal = self.getImpl().import_matrix_from_biom(self.ctx, params)[0]
        self.assertIn('matrix_obj_ref', returnVal)
        self.assertIn('amplicon_set_obj_ref', returnVal)
        self.assertIn('report_name', returnVal)
        self.assertIn('report_ref', returnVal)
        obj = self.dfu.get_objects(
            {'object_refs': [returnVal['matrix_obj_ref']]}
        )['data'][0]['data']
        self.assertIn('description', obj)
        self.assertEqual(obj['description'], 'OTU data')
        self.assertIn('row_attributemapping_ref', obj)
        self.assertNotIn('col_attributemapping_ref', obj)

    # @patch.object(DataFileUtil, "download_staging_file", side_effect=mock_download_staging_file)
    # def test_import_matrix_from_biom_2_1(self, download_staging_file):
    #     self.start_test()

    #     params = {'obj_type': 'AmpliconMatrix',
    #               'matrix_name': 'test_AmpliconMatrix',
    #               'workspace_name': self.wsName,
    #               "biom_fasta": {
    #                     "biom_file_biom_fasta": os.path.join('data', 'v2.1example.biom'),
    #                     "fasta_file_biom_fasta": os.path.join('data', 'phyloseq_test.fa')
    #                     },
    #               'scale': 'raw',
    #               'description': "OTU data",
    #               'amplicon_set_name': 'test_AmpliconSet'
    #               }
    #     returnVal = self.getImpl().import_matrix_from_biom(self.ctx, params)[0]
    #     self.assertIn('matrix_obj_ref', returnVal)
    #     self.assertIn('report_name', returnVal)
    #     self.assertIn('report_ref', returnVal)
    #     obj = self.dfu.get_objects(
    #         {'object_refs': [returnVal['matrix_obj_ref']]}
    #     )['data'][0]['data']
    #     self.assertIn('description', obj)
    #     self.assertEqual(obj['description'], 'OTU data')
    #     self.assertIn('attributes', obj)
    #     self.assertEqual(obj['attributes'], {'generated_by': 'QIIME 1.9.1',
    #                                          'create_date': '2017-05-22T11:07:28.478444',
    #                                          })
    #     self.assertIn('row_attributemapping_ref', obj)

    @patch.object(DataFileUtil, "download_staging_file", side_effect=mock_download_staging_file)
    def test_import_with_external_am(self, download_staging_file):
        self.start_test()

        params = {'obj_type': 'AmpliconMatrix',
                  'matrix_name': 'test_AmpliconMatrix',
                  'workspace_name': self.wsName,
                  "biom_fasta": {
                        "biom_file_biom_fasta": os.path.join('data', 'phyloseq_test.biom'),
                        "fasta_file_biom_fasta": os.path.join('data', 'phyloseq_test.fa')
                        },
                  'scale': 'raw',
                  'description': "OTU data",
                  'amplicon_set_name': 'test_AmpliconSet',
                  'col_attributemapping_ref': self.attribute_mapping_ref
                  }

        returnVal = self.getImpl().import_matrix_from_biom(self.ctx, params)[0]
        self.assertIn('matrix_obj_ref', returnVal)
        self.assertIn('report_name', returnVal)
        self.assertIn('report_ref', returnVal)
        obj = self.dfu.get_objects(
            {'object_refs': [returnVal['matrix_obj_ref']]}
        )['data'][0]['data']
        self.assertIn('description', obj)
        self.assertEqual(obj['description'], 'OTU data')
        self.assertIn('attributes', obj)
        self.assertEqual(obj['attributes'], {'generated_by': 'QIIME revision XYZ'})
        self.assertIn('row_attributemapping_ref', obj)
        self.assertIn('col_attributemapping_ref', obj)
        self.assertEqual(obj['col_attributemapping_ref'], self.attribute_mapping_ref)

    @patch.object(DataFileUtil, "download_staging_file", side_effect=mock_download_staging_file)
    def test_bad_import_matrix_params(self, download_staging_file):
        self.start_test()

        with self.assertRaisesRegex(ValueError, "parameter is required, but missing"):
            params = {'obj_type': 'AmpliconMatrix',
                      'matrix_name': 'test_AmpliconMatrix',
                      'workspace_name': self.wsName,
                      "biom_fasta": {
                            "biom_file_biom_fasta": os.path.join('data', 'phyloseq_test.biom'),
                            "fasta_file_biom_fasta": os.path.join('data', 'phyloseq_test.fa')
                            }
                      }
            returnVal = self.getImpl().import_matrix_from_biom(self.ctx, params)[0]

        with self.assertRaisesRegex(ValueError, "Unknown matrix object type"):
            params = {'obj_type': 'foo',
                      'matrix_name': 'test_AmpliconMatrix',
                      'amplicon_set_name': 'test_AmpliconSet',
                      'workspace_name': self.wsName,
                      "biom_fasta": {
                            "biom_file_biom_fasta": os.path.join('data', 'phyloseq_test.biom'),
                            "fasta_file_biom_fasta": os.path.join('data', 'phyloseq_test.fa')
                            },
                      'scale': 'log2'
                      }
            returnVal = self.getImpl().import_matrix_from_biom(self.ctx, params)[0]

        with self.assertRaisesRegex(ValueError, "Unknown scale type"):
            params = {'obj_type': 'AmpliconMatrix',
                      'matrix_name': 'test_AmpliconMatrix',
                      'amplicon_set_name': 'test_AmpliconSet',
                      'workspace_name': self.wsName,
                      "biom_fasta": {
                            "biom_file_biom_fasta": os.path.join('data', 'phyloseq_test.biom'),
                            "fasta_file_biom_fasta": os.path.join('data', 'phyloseq_test.fa')
                            },
                      'scale': 'foo'
                      }
            returnVal = self.getImpl().import_matrix_from_biom(self.ctx, params)[0]

        with self.assertRaisesRegex(ValueError, "IDs from the uploaded matrix do not match"):
            params = {'obj_type': 'AmpliconMatrix',
                      'matrix_name': 'test_AmpliconMatrix',
                      'workspace_name': self.wsName,
                      "biom_fasta": {
                            "biom_file_biom_fasta": os.path.join('data', 'phyloseq_test.biom'),
                            "fasta_file_biom_fasta": os.path.join('data', 'phyloseq_test.fa')
                            },
                      'scale': 'raw',
                      'description': "OTU data",
                      'amplicon_set_name': 'test_AmpliconSet',
                      'row_attributemapping_ref': self.attribute_mapping_ref
                      }
            returnVal = self.getImpl().import_matrix_from_biom(self.ctx, params)[0]
