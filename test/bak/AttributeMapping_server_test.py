# -*- coding: utf-8 -*-
import json
import os
import shutil
import time
import unittest
import uuid
from configparser import ConfigParser
from mock import patch

import pandas as pd

from GenericsAPI.Utils.AttributeUtils import AttributesUtil
from installed_clients.DataFileUtilClient import DataFileUtil
from GenericsAPI.GenericsAPIImpl import GenericsAPI
from GenericsAPI.GenericsAPIServer import MethodContext
from GenericsAPI.authclient import KBaseAuth as _KBaseAuth
from installed_clients.WorkspaceClient import Workspace as workspaceService

class AttributeUtilsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.maxDiff = 70000
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
        cls.serviceUtils = AttributesUtil(cls.cfg)
        cls.scratch = cls.cfg['scratch']
        cls.callback_url = os.environ['SDK_CALLBACK_URL']
        cls.dfu = DataFileUtil(cls.callback_url)

        suffix = int(time.time() * 1000)
        cls.wsName = "test_CompoundSetUtils_" + str(suffix)
        ret = cls.wsClient.create_workspace({'workspace': cls.wsName})
        cls.wsId = ret[0]
        cls.attribute_mapping = json.load(open('data/AM1.json'))
        info = cls.dfu.save_objects({
            "id": cls.wsId,
            "objects": [{
                "type": "KBaseExperiments.AttributeMapping",
                "data": cls.attribute_mapping,
                "name": "test_cond_set"
            }]
        })[0]
        cls.attribute_mapping_ref = "%s/%s/%s" % (info[6], info[0], info[4])
        cls.attribute_mapping_2 = json.load(open('data/AM2.json'))

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'wsName'):
            cls.wsClient.delete_workspace({'workspace': cls.wsName})
            print('Test workspace was deleted')

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

    def loadClusterSet(self):

        if hasattr(self.__class__, 'cluster_set_ref'):
            return self.__class__.cluster_set_ref

        expr_matrix_ref = self.loadExpressionMatrix()

        # using DFU, missing ClusterSet uploader
        object_type = 'KBaseExperiments.ClusterSet'
        cluster_set_object_name = 'test_clusterset'
        cluster_set_data = {'clustering_parameters': {'dist_metric': 'cityblock',
                                                      'k_num': '2'},
                            'clusters': [{'id_to_data_position': {
                                            'WRI_RS00015_CDS_1': 1,
                                            'WRI_RS00025_CDS_1': 2}},
                                         {'id_to_data_position': {
                                            'WRI_RS00010_CDS_1': 0}}],
                            'original_data': expr_matrix_ref}

        save_object_params = {
            'id': self.wsId,
            'objects': [{'type': object_type,
                         'data': cluster_set_data,
                         'name': cluster_set_object_name}]
        }

        dfu_oi = self.dfu.save_objects(save_object_params)[0]
        cluster_set_ref = str(dfu_oi[6]) + '/' + str(dfu_oi[0]) + '/' + str(dfu_oi[4])

        self.__class__.cluster_set_ref = cluster_set_ref
        print('Loaded ClusterSet: ' + cluster_set_ref)
        return cluster_set_ref

    def loadConditionClusterSet(self):

        if hasattr(self.__class__, 'condition_cluster_set_ref'):
            return self.__class__.condition_cluster_set_ref

        expr_matrix_ref = self.loadExpressionMatrix()

        # using DFU, missing ClusterSet uploader
        object_type = 'KBaseExperiments.ClusterSet'
        cluster_set_object_name = 'test_clusterset'
        cluster_set_data = {'clustering_parameters': {'dist_metric': 'cityblock',
                                                      'k_num': '2'},
                            'clusters': [{'id_to_data_position': {
                                            'instance_2': 1,
                                            'instance_3': 2}},
                                         {'id_to_data_position': {
                                            'instance_1': 0,
                                            'instance_4': 3}}],
                            'original_data': expr_matrix_ref}

        save_object_params = {
            'id': self.wsId,
            'objects': [{'type': object_type,
                         'data': cluster_set_data,
                         'name': cluster_set_object_name}]
        }

        dfu_oi = self.dfu.save_objects(save_object_params)[0]
        condition_cluster_set_ref = str(dfu_oi[6]) + '/' + str(dfu_oi[0]) + '/' + str(dfu_oi[4])

        self.__class__.condition_cluster_set_ref = condition_cluster_set_ref
        print('Loaded Condition ClusterSet: ' + condition_cluster_set_ref)
        return condition_cluster_set_ref

    def getWsClient(self):
        return self.__class__.wsClient

    def getWsId(self):
        return self.__class__.wsId

    def getImpl(self):
        return self.__class__.serviceImpl

    def getContext(self):
        return self.__class__.ctx

    def mock_download_staging_file(params):
        print('Mocking DataFileUtilClient.download_staging_file')

        filename = params.get('staging_file_subdir_path')

        return {'copy_file_path': os.path.join("data", filename)}
    
    # @unittest.skip("Only passes on CI")
    def test_add_ontology_info(self):
        factor = {'attribute': 'stalk development', "attribute_ont_id": "GO:0031150",
                "unit": "Hour", "unit_ont_id": "UO:0000032"}
        with_ref = self.serviceUtils._add_ontology_info(factor)
        self.assertEqual(with_ref.get('attribute_ont_ref'), '6308/3/2')
        self.assertEqual(with_ref.get('attribute_ont_id'), 'GO:0031150')
        self.assertEqual(with_ref.get('unit_ont_id'), 'UO:0000032')
        self.assertEqual(with_ref.get('unit_ont_ref'), '6308/15/6')
    
    def test_missing_params(self):
        with self.assertRaisesRegex(ValueError, "Required keys"):
            self.getImpl().file_to_attribute_mapping(self.getContext(), {})
        with self.assertRaisesRegex(ValueError, "Required keys"):
            self.getImpl().attribute_mapping_to_tsv_file(self.getContext(), {})
        with self.assertRaisesRegex(ValueError, "Required keys"):
            self.getImpl().export_attribute_mapping_tsv(self.getContext(), {})
        with self.assertRaisesRegex(ValueError, "Required keys"):
            self.getImpl().export_attribute_mapping_excel(self.getContext(), {})
        with self.assertRaisesRegex(ValueError, "Required keys"):
            self.getImpl().export_cluster_set_excel(self.getContext(), {})
    
    def test_tsv_import(self):
        params = {'output_ws_id': self.wsId,
                  'input_file_path': 'data/AM2.tsv',
                  'output_obj_name': 'AM2'}
        ret = self.getImpl().file_to_attribute_mapping(self.getContext(), params)[0]
        assert ret and ('attribute_mapping_ref' in ret)
        data = self.dfu.get_objects({
            'object_refs': [ret['attribute_mapping_ref']]
        })['data'][0]['data']
        self.assertEqual(data, self.attribute_mapping_2)
    
    #@unittest.skip("only works on CI")
    def test_isa_import_1(self):
        self.maxDiff = None
        params = {'output_ws_id': self.wsId,
                  'input_file_path': 'data/test_ISA.tsv',
                  'output_obj_name': 'ISA_AM'}
        ret = self.getImpl().file_to_attribute_mapping(self.getContext(), params)[0]
        assert ret and ('attribute_mapping_ref' in ret)
        data = self.dfu.get_objects({
            'object_refs': [ret['attribute_mapping_ref']]
        })['data'][0]['data']
        self.assertEqual(len(data['instances']), 18)
        self.assertEqual(len(list(data['instances'].values())[0]), 18)
        self.assertEqual(len(data['attributes']), 18)
        self.assertEqual(data['attributes'][-1],
                         {'attribute': 'Factor Value[time]',
                          'source': 'upload',
                          'attribute_ont_id': 'PATO:0000165',
                          'attribute_ont_ref': '6308/11/2',
                          'unit': 'day',
                          'unit_ont_id': 'UO:0000033',
                          'unit_ont_ref': '6308/15/6'})
        self.assertEqual(data['attributes'][-2],
                         {'attribute': 'Factor Value[compound]',
                          'source': 'upload',
                          'categories': {'orotic acid': {'attribute_ont_id': 'CHEBI:16742',
                                                         'attribute_ont_ref': '6308/19/1',
                                                         'value': 'orotic acid'},
                                         'vehicle': {'value': 'vehicle'}}})
    
    def test_isa_import_2(self):
        params = {'output_ws_id': self.wsId,
                  'input_file_path': 'data/test_ISA_2.tsv',
                  'output_obj_name': 'ISA_AM'}
        ret = self.getImpl().file_to_attribute_mapping(self.getContext(), params)[0]
        assert ret and ('attribute_mapping_ref' in ret)
        data = self.dfu.get_objects({
            'object_refs': [ret['attribute_mapping_ref']]
        })['data'][0]['data']
        self.assertEqual(len(data['instances']), 6)
        self.assertEqual(len(list(data['instances'].values())[0]), 12)
        self.assertEqual(len(data['attributes']), 12)
        self.assertEqual(data['attributes'][4],
                         {'attribute': 'Material Type',
                          'source': 'upload',
                          'categories': {
                              'deoxyribonucleic acid': {'attribute_ont_id': 'CHEBI:16991',
                                                        'attribute_ont_ref': '6308/19/1',
                                                        'value': 'deoxyribonucleic acid'}}})
    
    def test_excel_import(self):
        shock_file = '/AM1.xlsx'
        shutil.copy('/kb/module/test/data/' + shock_file, self.scratch + shock_file)
        shock_id = self.dfu.file_to_shock({'file_path': self.scratch + shock_file})['shock_id']
        params = {'output_ws_id': self.getWsId(),
                  'input_shock_id': shock_id,
                  'output_obj_name': 'AM1'}
        ret = self.getImpl().file_to_attribute_mapping(self.getContext(), params)[0]
        assert ret and ('attribute_mapping_ref' in ret)
        data = self.dfu.get_objects({
            'object_refs': [ret['attribute_mapping_ref']]
        })['data'][0]['data']

        self.assertEqual(data['instances'], self.attribute_mapping['instances'])
        for load_attr, expect_attr in zip(data['attributes'], self.attribute_mapping['attributes']):
            for key in ('attribute', 'attribute_ont_id', 'unit', 'unit_ont_id'):
                self.assertEqual(load_attr.get(key), expect_attr.get(key))
                

    def test_attribute_validation_1(self):
        file_path = 'data/AM_bad_attributes.tsv'
        params = {'output_ws_id': self.getWsId(),
                  'input_file_path': file_path,
                  'output_obj_name': 'BAD_AM'}
        with self.assertRaisesRegex(ValueError, "attributes failed validation: mass, inchikey"):
            ret = self.getImpl().file_to_attribute_mapping(self.getContext(), params)[0]

    def test_attribute_validation_isa(self):
        file_path = 'data/test_ISA_bad_attributes.tsv'
        params = {'output_ws_id': self.getWsId(),
                  'input_file_path': file_path,
                  'output_obj_name': 'BAD_AM'}
        with self.assertRaisesRegex(ValueError, "attributes failed validation: mass, inchikey"):
            ret = self.getImpl().file_to_attribute_mapping(self.getContext(), params)[0]

    def test_excel_infer_column(self):
        shock_file = '/gene_attributes.xlsx'
        shutil.copy('/kb/module/test/data/' + shock_file, self.scratch + shock_file)
        shock_id = self.dfu.file_to_shock({'file_path': self.scratch + shock_file})['shock_id']
        params = {'output_ws_id': self.getWsId(),
                  'input_shock_id': shock_id,
                  'output_obj_name': 'AM1'}
        ret = self.getImpl().file_to_attribute_mapping(self.getContext(), params)[0]
        assert ret and ('attribute_mapping_ref' in ret)
        data = self.dfu.get_objects({
            'object_refs': [ret['attribute_mapping_ref']]
        })['data'][0]['data']

        self.assertEqual(len(data['attributes']), 2)
        self.assertEqual(len(data['instances']), 13980)
        self.assertIn('AT1G01070', data['instances'])

    @patch.object(DataFileUtil, "download_staging_file", side_effect=mock_download_staging_file)
    def test_append_file_to_attribute_mapping(self, download_staging_file):

        with self.assertRaises(ValueError) as context:
            self.serviceUtils.append_file_to_attribute_mapping('AM2.tsv',
                                                               self.attribute_mapping_ref,
                                                               self.getWsId())
            self.assertIn('Appended attribute mapping misses', str(context.exception.args))

        with self.assertRaises(ValueError) as context:
            self.serviceUtils.append_file_to_attribute_mapping('AM1.tsv',
                                                               self.attribute_mapping_ref,
                                                               self.getWsId())
            self.assertIn('Duplicate attribute mappings', str(context.exception.args))

        new_am_name = 'append_file_am'
        ret = self.serviceUtils.append_file_to_attribute_mapping('AM1_append.tsv',
                                                                 self.attribute_mapping_ref,
                                                                 self.getWsId(),
                                                                 new_am_name)

        assert ret and ('attribute_mapping_ref' in ret)

        am_obj = self.dfu.get_objects({'object_refs': [ret['attribute_mapping_ref']]})['data'][0]

        self.assertEqual(am_obj['info'][1], new_am_name)

        new_attributes = am_obj['data']['attributes']
        self.assertEqual(len(new_attributes), 4)
        expected_attrs = ['Time series design', 'Treatment with Sirolimus',
                          'append Time series design', 'append Treatment with Sirolimus']
        self.assertCountEqual([x.get('attribute') for x in new_attributes], expected_attrs)

    def test_make_tsv(self):
        params = {'input_ref': self.attribute_mapping_ref, 'destination_dir': self.scratch}
        ret = self.getImpl().attribute_mapping_to_tsv_file(self.getContext(), params)[0]
        assert ret and ('file_path' in ret)

    def test_export_attribute_mapping_tsv(self):
        params = {'input_ref': self.attribute_mapping_ref}
        ret = self.getImpl().export_attribute_mapping_tsv(self.getContext(), params)[0]
        assert ret and ('shock_id' in ret)

    def test_export_attribute_mapping_excel(self):
        params = {'input_ref': self.attribute_mapping_ref}
        ret = self.getImpl().export_attribute_mapping_excel(self.getContext(), params)[0]
        assert ret and ('shock_id' in ret)

    def test_export_cluster_set_excel(self):
        self.loadClusterSet()

        params = {'input_ref': self.cluster_set_ref}
        ret = self.getImpl().export_attribute_mapping_excel(self.getContext(), params)[0]
        assert ret and ('shock_id' in ret)

        output_directory = os.path.join(self.scratch, str(uuid.uuid4()))
        os.makedirs(output_directory)

        self.dfu.shock_to_file({'shock_id': ret['shock_id'],
                                'file_path': output_directory,
                                'unpack': 'unpack'})

        xl_files = [file for file in os.listdir(output_directory) if file.endswith('.xlsx')]
        self.assertEqual(len(xl_files), 1)

        xl = pd.ExcelFile(os.path.join(output_directory, xl_files[0]))
        expected_sheet_names = ['ClusterSet']
        self.assertCountEqual(xl.sheet_names, expected_sheet_names)

        df = xl.parse("ClusterSet")
        expected_index = ['WRI_RS00010_CDS_1', 'WRI_RS00015_CDS_1', 'WRI_RS00025_CDS_1']
        expected_col = ['instance_1', 'instance_2', 'instance_3', 'instance_4', 'cluster']
        self.assertCountEqual(df.index.tolist(), expected_index)
        self.assertCountEqual(df.columns.tolist(), expected_col)

    def test_export_condition_cluster_set_excel(self):
        self.loadConditionClusterSet()

        params = {'input_ref': self.condition_cluster_set_ref}
        ret = self.getImpl().export_attribute_mapping_excel(self.getContext(), params)[0]
        assert ret and ('shock_id' in ret)

        output_directory = os.path.join(self.scratch, str(uuid.uuid4()))
        os.makedirs(output_directory)

        self.dfu.shock_to_file({'shock_id': ret['shock_id'],
                                'file_path': output_directory,
                                'unpack': 'unpack'})

        xl_files = [file for file in os.listdir(output_directory) if file.endswith('.xlsx')]
        self.assertEqual(len(xl_files), 1)

        xl = pd.ExcelFile(os.path.join(output_directory, xl_files[0]))
        expected_sheet_names = ['ClusterSet']
        self.assertCountEqual(xl.sheet_names, expected_sheet_names)

        df = xl.parse("ClusterSet")
        expected_index = ['instance_1', 'instance_2', 'instance_3', 'instance_4']
        expected_col = ['WRI_RS00010_CDS_1', 'WRI_RS00015_CDS_1', 'WRI_RS00025_CDS_1', 'cluster']
        self.assertCountEqual(df.index.tolist(), expected_index)
        self.assertCountEqual(df.columns.tolist(), expected_col)
    
