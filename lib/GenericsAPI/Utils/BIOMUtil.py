import errno
import logging
import os
import uuid

import biom
import pandas as pd
from Bio import SeqIO
import csv

from installed_clients.DataFileUtilClient import DataFileUtil
from GenericsAPI.Utils.AttributeUtils import AttributesUtil
from GenericsAPI.Utils.DataUtil import DataUtil
from GenericsAPI.Utils.MatrixUtil import MatrixUtil
from installed_clients.KBaseReportClient import KBaseReport
from installed_clients.KBaseSearchEngineClient import KBaseSearchEngine

TYPE_ATTRIBUTES = {'description', 'scale', 'row_normalization', 'col_normalization'}
SCALE_TYPES = {'raw', 'ln', 'log2', 'log10'}
DEFAULT_META_KEYS = ["taxonomy_id", "lineage", "score", "taxonomy_source", "species_name",
                     "consensus_sequence"]


class BiomUtil:

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

    def _process_params(self, params):
        logging.info('start validating import_matrix_from_biom params')

        # check for required parameters
        for p in ['obj_type', 'matrix_name', 'workspace_name', 'scale', 'amplicon_set_name']:
            if p not in params:
                raise ValueError('"{}" parameter is required, but missing'.format(p))

        obj_type = params.get('obj_type')
        if obj_type not in self.matrix_types:
            raise ValueError('Unknown matrix object type: {}'.format(obj_type))

        scale = params.get('scale')
        if scale not in SCALE_TYPES:
            raise ValueError('Unknown scale type: {}'.format(scale))

        biom_file = None
        tsv_file = None
        fasta_file = None
        metadata_keys = DEFAULT_META_KEYS

        if params.get('biom_tsv'):
            biom_tsv = params.get('biom_tsv')
            biom_file = biom_tsv.get('biom_file_biom_tsv')
            tsv_file = biom_tsv.get('tsv_file_biom_tsv')

            if not (biom_file and tsv_file):
                raise ValueError('missing BIOM or TSV file')

            biom_file = self.dfu.download_staging_file(
                                {'staging_file_subdir_path': biom_file}).get('copy_file_path')

            tsv_file = self.dfu.download_staging_file(
                                {'staging_file_subdir_path': tsv_file}).get('copy_file_path')
            mode = 'biom_tsv'
        elif params.get('biom_fasta'):
            biom_fasta = params.get('biom_fasta')
            biom_file = biom_fasta.get('biom_file_biom_fasta')
            fasta_file = biom_fasta.get('fasta_file_biom_fasta')

            if not (biom_file and fasta_file):
                raise ValueError('missing BIOM or FASTA file')

            biom_file = self.dfu.download_staging_file(
                                {'staging_file_subdir_path': biom_file}).get('copy_file_path')

            fasta_file = self.dfu.download_staging_file(
                                {'staging_file_subdir_path': fasta_file}).get('copy_file_path')
            mode = 'biom_fasta'
        elif params.get('tsv_fasta'):
            tsv_fasta = params.get('tsv_fasta')
            tsv_file = tsv_fasta.get('tsv_file_tsv_fasta')
            fasta_file = tsv_fasta.get('fasta_file_tsv_fasta')

            if not (tsv_file and fasta_file):
                raise ValueError('missing TSV or FASTA file')

            tsv_file = self.dfu.download_staging_file(
                                {'staging_file_subdir_path': tsv_file}).get('copy_file_path')

            fasta_file = self.dfu.download_staging_file(
                                {'staging_file_subdir_path': fasta_file}).get('copy_file_path')

            metadata_keys_str = tsv_fasta.get('metadata_keys_tsv_fasta')
            if metadata_keys_str:
                metadata_keys += [x.strip() for x in metadata_keys_str.split(',')]
            mode = 'tsv_fasta'
        elif params.get('tsv'):
            tsv = params.get('tsv')
            tsv_file = tsv.get('tsv_file_tsv')

            if not tsv_file:
                raise ValueError('missing TSV file')

            tsv_file = self.dfu.download_staging_file(
                                {'staging_file_subdir_path': tsv_file}).get('copy_file_path')

            metadata_keys_str = tsv.get('metadata_keys_tsv')
            if metadata_keys_str:
                metadata_keys += [x.strip() for x in metadata_keys_str.split(',')]

            mode = 'tsv'
        else:
            raise ValueError('missing valide file group type in parameters')

        return (biom_file, tsv_file, fasta_file, mode, list(set(metadata_keys)))

    def _retrieve_value(self, biom_metadata_dict, tsv_metadata_df, key, required=False):

        if key in biom_metadata_dict:
            return biom_metadata_dict.get(key)
        elif key in tsv_metadata_df:
            return tsv_metadata_df.get(key)
        elif required:
            raise ValueError('missing necessary [{}] from file'.format(key))
        else:
            return None

    def _search_taxon(self, scientific_name):
        """
        logic borrowed from: GFU.GenomeInterface
        https://github.com/kbaseapps/GenomeFileUtil/blob/master/lib/GenomeFileUtil/core/GenomeInterface.py#L216
        """
        taxonomy_ref = None

        search_params = {
            "object_types": ["taxon"],
            "match_filter": {
                "lookup_in_keys": {
                    "scientific_name": {"value": scientific_name}},
                "exclude_subobjects": 1
            },
            "access_filter": {
                "with_private": 0,
                "with_public": 1
            },
            "sorting_rules": [{
                "is_object_property": 0,
                "property": "timestamp",
                "ascending": 0
            }]
        }

        objects = self.kbse.search_objects(search_params)['objects']

        if objects:
            taxonomy_ref = '{}/{}'.format(self.taxon_wsname, objects[0].get('object_name'))
        else:
            search_params['match_filter']['lookup_in_keys'] = {
                "aliases": {"value": scientific_name}
            }
            objects = self.kbse.search_objects(search_params)['objects']
            if objects:
                taxonomy_ref = '{}/{}'.format(self.taxon_wsname, objects[0].get('object_name'))

        return taxonomy_ref

    def _fetch_taxonomy_ref(self, lineage):

        logging.info('start retrieving taxonomy ref from taxonomy service')

        taxonomy_ref = None
        scientific_name = None

        for item in lineage[::-1]:
            scientific_name = item.split('__')[-1]
            if scientific_name:
                taxonomy_ref = self._search_taxon(scientific_name)
                if taxonomy_ref:
                    return taxonomy_ref, scientific_name

        return taxonomy_ref, scientific_name

    def _retrieve_tsv_amplicon_set_data(self, tsv_file):
        amplicons = dict()

        try:
            logging.info('start parsing TSV file')
            reader = pd.read_csv(tsv_file, sep=None, iterator=True)
            inferred_sep = reader._engine.data.dialect.delimiter
            df = pd.read_csv(tsv_file, sep=inferred_sep, index_col=0)
        except Exception:
            raise ValueError('Cannot parse file. Please provide valide TSV file')

        if 'consensus_sequence' not in df.columns.tolist():
            raise ValueError('TSV file does not include consensus_sequence')

        logging.info('start processing each row in TSV')
        for observation_id in df.index:
            amplicon = dict()
            taxonomy = dict()

            # retrieve 'lineage'/'taxonomy' info
            lineage = self._retrieve_value([], df.loc[observation_id],
                                           'taxonomy')

            if isinstance(lineage, str):
                delimiter = csv.Sniffer().sniff(lineage).delimiter
                lineage = [x.strip() for x in lineage.split(delimiter)]
            if lineage:
                taxonomy.update({'lineage': lineage})
                # retrieve 'taxonomy_ref' info
                taxonomy_ref, scientific_name = self._fetch_taxonomy_ref(lineage)
                if taxonomy_ref:
                    taxonomy.update({'taxonomy_ref': taxonomy_ref})
                    taxonomy.update({'scientific_name': scientific_name})

            # retrieve 'taxonomy_id' info
            taxonomy_id = self._retrieve_value([], df.loc[observation_id],
                                               'taxonomy_id')
            if taxonomy_id:
                taxonomy.update({'taxonomy_id': taxonomy_id})

            # retrieve 'score' info
            score = self._retrieve_value([], df.loc[observation_id],
                                         'taxonomy_id')
            if score:
                taxonomy.update({'score': score})

            # retrieve 'taxonomy_source' info
            taxonomy_source = self._retrieve_value([], df.loc[observation_id],
                                                   'taxonomy_source')
            if taxonomy_source:
                taxonomy.update({'taxonomy_source': taxonomy_source})

            # retrieve 'species_name' info
            species_name = self._retrieve_value([], df.loc[observation_id],
                                                'species_name')
            if species_name:
                taxonomy.update({'species_name': species_name})

            amplicon.update({'consensus_sequence': df.loc[observation_id,
                                                          'consensus_sequence']})

            amplicon.update({'taxonomy': taxonomy})

            amplicons.update({observation_id: amplicon})

        logging.info('finished parsing TSV file')

        return amplicons

    def _retrieve_tsv_fasta_amplicon_set_data(self, tsv_file, fasta_file):
        amplicons = dict()
        try:
            logging.info('start parsing FASTA file')
            fastq_dict = SeqIO.index(fasta_file, "fasta")
        except Exception:
            raise ValueError('Cannot parse file. Please provide valide FASTA file')

        try:
            logging.info('start parsing TSV file')
            reader = pd.read_csv(tsv_file, sep=None, iterator=True)
            inferred_sep = reader._engine.data.dialect.delimiter
            df = pd.read_csv(tsv_file, sep=inferred_sep, index_col=0)
        except Exception:
            raise ValueError('Cannot parse file. Please provide valide TSV file')

        logging.info('start processing files')
        for observation_id in df.index:
            if observation_id not in fastq_dict:
                raise ValueError('FASTA file does not have [{}] OTU id'.format(observation_id))
            amplicon = dict()
            taxonomy = dict()

            # retrieve 'lineage'/'taxonomy' info
            lineage = self._retrieve_value([], df.loc[observation_id],
                                           'taxonomy')
            if isinstance(lineage, str):
                delimiter = csv.Sniffer().sniff(lineage).delimiter
                lineage = [x.strip() for x in lineage.split(delimiter)]
            if lineage:
                taxonomy.update({'lineage': lineage})
                # retrieve 'taxonomy_ref' info
                taxonomy_ref, scientific_name = self._fetch_taxonomy_ref(lineage)
                if taxonomy_ref:
                    taxonomy.update({'taxonomy_ref': taxonomy_ref})
                    taxonomy.update({'scientific_name': scientific_name})

            # retrieve 'taxonomy_id' info
            taxonomy_id = self._retrieve_value([], df.loc[observation_id],
                                               'taxonomy_id')
            if taxonomy_id:
                taxonomy.update({'taxonomy_id': taxonomy_id})

            # retrieve 'score' info
            score = self._retrieve_value([], df.loc[observation_id],
                                         'taxonomy_id')
            if score:
                taxonomy.update({'score': score})

            # retrieve 'taxonomy_source' info
            taxonomy_source = self._retrieve_value([], df.loc[observation_id],
                                                   'taxonomy_source')
            if taxonomy_source:
                taxonomy.update({'taxonomy_source': taxonomy_source})

            # retrieve 'species_name' info
            species_name = self._retrieve_value([], df.loc[observation_id],
                                                'species_name')
            if species_name:
                taxonomy.update({'species_name': species_name})

            amplicon.update({'consensus_sequence': str(fastq_dict.get(observation_id).seq)})

            amplicon.update({'taxonomy': taxonomy})

            amplicons.update({observation_id: amplicon})

        logging.info('finished processing files')
        return amplicons

    def _retrieve_biom_fasta_amplicon_set_data(self, biom_file, fasta_file):
        amplicons = dict()
        try:
            logging.info('start parsing FASTA file')
            fastq_dict = SeqIO.index(fasta_file, "fasta")
        except Exception:
            raise ValueError('Cannot parse file. Please provide valide FASTA file')

        logging.info('start parsing BIOM file')
        table = biom.load_table(biom_file)

        observation_ids = table._observation_ids.tolist()
        observation_metadata = table._observation_metadata

        logging.info('start processing files')
        for index, observation_id in enumerate(observation_ids):
            if observation_id not in fastq_dict:
                raise ValueError('FASTA file does not have [{}] OTU id'.format(observation_id))
            amplicon = dict()
            taxonomy = dict()

            # retrieve 'lineage'/'taxonomy' info
            lineage = self._retrieve_value(observation_metadata[index], [],
                                           'taxonomy')

            if isinstance(lineage, str):
                delimiter = csv.Sniffer().sniff(lineage).delimiter
                lineage = [x.strip() for x in lineage.split(delimiter)]
            if lineage:
                taxonomy.update({'lineage': lineage})
                # retrieve 'taxonomy_ref' info
                taxonomy_ref, scientific_name = self._fetch_taxonomy_ref(lineage)
                if taxonomy_ref:
                    taxonomy.update({'taxonomy_ref': taxonomy_ref})
                    taxonomy.update({'scientific_name': scientific_name})

            # retrieve 'taxonomy_id' info
            taxonomy_id = self._retrieve_value(observation_metadata[index], [],
                                               'taxonomy_id')
            if taxonomy_id:
                taxonomy.update({'taxonomy_id': taxonomy_id})

            # retrieve 'score' info
            score = self._retrieve_value(observation_metadata[index], [],
                                         'taxonomy_id')
            if score:
                taxonomy.update({'score': score})

            # retrieve 'taxonomy_source' info
            taxonomy_source = self._retrieve_value(observation_metadata[index], [],
                                                   'taxonomy_source')
            if taxonomy_source:
                taxonomy.update({'taxonomy_source': taxonomy_source})

            # retrieve 'species_name' info
            species_name = self._retrieve_value(observation_metadata[index], [],
                                                'species_name')
            if species_name:
                taxonomy.update({'species_name': species_name})

            amplicon.update({'consensus_sequence': str(fastq_dict.get(observation_id).seq)})

            amplicon.update({'taxonomy': taxonomy})

            amplicons.update({observation_id: amplicon})

        logging.info('finished processing files')
        return amplicons

    def _retrieve_biom_tsv_amplicon_set_data(self, biom_file, tsv_file):
        amplicons = dict()
        try:
            logging.info('start parsing TSV file')
            reader = pd.read_csv(tsv_file, sep=None, iterator=True)
            inferred_sep = reader._engine.data.dialect.delimiter
            df = pd.read_csv(tsv_file, sep=inferred_sep, index_col=0)
        except Exception:
            raise ValueError('Cannot parse file. Please provide valide tsv file')

        if 'consensus_sequence' not in df.columns.tolist():
            raise ValueError('TSV file does not include consensus_sequence')

        logging.info('start parsing BIOM file')
        table = biom.load_table(biom_file)

        observation_ids = table._observation_ids.tolist()
        observation_metadata = table._observation_metadata

        logging.info('start processing files')
        for index, observation_id in enumerate(observation_ids):
            if observation_id not in df.index:
                raise ValueError('TSV file does not have [{}] OTU id'.format(observation_id))
            amplicon = dict()
            taxonomy = dict()

            # retrieve 'lineage'/'taxonomy' info
            lineage = self._retrieve_value(observation_metadata[index],
                                           df.loc[observation_id],
                                           'taxonomy')
            if isinstance(lineage, str):
                delimiter = csv.Sniffer().sniff(lineage).delimiter
                lineage = [x.strip() for x in lineage.split(delimiter)]
            if lineage:
                taxonomy.update({'lineage': lineage})
                # retrieve 'taxonomy_ref' info
                taxonomy_ref, scientific_name = self._fetch_taxonomy_ref(lineage)
                if taxonomy_ref:
                    taxonomy.update({'taxonomy_ref': taxonomy_ref})
                    taxonomy.update({'scientific_name': scientific_name})

            # retrieve 'taxonomy_id' info
            taxonomy_id = self._retrieve_value(observation_metadata[index],
                                               df.loc[observation_id],
                                               'taxonomy_id')
            if taxonomy_id:
                taxonomy.update({'taxonomy_id': taxonomy_id})

            # retrieve 'score' info
            score = self._retrieve_value(observation_metadata[index],
                                         df.loc[observation_id],
                                         'taxonomy_id')
            if score:
                taxonomy.update({'score': score})

            # retrieve 'taxonomy_source' info
            taxonomy_source = self._retrieve_value(observation_metadata[index],
                                                   df.loc[observation_id],
                                                   'taxonomy_source')
            if taxonomy_source:
                taxonomy.update({'taxonomy_source': taxonomy_source})

            # retrieve 'species_name' info
            species_name = self._retrieve_value(observation_metadata[index],
                                                df.loc[observation_id],
                                                'species_name')
            if species_name:
                taxonomy.update({'species_name': species_name})

            amplicon.update({'consensus_sequence': df.loc[observation_id,
                                                          'consensus_sequence']})

            amplicon.update({'taxonomy': taxonomy})

            amplicons.update({observation_id: amplicon})

        logging.info('finished processing files')
        return amplicons

    def _file_to_amplicon_set_data(self, biom_file, tsv_file, fasta_file, mode, refs, description,
                                   matrix_obj_ref):

        logging.info('start parsing amplicon_set_data')

        amplicon_set_data = dict()

        if mode == 'biom_tsv':
            amplicons = self._retrieve_biom_tsv_amplicon_set_data(biom_file, tsv_file)
        elif mode == 'biom_fasta':
            amplicons = self._retrieve_biom_fasta_amplicon_set_data(biom_file, fasta_file)
        elif mode == 'tsv_fasta':
            amplicons = self._retrieve_tsv_fasta_amplicon_set_data(tsv_file, fasta_file)
        elif mode == 'tsv':
            amplicons = self._retrieve_tsv_amplicon_set_data(tsv_file)
        else:
            raise ValueError('error parsing _file_to_amplicon_set_data, mode: {}'.format(mode))

        amplicon_set_data.update({'amplicons': amplicons})

        if 'reads_set_ref' in refs:
            amplicon_set_data['reads_set_ref'] = refs.get('reads_set_ref')

        if description:
            amplicon_set_data['description'] = description

        matrix_obj_ref_array = matrix_obj_ref.split('/')
        amplicon_set_data['amplicon_matrix_ref'] = '{}/{}'.format(matrix_obj_ref_array[0],
                                                                  matrix_obj_ref_array[1])

        return amplicon_set_data

    def _file_to_amplicon_data(self, biom_file, tsv_file, mode, refs, matrix_name, workspace_id,
                               scale, description, metadata_keys=None):

        amplicon_data = refs

        if mode.startswith('biom'):
            logging.info('start parsing BIOM file for matrix data')
            table = biom.load_table(biom_file)
            observation_metadata = table._observation_metadata
            sample_metadata = table._sample_metadata

            matrix_data = {'row_ids': table._observation_ids.tolist(),
                           'col_ids': table._sample_ids.tolist(),
                           'values': table.matrix_data.toarray().tolist()}

            logging.info('start building attribute mapping object')
            amplicon_data.update(self.get_attribute_mapping("row", observation_metadata,
                                                            matrix_data, matrix_name, refs,
                                                            workspace_id))
            amplicon_data.update(self.get_attribute_mapping("col", sample_metadata,
                                                            matrix_data, matrix_name, refs,
                                                            workspace_id))

            amplicon_data['attributes'] = {}
            for k in ('create_date', 'generated_by'):
                val = getattr(table, k)
                if not val:
                    continue
                if isinstance(val, bytes):
                    amplicon_data['attributes'][k] = val.decode('utf-8')
                else:
                    amplicon_data['attributes'][k] = str(val)
        elif mode.startswith('tsv'):
            observation_metadata = None
            sample_metadata = None
            try:
                logging.info('start parsing TSV file for matrix data')
                reader = pd.read_csv(tsv_file, sep=None, iterator=True)
                inferred_sep = reader._engine.data.dialect.delimiter
                df = pd.read_csv(tsv_file, sep=inferred_sep, index_col=0)
            except Exception:
                raise ValueError('Cannot parse file. Please provide valide tsv file')
            else:
                metadata_df = None
                if metadata_keys:
                    shared_metadata_keys = list(set(metadata_keys) & set(df.columns))
                    if mode == 'tsv' and 'consensus_sequence' not in shared_metadata_keys:
                        raise ValueError('TSV file does not include consensus_sequence')
                    if shared_metadata_keys:
                        metadata_df = df[shared_metadata_keys]
                        df.drop(columns=shared_metadata_keys, inplace=True)
                try:
                    df = df.astype(float)
                except ValueError:
                    err_msg = 'Found some non-float values. Matrix contains only numeric values\n'
                    err_msg += 'Please list any non-numeric column names in  Metadata Keys field'
                    raise ValueError(err_msg)
                df.fillna(0, inplace=True)
                matrix_data = {'row_ids': df.index.tolist(),
                               'col_ids': df.columns.tolist(),
                               'values': df.values.tolist()}

            logging.info('start building attribute mapping object')
            amplicon_data.update(self.get_attribute_mapping("row", observation_metadata,
                                                            matrix_data, matrix_name, refs,
                                                            workspace_id, metadata_df))
            amplicon_data.update(self.get_attribute_mapping("col", sample_metadata,
                                                            matrix_data, matrix_name, refs,
                                                            workspace_id))

            amplicon_data['attributes'] = {}
        else:
            raise ValueError('error parsing _file_to_amplicon_data, mode: {}'.format(mode))

        amplicon_data.update({'data': matrix_data})

        amplicon_data['search_attributes'] = [f'{k}|{v}' for k, v in amplicon_data['attributes'].items()]

        amplicon_data['scale'] = scale
        if description:
            amplicon_data['description'] = description

        return amplicon_data

    def get_attribute_mapping(self, axis, metadata, matrix_data, matrix_name, refs,  workspace_id,
                              metadata_df=None):
        mapping_data = {}
        axis_ids = matrix_data[f'{axis}_ids']
        if refs.get(f'{axis}_attributemapping_ref'):
            am_data = self.dfu.get_objects(
                {'object_refs': [refs[f'{axis}_attributemapping_ref']]}
            )['data'][0]['data']
            unmatched_ids = set(axis_ids) - set(am_data['instances'].keys())
            if unmatched_ids:
                name = "Column" if axis == 'col' else "Row"
                raise ValueError(f"The following {name} IDs from the uploaded matrix do not match "
                                 f"the supplied {name} attribute mapping: {', '.join(unmatched_ids)}"
                                 f"\nPlease verify the input data or upload an excel file with a"
                                 f"{name} mapping tab.")
            else:
                mapping_data[f'{axis}_mapping'] = {x: x for x in axis_ids}

        elif metadata:
            name = matrix_name + "_{}_attributes".format(axis)
            mapping_data[f'{axis}_attributemapping_ref'] = self._metadata_to_attribute_mapping(
                axis_ids, metadata, name, workspace_id)
            # if coming from biom file, metadata and axis IDs are guaranteed to match
            mapping_data[f'{axis}_mapping'] = {x: x for x in axis_ids}
        elif metadata_df is not None:
            name = matrix_name + "_{}_attributes".format(axis)
            mapping_data[f'{axis}_attributemapping_ref'] = self._meta_df_to_attribute_mapping(
                axis_ids, metadata_df, name, workspace_id)
            mapping_data[f'{axis}_mapping'] = {x: x for x in axis_ids}

        return mapping_data

    def _meta_df_to_attribute_mapping(self, axis_ids, metadata_df, obj_name, ws_id):
        data = {'ontology_mapping_method': "TSV file", 'instances': {}}
        attribute_keys = metadata_df.columns.tolist()
        data['attributes'] = [{'attribute': key,
                               'attribute_ont_id': self.attr_util.DEFAULT_ONTOLOGY_ID,
                               'attribute_ont_ref': self.attr_util.DEFAULT_ONTOLOGY_REF,
                               } for key in attribute_keys]

        for axis_id in axis_ids:
            data['instances'][axis_id] = metadata_df.loc[axis_id].tolist()

        logging.info('start saving AttributeMapping object: {}'.format(obj_name))
        info = self.dfu.save_objects({
            "id": ws_id,
            "objects": [{
                "type": "KBaseExperiments.AttributeMapping",
                "data": data,
                "name": obj_name
            }]
        })[0]

        return f'{info[6]}/{info[0]}/{info[4]}'

    def _metadata_to_attribute_mapping(self, instances, metadata, obj_name, ws_id):
        data = {'ontology_mapping_method': "BIOM file", 'instances': {}}
        sample_set = metadata[0:min(len(metadata), 25)]
        metadata_keys = sorted(set((k for m_dict in sample_set for k in m_dict)))
        data['attributes'] = [{'attribute': key,
                               'attribute_ont_id': self.attr_util.DEFAULT_ONTOLOGY_ID,
                               'attribute_ont_ref': self.attr_util.DEFAULT_ONTOLOGY_REF,
                               } for key in metadata_keys]
        for inst, meta in zip(instances, metadata):
            data['instances'][inst] = [str(meta[attr]) for attr in metadata_keys]

        logging.info('start saving AttributeMapping object: {}'.format(obj_name))
        info = self.dfu.save_objects({
            "id": ws_id,
            "objects": [{
                "type": "KBaseExperiments.AttributeMapping",
                "data": data,
                "name": obj_name
            }]
        })[0]
        return f'{info[6]}/{info[0]}/{info[4]}'

    def _generate_report(self, matrix_obj_ref, amplicon_set_obj_ref, new_row_attr_ref,
                         new_col_attr_ref, workspace_name):
        """
        _generate_report: generate summary report
        """

        objects_created = [{'ref': matrix_obj_ref, 'description': 'Imported Amplicon Matrix'},
                           {'ref': amplicon_set_obj_ref, 'description': 'Imported Amplicon Set'}]

        if new_row_attr_ref:
            objects_created.append({'ref': new_row_attr_ref,
                                    'description': 'Imported Amplicons(Row) Attribute Mapping'})

        if new_col_attr_ref:
            objects_created.append({'ref': new_col_attr_ref,
                                    'description': 'Imported Samples(Column) Attribute Mapping'})

        report_params = {'message': '',
                         'objects_created': objects_created,
                         'workspace_name': workspace_name,
                         'report_object_name': 'import_matrix_from_biom_' + str(uuid.uuid4())}

        kbase_report_client = KBaseReport(self.callback_url, token=self.token)
        output = kbase_report_client.create_extended_report(report_params)

        report_output = {'report_name': output['name'], 'report_ref': output['ref']}

        return report_output

    def _df_to_tsv(self, amplicon_set_df, result_dir, amplicon_set_ref):
        logging.info('writting amplicon set data frame to tsv file')
        amplicon_set_obj = self.dfu.get_objects({'object_refs': [amplicon_set_ref]})['data'][0]
        amplicon_set_info = amplicon_set_obj['info']
        amplicon_set_name = amplicon_set_info[1]

        file_path = os.path.join(result_dir, amplicon_set_name + ".tsv")

        amplicon_set_df.to_csv(file_path, sep='\t', index=True, header=True)

        return file_path

    def _amplicon_set_to_df(self, amplicon_set_ref):
        logging.info('converting amplicon set to data frame')
        am_set_data = self.dfu.get_objects({'object_refs': [amplicon_set_ref]})['data'][0]['data']

        amplicon_matrix_ref = am_set_data.get('amplicon_matrix_ref')
        matrix_data = self.dfu.get_objects({'object_refs': [amplicon_matrix_ref]})['data'][0]['data']
        matrix_value_data = matrix_data.get('data')

        index = matrix_value_data.get('row_ids')
        columns = matrix_value_data.get('col_ids')
        values = matrix_value_data.get('values')

        df = pd.DataFrame(values, index=index, columns=columns)

        amplicons = am_set_data.get('amplicons')

        meta_index = list()
        meta_columns = ['taxonomy_id', 'taxonomy', 'score', 'taxonomy_source', 'species_name',
                        'consensus_sequence']
        meta_values = list()
        for otu_id, amplicon in amplicons.items():
            meta_index.append(otu_id)

            taxonomy_data = amplicon.get('taxonomy')
            taxonomy_id = taxonomy_data.get('taxonomy_id')
            taxonomy = taxonomy_data.get('lineage')
            score = taxonomy_data.get('score')
            taxonomy_source = taxonomy_data.get('taxonomy_source')
            species_name = taxonomy_data.get('species_name')

            consensus_sequence = amplicon.get('consensus_sequence')

            meta_values.append([taxonomy_id, taxonomy, score, taxonomy_source, species_name,
                                consensus_sequence])

        meta_df = pd.DataFrame(meta_values, index=meta_index, columns=meta_columns)

        merged_df = df.merge(meta_df, left_index=True, right_index=True, how='left',
                             validate='one_to_one')

        return merged_df

    def __init__(self, config):
        self.callback_url = config['SDK_CALLBACK_URL']
        self.scratch = config['scratch']
        self.token = config['KB_AUTH_TOKEN']
        self.dfu = DataFileUtil(self.callback_url)
        self.data_util = DataUtil(config)
        self.attr_util = AttributesUtil(config)
        self.matrix_util = MatrixUtil(config)
        self.matrix_types = [x.split(".")[1].split('-')[0]
                             for x in self.data_util.list_generic_types()]
        self.taxon_wsname = config['taxon-workspace-name']
        self.kbse = KBaseSearchEngine(config['search-url'])

    def import_matrix_from_biom(self, params):
        """
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

        (biom_file, tsv_file, fasta_file, mode, metadata_keys) = self._process_params(params)

        workspace_name = params.get('workspace_name')
        matrix_name = params.get('matrix_name')
        amplicon_set_name = params.get('amplicon_set_name')
        obj_type = params.get('obj_type')
        scale = params.get('scale')
        description = params.get('description')
        refs = {k: v for k, v in params.items() if "_ref" in k}

        if not isinstance(workspace_name, int):
            workspace_id = self.dfu.ws_name_to_id(workspace_name)
        else:
            workspace_id = workspace_name

        amplicon_data = self._file_to_amplicon_data(biom_file, tsv_file, mode, refs, matrix_name,
                                                    workspace_id, scale, description, metadata_keys)

        new_row_attr_ref = None
        if not params.get('row_attributemapping_ref'):
            new_row_attr_ref = amplicon_data.get('row_attributemapping_ref')

        new_col_attr_ref = None
        if not params.get('col_attributemapping_ref'):
            new_col_attr_ref = amplicon_data.get('col_attributemapping_ref')

        logging.info('start saving Matrix object: {}'.format(matrix_name))
        matrix_obj_ref = self.data_util.save_object({
                                                'obj_type': 'KBaseMatrices.{}'.format(obj_type),
                                                'obj_name': matrix_name,
                                                'data': amplicon_data,
                                                'workspace_name': workspace_id})['obj_ref']

        amplicon_set_data = self._file_to_amplicon_set_data(biom_file, tsv_file, fasta_file, mode,
                                                            refs, description, matrix_obj_ref)

        logging.info('start saving AmpliconSet object: {}'.format(amplicon_set_name))
        amplicon_set_obj_ref = self.data_util.save_object({
                                                'obj_type': 'KBaseExperiments.AmpliconSet',
                                                'obj_name': amplicon_set_name,
                                                'data': amplicon_set_data,
                                                'workspace_name': workspace_id})['obj_ref']

        logging.info('start resaving Matrix object with amplicon set: {}'.format(matrix_name))
        amplicon_data['amplicon_set_ref'] = '{}/{}'.format(workspace_id, amplicon_set_name)
        matrix_obj_ref = self.data_util.save_object({
                                                'obj_type': 'KBaseMatrices.{}'.format(obj_type),
                                                'obj_name': matrix_name,
                                                'data': amplicon_data,
                                                'workspace_name': workspace_id})['obj_ref']

        returnVal = {'matrix_obj_ref': matrix_obj_ref,
                     'amplicon_set_obj_ref': amplicon_set_obj_ref}

        report_output = self._generate_report(matrix_obj_ref, amplicon_set_obj_ref,
                                              new_row_attr_ref, new_col_attr_ref, workspace_name)

        returnVal.update(report_output)

        return returnVal

    def export_amplicon_set_tsv(self, params):
        """
        export AmpliconSet as TSV
        """
        logging.info('start exporting amplicon set object')
        amplicon_set_ref = params.get('input_ref')

        amplicon_set_df = self._amplicon_set_to_df(amplicon_set_ref)

        result_dir = os.path.join(self.scratch, str(uuid.uuid4()))
        self._mkdir_p(result_dir)

        self._df_to_tsv(amplicon_set_df, result_dir, amplicon_set_ref)

        package_details = self.dfu.package_for_download({
            'file_path': result_dir,
            'ws_refs': [amplicon_set_ref]
        })

        return {'shock_id': package_details['shock_id']}
